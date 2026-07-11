import socket
import threading
import csv
import os
from datetime import datetime

# ==========================
# Server Configuration
# ==========================
HOST = "0.0.0.0"
PORT = 5000

CHAT_HISTORY = "chat_history.csv"

# ==========================
# Global Variables
# ==========================

clients = {}
clients_lock = threading.Lock()

stats = {
    "messages_processed": 0,
    "broadcast_messages": 0,
    "private_messages": 0
}

stats_lock = threading.Lock()


# ==========================
# Chat History
# ==========================

def initialize_history():

    if not os.path.exists(CHAT_HISTORY):

        with open(CHAT_HISTORY, "w", newline="", encoding="utf-8") as file:

            writer = csv.writer(file)

            writer.writerow([
                "Timestamp",
                "Sender",
                "Receiver",
                "Type",
                "Message"
            ])


def log_message(sender, receiver, msg_type, message):

    with open(CHAT_HISTORY, "a", newline="", encoding="utf-8") as file:

        writer = csv.writer(file)

        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            sender,
            receiver,
            msg_type,
            message
        ])


def get_last_five(username):

    if not os.path.exists(CHAT_HISTORY):
        return []

    messages = []

    with open(CHAT_HISTORY, "r", encoding="utf-8") as file:

        reader = csv.DictReader(file)

        for row in reader:

            if row["Sender"] == username:

                messages.append(
                    f"[{row['Timestamp']}] "
                    f"To {row['Receiver']} "
                    f"({row['Type']}): "
                    f"{row['Message']}"
                )

    return messages[-5:]


# ==========================
# Statistics
# ==========================

def update_stats(message_type):

    with stats_lock:

        stats["messages_processed"] += 1

        if message_type == "BROADCAST":

            stats["broadcast_messages"] += 1

        elif message_type == "PRIVATE":

            stats["private_messages"] += 1


# ==========================
# Online Users
# ==========================

def send_online_users():

    with clients_lock:

        usernames = []

        for info in clients.values():

            usernames.append(info["username"])

        packet = "USERLIST|" + ",".join(usernames)

        dead_clients = []

        for sock in clients.keys():

            try:

                sock.sendall(packet.encode())

            except:

                dead_clients.append(sock)

        for sock in dead_clients:

            try:
                sock.close()
            except:
                pass

            if sock in clients:
                del clients[sock]


# ==========================
# Broadcast Function
# ==========================

def broadcast(message, sender=None):

    with clients_lock:

        disconnected = []

        for sock in clients.keys():

            if sock == sender:
                continue

            try:

                sock.sendall(message.encode())

            except:

                disconnected.append(sock)

        for sock in disconnected:

            try:
                sock.close()
            except:
                pass

            if sock in clients:

                del clients[sock]

        if disconnected:

            send_online_users()
        # ==========================
# Client Handler
# ==========================

def handle_client(client_socket, address):

    ip, port = address

    username = ""

    try:

        # Ask username
        client_socket.sendall("ENTER_USERNAME".encode())

        username = client_socket.recv(1024).decode().strip()

        if username == "":
            client_socket.close()
            return

        login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with clients_lock:

            clients[client_socket] = {
                "username": username,
                "ip": ip,
                "port": port,
                "login_time": login_time,
                "status": "Online"
            }

        print(f"[JOIN] {username} ({ip}:{port})")

        # Send updated online users to everyone
        send_online_users()

        # Send previous messages
        history = get_last_five(username)

        if history:

            client_socket.sendall(
                "\n===== Last Five Messages =====\n".encode()
            )

            for msg in history:

                client_socket.sendall(
                    (msg + "\n").encode()
                )

            client_socket.sendall(
                "==============================\n".encode()
            )

        # Notify everyone
        broadcast(
            f"[SERVER] {username} joined the chat.\n",
            client_socket
        )

        while True:

            data = client_socket.recv(1024)

            if not data:
                break

            message = data.decode().strip()

            if message == "":
                continue

            # -----------------------------
            # Statistics
            # -----------------------------

            if message == "/stats":

                with stats_lock, clients_lock:

                    response = (
                        "\n========== SERVER ==========\n"
                        f"Connected Users : {len(clients)}\n"
                        f"Messages        : {stats['messages_processed']}\n"
                        f"Broadcast       : {stats['broadcast_messages']}\n"
                        f"Private         : {stats['private_messages']}\n"
                        "============================\n"
                    )

                client_socket.sendall(
                    response.encode()
                )

                continue

            # -----------------------------
            # Online User List
            # -----------------------------

            if message == "/list":

                send_online_users()

                continue

            # -----------------------------
            # Private Message
            # -----------------------------

            if message.startswith("/msg "):

                parts = message.split(" ", 2)

                if len(parts) < 3:

                    client_socket.sendall(
                        "[ERROR] Usage: /msg username message\n".encode()
                    )

                    continue

                target = parts[1]

                private_message = parts[2]

                delivered = False

                with clients_lock:

                    for sock, info in clients.items():

                        if info["username"] == target:

                            sock.sendall(
                                f"[PRIVATE] {username}: {private_message}\n".encode()
                            )

                            delivered = True

                            break

                if delivered:

                    client_socket.sendall(
                        f"[PRIVATE to {target}] {private_message}\n".encode()
                    )

                    log_message(
                        username,
                        target,
                        "PRIVATE",
                        private_message
                    )

                    update_stats("PRIVATE")

                else:

                    client_socket.sendall(
                        f"[ERROR] User '{target}' not online.\n".encode()
                    )

                continue

            # -----------------------------
            # Broadcast Message
            # -----------------------------

            text = f"{username}: {message}\n"

            broadcast(
                text,
                client_socket
            )

            log_message(
                username,
                "ALL",
                "BROADCAST",
                message
            )

            update_stats("BROADCAST")    
    except Exception as e:

        print(f"[ERROR] {username}: {e}")

    finally:

        left_user = None

        with clients_lock:

            if client_socket in clients:

                left_user = clients[client_socket]["username"]
 
                del clients[client_socket]

        if left_user:

            print(f"[LEAVE] {left_user}")

            broadcast(
                f"[SERVER] {left_user} left the chat.\n"
            )

            send_online_users()

        try:
            client_socket.close()
        except:
            pass
        try:
            client_socket.close()
        except:
            pass


# ==========================
# Server Start
# ==========================

def start_server():

    initialize_history()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    server.bind((HOST, PORT))

    server.listen(10)

    print("=" * 50)
    print(" TCP Multi Client Chat Server")
    print("=" * 50)
    print(f"Listening on {HOST}:{PORT}")
    print("=" * 50)

    while True:

        try:

            client_socket, address = server.accept()

            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, address),
                daemon=True
            )

            thread.start()

        except KeyboardInterrupt:

            print("\nServer shutting down...")

            break

        except Exception as e:

            print("[SERVER ERROR]", e)

    with clients_lock:

        for sock in list(clients.keys()):

            try:
                sock.close()
            except:
                pass

    server.close()


# ==========================
# Main
# ==========================

if __name__ == "__main__":

    start_server()
