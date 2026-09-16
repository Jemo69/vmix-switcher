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
    initial_config = dict(config_manager.get())
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

        # 13. Test Merge transition in Direct mode
        status, res = req(f"{base}/api/vmix/switch", "POST", {"input": 3, "transition": "Merge", "duration": 500}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res["active"] == 3, f"Expected active 3 with Merge, got {res['active']}"
        print("✓ Direct mode Merge transition verified")

        # 14. Test Network info endpoint
        status, res = req(f"{base}/api/system/network", "GET", token=token)
        assert status == 200 and "ips" in res
        assert not any("http://ip:" in u for u in res["ips"]), f"Malformed IP found: {res['ips']}"
        print("✓ Network IP endpoints validated (no malformed candidate strings)")

        # 14. Test StartStopRecording & StartStopExternal & StartStopStreaming
        status, res = req(f"{base}/api/vmix/function", "POST", {"function": "StartStopRecording"}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res.get("recording") is True, f"Expected recording True, got {res.get('recording')}"
        print("✓ StartStopRecording toggle ON verified")

        status, res = req(f"{base}/api/vmix/function", "POST", {"function": "StartStopExternal"}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res.get("external") is True, f"Expected external True, got {res.get('external')}"
        print("✓ StartStopExternal toggle ON verified")

        status, res = req(f"{base}/api/vmix/function", "POST", {"function": "StartStopStreaming"}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert res.get("streaming") is True, f"Expected streaming True, got {res.get('streaming')}"
        print("✓ StartStopStreaming toggle ON verified")

        # 15. Test Audio Volume Endpoint & State
        status, res = req(f"{base}/api/vmix/volume", "POST", {"input": 7, "volume": 65}, token=token)
        assert status == 200 and res.get("success") is True
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        inp7 = next(i for i in res["allInputs"] if i["number"] == 7)
        assert inp7.get("volume") == 65.0, f"Expected volume 65.0, got {inp7.get('volume')}"
        print("✓ Microphone / Audio volume fader endpoint verified (set to 65%)")

        # 16. Test Dynamic Active and Preview Thumbnails
        for target in ["active", "preview", "0"]:
            req_dyn = urllib.request.Request(f"{base}/api/vmix/thumbnail/{target}?token={token}")
            with urllib.request.urlopen(req_dyn, timeout=3.0) as resp:
                assert resp.status == 200
                data = resp.read()
                assert len(data) > 0
        print("✓ Dynamic Program and Preview monitor thumbnail proxy verified")

        # 17. Test Priority & Frame Rate Config Update (30/60 fps fast tier, 1.5 bgFps eco, maxPriority 20)
        status, res = req(f"{base}/api/config", "PUT", {
            "previewFps": 30.0,
            "backgroundFps": 1.5,
            "maxPriorityInputs": 20
        }, token=token)
        assert status == 200 and res.get("success") is True
        cfg = res.get("config", {})
        assert cfg.get("previewFps") == 30.0, f"Expected previewFps 30.0, got {cfg.get('previewFps')}"
        assert cfg.get("backgroundFps") == 1.5, f"Expected backgroundFps 1.5, got {cfg.get('backgroundFps')}"
        assert cfg.get("maxPriorityInputs") == 20, f"Expected maxPriorityInputs 20, got {cfg.get('maxPriorityInputs')}"
        print("✓ Frame rate config update (30 fps fast tier, 1.5 fps eco tier, 20 max priority) verified")

        # Verify 60 fps scales up
        status, res = req(f"{base}/api/config", "PUT", {"previewFps": 60.0}, token=token)
        assert status == 200
        assert res.get("config", {}).get("previewFps") == 60.0
        print("✓ Frame rate scaling up to 60 fps verified")

        # 18. Test Priority Source Toggle (fast tier membership)
        status, res = req(f"{base}/api/sources/priority", "POST", {"input": 3, "priority": True}, token=token)
        assert status == 200 and res.get("success") is True
        assert "3" in res.get("priorityInputs", [])
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        inp3 = next(i for i in res["allInputs"] if i["number"] == 3)
        assert inp3.get("isPriority") is True, "Input 3 must have isPriority True"
        assert "3" in res.get("priorityInputs", [])
        print("✓ Source priority toggle (input 3 -> fast tier) verified in state")

        # 19. Test Priority Quota Enforcement (cap of maxPriorityInputs)
        # Set maxPriorityInputs to 2 to test the cap
        req(f"{base}/api/config", "PUT", {"maxPriorityInputs": 2}, token=token)
        # Input 3 is already priority. Add input 4 -> 2 inputs (cap reached).
        status, res = req(f"{base}/api/sources/priority", "POST", {"input": 4, "priority": True}, token=token)
        assert status == 200
        # Attempt to add input 5 -> should fail with 409 Conflict
        status, res = req(f"{base}/api/sources/priority", "POST", {"input": 5, "priority": True}, token=token)
        assert status == 409, f"Expected 409 Conflict when exceeding priority quota, got {status}"
        assert "Priority list is full" in res.get("detail", "")
        print("✓ Priority quota cap enforced (409 Conflict when exceeding max inputs)")

        # Restore maxPriorityInputs to 20
        req(f"{base}/api/config", "PUT", {"maxPriorityInputs": 20}, token=token)

        # 20. Test Auto-pick Priority (picks up to maxPriorityInputs live sources)
        status, res = req(f"{base}/api/sources/auto-priority", "POST", {}, token=token)
        assert status == 200 and res.get("success") is True
        assert len(res.get("priorityInputs", [])) > 0
        assert len(res.get("priorityInputs", [])) <= 20
        print(f"✓ Auto-pick priority verified (selected {len(res['priorityInputs'])} priority inputs)")

        # 21. Test Clear Priority (returns all inputs to eco pull)
        status, res = req(f"{base}/api/sources/clear-priority", "POST", {}, token=token)
        assert status == 200 and res.get("success") is True
        assert len(res.get("priorityInputs", [])) == 0
        time.sleep(0.2)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert len(res.get("priorityInputs", [])) == 0
        assert not any(i.get("isPriority") for i in res["allInputs"]), "No inputs should be priority after clear"
        print("✓ Clear priority verified (all inputs return to eco pull)")

        # 22. Test Thumbnail Conditional 304 Revalidation with ETag
        thumb_req = urllib.request.Request(f"{base}/api/vmix/thumbnail/1?token={token}")
        with urllib.request.urlopen(thumb_req, timeout=3.0) as resp:
            assert resp.status == 200
            etag = resp.headers.get("ETag")
            assert etag is not None, "Thumbnail response should include ETag"

        reval_req = urllib.request.Request(f"{base}/api/vmix/thumbnail/1?token={token}", headers={"If-None-Match": etag})
        try:
            with urllib.request.urlopen(reval_req, timeout=3.0) as resp:
                assert resp.status == 304
        except urllib.error.HTTPError as err:
            assert err.code == 304, f"Expected 304 Not Modified, got {err.code}"
        print("✓ Thumbnail conditional 304 revalidation (ETag / If-None-Match) verified")

        # 23. Test Multipart MJPEG Stream Endpoint
        stream_url = f"{base}/api/vmix/stream/1.mjpg?token={token}"
        req_stream = urllib.request.Request(stream_url)
        with urllib.request.urlopen(req_stream, timeout=3.0) as resp:
            assert resp.status == 200
            content_type = resp.headers.get("Content-Type", "")
            assert "multipart/x-mixed-replace" in content_type, f"Expected multipart/x-mixed-replace, got {content_type}"
            chunk = resp.read(2048)
            assert len(chunk) > 0
            assert b"--frame" in chunk
        print("✓ Tier 2 multipart MJPEG stream endpoint verified")

        # 17. Priority tier: toggle, state flag, venue cap, rate settings
        status, res = req(f"{base}/api/sources/priority", "POST", {"input": 2, "priority": True}, token=token)
        assert status == 200 and "2" in res.get("priorityInputs", []), f"Priority pick failed: {res}"
        print("✓ Input 2 starred into priority tier")
        time.sleep(0.4)
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        inp2 = next(i for i in res["allInputs"] if i["number"] == 2)
        assert inp2.get("isPriority") is True, "Expected isPriority True on input 2"
        assert "2" in res.get("priorityInputs", []), "Expected state to carry priorityInputs"
        assert "backgroundFps" in res and "maxPriorityInputs" in res, "Expected tier settings in state"
        print("✓ Priority flag + tier settings visible in state")

        # Venue cap: shrink to 2, fill, third pick must 409
        status, res = req(f"{base}/api/config", "PUT", {"maxPriorityInputs": 2}, token=token)
        assert status == 200 and res["config"]["maxPriorityInputs"] == 2
        status, res = req(f"{base}/api/sources/priority", "POST", {"input": 3, "priority": True}, token=token)
        assert status == 200
        status, res = req(f"{base}/api/sources/priority", "POST", {"input": 4, "priority": True}, token=token)
        assert status == 409, f"Expected 409 over venue cap, got {status}: {res}"
        print("✓ Venue priority cap enforced (409 over max)")
        # Cleanup picks for later runs
        for n in (2, 3):
            req(f"{base}/api/sources/priority", "POST", {"input": n, "priority": False}, token=token)
        req(f"{base}/api/config", "PUT", {"maxPriorityInputs": 20}, token=token)

        # Rate settings round-trip + clamps (30/60 high end, 1.5 low end)
        status, res = req(f"{base}/api/config", "PUT", {"previewFps": 60, "backgroundFps": 1.5}, token=token)
        assert status == 200 and res["config"]["previewFps"] == 60.0 and res["config"]["backgroundFps"] == 1.5
        status, res = req(f"{base}/api/config", "PUT", {"previewFps": 999, "backgroundFps": 0}, token=token)
        assert res["config"]["previewFps"] == 60.0 and res["config"]["backgroundFps"] == 0.1, res["config"]
        print("✓ Pull-rate settings round-trip with clamps (0.5–60 priority, 0.1–5 eco)")

        print("\nALL PYTHON INTEGRATION TESTS PASSED! 🎉")
    finally:
        config_manager.config = initial_config
        config_manager.save()

if __name__ == "__main__":
    test_all()
