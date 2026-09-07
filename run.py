#!/usr/bin/env python3
import sys
import subprocess

def check_dependencies():
    missing = []
    for pkg in ["fastapi", "uvicorn", "websockets"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)}...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])

if __name__ == "__main__":
    check_dependencies()
    import uvicorn
    from vmix.config import config_manager
    from server import app, get_network_ips

    cfg = config_manager.get()
    port = cfg.get("port", 3000)

    print("\n=============================================================")
    print("       🎬 vMix Web Switcher (Python) is Running!             ")
    print("=============================================================")
    print(f" Local Computer URL:   http://localhost:{port}")
    ips = get_network_ips(port)
    if ips:
        print(" Network Device Access (Tablets, Phones, Laptops):")
        for u in ips:
            print(f"   👉 {u}")
    print("-------------------------------------------------------------")
    print(f" Default Password:     {cfg.get('password', 'vmix')}")
    print(f" Targeting vMix at:    http://{cfg.get('vmixHost', '127.0.0.1')}:{cfg.get('vmixPort', 8088)}")
    print(f" Default Transition:   {cfg.get('defaultTransition', 'Fade')} ({cfg.get('transitionDuration', 500)}ms)")
    print("=============================================================\n")

    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
