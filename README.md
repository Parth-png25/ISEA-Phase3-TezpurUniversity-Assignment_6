# 🔒 Secure TCP Chat Application
### Assignment 7 – Secure Network Application Development Using TCP

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![TCP](https://img.shields.io/badge/Protocol-TCP-green.svg)
![GUI](https://img.shields.io/badge/GUI-Tkinter-orange.svg)
![Security](https://img.shields.io/badge/Security-SHA--256-red.svg)

## 👨‍💻 Student Information

**Name:** Parth Rawat  
**Roll Number:** 0126CY231042

---

# 📖 Project Overview

This project is an enhanced version of the multi-client TCP Chat Application developed in Assignment 6. The application has been upgraded by implementing practical security mechanisms such as user authentication, secure password storage, duplicate login prevention, input validation, failed login protection, session timeout, secure logging, and Wireshark verification.

---

# 🎯 Objectives

- Develop a secure multi-client TCP chat application.
- Implement authentication using username and password.
- Store passwords securely using SHA-256 hashing.
- Prevent duplicate logins.
- Validate user input.
- Protect against brute-force login attempts.
- Implement session timeout and secure logging.
- Verify communication using Wireshark.

---

# 🛠 Technologies Used

- Python 3
- Socket Programming
- Tkinter GUI
- Threading
- SHA-256 (hashlib)
- JSON / CSV
- Mininet
- Wireshark
- Linux (Ubuntu)

---

# ✨ Security Features

- ✅ User Authentication
- ✅ SHA-256 Password Hashing
- ✅ Duplicate Login Prevention
- ✅ Input Validation
- ✅ Failed Login Protection
- ✅ Session Timeout
- ✅ Logout Support
- ✅ Secure Logging
- ✅ Wireshark Verification

---

# 📂 Project Structure

```text
Assignment-7/
├── server.py
├── client_gui.py
├── users.json
├── security_log.txt
├── screenshots/
├── report.pdf
├── README.md
└── handwritten_reflection.pdf
```

---

# 🚀 How to Run

```bash
sudo mn --topo single,5
python3 server.py
python3 client_gui.py
```

---

# 📸 Screenshots

Place the following screenshots inside the `Screenshots` folder:

- Login_Window_Before_Connect.png
- Successful_Login_Online_Users.png
- Duplicate_Login_Prevention.png
- Invalid_Username_Login.png
- Invalid_Username_Password_Login.png
- Login_Lockout_After_Failed_Attempts.png
- Unsupported_Command_Error.png
- Authenticated_Chat_History.png
- Session_Timeout.png
- Wireshark_login_capture.png
- Wireshark_Failed_login.png
- Wireshark_Broadcast_Message.png
- Wireshark_Logout.png

---

# 📡 Wireshark Filter

```text
tcp.port == 5000
```

---

# 🧪 Testing Summary

| Test Case | Status |
|-----------|--------|
| Successful Login | ✅ |
| Invalid Username | ✅ |
| Wrong Password | ✅ |
| Duplicate Login | ✅ |
| Failed Login Lock | ✅ |
| Public Chat | ✅ |
| Private Chat | ✅ |
| Session Timeout | ✅ |
| Logout | ✅ |
| Wireshark Verification | ✅ |

---

# 📚 Learning Outcomes

- Authentication
- Password Hashing
- Secure TCP Communication
- Input Validation
- Session Management
- Secure Logging
- Wireshark Packet Analysis

---

# ✅ Conclusion

The application successfully integrates authentication, SHA-256 password hashing, duplicate login prevention, session timeout, input validation, secure logging, and Wireshark verification to provide a secure TCP chat system.

---

⭐ Developed for Assignment 7.
