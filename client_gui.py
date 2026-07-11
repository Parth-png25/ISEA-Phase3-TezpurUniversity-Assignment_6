import socket
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import scrolledtext

SERVER_HOST = "10.0.0.1"
SERVER_PORT = 5000


class ChatClient:

    def __init__(self):

        self.client = None
        self.username = ""

        self.login_window = tk.Tk()
        self.login_window.title("TCP Chat Login")
        self.login_window.geometry("400x450")
        self.login_window.resizable(False, False)

        self.build_login()

        self.login_window.mainloop()

    # ------------------------
    # Login Window
    # ------------------------

    def build_login(self):

        frame = ttk.Frame(self.login_window, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="TCP Chat Application",
            font=("Arial", 16, "bold")
        ).pack(pady=10)

        ttk.Label(frame, text="Username").pack(anchor="w")

        self.username_entry = ttk.Entry(frame)
        self.username_entry.pack(fill="x", pady=5)

        ttk.Label(frame, text="Password (Optional)").pack(anchor="w")

        self.password_entry = ttk.Entry(
            frame,
            show="*"
        )

        self.password_entry.pack(fill="x", pady=5)

        ttk.Label(frame, text="Server").pack(anchor="w")

        self.server_entry = ttk.Entry(frame)

        self.server_entry.insert(0, SERVER_HOST)

        self.server_entry.pack(fill="x", pady=5)

        ttk.Label(frame, text="Port").pack(anchor="w")

        self.port_entry = ttk.Entry(frame)

        self.port_entry.insert(0, str(SERVER_PORT))

        self.port_entry.pack(fill="x", pady=5)

        ttk.Button(
            frame,
            text="Connect",
            command=self.connect_server
        ).pack(pady=20)

    # ------------------------
    # Connect
    # ------------------------

    def connect_server(self):

        username = self.username_entry.get().strip()

        if username == "":

            messagebox.showerror(
                "Error",
                "Username cannot be empty."
            )

            return

        host = self.server_entry.get().strip()

        port = int(self.port_entry.get())

        try:

            self.client = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM
            )

            self.client.connect((host, port))

            request = self.client.recv(1024).decode()

            if request == "ENTER_USERNAME":

                self.client.send(username.encode())

            self.username = username

            self.login_window.destroy()

            self.build_chat_window()

        except Exception as e:

            messagebox.showerror(
                "Connection Error",
                str(e)
            )
                # ------------------------
    # Chat Window
    # ------------------------

    def build_chat_window(self):

        self.window = tk.Tk()
        self.window.title(f"TCP Chat - {self.username}")
        self.window.geometry("900x600")
        self.window.protocol("WM_DELETE_WINDOW", self.disconnect)

        # =====================
        # Top Frame
        # =====================

        top_frame = ttk.Frame(self.window)
        top_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(
            top_frame,
            text=f"Logged in as : {self.username}",
            font=("Arial", 11, "bold")
        ).pack(side="left")

        self.status_label = ttk.Label(
            top_frame,
            text="● Connected",
            foreground="green"
        )

        self.status_label.pack(side="right")

        # =====================
        # Middle Frame
        # =====================

        middle = ttk.Frame(self.window)
        middle.pack(fill="both", expand=True, padx=10)

        # Chat Area

        self.chat_box = scrolledtext.ScrolledText(
            middle,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Consolas", 10)
        )

        self.chat_box.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 10)
        )

        # Online Users

        user_frame = ttk.LabelFrame(
            middle,
            text="Online Users",
            width=200
        )

        user_frame.pack(
            side="right",
            fill="y"
        )

        self.user_list = tk.Listbox(
            user_frame,
            width=25,
            height=25
        )

        self.user_list.pack(
            fill="both",
            expand=True,
            padx=5,
            pady=5
        )

        # =====================
        # Bottom Frame
        # =====================

        bottom = ttk.Frame(self.window)
        bottom.pack(fill="x", padx=10, pady=10)

        ttk.Label(
            bottom,
            text="Private To"
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        self.private_entry = ttk.Entry(
            bottom,
            width=20
        )

        self.private_entry.grid(
            row=0,
            column=1,
            padx=5
        )

        ttk.Label(
            bottom,
            text="Message"
        ).grid(
            row=1,
            column=0,
            sticky="w",
            pady=10
        )

        self.message_entry = ttk.Entry(
            bottom,
            width=70
        )

        self.message_entry.grid(
            row=1,
            column=1,
            padx=5,
            sticky="ew"
        )

        self.message_entry.bind(
            "<Return>",
            lambda event: self.send_message()
        )

        ttk.Button(
            bottom,
            text="Send",
            command=self.send_message
        ).grid(
            row=1,
            column=2,
            padx=5
        )

        ttk.Button(
            bottom,
            text="Disconnect",
            command=self.disconnect
        ).grid(
            row=1,
            column=3,
            padx=5
        )

        bottom.columnconfigure(1, weight=1)

        # Start background receive thread

        threading.Thread(
            target=self.receive_messages,
            daemon=True
        ).start()

        self.window.mainloop()
            # ------------------------
    # Receive Messages
    # ------------------------

    def receive_messages(self):

        while True:

            try:

                message = self.client.recv(4096).decode()

                if not message:

                    break

                # ----------------------------
                # Automatic Online User Update
                # ----------------------------

                if message.startswith("USERLIST|"):

                    users = message.split("|", 1)[1]

                    self.user_list.delete(0, tk.END)

                    if users.strip() != "":

                        for user in users.split(","):

                            self.user_list.insert(
                                tk.END,
                                user
                            )

                    continue

                # ----------------------------
                # Normal Chat Messages
                # ----------------------------

                self.chat_box.config(state=tk.NORMAL)

                self.chat_box.insert(
                    tk.END,
                    message + "\n"
                )

                self.chat_box.config(state=tk.DISABLED)

                self.chat_box.see(tk.END)

            except:

                break

        self.status_label.config(
            text="● Disconnected",
            foreground="red"
        )

        try:
            self.client.close()
        except:
            pass
                # ------------------------
    # Send Message
    # ------------------------

    def send_message(self):

        message = self.message_entry.get().strip()

        if message == "":
            return

        private_user = self.private_entry.get().strip()

        try:

            if private_user != "":

                data = f"/msg {private_user} {message}"

            else:

                data = message

            self.client.sendall(data.encode())
            if private_user == "":

                self.chat_box.config(state=tk.NORMAL)

                self.chat_box.insert(
                tk.END,
                f"You: {message}\n"
    )

                self.chat_box.config(state=tk.DISABLED)

                self.chat_box.see(tk.END)

            else:

                self.chat_box.config(state=tk.NORMAL)
 
                self.chat_box.insert(
                tk.END,
                f"[PRIVATE to {private_user}] {message}\n"
    )

                self.chat_box.config(state=tk.DISABLED)

                self.chat_box.see(tk.END)

            self.message_entry.delete(0, tk.END)

        except Exception as e:

            messagebox.showerror(
                "Send Error",
                str(e)
            )

    # ------------------------
    # Disconnect
    # ------------------------

    def disconnect(self):
        try:
            self.client.shutdown(socket.SHUT_RDWR)
        except:
            pass

        try:
            self.client.close()
        except:
            pass

        self.status_label.config(
            text="● Disconnected",
            foreground="red"
    )

        self.window.destroy()

    # ------------------------
    # Run
    # ------------------------


if __name__ == "__main__":

    ChatClient()
