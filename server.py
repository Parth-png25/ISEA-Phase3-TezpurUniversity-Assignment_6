import csv
import hashlib
import json
import os
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
except Exception:
    psutil = None

DEFAULT_CONFIG = {
    "bind_host": "0.0.0.0",
    "server_port": 5000,
    "max_message_len": 500,
    "username_min_len": 3,
    "username_max_len": 20,
    "password_min_len": 6,
    "password_max_len": 64,
    "session_timeout": 180,
    "lockout_duration": 60,
    "max_failed_attempts": 5,
    "max_clients": 10,
    "accept_timeout": 1.0,
    "cleanup_interval": 5.0,
    "users_file": "users.json",
    "chat_history_file": "chat_history.csv",
    "security_log_file": "security_log.txt",
    "performance_results_file": "performance_results.csv",
    "performance_logging": True,
}

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]{3,20}$")

config = dict(DEFAULT_CONFIG)

clients = {}  # socket -> client info
clients_lock = threading.Lock()
socket_send_locks = {}  # socket -> threading.Lock

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

shutdown_event = threading.Event()

performance_lock = threading.Lock()
performance_state = {
    "start_time": time.time(),
    "delay_samples": 0,
    "delay_total_ms": 0.0,
}

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_config() -> dict:
    cfg_path = Path("config.json")
    loaded = {}
    if cfg_path.exists():
        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                loaded = {}
        except Exception:
            loaded = {}
    merged = dict(DEFAULT_CONFIG)
    merged.update(loaded)
    return merged


def ensure_files() -> None:
    users_file = Path(config["users_file"])
    if not users_file.exists():
        fallback = Path("users(2).json")
        if fallback.exists():
            try:
                shutil_copy = fallback.read_text(encoding="utf-8")
                users_file.write_text(shutil_copy, encoding="utf-8")
            except Exception:
                default_users = {
                    "admin": sha256_hash("Admin@123"),
                    "alice": sha256_hash("Alice@123"),
                    "bob": sha256_hash("Bob@123"),
                }
                with users_file.open("w", encoding="utf-8") as f:
                    json.dump(default_users, f, indent=2)
        else:
            default_users = {
                "admin": sha256_hash("Admin@123"),
                "alice": sha256_hash("Alice@123"),
                "bob": sha256_hash("Bob@123"),
            }
            with users_file.open("w", encoding="utf-8") as f:
                json.dump(default_users, f, indent=2)

    history_file = Path(config["chat_history_file"])
    if not history_file.exists():
        with history_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "sender", "receiver", "message_type", "message"])

    security_file = Path(config["security_log_file"])
    if not security_file.exists():
        security_file.write_text("", encoding="utf-8")

    performance_file = Path(config["performance_results_file"])
    if not performance_file.exists():
        with performance_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "event",
                "username",
                "active_clients",
                "messages_processed",
                "broadcast_messages",
                "private_messages",
                "average_delay_ms",
                "throughput_msg_per_sec",
                "cpu_usage_percent",
                "memory_usage_mb",
                "note",
            ])


def load_users() -> dict:
    users_file = Path(config["users_file"])
    with users_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("users.json must contain a JSON object of username -> password_hash")
    return data


def log_security(event: str, username: str = "-", ip: str = "-", detail: str = "-") -> None:
    line = f"{now_str()} | {event} | user={username} | ip={ip} | detail={detail}\n"
    with Path(config["security_log_file"]).open("a", encoding="utf-8") as f:
        f.write(line)


def log_chat(sender: str, receiver: str, message_type: str, message: str) -> None:
    with Path(config["chat_history_file"]).open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([now_str(), sender, receiver, message_type, message])


def _get_process_metrics() -> tuple[float, float]:
    if psutil is None:
        return 0.0, 0.0
    try:
        proc = psutil.Process(os.getpid())
        cpu = proc.cpu_percent(None)
        mem_mb = proc.memory_info().rss / (1024 * 1024)
        return round(float(cpu), 2), round(float(mem_mb), 2)
    except Exception:
        return 0.0, 0.0


def log_performance(event: str, username: str = "-", delay_ms: float | None = None, note: str = "-") -> None:
    if not config.get("performance_logging", True):
        return

    with performance_lock:
        if delay_ms is not None:
            performance_state["delay_samples"] += 1
            performance_state["delay_total_ms"] += max(0.0, float(delay_ms))

        avg_delay = 0.0
        if performance_state["delay_samples"]:
            avg_delay = performance_state["delay_total_ms"] / performance_state["delay_samples"]

        uptime = max(time.time() - performance_state["start_time"], 0.001)
        throughput = stats["messages_processed"] / uptime

        cpu_usage, memory_usage = _get_process_metrics()

        row = [
            now_str(),
            event,
            username,
            len(clients),
            stats["messages_processed"],
            stats["broadcast_messages"],
            stats["private_messages"],
            f"{avg_delay:.2f}",
            f"{throughput:.2f}",
            f"{cpu_usage:.2f}",
            f"{memory_usage:.2f}",
            note,
        ]

        with Path(config["performance_results_file"]).open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)


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
    if not (config["password_min_len"] <= len(password) <= config["password_max_len"]):
        return False, f"Password must be between {config['password_min_len']} and {config['password_max_len']} characters."
    return True, ""


def validate_message(message: str) -> tuple[bool, str]:
    if not message:
        return False, "Message cannot be empty."
    if len(message) > config["max_message_len"]:
        return False, f"Message too long. Maximum allowed is {config['max_message_len']} characters."
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

        if count >= config["max_failed_attempts"]:
            locked_until = int(time.time()) + config["lockout_duration"]
            count = 0

        failed_attempts[username] = {"count": count, "locked_until": locked_until}

        if locked_until > int(time.time()):
            return locked_until - int(time.time())
        return 0


def reset_failed_login(username: str) -> None:
    with failed_attempts_lock:
        failed_attempts.pop(username, None)


def get_client_send_lock(sock: socket.socket) -> threading.Lock | None:
    return socket_send_locks.get(sock)


def send_line(sock: socket.socket, message: str) -> bool:
    try:
        lock = get_client_send_lock(sock)
        if lock is None:
            sock.sendall((message + "\n").encode("utf-8"))
        else:
            with lock:
                sock.sendall((message + "\n").encode("utf-8"))
        return True
    except Exception:
        return False


def broadcast(message: str, exclude_sock: socket.socket | None = None) -> None:
    with clients_lock:
        targets = list(clients.keys())

    dead = []
    for sock in targets:
        if exclude_sock is not None and sock == exclude_sock:
            continue
        if not send_line(sock, message):
            dead.append(sock)

    for sock in dead:
        remove_client_socket(sock)


def send_user_list() -> None:
    with clients_lock:
        usernames = [info["username"] for info in clients.values()]
        targets = list(clients.keys())

    payload = "USERLIST|" + ",".join(usernames)
    dead = []
    for sock in targets:
        if not send_line(sock, payload):
            dead.append(sock)

    for sock in dead:
        remove_client_socket(sock)


def remove_client_socket(sock: socket.socket, reason: str = "Client disconnected") -> None:
    with clients_lock:
        info = clients.pop(sock, None)
        socket_send_locks.pop(sock, None)

    if not info:
        try:
            sock.close()
        except Exception:
            pass
        return

    username = info["username"]
    with active_users_lock:
        active_users.discard(username)

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass

    log_security("DISCONNECT", username=username, ip=info.get("ip", "-"), detail=reason)
    broadcast(f"[SERVER] {username} left the chat.", exclude_sock=sock)
    send_user_list()


def get_last_five_messages(username: str) -> list[str]:
    history_file = Path(config["chat_history_file"])
    if not history_file.exists():
        return []

    rows = []
    with history_file.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sender = row.get("sender", "")
            receiver = row.get("receiver", "")
            msg_type = row.get("message_type", "")
            message = row.get("message", "")
            timestamp = row.get("timestamp", "")

            if sender == username or receiver == username or receiver == "ALL":
                if msg_type == "PRIVATE":
                    rows.append(f"[{timestamp}] [PRIVATE] {sender} -> {receiver}: {message}")
                else:
                    rows.append(f"[{timestamp}] {sender}: {message}")

    return rows[-5:]


def authenticate_user(client_socket: socket.socket, address: tuple[str, int], users: dict) -> tuple[str | None, str]:
    ip, _ = address
    auth_start = time.perf_counter()

    if not send_line(client_socket, "AUTH_REQUIRED|Send credentials as username|password"):
        return None, "Socket closed before auth"

    try:
        client_socket.settimeout(60)
        raw = client_socket.recv(2048)
        if not raw:
            log_performance("AUTH_FAIL", username="-", delay_ms=(time.perf_counter() - auth_start) * 1000, note="No credentials received")
            return None, "No credentials received"

        payload = raw.decode("utf-8", errors="ignore").strip()
        if "|" not in payload:
            log_performance("AUTH_FAIL", username="-", delay_ms=(time.perf_counter() - auth_start) * 1000, note="Malformed authentication packet")
            return None, "Malformed authentication packet"

        username, password = payload.split("|", 1)
        username = username.strip()
        password = password.strip()

        valid_user, user_msg = validate_username(username)
        if not valid_user:
            log_security("AUTH_FAIL", username=username or "-", ip=ip, detail=user_msg)
            with stats_lock:
                stats["failed_logins"] += 1
            log_performance("AUTH_FAIL", username=username or "-", delay_ms=(time.perf_counter() - auth_start) * 1000, note=user_msg)
            return None, user_msg

        valid_pass, pass_msg = validate_password(password)
        if not valid_pass:
            log_security("AUTH_FAIL", username=username, ip=ip, detail=pass_msg)
            with stats_lock:
                stats["failed_logins"] += 1
            log_performance("AUTH_FAIL", username=username, delay_ms=(time.perf_counter() - auth_start) * 1000, note=pass_msg)
            return None, pass_msg

        locked, remaining = is_locked(username)
        if locked:
            msg = f"Account locked. Try again after {remaining} seconds."
            log_security("AUTH_LOCKED", username=username, ip=ip, detail=msg)
            with stats_lock:
                stats["failed_logins"] += 1
            log_performance("AUTH_LOCKED", username=username, delay_ms=(time.perf_counter() - auth_start) * 1000, note=msg)
            return None, msg

        expected_hash = users.get(username)
        if not expected_hash:
            lock_seconds = register_failed_login(username)
            detail = "Unknown username"
            if lock_seconds:
                detail += f"; account locked for {lock_seconds} seconds"
            log_security("AUTH_FAIL", username=username, ip=ip, detail=detail)
            with stats_lock:
                stats["failed_logins"] += 1
            log_performance("AUTH_FAIL", username=username, delay_ms=(time.perf_counter() - auth_start) * 1000, note="Invalid username or password")
            return None, "Invalid username or password."

        if sha256_hash(password) != expected_hash:
            lock_seconds = register_failed_login(username)
            detail = "Incorrect password"
            if lock_seconds:
                detail += f"; account locked for {lock_seconds} seconds"
            log_security("AUTH_FAIL", username=username, ip=ip, detail=detail)
            with stats_lock:
                stats["failed_logins"] += 1
            if lock_seconds:
                log_performance("AUTH_FAIL", username=username, delay_ms=(time.perf_counter() - auth_start) * 1000, note=f"Account locked for {lock_seconds} seconds")
                return None, f"Too many failed attempts. Account locked for {lock_seconds} seconds."
            return None, "Invalid username or password."

        with active_users_lock:
            if username in active_users:
                log_security("DUPLICATE_LOGIN", username=username, ip=ip, detail="User already logged in")
                log_performance("DUPLICATE_LOGIN", username=username, delay_ms=(time.perf_counter() - auth_start) * 1000, note="Duplicate login")
                return None, "This user is already logged in from another session."
            active_users.add(username)

        reset_failed_login(username)
        log_security("AUTH_SUCCESS", username=username, ip=ip, detail="Login successful")
        with stats_lock:
            stats["logins"] += 1

        with clients_lock:
            socket_send_locks[client_socket] = threading.Lock()
            clients[client_socket] = {
                "username": username,
                "ip": ip,
                "port": address[1],
                "login_time": now_str(),
                "status": "Online",
                "last_activity": time.time(),
            }

        log_performance("AUTH_SUCCESS", username=username, delay_ms=(time.perf_counter() - auth_start) * 1000, note="Login successful")
        return username, "AUTH_OK|Login successful"
    finally:
        client_socket.settimeout(None)


def handle_client(client_socket: socket.socket, address: tuple[str, int], users: dict) -> None:
    ip, port = address
    username = None

    try:
        if len(clients) >= config["max_clients"]:
            send_line(client_socket, "AUTH_FAIL|Server is busy. Please try again later.")
            log_security("REJECTED", username="-", ip=ip, detail="Maximum client limit reached")
            log_performance("SERVER_BUSY", username="-", delay_ms=0.0, note="Maximum client limit reached")
            return

        username, auth_reply = authenticate_user(client_socket, address, users)
        print(f"[LOGIN] {username} authenticated from {ip}:{port}")
        if not username:
            send_line(client_socket, f"AUTH_FAIL|{auth_reply}")
            return

        send_line(client_socket, auth_reply)
        send_user_list()

        history = get_last_five_messages(username)
        if history:
            send_line(client_socket, "HISTORY_START")
            for line in history:
                send_line(client_socket, line)
            send_line(client_socket, "HISTORY_END")

        broadcast(f"[SERVER] {username} joined the chat.", exclude_sock=client_socket)
        log_security("SESSION_START", username=username, ip=ip, detail="Session opened")

        client_socket.settimeout(1.0)

        while not shutdown_event.is_set():
            try:
                raw = client_socket.recv(4096)
                if not raw:
                    break

                message = raw.decode("utf-8", errors="ignore").strip()
                if not message:
                    continue

                event_start = time.perf_counter()

                with clients_lock:
                    if client_socket in clients:
                        clients[client_socket]["last_activity"] = time.time()

                if len(message) > config["max_message_len"] and not message.startswith("/"):
                    send_line(client_socket, f"[ERROR] Message too long. Max {config['max_message_len']} characters.")
                    continue

                if message == "/logout":
                    send_line(client_socket, "SERVER|Logged out successfully.")
                    log_security("LOGOUT", username=username, ip=ip, detail="User logged out")
                    log_performance("LOGOUT", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note="User logged out")
                    break

                if message == "/list":
                    send_user_list()
                    log_performance("LIST", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note="User list refreshed")
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

                    if len(private_message) > config["max_message_len"]:
                        send_line(client_socket, f"[ERROR] Message too long. Max {config['max_message_len']} characters.")
                        continue

                    target_sock = None
                    with clients_lock:
                        for sock, info in clients.items():
                            if info["username"] == target:
                                target_sock = sock
                                break

                    if target_sock:
                        if send_line(target_sock, f"[PRIVATE] {username}: {private_message}"):
                            send_line(client_socket, f"[PRIVATE to {target}] {private_message}")
                            log_chat(username, target, "PRIVATE", private_message)
                            update_stats("PRIVATE")
                            log_performance("PRIVATE_MESSAGE", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note=f"to {target}")
                        else:
                            remove_client_socket(target_sock, reason="Private message delivery failed")
                            send_line(client_socket, f"[ERROR] User '{target}' is currently unavailable.")
                            log_performance("PRIVATE_MESSAGE_FAIL", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note=f"Delivery failed to {target}")
                    else:
                        send_line(client_socket, f"[ERROR] User '{target}' not online.")
                        log_performance("PRIVATE_MESSAGE_FAIL", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note=f"{target} not online")
                    continue

                if message.startswith("/"):
                    send_line(client_socket, "[ERROR] Unsupported command. Use /msg, /list, or /logout.")
                    log_performance("INVALID_COMMAND", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note=message[:50])
                    continue

                valid_msg, msg_error = validate_message(message)
                if not valid_msg:
                    send_line(client_socket, f"[ERROR] {msg_error}")
                    log_performance("INVALID_MESSAGE", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note=msg_error)
                    continue

                formatted = f"{username}: {message}"
                broadcast(formatted, exclude_sock=client_socket)
                send_line(client_socket, formatted)
                log_chat(username, "ALL", "BROADCAST", message)
                update_stats("BROADCAST")
                log_performance("BROADCAST", username=username, delay_ms=(time.perf_counter() - event_start) * 1000, note="Broadcast sent")

            except socket.timeout:
                with clients_lock:
                    last_activity = clients.get(client_socket, {}).get("last_activity", time.time())

                if time.time() - last_activity > config["session_timeout"]:
                    send_line(client_socket, "SERVER|Session timed out due to inactivity.")
                    log_security("SESSION_TIMEOUT", username=username, ip=ip, detail="Inactivity timeout")
                    log_performance("TIMEOUT", username=username, delay_ms=0.0, note="Inactivity timeout")
                    break
                continue

            except ConnectionResetError:
                log_security("CONNECTION_RESET", username=username or "-", ip=ip, detail="Peer reset connection")
                log_performance("CONNECTION_RESET", username=username or "-", delay_ms=0.0, note="Peer reset connection")
                break

    except Exception as e:
        if username:
            log_security("SERVER_ERROR", username=username, ip=ip, detail=str(e))
        else:
            log_security("SERVER_ERROR", username="-", ip=ip, detail=str(e))

    finally:
        remove_client_socket(client_socket, reason="Client handler stopped")


def cleanup_loop() -> None:
    while not shutdown_event.is_set():
        time.sleep(config["cleanup_interval"])
        stale = []
        now = time.time()

        with clients_lock:
            for sock, info in list(clients.items()):
                if now - info.get("last_activity", now) > config["session_timeout"]:
                    stale.append((sock, info.get("username", "-")))

        for sock, username in stale:
            log_security("SESSION_TIMEOUT", username=username, ip=clients.get(sock, {}).get("ip", "-"), detail="Cleanup loop timeout")
            log_performance("TIMEOUT", username=username, delay_ms=0.0, note="Cleanup loop timeout")
            try:
                send_line(sock, "SERVER|Session timed out due to inactivity.")
            except Exception:
                pass
            remove_client_socket(sock, reason="Cleanup loop timeout")


def start_server() -> None:
    global config
    config = load_config()
    ensure_files()
    users = load_users()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((config["bind_host"], int(config["server_port"])))
    server.listen(int(config["max_clients"]))
    server.settimeout(float(config["accept_timeout"]))

    print("=" * 68)
    print(" Secure TCP Multi-Client Chat Server (Assignment 8)")
    print("=" * 68)
    print(f"Listening on {config['bind_host']}:{config['server_port']}")
    print(f"Users file: {config['users_file']}")
    print(f"Security log: {config['security_log_file']}")
    print(f"Chat history: {config['chat_history_file']}")
    print(f"Performance results: {config['performance_results_file']}")
    print("=" * 68)

    log_performance("STARTUP", username="-", delay_ms=0.0, note="Server initialized")

    cleaner = threading.Thread(target=cleanup_loop, daemon=True)
    cleaner.start()

    try:
        while not shutdown_event.is_set():
            try:
                client_socket, address = server.accept()
            except socket.timeout:
                continue

            with clients_lock:
                current_clients = len(clients)

            if current_clients >= int(config["max_clients"]):
                try:
                    send_line(client_socket, "AUTH_FAIL|Server is busy. Please try again later.")
                except Exception:
                    pass
                try:
                    client_socket.close()
                except Exception:
                    pass
                log_security("REJECTED", username="-", ip=address[0], detail="Maximum client limit reached")
                continue

            thread = threading.Thread(
                target=handle_client,
                args=(client_socket, address, users),
                daemon=True,
            )
            thread.start()

    except KeyboardInterrupt:
        print("\nServer shutting down...")
    finally:
        shutdown_event.set()

        with clients_lock:
            sockets = list(clients.keys())

        for sock in sockets:
            remove_client_socket(sock, reason="Server shutdown")

        try:
            server.close()
        except Exception:
            pass


if __name__ == "__main__":
    start_server()
