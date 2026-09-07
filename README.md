# 🎬 vMix Web Switcher (Python)

A modern, high-contrast, responsive web switcher for **vMix live video production software** powered by **Python (FastAPI & WebSockets)**. Designed for smartphones, tablets (iPads/Android), laptops, and touchscreens across your local network.

---

## ✨ Features

- 🔴 **Instant Numbered Source Buttons**: Clean, responsive tactile buttons for each numbered source with live tally status (Red for Program/Live, Green for Preview).
- ⚡ **Direct Transition to Main Output**: When a source button is pressed, it automatically transitions directly to the main display / Program output using your configured default transition (e.g., Fade 500ms, Cut, Zoom, Wipe, Transition 1–4).
- 👁️ **App-Side Source Ignore / Filtering**: Easily hide/ignore auxiliary or background inputs (audio buses, lower thirds, test patterns, overlays) from the switcher interface without modifying or deleting anything in vMix!
- 🔒 **Password Protected**: Network security ensures only authorized operators on the local network can access and switch.
- 📱 **Mobile & Tablet Optimized**: Low-latency touch buttons with haptic vibration feedback, studio sound clicks, and adaptive layouts.
- 🔄 **Real-Time Tallies via WebSocket**: Instant sub-50ms synchronization across all connected crew devices simultaneously.
- ⌨️ **Keyboard Shortcuts**: Use keys `1`–`9` to switch sources, `Space` for Auto/Fade transition, and `Enter` for Cut.
- 🎛️ **Dual Switching Modes**:
  - **Direct Switch Mode (Default)**: Pressing an input immediately transitions it to the main display.
  - **Preview + Take Mode**: Traditional broadcast mode staging the source in Preview first, then using CUT or AUTO.
- 📡 **Offline Simulator / Demo Mode**: Built-in vMix simulator allowing full testing of transitions, tallies, and source filtering even when vMix is not running!

---

## 🚀 Quick Start

### Prerequisites
- [Python 3.9+](https://www.python.org/)
- [vMix](https://www.vmix.com/) (running on Windows).

### 1. Enable Web Controller in vMix
1. Open **vMix** on your computer.
2. Go to **Settings** (top right gear icon) > **Web Controller**.
3. Check **Enabled**.
4. Note the port (default is `8088`).

### 2. Start the Switcher

#### On Windows (vMix PC):
- Double-click **`start.bat`**, or run in Command Prompt:
  ```cmd
  pip install -r requirements.txt
  python run.py
  ```

#### On Linux / macOS:
- Run:
  ```bash
  chmod +x start.sh
  ./start.sh
  ```
  or:
  ```bash
  pip install -r requirements.txt
  python3 run.py
  ```

Once started, the console displays:
```text
=============================================================
       🎬 vMix Web Switcher (Python) is Running!             
=============================================================
 Local Computer URL:   http://localhost:3000
 Network Device Access (Tablets, Phones, Laptops):
   👉 http://192.168.1.50:3000  (Wi-Fi / Ethernet)
-------------------------------------------------------------
 Default Password:     vmix
 Targeting vMix at:    http://127.0.0.1:8088
 Default Transition:   Fade (500ms)
=============================================================
```

### 3. Connect from Phones / Tablets / Laptops
1. Connect your phone or tablet to the **same Wi-Fi network** as the vMix computer.
2. Open a web browser (Safari, Chrome, etc.) and enter the network URL (e.g., `http://192.168.1.50:3000`).
3. Enter the password:
   - **Default Password:** `vmix`

---

## 🎛️ How to Use

### Switching Sources
- **Direct Switch**: Tap any source button to transition that input directly to the Program output.
- **Change Default Transition**: Use the transition dropdown at the top center to choose between `Fade`, `Cut`, `Zoom`, `Wipe`, `Slide`, `Fly`, `CrossZoom`, `Transition 1`, or `Transition 2`.
- **Manual Cut & Auto**: Use the dedicated **CUT** and **AUTO** buttons for immediate transitions between Preview and Program.

### Ignoring Sources (App-Side Hiding)
1. Click **Manage Sources** in the top navigation bar.
2. You will see a list of all inputs detected from vMix.
3. Toggle off **Display on Switcher** for any source you want to hide (e.g., audio inputs, color bars, or background graphics).
4. Optionally enter a custom **Display Nickname** to give inputs clear labels on your switcher buttons without altering presets in vMix.
5. Ignored sources are saved on the app server and instantly hidden from all connected switcher devices.

### Settings & Customization
Click the **Settings** gear icon in the top header to configure:
- **Switcher Action**: Switch between *Direct to Program* and *Preview + Take*.
- **Default Transition & Duration**: Adjust transition speed (e.g. 250ms, 500ms, 1000ms).
- **Target vMix Host & Port**: Connect to vMix on `127.0.0.1:8088` or a remote vMix machine on your LAN.
- **Change Password**: Set a new access password for crew members.
- **Offline Simulator Mode**: Turn on mock mode to test inputs and switching without vMix open.

---

## 📁 Python Project Architecture

```
vmix-swicther/
├── config.json              # Persistent settings (password, ignored inputs, transitions)
├── requirements.txt         # Python dependencies (fastapi, uvicorn, websockets)
├── run.py                   # Python entry point launcher with auto-dependency check
├── server.py                # FastAPI REST API + WebSocket real-time tally broadcaster
├── start.bat                # Windows one-click launcher
├── start.sh                 # Linux/macOS launcher
├── vmix/
│   ├── __init__.py
│   ├── config.py            # Settings persistence & token generator
│   ├── mock.py              # Offline broadcast simulator
│   └── client.py            # vMix HTTP XML API poller & switching engine
├── public/
│   ├── index.html           # Responsive broadcast UI
│   ├── css/
│   │   └── style.css        # Broadcast dark theme & tally styling
│   └── js/
│       ├── api.js           # Client-side API wrapper & auth management
│       └── app.js           # Switcher controller, WebSocket client & haptics
└── test/
    └── test_python_switcher.py # Python integration test suite
```
