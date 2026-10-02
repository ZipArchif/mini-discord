import socketio
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
import threading
import time

# === НАСТРОЙКА ===
SERVER_URL = 'https://mini-discord.onrender.com'  # ← поменяй на свой URL
# Для локального теста: 'http://127.0.0.1:5000'
# =================


class ChatClient:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("MiniDiscord")
        self.root.geometry("800x560")
        self.root.configure(bg="#2b2d31")
        self.root.minsize(600, 400)

        self.username = None
        self.connected = False
        self.sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,       # бесконечно
            reconnection_delay=1,
            reconnection_delay_max=30,
        )
        self._register_handlers()

        self.build_login()

    # ---------- ОКНО ВХОДА ----------
    def build_login(self):
        self.login_frame = tk.Frame(self.root, bg="#2b2d31")
        self.login_frame.pack(expand=True)

        tk.Label(self.login_frame, text="MiniDiscord",
                 bg="#2b2d31", fg="#5865f2",
                 font=("Arial", 26, "bold")).pack(pady=(0, 20))

        tk.Label(self.login_frame, text="Твой ник:",
                 bg="#2b2d31", fg="#dbdee1",
                 font=("Arial", 12)).pack(anchor="w")

        self.nick_entry = tk.Entry(self.login_frame, bg="#1e1f22", fg="#dbdee1",
                                   insertbackground="#dbdee1", bd=0,
                                   font=("Arial", 14), width=30)
        self.nick_entry.pack(ipady=8, pady=(5, 15))
        self.nick_entry.bind("<Return>", lambda e: self.do_login())

        self.status_label = tk.Label(self.login_frame, text="",
                                     bg="#2b2d31", fg="#ed4245",
                                     font=("Arial", 10))
        self.status_label.pack()

        self.login_btn = tk.Button(self.login_frame, text="Войти",
                                   bg="#5865f2", fg="white", bd=0,
                                   font=("Arial", 12, "bold"),
                                   width=20, command=self.do_login)
        self.login_btn.pack(pady=15, ipady=6)

        self.nick_entry.focus()

    def do_login(self):
        username = self.nick_entry.get().strip()
        if not username:
            self.status_label.config(text="Введи ник")
            return
        if len(username) > 32:
            self.status_label.config(text="Ник слишком длинный (макс 32)")
            return

        self.username = username
        self.status_label.config(text="Подключение...", fg="#faa61a")
        self.login_btn.config(state=tk.DISABLED)

        threading.Thread(target=self._connect_thread, daemon=True).start()

    def _connect_thread(self):
        try:
            self.sio.connect(SERVER_URL, transports=['websocket'],
                             wait_timeout=20)
            self.sio.emit('join', self.username)
            self.connected = True
            self.root.after(0, self.build_chat)
        except Exception as e:
            self.root.after(0, lambda: self.status_label.config(
                text=f"Ошибка: {e}", fg="#ed4245"))
            self.root.after(0, lambda: self.login_btn.config(state=tk.NORMAL))

    # ---------- ОКНО ЧАТА ----------
    def build_chat(self):
        self.login_frame.destroy()

        # Левая панель — пользователи
        left = tk.Frame(self.root, bg="#1e1f22", width=200)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        tk.Label(left, text="ОНЛАЙН", bg="#1e1f22", fg="#949ba4",
                 font=("Arial", 10, "bold")).pack(pady=12)

        self.users_list = tk.Listbox(left, bg="#1e1f22", fg="#dbdee1",
                                     bd=0, highlightthickness=0,
                                     font=("Arial", 11), selectbackground="#5865f2")
        self.users_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.conn_label = tk.Label(left, text="● онлайн",
                                   bg="#1e1f22", fg="#23a55a",
                                   font=("Arial", 9))
        self.conn_label.pack(pady=5)

        # Правая — чат
        right = tk.Frame(self.root, bg="#313338")
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        header = tk.Frame(right, bg="#313338", height=40)
        header.pack(fill=tk.X, padx=15, pady=(10, 0))
        tk.Label(header, text="# общий", bg="#313338", fg="#f2f3f5",
                 font=("Arial", 13, "bold")).pack(side=tk.LEFT)

        self.chat = scrolledtext.ScrolledText(right, bg="#313338", fg="#dbdee1",
                                              bd=0, font=("Consolas", 11),
                                              state=tk.DISABLED, wrap=tk.WORD)
        self.chat.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)
        self.chat.tag_config("system", foreground="#949ba4", font=("Arial", 10, "italic"))
        self.chat.tag_config("user", foreground="#5865f2", font=("Arial", 11, "bold"))
        self.chat.tag_config("text", foreground="#dbdee1", font=("Arial", 11))
        self.chat.tag_config("error", foreground="#ed4245")
        self.chat.tag_config("typing", foreground="#949ba4", font=("Arial", 9, "italic"))

        bottom = tk.Frame(right, bg="#313338")
        bottom.pack(fill=tk.X, padx=15, pady=(0, 15))

        self.entry = tk.Entry(bottom, bg="#383a40", fg="#dbdee1",
                              insertbackground="#dbdee1", bd=0,
                              font=("Arial", 12))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=10, padx=(0, 8))
        self.entry.bind("<Return>", self.send_message)
        self.entry.bind("<KeyRelease>", self.on_typing)

        tk.Button(bottom, text="→", bg="#5865f2", fg="white",
                  bd=0, font=("Arial", 14, "bold"), width=4,
                  activebackground="#4752c4",
                  command=self.send_message).pack(side=tk.RIGHT)
        self.entry.focus()

        # приветствие
        self.append_system(f"Добро пожаловать, {self.username}!")

    # ---------- ЛОГИКА ----------
    def send_message(self, event=None):
        text = self.entry.get().strip()
        if not text or not self.connected:
            return
        self.sio.emit('message', text)
        self.append_user(self.username, text)
        self.entry.delete(0, tk.END)

    def on_typing(self, event=None):
        if self.connected and event.keysym not in ('Return', 'Shift_L', 'Shift_R'):
            self.sio.emit('typing')

    # ---------- ОТРИСОВКА ----------
    def append_system(self, text):
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, f"— {text}\n", "system")
        self.chat.see(tk.END)
        self.chat.config(state=tk.DISABLED)

    def append_user(self, user, text):
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, f"{user}: ", "user")
        self.chat.insert(tk.END, f"{text}\n", "text")
        self.chat.see(tk.END)
        self.chat.config(state=tk.DISABLED)

    def append_error(self, text):
        self.chat.config(state=tk.NORMAL)
        self.chat.insert(tk.END, f"⚠ {text}\n", "error")
        self.chat.see(tk.END)
        self.chat.config(state=tk.DISABLED)

    def show_typing(self, user):
        # очень простая индикация — просто пишем в статус
        self.conn_label.config(text=f"{user} печатает...", fg="#faa61a")
        self.root.after(1500, self._reset_typing)

    def _reset_typing(self):
        if self.connected:
            self.conn_label.config(text="● онлайн", fg="#23a55a")

    def update_users(self, users):
        self.users_list.delete(0, tk.END)
        for u in sorted(users):
            prefix = "  ● " if u == self.username else "  ○ "
            self.users_list.insert(tk.END, f"{prefix}{u}")

    # ---------- СОБЫТИЯ SOCKETIO ----------
    def _register_handlers(self):
        @self.sio.on('message')
        def on_message(data):
            user = data.get('user')
            text = data.get('text', '')
            if user == 'СИСТЕМА':
                self.root.after(0, self.append_system, text)
            elif user != self.username:  # свои уже показали локально
                self.root.after(0, self.append_user, user, text)

        @self.sio.on('users')
        def on_users(users):
            self.root.after(0, self.update_users, users)

        @self.sio.on('error_msg')
        def on_error(msg):
            self.root.after(0, self.append_error, msg)

        @self.sio.on('typing')
        def on_typing(data):
            user = data.get('user')
            if user and user != self.username:
                self.root.after(0, self.show_typing, user)

        @self.sio.on('disconnect')
        def on_disconnect():
            self.connected = False
            self.root.after(0, lambda: self.conn_label.config(
                text="● переподключение...", fg="#ed4245"))
            self.root.after(0, self.append_system, "Соединение потеряно")

        @self.sio.on('connect')
        def on_connect():
            if self.username and not self.connected:
                # реконнект после разрыва
                self.sio.emit('join', self.username)
                self.connected = True
                self.root.after(0, lambda: self.conn_label.config(
                    text="● онлайн", fg="#23a55a"))
                self.root.after(0, self.append_system, "Переподключено")

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    ChatClient().run()