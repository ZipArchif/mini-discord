import os
import hashlib
import eventlet
eventlet.monkey_patch()
from livekit import api as lk_api

from flask import Flask, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')
app.config['JSON_AS_ASCII'] = False
LIVEKIT_URL = os.environ.get('LIVEKIT_URL', '')
LIVEKIT_API_KEY = os.environ.get('LIVEKIT_API_KEY', '')
LIVEKIT_API_SECRET = os.environ.get('LIVEKIT_API_SECRET', '')

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=False,
    engineio_logger=False,
)

# ============ ХРАНИЛИЩЕ В ПАМЯТИ ============
# users: {username: password_hash}
users = {}
# sessions: {sid: username}
sessions = {}
# dm_history: {(user_a, user_b): [{"from": ..., "text": ..., "ts": ...}, ...]}
dm_history = {}
# ============================================


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()


def dm_key(a: str, b: str) -> tuple:
    return tuple(sorted([a, b]))


def online_users() -> list:
    return sorted(set(sessions.values()))


def broadcast_user_list():
    """Рассылает всем список зарегистрированных + флаг онлайн."""
    payload = [
        {"username": u, "online": u in sessions.values()}
        for u in sorted(users.keys())
    ]
    emit('user_list', payload, broadcast=True)


# ==================== HTTP ====================
@app.route('/')
def health():
    return {
        'status': 'ok',
        'registered': len(users),
        'online': len(sessions),
        'users': online_users(),
        'livekit_configured': bool(LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET),
    }

@app.route('/token')
def get_token():
    """Выдаёт JWT для подключения к LiveKit-комнате."""
    username = request.args.get('username', 'guest')
    room = request.args.get('room', 'test_room')

    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        return {'error': 'LiveKit не настроен на сервере'}, 500

    try:
        token = (
            lk_api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(username)
            .with_name(username)
            .with_grants(lk_api.VideoGrants(
                room_join=True,
                room=room,
            ))
            .to_jwt()
        )
        return {'token': token, 'url': LIVEKIT_URL}
    except Exception as e:
        return {'error': str(e)}, 500
# ==================== SOCKETIO ====================
@socketio.on('connect')
def on_connect():
    print(f'[+] Socket: {request.sid}')


@socketio.on('register')
def on_register(data):
    """Регистрация или вход. data = {username, password}"""
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    if not username or len(username) < 2:
        emit('auth_error', 'Ник должен быть минимум 2 символа')
        return
    if len(username) > 32:
        emit('auth_error', 'Ник слишком длинный (макс 32)')
        return
    if len(password) < 3:
        emit('auth_error', 'Пароль минимум 3 символа')
        return

    pwd_hash = hash_password(password)

    if username in users:
        # вход существующего
        if users[username] != pwd_hash:
            emit('auth_error', 'Неверный пароль')
            return
        if username in sessions.values():
            emit('auth_error', 'Этот ник уже в сети')
            return
    else:
        # регистрация нового
        users[username] = pwd_hash

    sessions[request.sid] = username
    print(f'[AUTH] {username}')

    emit('auth_ok', {'username': username})
    broadcast_user_list()


@socketio.on('disconnect')
def on_disconnect():
    username = sessions.pop(request.sid, None)
    if username:
        print(f'[-] {username} отключился')
        broadcast_user_list()


@socketio.on('get_history')
def on_get_history(data):
    """data = {with_user} — вернуть историю ЛС с этим юзером."""
    me = sessions.get(request.sid)
    other = data.get('with_user')
    if not me or not other:
        return
    history = dm_history.get(dm_key(me, other), [])
    emit('dm_history', {'with_user': other, 'messages': history})


@socketio.on('dm')
def on_dm(data):
    """Личное сообщение. data = {to, text}"""
    me = sessions.get(request.sid)
    if not me:
        emit('auth_error', 'Сессия истекла, войдите заново')
        return

    to_user = (data.get('to') or '').strip()
    text = (data.get('text') or '').strip()

    if not to_user or to_user not in users:
        emit('dm_error', 'Получатель не найден')
        return
    if not text:
        return
    if len(text) > 2000:
        text = text[:2000]

    msg = {'from': me, 'to': to_user, 'text': text}

    # сохраняем в историю
    key = dm_key(me, to_user)
    dm_history.setdefault(key, []).append(msg)

    # отправляем получателю, если онлайн
    for sid, name in list(sessions.items()):
        if name == to_user:
            emit('dm', msg, to=sid)
    # отправителю — эхо, чтобы показал у себя
    emit('dm', msg, to=request.sid)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)
