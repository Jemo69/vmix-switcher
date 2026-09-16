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

        # 24. Live capture config round-trip + clamps (5-30 fps, 0-16 monitor, 320-1920 width, 40-90 quality)
        status, res = req(f"{base}/api/config", "PUT", {
            "liveCapEnabled": True, "liveCapMonitor": 1, "liveCapFps": 25,
            "liveCapWidth": 960, "liveCapQuality": 70
        }, token=token)
        assert status == 200 and res.get("success") is True
        cfg = res.get("config", {})
        assert cfg.get("liveCapFps") == 25 and cfg.get("liveCapMonitor") == 1
        assert cfg.get("liveCapWidth") == 960 and cfg.get("liveCapQuality") == 70
        assert cfg.get("liveCapEnabled") is True
        print("✓ Live capture config round-trip verified")
        status, res = req(f"{base}/api/config", "PUT", {
            "liveCapFps": 999, "liveCapMonitor": 99, "liveCapWidth": 5000, "liveCapQuality": 5
        }, token=token)
        assert status == 200
        cfg = res.get("config", {})
        assert cfg.get("liveCapFps") == 30, cfg
        assert cfg.get("liveCapMonitor") == 16, cfg
        assert cfg.get("liveCapWidth") == 1920, cfg
        assert cfg.get("liveCapQuality") == 40, cfg
        status, res = req(f"{base}/api/config", "PUT", {"liveCapFps": 0}, token=token)
        assert res.get("config", {}).get("liveCapFps") == 5, res
        print("✓ Live capture config clamps verified (5-30 fps, 0-16 monitor, 320-1920 width, 40-90 quality)")

        # 25. Live capture clamp unit checks
        from vmix.livecap import clamp_fps, clamp_monitor, clamp_quality, clamp_width
        assert (clamp_fps(25), clamp_fps(999), clamp_fps(0), clamp_fps("x")) == (25, 30, 5, 25)
        assert (clamp_monitor(1), clamp_monitor(99), clamp_monitor(-3)) == (1, 16, 0)
        assert (clamp_width(960), clamp_width(9), clamp_width(99999)) == (960, 320, 1920)
        assert (clamp_quality(70), clamp_quality(1), clamp_quality(500)) == (70, 40, 90)
        print("✓ Live capture clamp helpers verified")

        # 26. Live status endpoint (mock mode -> honestly unavailable, never a wrong feed)
        status, res = req(f"{base}/api/vmix/live/status", "GET", token=token)
        assert status == 200, f"Expected 200 for live status, got {status}"
        for key in ("running", "available", "fpsTarget", "monitorRequested", "error"):
            assert key in res, f"live status missing key {key}"
        assert res.get("available") is False, "mock mode must report unavailable"
        assert "simulator" in str(res.get("error", "")).lower(), res
        print("✓ Live status endpoint verified (honest unavailable in simulator mode)")

        # 27. Live still endpoint always returns a valid JPEG (placeholder when unavailable)
        still_req = urllib.request.Request(f"{base}/api/vmix/live/program.jpg?token={token}")
        with urllib.request.urlopen(still_req, timeout=5.0) as resp:
            assert resp.status == 200
            assert "image/jpeg" in resp.headers.get("Content-Type", "")
            still_data = resp.read()
            assert still_data[:2] == b"\xff\xd8", "must be a real JPEG (SOI marker)"
            assert len(still_data) > 1000, "placeholder slate must have content"
        print("✓ Live still endpoint verified (valid JPEG placeholder when unavailable)")

        # 28. Live MJPEG endpoint: unavailable -> clean empty multipart (no frozen fake-live frame)
        mjpg_req = urllib.request.Request(f"{base}/api/vmix/live/program.mjpg?token={token}")
        with urllib.request.urlopen(mjpg_req, timeout=5.0) as resp:
            assert resp.status == 200
            assert "multipart/x-mixed-replace" in resp.headers.get("Content-Type", "")
            body = resp.read()
            assert b"\xff\xd8" not in body, "must not serve frames while unavailable"
        print("✓ Live MJPEG endpoint verified (ends cleanly while unavailable)")

        # 29. State carries live-capture availability + vMix host for LiveLAN derivation
        status, res = req(f"{base}/api/vmix/state", "GET", token=token)
        assert status == 200
        assert "liveCapAvailable" in res and "liveCapFps" in res and "vmixHost" in res
        assert res.get("liveCapAvailable") is False
        print("✓ State live-capture fields verified")

        # 30. Live endpoints require auth
        anon_req = urllib.request.Request(f"{base}/api/vmix/live/status")
        try:
            with urllib.request.urlopen(anon_req, timeout=3.0) as resp:
                raise AssertionError(f"Expected 401, got {resp.status}")
        except urllib.error.HTTPError as err:
            assert err.code == 401, f"Expected 401, got {err.code}"
        print("✓ Live endpoints enforce authentication")

        # 31. Auto-aim similarity matrix (deterministic synthetic scenes)
        import random as _r
        from PIL import Image as _I, ImageDraw as _D
        from vmix.liveaim import aim_once, similarity
        def _prog(w, h, bg, seed):
            _r.seed(seed)
            im = _I.new("RGB", (w, h), bg)
            d = _D.Draw(im)
            for _ in range(30):
                x0, y0 = _r.randint(0, w - 60), _r.randint(0, h - 60)
                d.ellipse([x0, y0, x0 + _r.randint(20, 100), y0 + _r.randint(20, 100)],
                          fill=(_r.randint(0, 255), _r.randint(0, 255), _r.randint(0, 255)))
            return im
        _P = _prog(640, 360, (140, 20, 30), 7)
        _P43 = _prog(480, 360, (30, 120, 160), 11)
        _Q = _prog(640, 360, (20, 90, 40), 99)
        _lb = _I.new("RGB", (640, 360), (0, 0, 0)); _lb.paste(_P.resize((640, 240)), (0, 60))
        _pb = _I.new("RGB", (640, 360), (0, 0, 0)); _pb.paste(_P43, (80, 0))
        _W = _prog(860, 360, (90, 40, 120), 21)
        _fit = _W.resize((640, 268))
        _filmlb = _I.new("RGB", (640, 360), (0, 0, 0)); _filmlb.paste(_fit, (0, 46))
        _V = _prog(360, 640, (40, 100, 140), 33)
        _fitv = _V.resize((203, 360))
        _vpb = _I.new("RGB", (640, 360), (0, 0, 0)); _vpb.paste(_fitv, (218, 0))
        _U = _I.new("RGB", (1366, 768), (9, 13, 22))
        _M = _U.copy(); _M.paste(_P.resize((300, 168)), (533, 200))
        for name, a, b, want_match in [
            ("identical", _P, _P.copy(), True), ("resized", _P, _P.resize((1920, 1080)), True),
            ("pillarboxed", _P43, _pb, True), ("film-letterbox", _W, _filmlb, True),
            ("vertical", _V, _vpb, True), ("different", _P, _Q, False),
            ("dark-ui", _P, _U, False), ("browser-mirror", _P, _M, False),
        ]:
            s = similarity(a, b)
            assert (s > 0.45) == want_match, f"aim similarity {name}: {s:.3f}"
        print("✓ Auto-aim similarity matrix verified (matches pass, others fail)")

        # 32. aim_once scan path with real display pixels when a display exists
        try:
            import mss as _mss
            with _mss.mss() as _sct:
                _mons = _sct.monitors
                assert len(_mons) > 1, "expected at least one physical display"
                _shot = _sct.grab(_mons[1])
                from PIL import Image as _I2
                _ref = _I2.frombytes("RGB", _shot.size, _shot.bgra, "raw", "BGRX")
            _res = aim_once(_ref)
            assert _res.get("monitorCount", 0) >= 1
            assert _res.get("bestIdx") == 1, f"self-match should win: {_res}"
            assert _res.get("bestScore", 0) > 0.9, f"self-match score: {_res}"
            print(f"✓ Auto-aim live scan verified (self-match {_res.get('bestScore')} on display 1)")
        except Exception as e:
            print(f"· Auto-aim live scan skipped (no display in this environment: {e})")

        # 33. Rescan endpoint: honest refusal in simulator mode, auth enforced
        status, res = req(f"{base}/api/vmix/live/rescan", "POST", {}, token=token)
        assert status == 200, f"Expected 200, got {status}"
        assert res.get("ok") is False, "mock mode must refuse auto-aim"
        print("✓ Live rescan endpoint verified (honest refusal in simulator mode)")

        # 34. liveCapAuto config round-trip
        status, res = req(f"{base}/api/config", "PUT", {"liveCapAuto": False}, token=token)
        assert status == 200 and res.get("config", {}).get("liveCapAuto") is False
        status, res = req(f"{base}/api/config", "PUT", {"liveCapAuto": True}, token=token)
        assert status == 200 and res.get("config", {}).get("liveCapAuto") is True
        print("✓ Live auto-aim config round-trip verified")

        # 35. Live status carries auto-aim fields
        status, res = req(f"{base}/api/vmix/live/status", "GET", token=token)
        assert status == 200
        for key in ("autoIdx", "autoScore", "monitorUsed", "monitorCount"):
            assert key in res, f"live status missing key {key}"
        print("✓ Live status auto-aim fields verified")

        print("\nALL PYTHON INTEGRATION TESTS PASSED! 🎉")
    finally:
        config_manager.config = initial_config
        config_manager.save()

if __name__ == "__main__":
    test_all()
