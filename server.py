import os
import eventlet
eventlet.monkey_patch()

from flask import Flask, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    logger=False,
    engineio_logger=False,
)

# sid -> username
clients = {}


def broadcast_users():
    """Рассылает всем актуальный список онлайн-пользователей."""
    emit('users', list(clients.values()), broadcast=True)


@socketio.on('connect')
def on_connect():
    print(f'[+] Подключение: {request.sid}')


@socketio.on('join')
def on_join(username):
    username = (username or '').strip()[:32]
    if not username:
        emit('error_msg', 'Ник не может быть пустым')
        return
    # проверка на дубликат
    if username in clients.values():
        emit('error_msg', 'Такой ник уже занят')
        return

    clients[request.sid] = username
    print(f'[JOIN] {username} ({request.sid})')

    emit('message',
         {'user': 'СИСТЕМА', 'text': f'{username} присоединился к чату'},
         broadcast=True)
    broadcast_users()


@socketio.on('message')
def on_message(data):
    user = clients.get(request.sid)
    if not user:
        emit('error_msg', 'Сначала войдите в чат')
        return

    text = (data or '').strip()
    if not text:
        return
    if len(text) > 2000:
        text = text[:2000]

    print(f'[MSG] {user}: {text}')
    emit('message', {'user': user, 'text': text}, broadcast=True)


@socketio.on('typing')
def on_typing():
    user = clients.get(request.sid)
    if user:
        emit('typing', {'user': user}, broadcast=True, include_self=False)


@socketio.on('disconnect')
def on_disconnect():
    user = clients.pop(request.sid, None)
    if user:
        print(f'[-] {user} отключился')
        emit('message',
             {'user': 'СИСТЕМА', 'text': f'{user} покинул чат'},
             broadcast=True)
        broadcast_users()


@app.route('/')
def health():
    """Эндпоинт для пинга (UptimeRobot)."""
    return {
        'status': 'ok',
        'online': len(clients),
        'users': list(clients.values()),
    }


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port)