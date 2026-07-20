# 🚀 TCP Chat Application -- Assignment 8

### Application Optimization, Scalability and Reliability

![Python](https://img.shields.io/badge/Python-3.x-blue.svg)
![Protocol](https://img.shields.io/badge/Protocol-TCP-green.svg)
![GUI](https://img.shields.io/badge/GUI-Tkinter-orange.svg)
![Scalability](https://img.shields.io/badge/Concurrent%20Clients-10-success.svg)
![Performance](https://img.shields.io/badge/Performance-Auto%20Logging-red.svg)

------------------------------------------------------------------------

## 👨‍💻 Student Information

  ---------------- -------------------
  **Name**         Parth Rawat
  **Roll No.**     0126CY231042
  ---------------- -------------------

------------------------------------------------------------------------

## 📖 Project Overview

This project is the enhanced version of the Secure TCP Chat Application
developed in Assignment 7. The focus of Assignment 8 is to improve
**connection management, reliability, scalability, configuration
management, and performance evaluation** while preserving the existing
TCP communication protocol.

------------------------------------------------------------------------

## 🎯 Assignment Objectives

-   Improve connection management
-   Automatic inactive client cleanup
-   Graceful shutdown
-   Automatic reconnection support
-   Support 10 concurrent clients
-   Configuration management using `config.json`
-   Automatic performance logging
-   Wireshark verification
-   Performance evaluation using graphs

------------------------------------------------------------------------

## ✨ Features

### 🔹 Connection Management

-   Automatic client cleanup
-   Duplicate login prevention
-   Session timeout
-   Online users management

### 🔹 Reliability

-   Graceful shutdown
-   Exception handling
-   Login validation
-   Account lockout protection

### 🔹 Scalability

-   Supports **10 concurrent clients**
-   Thread-safe client handling
-   Optimized socket management

### 🔹 Performance

-   Auto-generated `performance_results.csv`
-   Delay measurement
-   Throughput calculation
-   CPU usage logging
-   Memory usage logging
-   Graph generation

------------------------------------------------------------------------

## 🛠 Technologies Used

-   Python 3
-   Socket Programming
-   Tkinter
-   Threading
-   JSON
-   CSV
-   SHA-256
-   psutil
-   Wireshark
-   Mininet

------------------------------------------------------------------------

## 📂 Project Structure

``` text
Assignment-8/
│
├── server.py
├── client_gui.py
├── config.json
├── users.json
├── performance_results.csv
├── chat_history.csv
├── security_log.txt
├── graphs/
├── screenshots/
├── report.pdf
├── handwritten_reflection.pdf
└── README.md
```

------------------------------------------------------------------------

## 🚀 Getting Started

### Clone Repository

``` bash
git clone <repository-url>
cd Assignment-8
```

### Run Server

``` bash
python3 server.py
```

### Run Client

``` bash
python3 client_gui.py
```

------------------------------------------------------------------------

## 📊 Performance Evaluation

   Concurrent Clients   Status
  -------------------- --------
           5              ✅
           8              ✅
           10             ✅

### Metrics Collected

-   Average Delay
-   Throughput
-   CPU Usage
-   Memory Usage

## 📊 Performance Graphs

### Average Delay vs Concurrent Clients
![Average Delay](Graphs/average_delay_ms.png)

### Throughput vs Concurrent Clients
![Throughput](Graphs/throughput_msg_per_sec.png)

### CPU Usage vs Concurrent Clients
![CPU Usage](Graphs/cpu_usage_percent.png)

### Memory Usage vs Concurrent Clients
![Memory Usage](Graphs/memory_usage_mb.png)
------------------------------------------------------------------------

## 📸 Screenshots

### Successful Login
![Successful Login](Screenshots/Successful_login.png)

### Authenticated Chat
![Authenticated Chat](Screenshots/Authenticated_chat.png)

### Duplicate Login Blocked
![Duplicate Login](Screenshots/Duplicate_login_blocked.png)

### Wrong Password
![Wrong Password](Screenshots/Wrong_password_username.png)

### Password Too Short
![Password Too Short](Screenshots/Password_too_short.png)

### Account Lockout
![Account Lockout](Screenshots/Too_many_failed_attempts.png)

### Session Timeout
![Session Timeout](Screenshots/Session_Timeout.png)

### Logout
![Logout](Screenshots/Logged_out_disconnect.png)

### Wireshark Login Success
![Wireshark Login](Screenshots/Wireshark_login_successful.png)

### Wireshark Authenticated Chat
![Wireshark Chat](Screenshots/Wireshark_Authenticated_chat.png)

### Wireshark Failed Login
![Wireshark Failed Login](Screenshots/Wireshark_failed_login_traffic.png)

### Wireshark Logout
![Wireshark Logout](Screenshots/Wireshark_logout_timeout_traffic.png)

------------------------------------------------------------------------

## 📡 Wireshark Filter

``` text
tcp.port == 5000
```

------------------------------------------------------------------------

## ✅ Testing Summary

  Test Case                   Status
  -------------------------- --------
  Login Authentication          ✅
  Duplicate Login               ✅
  Session Timeout               ✅
  Private Chat                  ✅
  Broadcast Chat                ✅
  Auto Performance Logging      ✅
  10 Concurrent Clients         ✅
  Wireshark Verification        ✅

------------------------------------------------------------------------

## 📚 Learning Outcomes

-   Connection Management
-   Reliability Enhancement
-   Scalability Improvement
-   Configuration Management
-   Performance Evaluation
-   TCP Socket Programming
-   Wireshark Packet Analysis

------------------------------------------------------------------------

## ✅ Conclusion

This project successfully enhances the previous TCP-based multi-client
chat application by improving connection management, reliability,
scalability, and performance monitoring. It supports up to 10 concurrent
clients, uses configurable settings through `config.json`, automatically
generates performance logs, and verifies TCP communication using
Wireshark. The implementation demonstrates a stable, maintainable, and
optimized client-server application suitable for the Assignment 8
objectives.

------------------------------------------------------------------------

⭐ **Developed by Parth Rawat**
