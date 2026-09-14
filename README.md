# 🎬 vMix Web Switcher (Python)

A modern, high-contrast, responsive web switcher for **vMix live video production software** — powered by **Python (FastAPI + WebSockets)**. Control your live show from phones, tablets (iPad/Android), laptops, and touchscreens on your local network.

- 🔴 **Live Visual Video Monitors**: Real-time Program (Red) and Preview (Green) video feeds right on the switcher bar
- ⚡ **Dual Switching Modes**: One-tap toggle between **Direct Switch** (instant to Program) and **Preview + Take** (stage first, CUT/AUTO)
- 🔴 **Interactive Broadcast Controls**: Clickable **REC** (with live timer), **STREAM**, **EXT** (External output), and **FULLSCREEN**
- 🎤 **Dedicated Mic & Audio Console**: Tactical Mute/Live toggles, volume fader sliders (0-100%), and animated VU peak meters
- 🖥️ **Big Screen Preview (Multiviewer)**: Fullscreen-ready production multiviewer with giant twin 16:9 displays, live clock, and multi-camera grid
- 👁️ Hide auxiliary inputs (audio, overlays, test patterns) without touching vMix
- 📱 Touch-optimized with haptics + click sounds, ⌨️ shortcuts (`1`–`9`, `Space`, `Enter`)
- 🔄 Real-time sync across all crew devices via WebSocket
- 📡 Offline Simulator mode for rehearsal without vMix

---

## ✅ Pick your path (30 seconds)

| Who you are | What to do |
|---|---|
| **Non-technical (easiest — no Python)** | Download the ready-made app from [**Releases**](https://github.com/Jemo69/vmix-switcher/releases) → double-click → done. See [Option A](#option-a--easiest-download-the-ready-made-app-no-python-needed-recommended-for-non-technical-users). |
| **Semi-technical (have Python)** | Double-click **`start.bat`** (Windows) or run **`./start.sh`** (macOS/Linux). See [Option B](#option-b--one-click-script-needs-python-once). |
| **Technical / developer** | Clone, `pip install`, `python run.py`. See [Option C](#option-c--technical-manual-install). |

> **First: enable vMix Web Controller** (all options need this once):
> 1. Open **vMix** → **Settings** (gear, top right) → **Web Controller** → check **Enabled**.
> 2. Note the port (default `8088`).

---

## Option A — Easiest: download the ready-made app (no Python needed) ⭐ Recommended for non-technical users

1. Go to [**Releases**](https://github.com/Jemo69/vmix-switcher/releases) and download the file for your computer:
   - Windows → `vmix-switcher-windows.exe`
   - macOS → `vmix-switcher-macos`
   - Linux → `vmix-switcher-linux`
2. Run it:
   - **Windows:** double-click the `.exe`. If SmartScreen warns, click *More info → Run anyway* (it's your own unsigned build).
   - **macOS:** first time only — right-click the file → **Open** → **Open** (this bypasses Gatekeeper for unsigned apps). If blocked: *System Settings → Privacy & Security → Open Anyway*. You may need `chmod +x vmix-switcher-macos` if downloaded via browser.
   - **Linux:** `chmod +x vmix-switcher-linux && ./vmix-switcher-linux`
3. A black window opens showing your URLs, e.g.:
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
4. **Keep that window open** while switching. Open `http://localhost:3000` on the vMix PC, or the `http://192.168.x.x:3000` address on crew phones/tablets (same Wi-Fi). Password: `vmix`.

> 💡 **Updating:** download the new Release file and replace the old one. Your settings live in `config.json` *next to* the app, so they survive updates.

---

## Option B — One-click script (needs Python once)

Good when Releases aren't built yet, or you want the latest source.

**Prerequisite (once):** install [Python 3.11+](https://www.python.org/downloads/) and ✅ check **"Add python.exe to PATH"** on Windows.

- **Windows:** double-click **`start.bat`**. It installs dependencies, opens your browser, and starts the server.
- **macOS / Linux:** open a terminal in this folder, then:
  ```bash
  chmod +x start.sh
  ./start.sh
  ```

Then open `http://localhost:3000` (PC) or the network URL shown in the console (phones/tablets). Password: `vmix`.

---

## Option C — Technical: manual install

```bash
git clone https://github.com/Jemo69/vmix-switcher.git
cd vmix-switcher
pip install -r requirements.txt
python run.py        # or: python3 run.py
```

Open `http://localhost:3000`. Run tests with:

```bash
python -m pytest test/ -v
# or: python test/test_python_switcher.py
```

---

## 📲 Connect crew devices (all options)

1. Connect phones/tablets to the **same Wi-Fi** as the vMix computer.
2. In their browser, enter the network URL from the console (e.g. `http://192.168.1.50:3000`).
3. Enter password (default `vmix`, changeable in Settings ⚙️).

> 🧱 **Windows Firewall on first run?** Click *Allow access* so tablets/phones can reach the app. If devices can't connect, verify: same Wi-Fi (not guest network), firewall allows port `3000`, and no VPN is isolating the PC.

---

## 🎛️ App Modes & How to use

The switcher features 3 dedicated operational modes accessible via the top tab bar:

### 1. 🎬 Video Switcher Mode
- **Live Video Monitors:** View real-time Program & Preview feeds at the top of the console.
- **Direct Switch vs Preview + Take:** Switch between instant switching or traditional preview staging directly via the mode pills.
- **Quick Transitions:** Instant **CUT**, **AUTO** with selectable transition types (`Fade`, `Zoom`, `Wipe`, `Slide`, `Fly`, `CrossZoom`, `Trans 1/2`), plus **FTB** and **QuickPlay**.
- **Interactive Broadcast Badges:**
  - **REC:** Tap to start/stop recording with live timer display.
  - **STREAM:** Tap to start/stop streaming.
  - **EXT:** Tap to activate/deactivate external output.
  - **FULLSCREEN:** Tap to expand the switcher to edge-to-edge fullscreen.

### 2. 🎤 Mic & Audio Console Mode
- **Tactile Mute/Live Toggles:** Instantly mute or take microphone/audio channels live on air.
- **Fader Sliders:** Smooth 0–100% volume adjustment with real-time feedback.
- **Signal Peak VU Meters:** Live animated level meters indicating audio activity.
- **Master Actions:** Quick **Mute All Mics** and **Unmute All** buttons.

### 3. 🖥️ Big Screen Preview (Multiviewer) Mode
- **Giant Twin Displays:** Large-format 16:9 side-by-side Program (Red) & Preview (Green) video monitors.
- **Production Clock:** Live high-visibility production studio clock.
- **Multi-Camera Grid:** Multiview camera layout with red/green tally borders; tap any camera to switch or stage.
- **Dedicated Fullscreen:** One-click expansion for secondary monitors or multiviewer displays.

- **Direct Switch (default):** tap a source → it transitions straight to Program output.
- **Change transition:** dropdown at top center (`Fade`, `Cut`, `Zoom`, `Wipe`, `Slide`, `Fly`, `CrossZoom`, `Transition 1/2` + duration).
- **Preview + Take mode:** Settings ⚙️ → *Switcher Action* → stage in Preview, then **CUT** / **AUTO**.
- **Hide sources:** *Manage Sources* → toggle off *Display on Switcher* (e.g. audio, color bars). Optional **Display Nickname** per input.
- **Settings ⚙️:** switcher mode, default transition + duration, vMix host/port, password, poll interval, **Live Preview Refresh Rate** (1–10 fps), **Offline Simulator Mode** (rehearse without vMix).

---

## 🔧 Configuration

Settings persist in `config.json`:
- Source/script runs → `<repo>/config.json`
- Standalone exe/app → `config.json` **next to the executable**

| Key | Default | Meaning |
|---|---|---|
| `port` | `3000` | Web UI port |
| `password` | `vmix` | Crew login |
| `vmixHost` / `vmixPort` | `127.0.0.1` / `8088` | Where vMix Web Controller lives |
| `defaultTransition` / `transitionDuration` | `Fade` / `500` | Transition + ms |
| `switcherMode` | `direct` | `direct` or `preview_take` |
| `previewFps` | `4` | Live preview snapshot refresh rate (0.5–10 fps). Higher = smoother previews, more load on the vMix PC |
| `mockMode` | `false` | Simulator when vMix is offline |

---

## 📦 Build the executable yourself

You don't need this if you downloaded from Releases — this is for maintainers/developers.

```bash
pip install -r requirements.txt -r requirements-build.txt
python build_exe.py
# Output: dist/vmix-switcher-windows.exe  (or -macos / -linux on those OSes)
```

Flags: `--onedir` (folder build, faster startup) · `--debug` (verbose logs).

### 🚀 Publish a new Release (maintainer, 2 commands)

Binaries build automatically via GitHub Actions when you push a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Then check the **Actions** tab → **Build Release Binaries** → once green, the files appear under **Releases** for the crew to download. You can also trigger a test build anytime from *Actions → Run workflow* without tagging.

---

## ❓ Troubleshooting / FAQ

| Problem | Fix |
|---|---|
| `Python is not installed` (start.bat/sh) | Install Python 3.11+ from python.org; on Windows re-install with **Add to PATH** checked. |
| Port `3000` already in use | Close the other copy, or edit `port` in `config.json` and restart. |
| Phones can't reach the page | Same Wi-Fi? Firewall allowed? Right IP from console? No client-isolation/guest Wi-Fi? |
| `Can't connect to vMix` in UI | vMix open? Web Controller enabled on port `8088`? `vmixHost` correct in Settings? Try Simulator Mode to confirm the app itself works. |
| macOS says app is damaged / can't open | Right-click → Open (once), or *Privacy & Security → Open Anyway*. |
| SmartScreen warning (Windows exe) | *More info → Run anyway*. Expected for unsigned self-builds. |
| Want a fresh password/secret | Settings ⚙️ → change password (min 3 chars). |

---

## 📁 Project structure

```
vmix-switcher/
├── config.json              # Persistent settings (created/updated on first run)
├── requirements.txt         # Runtime deps (fastapi, uvicorn, websockets)
├── requirements-build.txt   # Build-only dep (pyinstaller)
├── run.py                   # Entry point (dev + PyInstaller target)
├── server.py                # FastAPI REST API + WebSocket tally broadcaster
├── build_exe.py             # Cross-platform PyInstaller build (win/mac/linux)
├── start.bat                # Windows one-click launcher
├── start.sh                 # macOS/Linux one-click launcher
├── .github/workflows/build-release.yml  # Auto-builds exe/app on version tags
├── vmix/
│   ├── __init__.py
│   ├── config.py            # Settings persistence (exe-aware path)
│   ├── mock.py              # Offline broadcast simulator
│   └── client.py            # vMix HTTP XML API poller & switching engine
├── public/
│   ├── index.html           # Responsive broadcast UI
│   ├── css/style.css
│   └── js/ (api.js, app.js)
└── test/
    └── test_python_switcher.py
```

## 🤝 Contributing

PRs welcome — open an issue first for big changes. Keep the non-technical path working: if you touch startup/config, verify both `python run.py` **and** the PyInstaller binary still boot and serve `public/`.
