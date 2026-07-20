import json
import re
import socket
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

DEFAULT_CONFIG = {
    "default_server_host": "10.0.0.1",
    "server_port": 5000,
    "max_message_len": 500,
    "auto_reconnect": True,
    "reconnect_attempts": 5,
    "reconnect_delay": 2,
    "connect_timeout": 10,
    "recv_timeout": 10,
}

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    cfg_path = Path("config.json")
    if cfg_path.exists():
        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                cfg.update(loaded)
        except Exception:
            pass
    return cfg


class ChatClient:
    def __init__(self):
        self.config = load_config()
        self.client = None
        self.username = ""
        self.password = ""
        self.host = self.config["default_server_host"]
        self.port = int(self.config["server_port"])
        self.running = False
        self.manual_logout = False
        self.reconnecting = False
        self.recv_thread = None
        self.buffer = ""
        self.connect_lock = threading.Lock()

        self.login_window = tk.Tk()
        self.login_window.title("TCP Chat Login")
        self.login_window.geometry("430x470")
        self.login_window.resizable(False, False)
        self.login_window.protocol("WM_DELETE_WINDOW", self.close_app)

        self._build_login()
        self.login_window.mainloop()

    # ----------------------------
    # Login UI
    # ----------------------------
    def _build_login(self):
        frame = ttk.Frame(self.login_window, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Secure TCP Chat", font=("Arial", 16, "bold")).pack(pady=(0, 10))

        ttk.Label(frame, text="Username").pack(anchor="w")
        self.username_entry = ttk.Entry(frame)
        self.username_entry.pack(fill="x", pady=5)

        ttk.Label(frame, text="Password").pack(anchor="w")
        self.password_entry = ttk.Entry(frame, show="*")
        self.password_entry.pack(fill="x", pady=5)

        ttk.Label(frame, text="Server IP").pack(anchor="w")
        self.server_entry = ttk.Entry(frame)
        self.server_entry.insert(0, self.host)
        self.server_entry.pack(fill="x", pady=5)

        ttk.Label(frame, text="Port").pack(anchor="w")
        self.port_entry = ttk.Entry(frame)
        self.port_entry.insert(0, str(self.port))
        self.port_entry.pack(fill="x", pady=5)

        self.login_status = ttk.Label(frame, text="")
        self.login_status.pack(pady=(8, 0))

        ttk.Button(frame, text="Connect", command=self.connect_server).pack(pady=20)
        self.login_window.bind("<Return>", lambda event: self.connect_server())

    def _validate_inputs(self, username: str, password: str) -> tuple[bool, str]:
        if not username:
            return False, "Username cannot be empty."
        if not USERNAME_PATTERN.fullmatch(username):
            return False, "Username must be 3-20 characters and contain only letters, numbers, or underscore."
        if not password:
            return False, "Password cannot be empty."
        if len(password) < 6:
            return False, "Password must be at least 6 characters."
        return True, ""

    def _recv_line(self, sock: socket.socket, timeout: float = 10.0) -> str:
        sock.settimeout(timeout)
        data = ""
        while "\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                break
            data += chunk.decode("utf-8", errors="ignore")
        sock.settimeout(None)
        return data.split("\n", 1)[0].strip()

    def _connect_and_authenticate(self, quiet: bool = False) -> tuple[bool, str]:
        try:
            port = int(self.port_entry.get().strip())
        except ValueError:
            return False, "Port must be a number."

        host = self.server_entry.get().strip()
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        ok, msg = self._validate_inputs(username, password)
        if not ok:
            return False, msg

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(int(self.config["connect_timeout"]))
            sock.connect((host, port))

            first_reply = self._recv_line(sock, timeout=int(self.config["connect_timeout"]))
            if not first_reply.startswith("AUTH_REQUIRED"):
                raise RuntimeError(f"Unexpected server response: {first_reply}")

            sock.sendall(f"{username}|{password}".encode("utf-8"))
            auth_reply = self._recv_line(sock, timeout=int(self.config["connect_timeout"]))
            if not auth_reply:
                raise RuntimeError("No response from server.")

            if auth_reply.startswith("AUTH_FAIL|"):
                sock.close()
                return False, auth_reply.split("|", 1)[1]

            if not auth_reply.startswith("AUTH_OK"):
                sock.close()
                raise RuntimeError(f"Unexpected response: {auth_reply}")

            with self.connect_lock:
                if self.client:
                    try:
                        self.client.close()
                    except Exception:
                        pass
                self.client = sock
                self.username = username
                self.password = password
                self.host = host
                self.port = port
                self.buffer = ""
                self.running = True
                self.manual_logout = False

            return True, "Login successful"

        except Exception as e:
            try:
                sock.close()
            except Exception:
                pass
            if quiet:
                return False, str(e)
            return False, str(e)

    def connect_server(self):
        ok, msg = self._connect_and_authenticate()
        if not ok:
            messagebox.showerror("Connection Error", msg)
            return

        self.login_window.withdraw()
        self._build_chat_window()
        self._start_receive_thread()
        self._request_user_list()
        self._append_chat("[SERVER] Connected successfully.")

    # ----------------------------
    # Chat UI
    # ----------------------------
    def _build_chat_window(self):
        self.window = tk.Toplevel(self.login_window)
        self.window.title(f"TCP Chat - {self.username}")
        self.window.geometry("920x620")
        self.window.protocol("WM_DELETE_WINDOW", self.disconnect)

        top_frame = ttk.Frame(self.window)
        top_frame.pack(fill="x", padx=10, pady=8)

        ttk.Label(top_frame, text=f"Logged in as: {self.username}", font=("Arial", 11, "bold")).pack(side="left")
        self.status_label = ttk.Label(top_frame, text="● Connected", foreground="green")
        self.status_label.pack(side="right")

        main = ttk.Frame(self.window)
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.chat_box = scrolledtext.ScrolledText(main, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 10))
        self.chat_box.pack(side="left", fill="both", expand=True, padx=(0, 10))

        user_frame = ttk.LabelFrame(main, text="Online Users", width=210)
        user_frame.pack(side="right", fill="y")

        self.user_list = tk.Listbox(user_frame, width=25, height=28)
        self.user_list.pack(fill="both", expand=True, padx=5, pady=5)

        bottom = ttk.Frame(self.window)
        bottom.pack(fill="x", padx=10, pady=10)

        ttk.Label(bottom, text="Private To").grid(row=0, column=0, sticky="w")
        self.private_entry = ttk.Entry(bottom, width=20)
        self.private_entry.grid(row=0, column=1, padx=5, sticky="w")

        ttk.Label(bottom, text="Message").grid(row=1, column=0, sticky="w", pady=10)
        self.message_entry = ttk.Entry(bottom, width=75)
        self.message_entry.grid(row=1, column=1, padx=5, sticky="ew")
        self.message_entry.bind("<Return>", lambda event: self.send_message())

        ttk.Button(bottom, text="Send", command=self.send_message).grid(row=1, column=2, padx=5)
        ttk.Button(bottom, text="Reconnect", command=self.manual_reconnect).grid(row=1, column=3, padx=5)
        ttk.Button(bottom, text="Logout", command=self.disconnect).grid(row=1, column=4, padx=5)

        bottom.columnconfigure(1, weight=1)

    # ----------------------------
    # UI helpers
    # ----------------------------
    def _append_chat(self, text: str):
        if not hasattr(self, "chat_box"):
            return
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, text + "\n")
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.see(tk.END)

    def _set_status(self, text: str, color: str = "green"):
        if hasattr(self, "status_label"):
            self.status_label.config(text=text, foreground=color)

    def _update_user_list(self, users_text: str):
        if not hasattr(self, "user_list"):
            return
        self.user_list.delete(0, tk.END)
        users = [u.strip() for u in users_text.split(",") if u.strip()]
        for user in users:
            self.user_list.insert(tk.END, user)

    def _request_user_list(self):
        if self.client and self.running:
            try:
                self.client.sendall("/list".encode("utf-8"))
            except Exception:
                self._handle_disconnect("Failed to request user list.")

    # ----------------------------
    # Receive loop
    # ----------------------------
    def _start_receive_thread(self):
        self.recv_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.recv_thread.start()

    def _receive_loop(self):
        try:
            while self.running and self.client:
                try:
                    data = self.client.recv(4096)
                    if not data:
                        raise ConnectionError("Connection closed by server.")

                    self.buffer += data.decode("utf-8", errors="ignore")

                    while "\n" in self.buffer:
                        line, self.buffer = self.buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue

                        if line.startswith("USERLIST|"):
                            users_text = line.split("|", 1)[1]
                            self.window.after(0, self._update_user_list, users_text)
                            continue

                        if line == "HISTORY_START" or line == "HISTORY_END":
                            continue

                        if line.startswith("SERVER|"):
                            msg = line.split("|", 1)[1]
                            self.window.after(0, self._append_chat, f"[SERVER] {msg}")
                            if "timed out" in msg.lower() or "logged out" in msg.lower():
                                self.window.after(0, self._set_status, "● Disconnected", "red")
                                self.running = False
                                self.manual_logout = True
                                return
                            continue

                        self.window.after(0, self._append_chat, line)

                except socket.timeout:
                    continue

                except Exception as e:
                    self._handle_disconnect(str(e))
                    return

        finally:
            if self.running and not self.manual_logout:
                self._handle_disconnect("Disconnected from server.")

    def _handle_disconnect(self, reason: str):
        with self.connect_lock:
            if self.client:
                try:
                    self.client.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None

        self.running = False
        self.window.after(0, self._set_status, f"● Disconnected", "red")
        self.window.after(0, self._append_chat, f"[SERVER] {reason}")

        if self.config.get("auto_reconnect", True) and not self.manual_logout and not self.reconnecting:
            self._schedule_reconnect()

    def _schedule_reconnect(self):
        self.reconnecting = True
        thread = threading.Thread(target=self._reconnect_worker, daemon=True)
        thread.start()

    def _reconnect_worker(self):
        attempts = int(self.config.get("reconnect_attempts", 5))
        delay = int(self.config.get("reconnect_delay", 2))

        for attempt in range(1, attempts + 1):
            if self.manual_logout:
                break

            self.window.after(0, self._set_status, f"● Reconnecting... ({attempt}/{attempts})", "orange")
            time.sleep(delay * attempt)

            ok, msg = self._connect_and_authenticate(quiet=True)
            if ok:
                self.running = True
                self.window.after(0, self._set_status, "● Connected", "green")
                self.window.after(0, self._append_chat, "[SERVER] Reconnected successfully.")
                self.window.after(0, self._request_user_list)
                self._start_receive_thread()
                self.reconnecting = False
                return

        self.reconnecting = False
        self.window.after(0, self._set_status, "● Disconnected", "red")
        self.window.after(0, self._append_chat, "[SERVER] Auto-reconnect failed.")

    def manual_reconnect(self):
        if self.reconnecting:
            return
        if self.running:
            messagebox.showinfo("Reconnect", "You are already connected.")
            return
        if not self.username or not self.password:
            messagebox.showerror("Reconnect", "No saved login available. Please connect again.")
            return
        self._schedule_reconnect()

    # ----------------------------
    # Send message
    # ----------------------------
    def send_message(self):
        if not self.client or not self.running:
            return

        message = self.message_entry.get().strip()
        private_user = self.private_entry.get().strip()

        if not message:
            return

        if len(message) > int(self.config["max_message_len"]):
            messagebox.showerror("Message Too Long", f"Maximum allowed length is {self.config['max_message_len']} characters.")
            return

        if private_user:
            payload = f"/msg {private_user} {message}"
        else:
            payload = message

        try:
            self.client.sendall(payload.encode("utf-8"))
            self.message_entry.delete(0, tk.END)
        except Exception as e:
            self._handle_disconnect(str(e))

    # ----------------------------
    # Disconnect / Logout
    # ----------------------------
    def disconnect(self):
        self.manual_logout = True
        self.running = False

        try:
            if self.client:
                self.client.sendall("/logout".encode("utf-8"))
        except Exception:
            pass

        with self.connect_lock:
            try:
                if self.client:
                    self.client.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None

        if hasattr(self, "window") and self.window.winfo_exists():
            self.window.destroy()

        if hasattr(self, "login_window") and self.login_window.winfo_exists():
            self.login_window.deiconify()
            self.login_status.config(text="Logged out.")

    def close_app(self):
        self.manual_logout = True
        self.running = False

        try:
            if self.client:
                self.client.sendall("/logout".encode("utf-8"))
        except Exception:
            pass

        with self.connect_lock:
            try:
                if self.client:
                    self.client.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None

        try:
            if hasattr(self, "window") and self.window.winfo_exists():
                self.window.destroy()
        except Exception:
            pass

        try:
            if hasattr(self, "login_window") and self.login_window.winfo_exists():
                self.login_window.destroy()
        except Exception:
            pass


if __name__ == "__main__":
    ChatClient()
