import os
import sys
import subprocess
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import requests

os.environ['PYTHONUNBUFFERED'] = '1'

app = Flask(__name__)
app.secret_key = "fast_secure_key"

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

user_sessions = {}
cache = {}

# -------- CACHE --------
def get_cache(key):
    d = cache.get(key)
    if not d: return None
    if time.time() - d['time'] > 30: return None
    return d['value']

def set_cache(key, val):
    cache[key] = {'value': val, 'time': time.time()}

# -------- ROUTES --------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/control', methods=['POST'])
def control():
    data = request.json
    name = data.get('name')
    action = data.get('action')

    if action == 'start':
        if name in user_sessions and user_sessions[name]['running']:
            return jsonify({"status":"error","msg":"Already running"})

        proc = subprocess.Popen(
            [sys.executable,'-u','main.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        user_sessions[name] = {
            'proc': proc,
            'running': True,
            'end': datetime.now()+timedelta(minutes=60)
        }

        threading.Thread(target=logs,args=(proc,name),daemon=True).start()
        return jsonify({"status":"success"})

    if action == 'stop':
        if name in user_sessions:
            user_sessions[name]['proc'].terminate()
            user_sessions[name]['running'] = False
        return jsonify({"status":"stopped"})

    return jsonify({"status":"error"})

@app.route('/api/guild')
def guild():
    gid = request.args.get('gid')
    reg = request.args.get('reg')

    key = f"{gid}_{reg}"
    c = get_cache(key)
    if c: return jsonify(c)

    try:
        url = f"https://guild-info-danger.vercel.app/guild?guild_id={gid}&region={reg}"
        r = requests.get(url, timeout=5).json()
        set_cache(key, r)
        return jsonify(r)
    except:
        return jsonify({"error":"slow api"})

# -------- LOG --------
def logs(proc,name):
    for line in iter(proc.stdout.readline,''):
        socketio.emit('log',{'data':line,'user':name})

# -------- AUTO STOP --------
def cleaner():
    while True:
        now = datetime.now()
        for n,d in list(user_sessions.items()):
            if d['running'] and now>d['end']:
                d['proc'].terminate()
                d['running']=False
        time.sleep(5)

threading.Thread(target=cleaner,daemon=True).start()

# -------- RUN --------
if __name__=='__main__':
    port=int(os.environ.get("PORT",10000))
    socketio.run(app,host='0.0.0.0',port=port)
