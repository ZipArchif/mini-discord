import socketio
import sys

SERVER_URL = 'https://mini-discord.onrender.com'  # ← поменяй

sio = socketio.Client()


@sio.on('message')
def on_message(data):
    if data['user'] == 'СИСТЕМА':
        print(f"\n— {data['text']}")
    else:
        print(f"\n{data['user']}: {data['text']}")


@sio.on('users')
def on_users(users):
    print(f"\n[Онлайн: {', '.join(users)}]")


@sio.on('error_msg')
def on_error(msg):
    print(f"\n⚠ {msg}")


if __name__ == '__main__':
    username = input("Ник: ").strip()
    print(f"Подключение к {SERVER_URL}...")
    sio.connect(SERVER_URL)
    sio.emit('join', username)
    print("Введите сообщение (Ctrl+C для выхода):\n")
    try:
        while True:
            msg = input()
            if msg.strip():
                sio.emit('message', msg)
    except (KeyboardInterrupt, EOFError):
        sio.disconnect()
        print("\nОтключено")