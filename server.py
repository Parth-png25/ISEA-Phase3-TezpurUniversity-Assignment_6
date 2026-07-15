import csv
import hashlib
import json
import os
import re
import socket
import threading
import time
from datetime import datetime

HOST = "0.0.0.0"
PORT = 5000

USERS_FILE = "users.json"
CHAT_HISTORY = "chat_history.csv"
SECURITY_LOG = "security_log.txt"

MAX_MESSAGE_LEN = 500
USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 20
PASSWORD_MIN_LEN = 6
PASSWORD_MAX_LEN = 64
SESSION_TIMEOUT = 180  # seconds
LOCKOUT_DURATION = 60  # seconds
MAX_FAILED_ATTEMPTS = 5

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")

clients = {}  # socket -> client info
clients_lock = threading.Lock()

active_users = set()
active_users_lock = threading.Lock()

failed_attempts = {}  # username -> {"count": int, "locked_until": float}
failed_attempts_lock = threading.Lock()

stats = {
    "messages_processed": 0,
    "broadcast_messages": 0,
    "private_messages": 0,
    "logins": 0,
    "failed_logins": 0,
}
stats_lock = threading.Lock()


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def ensure_files() -> None:
    if not os.path.exists(USERS_FILE):
        default_users = {
            # Demo accounts for testing assignment 7
            "admin": sha256_hash("Admin@123"),
            "alice": sha256_hash("Alice@123"),
            "bob": sha256_hash("Bob@123"),
        }
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default_users, f, indent=2)

    if not os.path.exists(CHAT_HISTORY):
        with open(CHAT_HISTORY, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "sender", "receiver", "message_type", "message"])

    if not os.path.exists(SECURITY_LOG):
        with open(SECURITY_LOG, "w", encoding="utf-8") as f:
            f.write("")


def load_users() -> dict:
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("users.json must contain a JSON object of username -> password_hash")
    return data


def log_security(event: str, username: str = "-", ip: str = "-", detail: str = "-") -> None:
    line = f"{now_str()} | {event} | user={username} | ip={ip} | detail={detail}\n"
    with open(SECURITY_LOG, "a", encoding="utf-8") as f:
        f.write(line)


def log_chat(sender: str, receiver: str, message_type: str, message: str) -> None:
    with open(CHAT_HISTORY, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([now_str(), sender, receiver, message_type, message])


def update_stats(kind: str) -> None:
    with stats_lock:
        stats["messages_processed"] += 1
        if kind == "BROADCAST":
            stats["broadcast_messages"] += 1
        elif kind == "PRIVATE":
            stats["private_messages"] += 1


def validate_username(username: str) -> tuple[bool, str]:
    if not username:
        return False, "Username cannot be empty."
    if not USERNAME_PATTERN.fullmatch(username):
        return False, "Username must be 3-20 characters using letters, numbers, or underscore."
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    if not password:
        return False, "Password cannot be empty."
    if not (PASSWORD_MIN_LEN <= len(password) <= PASSWORD_MAX_LEN):
        return False, f"Password must be between {PASSWORD_MIN_LEN} and {PASSWORD_MAX_LEN} characters."
    return True, ""


def validate_message(message: str) -> tuple[bool, str]:
    if not message:
        return False, "Message cannot be empty."
    if len(message) > MAX_MESSAGE_LEN:
        return False, f"Message too long. Maximum allowed is {MAX_MESSAGE_LEN} characters."
    return True, ""


def is_locked(username: str) -> tuple[bool, int]:
    with failed_attempts_lock:
        data = failed_attempts.get(username)
        if not data:
            return False, 0

        locked_until = data.get("locked_until", 0)
        remaining = int(locked_until - time.time())
        if remaining > 0:
            return True, remaining

        if locked_until and remaining <= 0:
            failed_attempts[username] = {"count": 0, "locked_until": 0}
        return False, 0


def register_failed_login(username: str) -> int:
    with failed_attempts_lock:
        data = failed_attempts.get(username, {"count": 0, "locked_until": 0})
        count = int(data.get("count", 0)) + 1
        locked_until = int(data.get("locked_until", 0))

        if count >= MAX_FAILED_ATTEMPTS:
            locked_until = int(time.time()) + LOCKOUT_DURATION
            count = 0

        failed_attempts[username] = {"count": count, "locked_until": locked_until}

        if locked_until > int(time.time()):
            return locked_until - int(time.time())
        return 0


def reset_failed_login(username: str) -> None:
    with failed_attempts_lock:
        if username in failed_attempts:
            failed_attempts.pop(username, None)


def send_line(sock: socket.socket, message: str) -> bool:
    try:
        sock.sendall((message + "\n").encode("utf-8"))
        return True
    except Exception:
        return False


def broadcast(message: str, exclude_sock: socket.socket | None = None) -> None:
    with clients_lock:
        dead = []
        for sock in list(clients.keys()):
            if exclude_sock is not None and sock == exclude_sock:
                continue
            try:
                sock.sendall((message + "\n").encode("utf-8"))
            except Exception:
                dead.append(sock)

        for sock in dead:
            remove_client_socket(sock)


def send_user_list() -> None:
    with clients_lock:
        usernames = [info["username"] for info in clients.values()]
        payload = "USERLIST|" + ",".join(usernames)

        dead = []
        for sock in list(clients.keys()):
            try:
                sock.sendall((payload + "\n").encode("utf-8"))
            except Exception:
                dead.append(sock)

        for sock in dead:
            remove_client_socket(sock)


def remove_client_socket(sock: socket.socket) -> None:
    with clients_lock:
        info = clients.pop(sock, None)

    if not info:
        return

    username = info["username"]
    with active_users_lock:
        active_users.discard(username)

    try:
        sock.close()
    except Exception:
        pass

    log_security("DISCONNECT", username=username, ip=info.get("ip", "-"), detail="Client disconnected")
    broadcast(f"[SERVER] {username} left the chat.", exclude_sock=sock)
    send_user_list()


def get_last_five_messages(username: str) -> list[str]:
    if not os.path.exists(CHAT_HISTORY):
        return []

    rows = []
    with open(CHAT_HISTORY, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sender = row.get("sender", "")
            receiver = row.get("receiver", "")
            msg_type = row.get("message_type", "")
            message = row.get("message", "")
            timestamp = row.get("timestamp", "")

            # Show messages sent by or addressed to the user
            if sender == username or receiver == username or receiver == "ALL":
                if msg_type == "PRIVATE":
                    rows.append(f"[{timestamp}] [PRIVATE] {sender} -> {receiver}: {message}")
                else:
                    rows.append(f"[{timestamp}] {sender}: {message}")

    return rows[-5:]


def authenticate_user(client_socket: socket.socket, address: tuple[str, int], users: dict) -> tuple[str | None, str]:
    ip, _ = address

    if not send_line(client_socket, "AUTH_REQUIRED|Send credentials as username|password"):
        return None, "Socket closed before auth"

    try:
        client_socket.settimeout(60)
        raw = client_socket.recv(2048)
        if not raw:
            return None, "No credentials received"

        try:
            payload = raw.decode("utf-8", errors="ignore").strip()
        except Exception:
            return None, "Invalid encoding"

        if "|" not in payload:
            return None, "Malformed authentication packet"

        username, password = payload.split("|", 1)
        username = username.strip()
        password = password.strip()

        valid_user, user_msg = validate_username(username)
        if not valid_user:
            log_security("AUTH_FAIL", username=username or "-", ip=ip, detail=user_msg)
            update_stats("FAILED")
            return None, user_msg

        valid_pass, pass_msg = validate_password(password)
        if not valid_pass:
            log_security("AUTH_FAIL", username=username, ip=ip, detail=pass_msg)
            update_stats("FAILED")
            return None, pass_msg

        locked, remaining = is_locked(username)
        if locked:
            msg = f"Account locked. Try again after {remaining} seconds."
            log_security("AUTH_LOCKED", username=username, ip=ip, detail=msg)
            update_stats("FAILED")
            return None, msg

        expected_hash = users.get(username)
        if not expected_hash:
            lock_seconds = register_failed_login(username)
            detail = "Unknown username"
            if lock_seconds:
                detail += f"; account locked for {lock_seconds} seconds"
            log_security("AUTH_FAIL", username=username, ip=ip, detail=detail)
            update_stats("FAILED")
            return None, "Invalid username or password."

        if sha256_hash(password) != expected_hash:
            lock_seconds = register_failed_login(username)
            detail = "Incorrect password"
            if lock_seconds:
                detail += f"; account locked for {lock_seconds} seconds"
            log_security("AUTH_FAIL", username=username, ip=ip, detail=detail)
            update_stats("FAILED")
            if lock_seconds:
                return None, f"Too many failed attempts. Account locked for {lock_seconds} seconds."
            return None, "Invalid username or password."

        with active_users_lock:
            if username in active_users:
                log_security("DUPLICATE_LOGIN", username=username, ip=ip, detail="User already logged in")
                return None, "This user is already logged in from another session."

            active_users.add(username)

        reset_failed_login(username)
        log_security("AUTH_SUCCESS", username=username, ip=ip, detail="Login successful")
        with stats_lock:
            stats["logins"] += 1

        with clients_lock:
            clients[client_socket] = {
                "username": username,
                "ip": ip,
                "port": address[1],
                "login_time": now_str(),
                "status": "Online",
                "last_activity": time.time(),
            }

        return username, "AUTH_OK|Login successful"

    finally:
        client_socket.settimeout(None)


def handle_client(client_socket: socket.socket, address: tuple[str, int], users: dict) -> None:
    ip, port = address
    username = None

    try:
        username, auth_reply = authenticate_user(client_socket, address, users)  
        print(f"[LOGIN] {username} authenticated")
        if not username:
            send_line(client_socket, f"AUTH_FAIL|{auth_reply}")
            return

        send_line(client_socket, auth_reply)
        send_user_list()
        print("[CLIENTS]", clients)

        history = get_last_five_messages(username)
        if history:
            send_line(client_socket, "HISTORY_START")
            for line in history:
                send_line(client_socket, line)
            send_line(client_socket, "HISTORY_END")

        broadcast(f"[SERVER] {username} joined the chat.", exclude_sock=client_socket)
        log_security("SESSION_START", username=username, ip=ip, detail="Session opened")

        client_socket.settimeout(5.0)

        while True:
            try:
                raw = client_socket.recv(4096)
                if not raw:
                    break

                message = raw.decode("utf-8", errors="ignore").strip()
                if not message:
                    continue

                with clients_lock:
                    if client_socket in clients:
                        clients[client_socket]["last_activity"] = time.time()

                if len(message) > MAX_MESSAGE_LEN and not message.startswith("/"):
                    send_line(client_socket, f"[ERROR] Message too long. Max {MAX_MESSAGE_LEN} characters.")
                    continue

                if message == "/logout":
                    send_line(client_socket, "SERVER|Logged out successfully.")
                    log_security("LOGOUT", username=username, ip=ip, detail="User logged out")
                    break

                if message == "/list":
                    send_user_list()
                    continue

                if message.startswith("/msg "):
                    parts = message.split(" ", 2)
                    if len(parts) < 3:
                        send_line(client_socket, "[ERROR] Usage: /msg username message")
                        continue

                    target, private_message = parts[1].strip(), parts[2].strip()
                    if not target or not private_message:
                        send_line(client_socket, "[ERROR] Usage: /msg username message")
                        continue

                    if len(private_message) > MAX_MESSAGE_LEN:
                        send_line(client_socket, f"[ERROR] Message too long. Max {MAX_MESSAGE_LEN} characters.")
                        continue

                    delivered = False
                    target_sock = None
                    with clients_lock:
                        for sock, info in clients.items():
                            if info["username"] == target:
                                target_sock = sock
                                delivered = True
                                break

                    if delivered and target_sock:
                        send_line(target_sock, f"[PRIVATE] {username}: {private_message}")
                        send_line(client_socket, f"[PRIVATE to {target}] {private_message}")
                        log_chat(username, target, "PRIVATE", private_message)
                        update_stats("PRIVATE")
                    else:
                        send_line(client_socket, f"[ERROR] User '{target}' not online.")
                    continue

                if message.startswith("/"):
                    send_line(client_socket, "[ERROR] Unsupported command. Use /msg, /list, or /logout.")
                    continue

                valid_msg, msg_error = validate_message(message)
                if not valid_msg:
                    send_line(client_socket, f"[ERROR] {msg_error}")
                    continue

                formatted = f"{username}: {message}"
                broadcast(formatted, exclude_sock=client_socket)
                send_line(client_socket, formatted)
                log_chat(username, "ALL", "BROADCAST", message)
                update_stats("BROADCAST")

            except socket.timeout:
                with clients_lock:
                    last_activity = clients.get(client_socket, {}).get("last_activity", time.time())

                if time.time() - last_activity > SESSION_TIMEOUT:
                    send_line(client_socket, "SERVER|Session timed out due to inactivity.")
                    log_security("SESSION_TIMEOUT", username=username, ip=ip, detail="Inactivity timeout")
                    break
                continue

    except Exception as e:
        if username:
            log_security("SERVER_ERROR", username=username, ip=ip, detail=str(e))
        else:
            log_security("SERVER_ERROR", username="-", ip=ip, detail=str(e))

    finally:
        with clients_lock:
            info = clients.pop(client_socket, None)

        if info:
            with active_users_lock:
                active_users.discard(info["username"])
            broadcast(f"[SERVER] {info['username']} left the chat.", exclude_sock=client_socket)
            send_user_list()

        try:
            client_socket.close()
        except Exception:
            pass


def start_server() -> None:
    ensure_files()
    users = load_users()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(20)

    print("=" * 60)
    print(" Secure TCP Multi-Client Chat Server (Assignment 7)")
    print("=" * 60)
    print(f"Listening on {HOST}:{PORT}")
    print(f"Users file: {USERS_FILE}")
    print(f"Security log: {SECURITY_LOG}")
    print(f"Chat history: {CHAT_HISTORY}")
    print("=" * 60)

    try:
        while True:
            client_socket, address = server.accept()
            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, address, users),
                daemon=True,
            )
            thread.start()
    except KeyboardInterrupt:
        print("\nServer shutting down...")
    finally:
        with clients_lock:
            sockets = list(clients.keys())
        for sock in sockets:
            try:
                sock.close()
            except Exception:
                pass
        try:
            server.close()
        except Exception:
            pass


if __name__ == "__main__":
    start_server()
