import re
import socket
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

DEFAULT_SERVER_HOST = "10.0.0.1"
DEFAULT_SERVER_PORT = 5000
MAX_MESSAGE_LEN = 500

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")


class ChatClient:
    def __init__(self):
        self.client = None
        self.username = ""
        self.running = True
        self.recv_thread = None
        self.buffer = ""
        
        self.login_window = tk.Tk()
        self.login_window.title("TCP Chat Login")
        self.login_window.geometry("430x470")
        self.login_window.resizable(False, False)

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
        self.server_entry.insert(0, DEFAULT_SERVER_HOST)
        self.server_entry.pack(fill="x", pady=5)

        ttk.Label(frame, text="Port").pack(anchor="w")
        self.port_entry = ttk.Entry(frame)
        self.port_entry.insert(0, str(DEFAULT_SERVER_PORT))
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

    # ----------------------------
    # Connect
    # ----------------------------
    def connect_server(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        host = self.server_entry.get().strip()
        port_text = self.port_entry.get().strip()

        ok, msg = self._validate_inputs(username, password)
        if not ok:
            messagebox.showerror("Invalid Input", msg)
            return

        try:
            port = int(port_text)
        except ValueError:
            messagebox.showerror("Invalid Port", "Port must be a number.")
            return

        try:
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect((host, port))

            first_reply = self._recv_line(self.client)
            if not first_reply.startswith("AUTH_REQUIRED"):
                raise RuntimeError(f"Unexpected server response: {first_reply}")

            self.client.sendall(f"{username}|{password}".encode("utf-8"))

            auth_reply = self._recv_line(self.client)
            if not auth_reply:
                raise RuntimeError("No response from server.")

            if auth_reply.startswith("AUTH_FAIL|"):
                messagebox.showerror("Login Failed", auth_reply.split("|", 1)[1])
                self.client.close()
                self.client = None
                return

            if auth_reply.startswith("AUTH_OK"):
                self.username = username
                self.running = True

                self.login_window.withdraw()

                self._build_chat_window()

                self.recv_thread = threading.Thread(
                    target=self._receive_loop,
                    daemon=True
                )
                self.recv_thread.start()

                return

            raise RuntimeError(f"Unexpected response: {auth_reply}")

        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            try:
                if self.client:
                    self.client.close()
            except Exception:
                pass
            self.client = None

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
        ttk.Button(bottom, text="Logout", command=self.disconnect).grid(row=1, column=3, padx=5)

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

    # ----------------------------
    # Background receive
    # ----------------------------
    def _receive_loop(self):
        try:
            while self.running:
                try:
                    data = self.client.recv(4096)
                    if not data:
                        break

                    self.buffer += data.decode("utf-8", errors="ignore")

                    while "\n" in self.buffer:
                        line, self.buffer = self.buffer.split("\n", 1)
                        line = line.strip()
                        print("RECEIVED:", repr(line))
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
                                return
                            continue

                        self.window.after(0, self._append_chat, line)

                except Exception:
                    break
        finally:
            try:
                if self.running and self.window.winfo_exists():
                    self.window.after(0, self._set_status, "● Disconnected", "red")
            except RuntimeError:
                pass
            except tk.TclError:
                pass

            self.running = False

            try:
                self.client.close()
            except Exception:
                pass

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

        if len(message) > MAX_MESSAGE_LEN:
            messagebox.showerror("Message Too Long", f"Maximum allowed length is {MAX_MESSAGE_LEN} characters.")
            return

        if private_user:
            payload = f"/msg {private_user} {message}"
        else:
            payload = message

        try:
            self.client.sendall(payload.encode("utf-8"))
            self.message_entry.delete(0, tk.END)
        except Exception as e:
            messagebox.showerror("Send Error", str(e))

    # ----------------------------
    # Disconnect / Logout
    # ----------------------------
    def disconnect(self):
        if self.client and self.running:
            try:
                self.client.sendall("/logout".encode("utf-8"))
            except Exception:
                pass

        self.running = False

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

        if hasattr(self, "window") and self.window.winfo_exists():
            self.window.destroy()


if __name__ == "__main__":
    ChatClient()
