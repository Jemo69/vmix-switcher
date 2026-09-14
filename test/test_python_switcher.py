import json
import time
import urllib.request
import urllib.error
import threading
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from vmix.config import config_manager
from server import app

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=3006, log_level="error")

def req(url, method="GET", data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3.0) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as err:
        content = err.read().decode("utf-8")
        return err.code, json.loads(content) if content else {}

def test_all():
    print("Starting Python vMix Switcher test suite...")
    initial_config = config_manager.get()
    try:
        config_manager.update({"mockMode": True, "password": "testpythonpwd", "port": 3006, "ignoredInputs": []})

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(1.0)

        base = "http://127.0.0.1:3006"

        # 1. Bad login
        status, res = req(f"{base}/api/auth/login", "POST", {"password": "bad"})
        assert status == 401, f"Expected 401, got {status}"
        print("✓ Bad login rejected with 401")

        # 2. Good login
        status, res = req(f"{base}/api/auth/login", "POST", {"password": "testpythonpwd"})
        assert status == 200 and "token" in res, f"Expected 200 with token, got {res}"
        token = res["token"]
        print("✓ Good login successful, token received")

        # 3. Check auth
        status, res = req(f"{base}/api/auth/check", "GET", token=token)
        assert status == 200 and res.get("authenticated") is True
        print("✓ Token authenticated successfully")

        # 4. State
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert status == 200
        assert len(res["inputs"]) == 8, f"Expected 8 inputs, got {len(res['inputs'])}"
        print("✓ Switcher state retrieved with 8 inputs")

        # 5. Switch input with transition
        status, res = req(f"{base}/api/vmix/switch", "POST", {"input": 4, "transition": "Fade", "duration": 500}, token=token)
        assert status == 200 and res.get("success") is True
        print("✓ Switched input 4 with Fade")

        # Verify active is 4
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res["active"] == 4, f"Expected active 4, got {res['active']}"
        print("✓ Active Program input verified as 4")

        # 6. Ignore source on app side
        status, res = req(f"{base}/api/sources/ignore", "POST", {"input": 7, "ignore": True}, token=token)
        assert status == 200
        assert "7" in res.get("ignoredInputs", [])
        print("✓ Input 7 ignored on app side")

        # Verify visible inputs vs all inputs
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert len(res["visibleInputs"]) == 7, f"Expected 7 visible, got {len(res['visibleInputs'])}"
        assert not any(i["number"] == 7 for i in res["visibleInputs"]), "Input 7 must NOT be in visibleInputs"
        assert any(i["number"] == 7 for i in res["allInputs"]), "Input 7 MUST still be in allInputs (vMix unharmed)"
        print("✓ Verified app-side ignore: hidden from switcher, untouched in vMix!")

        # 7. Test Thumbnail endpoint
        thumb_url = f"{base}/api/vmix/thumbnail/1?token={token}"
        req_thumb = urllib.request.Request(thumb_url)
        with urllib.request.urlopen(req_thumb, timeout=3.0) as resp:
            assert resp.status == 200, f"Expected 200 for thumbnail, got {resp.status}"
            data = resp.read()
            assert len(data) > 0, "Thumbnail data must not be empty"
            print("✓ Live Thumbnail proxy endpoint verified (returns valid image data)")

        # 8. Test Overlay endpoint
        status, res = req(f"{base}/api/vmix/overlay", "POST", {"overlay": 1, "input": 6}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        inp6 = next(i for i in res["allInputs"] if i["number"] == 6)
        assert 1 in inp6.get("activeOverlays", []), f"Expected overlay 1 on input 6, got {inp6.get('activeOverlays')}"
        print("✓ Overlay 1 toggle and activeOverlays state verified")

        # 9. Test Audio mute endpoint
        status, res = req(f"{base}/api/vmix/audio", "POST", {"input": 1}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        inp1 = next(i for i in res["allInputs"] if i["number"] == 1)
        assert inp1.get("muted") is True, f"Expected input 1 to be muted, got {inp1.get('muted')}"
        print("✓ Audio toggle and mute state verified")

        # 10. Test FTB (Fade to Black)
        status, res = req(f"{base}/api/vmix/function", "POST", {"function": "FadeToBlack"}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res.get("fadeToBlack") is True, "Expected fadeToBlack to be True"
        print("✓ Fade to Black toggle ON verified")

        status, res = req(f"{base}/api/vmix/function", "POST", {"function": "FadeToBlack"}, token=token)
        assert status == 200
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res.get("fadeToBlack") is False, "Expected fadeToBlack to be False"
        print("✓ Fade to Black toggle OFF verified")

        # 11. Test already-active protection in Direct mode
        status, res = req(f"{base}/api/vmix/switch", "POST", {"input": 4}, token=token)
        assert status == 200
        assert res.get("result", {}).get("message") == "Input is already active on Program"
        print("✓ Already-active protection verified (prevents accidental camera swap)")

        # 12. Test Transition1 in Direct mode
        status, res = req(f"{base}/api/vmix/switch", "POST", {"input": 2, "transition": "Transition1"}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res["active"] == 2, f"Expected active 2 with Transition1, got {res['active']}"
        print("✓ Direct mode Transition1 staging and execution verified")

        # 13. Test Network info endpoint
        status, res = req(f"{base}/api/system/network", "GET", token=token)
        assert status == 200 and "ips" in res
        assert not any("http://ip:" in u for u in res["ips"]), f"Malformed IP found: {res['ips']}"
        print("✓ Network IP endpoints validated (no malformed candidate strings)")

        print("\nALL PYTHON INTEGRATION TESTS PASSED! 🎉")
    finally:
        config_manager.config = initial_config
        config_manager.save()

if __name__ == "__main__":
    test_all()
