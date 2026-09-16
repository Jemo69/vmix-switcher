import asyncio
import hashlib
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

from .config import config_manager
from .livecap import clamp_fps, live_capture
from .mock import mock_vmix

class VMixClient:
    # Snapshot budget & live pipeline:
    # Live moving video feeds (Camera, NDI, Video, Desktop) refresh rapidly to
    # provide a true live broadcast confidence feeling, while static sources (Color bars,
    # images, titles) stay on a gentle rhythm to preserve PC and network resources.
    # Atomic temporary file writes prevent GDI+ sharing violations on Windows.
    LIVE_SOURCE_TYPES = {
        "camera", "ndi", "desktopcapture", "video", "videolist",
        "vmixcall", "stream", "replay", "source"
    }
    SNAP_MIN_ANY_INTERVAL = 0.5       # global pacing: each trigger holds the lock for the
                                      # full vMix render, so pacing faster than a render
                                      # only piles up timeouts / GDI contention
    SNAP_MIN_MONITOR_INTERVAL = 0.8   # active / preview inputs, kept near the preview cadence
    SNAP_MIN_LIVE_INTERVAL = 2.0      # Camera / NDI feeds, enough motion without overwhelming vMix
    SNAP_MIN_STATIC_INTERVAL = 45.0   # static stills (titles, image, colour, audio)
    SNAP_MAX_FILE_AGE = 60.0          # serve files up to this old while revalidating
    SNAP_SUCCESS_FRESH = 20.0         # file newer than this counts as "live"
    SNAP_BREAKER_TRIPS = 5            # consecutive failures before pausing
    SNAP_BREAKER_PAUSE = 30.0         # pause duration after trips (seconds)
    SNAP_CHOKE_PAUSE = 120.0          # ...escalated when trips repeat with no success between
    SNAP_FUNCTION_TIMEOUT = 10.0      # HTTP timeout: vMix may block while rendering
    # Poll rate (HTTP GET thumbnails, cheap ETag/304s) may run at 30-60fps.
    # Render rate (SnapshotInput to vMix, a full render + JPEG encode each)
    # must stay sustainable or vMix GDI+ faults and EVERYTHING decays to
    # placeholders. The floors below decouple the two on purpose.
    RENDER_MIN_GAP = 0.6              # steady-state minimum seconds between render starts
    RENDER_BURST_GAP = 0.3            # ...even while converging overdue inputs (never unbounded)

    def __init__(self):
        self.connected = False
        self.last_state: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self.poll_task: Optional[asyncio.Task] = None
        self.callbacks: List[Callable[[Dict[str, Any]], Any]] = []
        self._thumb_cache: Dict[str, tuple[float, bytes, str]] = {}  # key -> (timestamp, data, content_type)
        self._thumb_inflight: Dict[str, asyncio.Future] = {}  # key -> shared in-flight fetch
        self._last_signature: Optional[tuple] = None
        self._last_broadcast_time: float = 0.0
        # Live snapshot thumbnails (see _load_thumbnail for rationale)
        self._snap_dir: Optional[str] = None
        self._snap_last_any: float = 0.0
        self._snap_lock = asyncio.Lock()
        self._snap_pending_keys: set[str] = set()  # never queue duplicate captures for one source
        self._snap_backoff: dict[str, tuple[int, float]] = {}  # key -> (fail streak, next allowed epoch)
        self._snap_errors: dict[str, str] = {}  # key -> last failure detail (surfaced per input)
        self._snap_waiting: dict[str, float] = {}  # key -> first skipped epoch (fair queue)
        self._snap_render_ema: Optional[float] = None  # EMA of vMix render round-trip seconds
        self._snap_breaker_escalations: int = 0  # breaker trips with no success between
        self._snap_fail_streak: int = 0
        self._snap_paused_until: float = 0.0
        self._snap_last_success: float = 0.0
        self._thumb_mode: str = "starting"  # live|starting|paused|remote|offline|mock
        self._thumb_detail: str = ""

    def add_callback(self, cb: Callable[[Dict[str, Any]], Any]) -> None:
        if cb not in self.callbacks:
            self.callbacks.append(cb)

    def remove_callback(self, cb: Callable[[Dict[str, Any]], Any]) -> None:
        if cb in self.callbacks:
            self.callbacks.remove(cb)

    def start(self) -> None:
        if self.poll_task is None or self.poll_task.done():
            self.poll_task = asyncio.create_task(self._poll_loop())

    def stop(self) -> None:
        if self.poll_task and not self.poll_task.done():
            self.poll_task.cancel()
            self.poll_task = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self.poll()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.connected = False
                self.last_error = str(e)

            cfg = config_manager.get()
            interval = max(0.1, cfg.get("pollIntervalMs", 300) / 1000.0)
            await asyncio.sleep(interval)

    async def poll(self) -> Optional[Dict[str, Any]]:
        cfg = config_manager.get()

        if cfg.get("mockMode", False):
            state = mock_vmix.get_state()
            self.connected = True
            self.last_error = None
            return self._process_state(state, is_mock=True)

        host = cfg.get("vmixHost", "127.0.0.1")
        port = cfg.get("vmixPort", 8088)
        url = f"http://{host}:{port}/api/"

        try:
            raw_xml = await asyncio.to_thread(self._fetch_url, url)
            state = self._parse_xml(raw_xml)
            self.connected = True
            self.last_error = None
            return self._process_state(state, is_mock=False)
        except Exception as err:
            self.connected = False
            self.last_error = str(err)
            return None

    def _fetch_url(self, url: str, timeout: float = 1.5) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "vMix-Web-Switcher/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as err:
            err_msg = ""
            try:
                err_msg = err.read().decode("utf-8", errors="replace").strip()
            except Exception:
                pass
            raise RuntimeError(f"vMix HTTP Error {err.code}: {err_msg or err.reason}")

    def _parse_xml(self, xml_text: str) -> Dict[str, Any]:
        root = ET.fromstring(xml_text)

        version = root.findtext("version", "Unknown")
        edition = root.findtext("edition", "")
        preset = root.findtext("preset", "")

        active_val = root.findtext("active", "0")
        preview_val = root.findtext("preview", "0")
        active_num = int(active_val) if active_val.isdigit() else active_val
        preview_num = int(preview_val) if preview_val.isdigit() else preview_val

        fade_to_black = (root.findtext("fadeToBlack", "False") or "").lower() == "true"
        recording = (root.findtext("recording", "False") or "").lower() == "true"
        streaming = (root.findtext("streaming", "False") or "").lower() == "true"
        fullscreen = (root.findtext("fullscreen", "False") or "").lower() == "true"
        external = (root.findtext("external", "False") or "").lower() == "true"

        # Overlays
        overlays: Dict[str, Optional[int]] = {"1": None, "2": None, "3": None, "4": None}
        overlays_elem = root.find("overlays")
        if overlays_elem is not None:
            for ov in overlays_elem.findall("overlay"):
                ov_num = ov.attrib.get("number", "")
                val = ov.text.strip() if ov.text else ""
                if ov_num and val:
                    overlays[ov_num] = int(val) if val.isdigit() else val

        # Inputs
        inputs_elem = root.find("inputs")
        raw_inputs = inputs_elem.findall("input") if inputs_elem is not None else []

        inputs = []
        for inp in raw_inputs:
            num_str = inp.attrib.get("number", "0")
            num = int(num_str) if num_str.isdigit() else 0
            key = inp.attrib.get("key", str(num))
            title = inp.attrib.get("title") or (inp.text.strip() if inp.text else "") or f"Input {num}"
            short_title = inp.attrib.get("shortTitle") or title
            inp_type = inp.attrib.get("type", "Generic")
            state = inp.attrib.get("state", "Running")
            muted = (inp.attrib.get("muted", "False") or "").lower() == "true"
            volume_str = inp.attrib.get("volume", "100")
            try:
                volume = float(volume_str)
            except ValueError:
                volume = 100.0

            is_active = bool(active_num and ((num == active_num) or (key == str(active_val))))
            is_preview = bool(preview_num and ((num == preview_num) or (key == str(preview_val))))

            # Active overlays for this input
            active_overlays = [int(k) for k, v in overlays.items() if k.isdigit() and (v == num or str(v) == key)]

            # Live motion signal classification
            type_lower = inp_type.lower()
            is_live_source = any(t in type_lower for t in self.LIVE_SOURCE_TYPES)
            if not is_live_source:
                signal_status = "static"
            elif (state or "").lower() in ("running", "active", "playing"):
                signal_status = "live"
            else:
                signal_status = "standby"

            inputs.append({
                "number": num,
                "key": key,
                "title": title,
                "shortTitle": short_title,
                "type": inp_type,
                "state": state,
                "muted": muted,
                "volume": volume,
                "isActive": is_active,
                "isPreview": is_preview,
                "activeOverlays": active_overlays,
                "isLiveSource": is_live_source,
                "signalStatus": signal_status
            })

        return {
            "version": version,
            "edition": edition,
            "preset": preset,
            "active": active_num,
            "preview": preview_num,
            "fadeToBlack": fade_to_black,
            "recording": recording,
            "streaming": streaming,
            "fullscreen": fullscreen,
            "external": external,
            "overlays": overlays,
            "inputs": inputs
        }

    def _process_state(self, state: Dict[str, Any], is_mock: bool = False) -> Dict[str, Any]:
        cfg = config_manager.get()
        ignored = set(str(x) for x in cfg.get("ignoredInputs", []))
        aliases = cfg.get("inputAliases", {})
        colors = cfg.get("inputColors", {})

        all_inputs = []
        for inp in state.get("inputs", []):
            inp_num_str = str(inp["number"])
            inp_key = str(inp["key"])
            custom_title = aliases.get(inp_num_str) or aliases.get(inp_key) or inp["shortTitle"] or inp["title"]
            custom_color = colors.get(inp_num_str) or colors.get(inp_key)
            is_ignored = (inp_num_str in ignored) or (inp_key in ignored)
            is_priority = self._is_picked_priority(inp_key) or self._is_picked_priority(inp_num_str)

            all_inputs.append({
                **inp,
                "customTitle": custom_title,
                "customColor": custom_color,
                "isIgnored": is_ignored,
                "isPriority": is_priority,
                "snapAgeSec": self._snap_age_for_key(str(inp.get("key") or inp.get("number"))),
                "snapError": self._snap_errors.get(str(inp.get("key"))) or self._snap_errors.get(str(inp.get("number"))),
            })

        visible_inputs = [i for i in all_inputs if not i["isIgnored"]]

        livecap = self._livecap_ensure()

        full_state = {
            **state,
            "isMock": is_mock,
            "connected": True,
            "lastUpdated": int(time.time() * 1000),
            "allInputs": all_inputs,
            "visibleInputs": visible_inputs,
            "ignoredCount": len(all_inputs) - len(visible_inputs),
            "defaultTransition": cfg.get("defaultTransition", "Fade"),
            "transitionDuration": cfg.get("transitionDuration", 500),
            "switcherMode": cfg.get("switcherMode", "direct"),
            "previewFps": self._preview_fps(),
            "backgroundFps": self._background_fps(),
            "priorityInputs": sorted(list(self._priority_set()), key=lambda x: (0, int(x)) if x.isdigit() else (1, x)),
            "maxPriorityInputs": config_manager.max_priority_inputs(),
            "livelanUrl": cfg.get("livelanUrl", ""),
            "vmixHost": cfg.get("vmixHost", "127.0.0.1"),
            "vmixPort": cfg.get("vmixPort", 8088),
            "liveCapAvailable": livecap.get("available", False),
            "liveCapFps": livecap.get("fps", 25),
            "liveCapError": livecap.get("error"),
            "snapFreshSec": self.SNAP_SUCCESS_FRESH,
            "snapMaxAgeSec": self.SNAP_MAX_FILE_AGE,
            **self.thumbnail_status(),
        }

        self.last_state = full_state

        # Check if state signature changed or if periodic sync interval (5.0s) has passed
        sig = (
            full_state.get("connected"),
            full_state.get("active"),
            full_state.get("preview"),
            full_state.get("fadeToBlack"),
            full_state.get("recording"),
            full_state.get("streaming"),
            full_state.get("fullscreen"),
            full_state.get("external"),
            full_state.get("defaultTransition"),
            full_state.get("transitionDuration"),
            full_state.get("switcherMode"),
            full_state.get("previewFps"),
            full_state.get("backgroundFps"),
            tuple(full_state.get("priorityInputs", [])),
            full_state.get("maxPriorityInputs"),
            full_state.get("liveCapAvailable"),
            full_state.get("liveCapFps"),
            full_state.get("liveCapError"),
            full_state.get("vmixHost"),
            full_state.get("thumbnailMode"),
            len(visible_inputs),
            tuple((i["number"], i.get("isActive"), i.get("isPreview"), tuple(i.get("activeOverlays", [])), i.get("muted"), i.get("volume"), i.get("state"), i.get("signalStatus"), i.get("isPriority"), i.get("customTitle"), i.get("isIgnored"), i.get("snapError")) for i in all_inputs)
        )

        now = time.time()
        if sig != self._last_signature or (now - self._last_broadcast_time > 5.0):
            self._last_signature = sig
            self._last_broadcast_time = now
            self._notify(full_state)

        return full_state

    def _livecap_ensure(self) -> Dict[str, Any]:
        """Keep the low-latency capture in its correct state and report it.

        Runs on every poll (idempotent, no restarts): capture is allowed
        ONLY on the vMix PC outside simulator mode, so a remote server can
        never stream its own desktop as the Program feed.
        """
        cfg = config_manager.get()
        fps = clamp_fps(cfg.get("liveCapFps", 25))
        if cfg.get("mockMode", False):
            live_capture.stop("simulator mode")
            return {"available": False, "fps": fps, "error": "simulator mode"}
        if not self._is_vmix_local():
            live_capture.stop("needs the server on the vMix PC")
            return {"available": False, "fps": fps,
                    "error": "needs the server on the vMix PC"}
        if not cfg.get("liveCapEnabled", True):
            live_capture.stop("disabled in settings")
            return {"available": False, "fps": fps,
                    "error": "disabled in settings"}
        live_capture.configure(
            fps,
            cfg.get("liveCapMonitor", 1),
            cfg.get("liveCapWidth", 960),
            cfg.get("liveCapQuality", 70),
        )
        live_capture.start()
        st = live_capture.status()
        if st.get("running"):
            return {"available": True, "fps": fps, "error": None}
        return {"available": False, "fps": fps,
                "error": st.get("error") or "capture failed"}

    def _notify(self, state: Dict[str, Any]) -> None:
        for cb in list(self.callbacks):
            try:
                res = cb(state)
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass

    async def execute_function(self, func_name: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        params = params or {}
        cfg = config_manager.get()

        if cfg.get("mockMode", False):
            res = mock_vmix.execute_function(func_name, params)
            # Invalidate signature to force immediate broadcast
            self._last_signature = None
            await self.poll()
            return res

        host = cfg.get("vmixHost", "127.0.0.1")
        port = cfg.get("vmixPort", 8088)

        query_dict = {"Function": func_name, **params}
        query_str = urllib.parse.urlencode(query_dict)
        url = f"http://{host}:{port}/api/?{query_str}"

        data = await asyncio.to_thread(self._fetch_url, url, 2.0)
        # Fast poll so UI tallies update immediately
        asyncio.create_task(self._delayed_poll(0.05))
        return {"success": True, "data": data}

    async def _delayed_poll(self, delay: float) -> None:
        await asyncio.sleep(delay)
        # Invalidate signature so switch triggers an immediate broadcast
        self._last_signature = None
        await self.poll()

    async def switch_input(self, input_number: int | str, transition_override: Optional[str] = None, duration_override: Optional[int] = None) -> Dict[str, Any]:
        cfg = config_manager.get()
        mode = cfg.get("switcherMode", "direct")
        transition = transition_override or cfg.get("defaultTransition", "Fade")
        duration = duration_override if duration_override is not None else cfg.get("transitionDuration", 500)

        if mode == "preview_take":
            return await self.execute_function("PreviewInput", {"Input": input_number})

        # Direct mode: transition selected input directly to output!
        # Safety check: If input is already active on Program, do not re-transition (prevents accidental swap)
        if self.last_state:
            active_val = str(self.last_state.get("active", ""))
            input_str = str(input_number)
            if active_val and (active_val == input_str):
                return {"success": True, "message": "Input is already active on Program"}
            for inp in self.last_state.get("allInputs", []):
                if (str(inp.get("number")) == input_str or str(inp.get("key")) == input_str) and inp.get("isActive"):
                    return {"success": True, "message": "Input is already active on Program"}

        trans_lower = transition.lower()
        if trans_lower in ("cut", "cutdirect"):
            return await self.execute_function("CutDirect", {"Input": input_number})

        # In vMix, Transition1 to Transition4 shortcut functions do not accept Input parameter;
        # they click the Transition 1..4 button which transitions Preview to Active.
        # To direct-transition with Transition1..4, stage the input in Preview first, then trigger Transition.
        if trans_lower in ("transition1", "transition2", "transition3", "transition4"):
            await self.execute_function("PreviewInput", {"Input": input_number})
            return await self.execute_function(transition)

        params: Dict[str, Any] = {"Input": input_number}
        if duration and not trans_lower.startswith("transition"):
            params["Duration"] = duration

        return await self.execute_function(transition, params)

    async def toggle_overlay(self, overlay_num: int | str, input_number: int | str) -> Dict[str, Any]:
        return await self.execute_function(f"OverlayInput{overlay_num}", {"Input": input_number})

    async def toggle_audio(self, input_number: int | str) -> Dict[str, Any]:
        return await self.execute_function("Audio", {"Input": input_number})

    async def get_thumbnail(self, input_id: int | str) -> tuple[bytes, str]:
        """Fetches JPEG thumbnail from vMix or generates clean SVG thumbnail for mock inputs."""
        str_id = str(input_id).lower()
        if str_id in ("active", "program", "pgm", "0"):
            target_id = self.last_state.get("active", 1) if self.last_state else 1
        elif str_id in ("preview", "prv"):
            target_id = self.last_state.get("preview", 2) if self.last_state else 2
        else:
            target_id = input_id

        cache_key = str(target_id)
        now = time.time()
        cached = self._thumb_cache.get(cache_key)
        if cached and (now - cached[0]) < self._thumb_cache_ttl():
            return cached[1], cached[2]

        # Collapse concurrent requests for the same input into one vMix fetch
        pending = self._thumb_inflight.get(cache_key)
        if pending is not None:
            return await pending

        pending = asyncio.get_running_loop().create_future()
        self._thumb_inflight[cache_key] = pending
        try:
            result = await self._load_thumbnail(target_id, cache_key)
        except BaseException as err:
            if not pending.done():
                pending.set_exception(err)
            raise
        else:
            if not pending.done():
                pending.set_result(result)
            return result
        finally:
            self._thumb_inflight.pop(cache_key, None)

    def _resolve_target_id(self, input_id: int | str) -> Any:
        str_id = str(input_id).lower()
        if str_id in ("active", "program", "pgm", "0"):
            return self.last_state.get("active", 1) if self.last_state else 1
        elif str_id in ("preview", "prv"):
            return self.last_state.get("preview", 2) if self.last_state else 2
        return input_id

    def _snap_path_for_key(self, key: str) -> str:
        import os
        return os.path.join(self._snap_dir_path(), self._snap_filename(str(key)))

    def _snap_file_stat(self, key: str) -> Optional[tuple[float, int]]:
        """(mtime, size) of an input's snapshot file, or None."""
        import os
        try:
            st = os.stat(self._snap_path_for_key(key))
            return (st.st_mtime, st.st_size)
        except OSError:
            return None

    def snapshot_etag(self, input_id: int | str) -> Optional[str]:
        """Weak ETag for conditional thumbnail requests. Stat-only (no file
        read), None when there is no servable snapshot (offline / remote /
        not yet captured) so those keep today's no-store behavior."""
        cfg = config_manager.get()
        if cfg.get("mockMode", False):
            target_id = self._resolve_target_id(input_id)
            is_act = False
            is_prv = False
            title = ""
            if self.last_state:
                for inp in self.last_state.get("allInputs", []):
                    if str(inp.get("number")) == str(target_id) or str(inp.get("key")) == str(target_id):
                        is_act = bool(inp.get("isActive"))
                        is_prv = bool(inp.get("isPreview"))
                        title = str(inp.get("title") or "")
                        break
            h = hashlib.md5(f"mock-{target_id}-{is_act}-{is_prv}-{title}".encode("utf-8")).hexdigest()[:12]
            return f'W/"{h}"'
        if not self.connected:
            return None
        if not self._is_vmix_local():
            return None
        key = self._resolve_input_key(self._resolve_target_id(input_id))
        fs = self._snap_file_stat(key)
        if not fs:
            return None
        mtime, size = fs
        if (time.time() - mtime) > self.SNAP_MAX_FILE_AGE:
            return None
        return f'W/"{int(mtime * 1000):x}-{size:x}"'

    def note_poll(self, input_id: int | str) -> bool:
        """Poll-driven render scheduling without serving bytes: lets 304 fast
        paths keep snapshots refreshing. Returns True if a trigger fired."""
        if config_manager.get().get("mockMode", False) or not self.connected:
            return False
        if not self._is_vmix_local():
            return False
        try:
            key = self._resolve_input_key(self._resolve_target_id(input_id))
        except Exception:
            return False
        fs = self._snap_file_stat(key)
        mtime = fs[0] if fs else 0.0
        return self._schedule_trigger(key, self._snap_path_for_key(key), mtime, time.time())

    def _schedule_trigger(self, key: str, path: str, mtime: float, now: float) -> bool:
        """Fire a snapshot capture when due, backed-off-aware. Shared by the
        serving path and the 304 poll path so both keep renders scheduled."""
        if now < self._snap_paused_until:
            return False
        if now < self._snap_backoff.get(str(key), (0, 0.0))[1]:
            return False
        interval = self._get_input_interval(key)
        if not ((mtime <= 0) or ((now - mtime) > interval)):
            return False
        if key in self._snap_pending_keys:
            return False
        # Fair scheduling: the pace gate alone lets always-due inputs (monitors
        # at fast pull rates) win every race, starving the wall while looking
        # healthy. Skipped inputs join a queue; each open slot goes to the
        # longest-waiting demanded input, so every input provably gets a turn.
        overdue = (mtime <= 0) or ((now - mtime) > 3 * interval)
        render_cost = self._snap_render_ema if self._snap_render_ema else 0.3
        pace = max(self.RENDER_MIN_GAP, self._snap_any_interval(), min(3.0, render_cost * 1.5))
        gap = self.RENDER_BURST_GAP if overdue else pace
        if (now - self._snap_last_any) < gap:
            self._snap_waiting.setdefault(str(key), now)
            self._prune_waiting(now)
            return False
        served = self._serve_oldest_waiter(exclude=str(key), now=now)
        if served is not None:
            # Gave this slot to a hungrier input; self stays due for next time.
            self._snap_waiting.setdefault(str(key), now)
            return False
        self._snap_waiting.pop(str(key), None)
        self._snap_last_any = now
        self._snap_pending_keys.add(key)
        try:
            asyncio.create_task(self._trigger_snapshot_guarded(key, path))
        except RuntimeError:
            self._snap_pending_keys.discard(key)
            return False
        return True

    def _prune_waiting(self, now: float) -> None:
        for k, ts in list(self._snap_waiting.items()):
            if now - ts > 60.0:
                self._snap_waiting.pop(k, None)

    def _serve_oldest_waiter(self, exclude: str, now: float) -> Optional[str]:
        """Fire the longest-waiting demanded input that is still eligible.
        Returns its key, or None if nobody qualifies."""
        for key in sorted(self._snap_waiting, key=lambda k: self._snap_waiting[k]):
            if key == exclude or key in self._snap_pending_keys:
                continue
            if now < self._snap_backoff.get(key, (0, 0.0))[1]:
                continue
            fs = self._snap_file_stat(key)
            wmtime = fs[0] if fs else 0.0
            if wmtime > 0 and (now - wmtime) <= self._get_input_interval(key):
                self._snap_waiting.pop(key, None)
                continue
            try:
                asyncio.create_task(
                    self._trigger_snapshot_guarded(key, self._snap_path_for_key(key)))
            except RuntimeError:
                return None
            self._snap_waiting.pop(key, None)
            self._snap_pending_keys.add(key)
            self._snap_last_any = now
            return key
        return None

    def _snap_any_interval(self) -> float:
        # Scale pacing with priority framerate (down to 16ms for 60fps)
        return max(0.016, min(0.5, 0.5 / (self._preview_fps() / 4.0)))

    def _thumb_cache_ttl(self) -> float:
        fps = self._preview_fps()
        # Cache long enough to coalesce the burst of frontend requests
        # (program monitor + corner hero + grid tile all ask for the same
        # input within the same tick), but short enough to stay "live".
        return min(2.0, max(0.015, 0.8 / fps))

    def _preview_fps(self) -> float:
        # Priority-tier pull rate. High values (30/60) mean tiles re-poll fast
        # via cheap conditional requests — vMix still renders each snapshot at
        # its own physical pace (~1/s shared), so this buys instant delivery
        # of fresh frames, not more renders.
        try:
            fps = float(config_manager.get().get("previewFps", 4))
        except (TypeError, ValueError):
            fps = 4.0
        return min(60.0, max(0.5, fps))

    def _background_fps(self) -> float:
        # Eco-tier pull + render rate for non-priority inputs.
        try:
            fps = float(config_manager.get().get("backgroundFps", 1.5))
        except (TypeError, ValueError):
            fps = 1.5
        return min(5.0, max(0.1, fps))

    def _priority_set(self) -> set:
        return set(str(x) for x in config_manager.get().get("priorityInputs", []))

    def _is_picked_priority(self, key: str) -> bool:
        """True when the operator starred this input (number or key match)."""
        picked = self._priority_set()
        if str(key) in picked:
            return True
        for inp in (self.last_state.get("allInputs", []) if self.last_state else []):
            if str(inp.get("key")) == str(key) or str(inp.get("number")) == str(key):
                if str(inp.get("number")) in picked or str(inp.get("key")) in picked:
                    return True
        return False

    @staticmethod
    def _sniff_image_mime(data: bytes) -> Optional[str]:
        if not data or len(data) < 4:
            return None
        if data[:2] == b"\xff\xd8":
            return "image/jpeg"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if data[:4] in (b"RIFF",) and len(data) > 12 and data[8:12] == b"WEBP":
            return "image/webp"
        return None

    async def _load_thumbnail(self, target_id: Any, cache_key: str) -> tuple[bytes, str]:
        # vMix exposes NO per-input image endpoint (there is no Thumbnail.aspx
        # — verified against official docs + forums). The supported path is
        #   Function=SnapshotInput&Input=<num|key>&Value=<abs path on vMix PC>
        # which writes a JPEG on the vMix machine. That only works when this
        # server runs ON the vMix PC (the documented setup), so we detect that
        # and otherwise serve honest placeholders instead of fake "live" images.
        now = time.time()
        cfg = config_manager.get()

        if cfg.get("mockMode", False):
            self._set_thumb_status("mock", "Simulator — demo graphics")
            return self._svg_bytes(str(target_id))

        if not self.connected:
            self._set_thumb_status("offline", "vMix offline")
            return self._svg_bytes(str(target_id))

        if not self._is_vmix_local():
            self._set_thumb_status("remote", "Live images need the switcher running on the vMix PC")
            return self._svg_bytes(str(target_id))

        # Local vMix PC: snapshot pipeline with stale-while-revalidate.
        # The HTTP response never blocks on vMix rendering: we serve the last
        # snapshot file immediately and fire-and-forget the refresh trigger.
        import os
        key = self._resolve_input_key(target_id)
        path = os.path.join(self._snap_dir_path(), self._snap_filename(key))

        mtime = 0.0
        if os.path.isfile(path):
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0

        if mtime > 0 and (now - mtime) <= self.SNAP_SUCCESS_FRESH:
            self._snap_last_success = max(self._snap_last_success, mtime)

        self._schedule_trigger(key, path, mtime, now)

        if mtime > 0 and (now - mtime) <= self.SNAP_MAX_FILE_AGE:
            try:
                with open(path, "rb") as fh:
                    raw = fh.read()
                mime = self._sniff_image_mime(raw) or "image/jpeg"
                self._thumb_cache[cache_key] = (now, raw, mime)
                if (now - mtime) <= self.SNAP_SUCCESS_FRESH:
                    self._set_thumb_status("live", "Snapshots refreshing from vMix")
                else:
                    self._set_thumb_status("starting", "Waiting on fresh snapshots from vMix…")
                return raw, mime
            except OSError:
                pass

        if (now - self._snap_last_success) <= self.SNAP_SUCCESS_FRESH:
            # Another input is already streaming snapshots — don't let one
            # still-converging input hide that from the UI pills.
            self._set_thumb_status("live", "Snapshots refreshing from vMix")
        elif now < self._snap_paused_until:
            self._set_thumb_status("paused", self._thumb_detail or "Snapshots paused — vMix reported save errors")
        else:
            self._set_thumb_status("starting", "Requesting first snapshots from vMix…")
        return self._svg_bytes(str(target_id))

    async def _trigger_snapshot_guarded(self, key: str, path: str) -> None:
        # Atomic snapshot write:
        # vMix writes to a unique temporary file path. This ensures vMix's .NET GDI+
        # Bitmap.Save never collides with any concurrent read from Python, preventing
        # the infamous "A generic error occurred in GDI+" sharing violation.
        import os
        safe_key = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in str(key))
        temp_filename = f"snap_{safe_key[:32]}_{int(time.time() * 1000)}.jpg"
        temp_path = os.path.join(self._snap_dir_path(), temp_filename)

        try:
            async with self._snap_lock:
                cfg = config_manager.get()
                host = cfg.get("vmixHost", "127.0.0.1")
                port = cfg.get("vmixPort", 8088)
                query = urllib.parse.urlencode(
                    {"Function": "SnapshotInput", "Input": key, "Value": temp_path}
                )
                url = f"http://{host}:{port}/api/?{query}"
                render_start = time.time()
                await asyncio.to_thread(self._fetch_url, url, self.SNAP_FUNCTION_TIMEOUT)
                render_dt = time.time() - render_start
                # EMA of render cost drives adaptive pacing: a slow/choking vMix
                # box automatically gets breathing room between captures.
                if self._snap_render_ema is None:
                    self._snap_render_ema = render_dt
                else:
                    self._snap_render_ema += 0.3 * (render_dt - self._snap_render_ema)

            # Once the API returns, vMix has finished writing and closed the file.
            # Read and cache the raw JPEG in memory, and atomically replace target path.
            # NOTE: vMix answers HTTP 200 even when the render silently fails, so a
            # missing file is a failure too — otherwise inputs stall at IMG:LOAD
            # forever with zero signal (no file, no error, no backoff).
            if not os.path.isfile(temp_path):
                await self._await_snapshot_file(temp_path)
            if os.path.isfile(temp_path):
                try:
                    with open(temp_path, "rb") as fh:
                        raw = fh.read()
                    mime = self._sniff_image_mime(raw) or "image/jpeg"
                    cache_key = str(key)
                    self._thumb_cache[cache_key] = (time.time(), raw, mime)
                    try:
                        os.replace(temp_path, path)
                    except OSError:
                        pass
                finally:
                    if os.path.isfile(temp_path):
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
            else:
                raise RuntimeError(f"vMix accepted SnapshotInput for {key!r} but wrote no file")
        except Exception as err:
            self._record_snap_failure(key, f"Snapshot failed: {err}")
        else:
            self._record_snap_success(key)
        finally:
            self._snap_pending_keys.discard(key)

    @staticmethod
    async def _await_snapshot_file(temp_path: str, timeout: float = 6.0) -> None:
        """vMix sometimes renders asynchronously after the API returns. Give
        the file a short grace window before calling it a silent failure."""
        import os
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.isfile(temp_path):
                return
            await asyncio.sleep(0.25)

    def _record_snap_success(self, key: str = "") -> None:
        self._snap_fail_streak = 0
        self._snap_breaker_escalations = 0
        if key:
            self._snap_backoff.pop(str(key), None)
            self._snap_errors.pop(str(key), None)

    def _record_snap_failure(self, key: str, detail: str) -> None:
        self._snap_fail_streak += 1
        self._snap_errors[str(key)] = detail
        # Per-input backoff: a failing input must not hammer vMix (and starve
        # the inputs that do work). 3s, 6s, 12s… capped at 60s.
        streak, _ = self._snap_backoff.get(str(key), (0, 0.0))
        streak += 1
        wait = min(60.0, 3.0 * (2 ** (streak - 1)))
        self._snap_backoff[str(key)] = (streak, time.time() + wait)
        if streak == 2:
            # Visible in the server console window so a stuck input is obvious
            # without opening devtools: which input, and why.
            print(f"[snap] input {key} failing ({detail}) — backing off, retrying quietly")
        if self._snap_fail_streak >= self.SNAP_BREAKER_TRIPS:
            # Escalation: trips repeating with no success between mean vMix
            # itself is choking (typically undeleted GDI+ error dialogs on the
            # vMix PC). Hammering harder only deepens it — cool down longer and
            # say exactly where to look. Any success resets the escalation.
            self._snap_breaker_escalations += 1
            if self._snap_breaker_escalations >= 2:
                self._snap_paused_until = time.time() + self.SNAP_CHOKE_PAUSE
                self._set_thumb_status(
                    "paused",
                    "vMix isn't answering snapshot requests — check the vMix PC screen "
                    "for error popups (dismiss any GDI+ dialogs), then wait; retries resume automatically",
                )
            else:
                self._snap_paused_until = time.time() + self.SNAP_BREAKER_PAUSE
                self._set_thumb_status("paused", "Snapshots paused 30s — vMix reported save errors")
        else:
            self._set_thumb_status("starting", detail)

    def _snap_age_for_key(self, key: str) -> Optional[int]:
        """Age of the last snapshot file for an input, or None if none yet.
        Lets the UI tell 'waiting for first snap' apart from 'stuck'."""
        import os
        try:
            if not self._snap_dir:
                return None
            path = os.path.join(self._snap_dir, self._snap_filename(key))
            return int(time.time() - os.path.getmtime(path))
        except OSError:
            return None

    def _get_input_data(self, target_id: Any) -> Optional[Dict[str, Any]]:
        tid = str(target_id)
        if self.last_state:
            for inp in self.last_state.get("allInputs", []):
                if str(inp.get("number")) == tid or str(inp.get("key")) == tid:
                    return inp
        return None

    def _is_live_source(self, key: str) -> bool:
        """True for live moving video feeds (Camera, NDI, Desktop, Video, Call)"""
        inp = self._get_input_data(key)
        if not inp:
            return False
        inp_type = str(inp.get("type", "")).lower()
        return any(t in inp_type for t in self.LIVE_SOURCE_TYPES)

    def _get_input_interval(self, key: str) -> float:
        """Dynamic tiered render rhythm:
        - Monitors (Program/Preview): always fast live tier (up to 30/60 fps).
        - Starred / Priority inputs: fast live tier (up to 30/60 fps).
          Note: Images picked as priority ALSO get priority pulling!
        - Non-priority live feeds (Camera, NDI, Video, Desktop):
          eco rate (1.0 / backgroundFps, default 1.5 frames = ~0.66s).
        - Non-priority static stills (images, titles, colours, audio):
          kept at SNAP_MIN_STATIC_INTERVAL (45s).
          ('Images don't need to be pulled every frame except if it's put as a priority frame')"""
        priority_interval = max(0.016, 1.0 / self._preview_fps())
        bg_interval = max(0.1, 1.0 / self._background_fps())

        if self._is_monitor_input(key) or self._is_picked_priority(key):
            return priority_interval
        if self._is_live_source(key):
            return bg_interval
        return self.SNAP_MIN_STATIC_INTERVAL

    def _is_monitor_input(self, key: str) -> bool:
        """True when this input is currently routed to Program or Preview
        (monitors refresh faster; grid stills barely change)."""
        st = self.last_state
        if not st:
            return False
        keys = {str(key)}
        for inp in st.get("allInputs", []):
            if str(inp.get("key")) == str(key) or str(inp.get("number")) == str(key):
                keys.add(str(inp.get("number")))
                keys.add(str(inp.get("key")))
        active = str(st.get("active", ""))
        preview = str(st.get("preview", ""))
        return bool((active and active in keys) or (preview and preview in keys))

    def _set_thumb_status(self, mode: str, detail: str) -> None:
        if mode != self._thumb_mode:
            self._thumb_mode = mode
            self._last_signature = None  # force rebroadcast so the UI pill flips
        self._thumb_detail = detail

    def thumbnail_status(self) -> Dict[str, Any]:
        return {
            "thumbnailLive": self._thumb_mode == "live",
            "thumbnailMode": self._thumb_mode,
            "thumbnailDetail": self._thumb_detail,
        }

    def _is_vmix_local(self) -> bool:
        """True when the configured vMix host is this machine (loopback or a
        local interface IP). Snapshots are files on the vMix PC, so only a
        same-machine server can capture and serve them."""
        host = (config_manager.get().get("vmixHost", "127.0.0.1") or "").strip().lower()
        if host in ("127.0.0.1", "localhost", "::1"):
            return True
        try:
            import socket
            try:
                target = socket.gethostbyname(host)
            except OSError:
                return False
            if target in ("127.0.0.1", "::1"):
                return True
            try:
                if target == socket.gethostbyname(socket.gethostname()):
                    return True
            except OSError:
                pass
            return False
        except Exception:
            return False

    def _snap_dir_path(self) -> str:
        import os
        import tempfile
        if not self._snap_dir:
            d = os.path.join(tempfile.gettempdir(), "vmix-switcher-snaps")
            os.makedirs(d, exist_ok=True)
            self._snap_dir = d
        return self._snap_dir

    @staticmethod
    def _snap_filename(key: str) -> str:
        safe = "".join(c if (c.isalnum() or c in ("-", "_")) else "_" for c in str(key))
        return f"snap_{safe[:64]}.jpg"

    def _resolve_input_key(self, target_id: Any) -> str:
        """Stable snapshot identity for an input (keys survive reordering)."""
        tid = str(target_id)
        if self.last_state:
            for inp in self.last_state.get("allInputs", []):
                if str(inp.get("number")) == tid or str(inp.get("key")) == tid:
                    return str(inp.get("key") or inp.get("number"))
        return tid

    def _svg_bytes(self, input_id: str) -> tuple[bytes, str]:
        return self._generate_mock_svg(input_id).encode("utf-8"), "image/svg+xml"

    def _generate_mock_svg(self, input_id: str) -> str:
        title = f"Input {input_id}"
        inp_type = "Source"
        is_active = False
        is_preview = False
        if self.last_state:
            for inp in self.last_state.get("allInputs", []):
                if str(inp.get("number")) == input_id or str(inp.get("key")) == input_id:
                    title = inp.get("customTitle") or inp.get("shortTitle") or inp.get("title") or title
                    inp_type = inp.get("type", "Source")
                    is_active = bool(inp.get("isActive"))
                    is_preview = bool(inp.get("isPreview"))
                    break

        # Tally border styling
        border_stroke = "#334155"
        tally_text = "STANDBY"
        tally_bg = "#1e293b"
        if is_active:
            border_stroke = "#ef4444"
            tally_text = "PROGRAM / LIVE"
            tally_bg = "#dc2626"
        elif is_preview:
            border_stroke = "#10b981"
            tally_text = "PREVIEW"
            tally_bg = "#059669"

        type_lower = inp_type.lower()
        title_lower = title.lower()

        # 1. Color Bars / Test Pattern
        if "colour" in type_lower or "color" in title_lower or "bars" in title_lower or "pattern" in title_lower:
            return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <rect x="0" y="0" width="45.7" height="135" fill="#c0c0c0"/>
  <rect x="45.7" y="0" width="45.7" height="135" fill="#c0c000"/>
  <rect x="91.4" y="0" width="45.7" height="135" fill="#00c0c0"/>
  <rect x="137.1" y="0" width="45.7" height="135" fill="#00c000"/>
  <rect x="182.8" y="0" width="45.7" height="135" fill="#c000c0"/>
  <rect x="228.5" y="0" width="45.7" height="135" fill="#c00000"/>
  <rect x="274.2" y="0" width="45.8" height="135" fill="#0000c0"/>
  <rect x="0" y="135" width="64" height="45" fill="#0000c0"/>
  <rect x="64" y="135" width="64" height="45" fill="#ffffff"/>
  <rect x="128" y="135" width="64" height="45" fill="#c000c0"/>
  <rect x="192" y="135" width="64" height="45" fill="#1e1e1e"/>
  <rect x="256" y="135" width="64" height="45" fill="#000000"/>
  <rect x="0" y="0" width="320" height="180" fill="none" stroke="{border_stroke}" stroke-width="6"/>
  <rect x="10" y="10" width="55" height="24" rx="4" fill="{tally_bg}"/>
  <text x="37" y="27" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#fff" text-anchor="middle">IN {input_id}</text>
  <rect x="10" y="146" width="300" height="24" rx="4" fill="rgba(0,0,0,0.7)"/>
  <text x="160" y="163" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#f8fafc" text-anchor="middle">{title[:28]}</text>
</svg>'''

        # 2. Microphone / Audio
        if "audio" in type_lower or "mic" in title_lower:
            return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <rect width="320" height="180" fill="#0b1329"/>
  <!-- Audio spectrum waves -->
  <path d="M 20 90 Q 40 40 60 90 T 100 90 T 140 30 T 180 90 T 220 50 T 260 90 T 300 90" fill="none" stroke="#38bdf8" stroke-width="3" opacity="0.6"/>
  <path d="M 20 90 Q 50 130 80 90 T 140 150 T 200 90 T 260 130 T 300 90" fill="none" stroke="#818cf8" stroke-width="2" opacity="0.4"/>
  <!-- Mic icon -->
  <circle cx="160" cy="70" r="28" fill="#1e293b"/>
  <path d="M154 58a6 6 0 0 1 12 0v14a6 6 0 0 1-12 0V58zm-4 10a10 10 0 0 0 20 0h2a12 12 0 0 1-11 11.9v4.1h4v2h-10v-2h4v-4.1A12 12 0 0 1 148 68h2z" fill="#38bdf8"/>
  <rect x="0" y="0" width="320" height="180" fill="none" stroke="{border_stroke}" stroke-width="6"/>
  <rect x="10" y="10" width="55" height="24" rx="4" fill="{tally_bg}"/>
  <text x="37" y="27" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#fff" text-anchor="middle">IN {input_id}</text>
  <rect x="10" y="146" width="300" height="24" rx="4" fill="rgba(0,0,0,0.7)"/>
  <text x="160" y="163" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#38bdf8" text-anchor="middle">{title[:28]} (AUDIO)</text>
</svg>'''

        # 3. Screen Share / PPT / Desktop
        if "desktop" in type_lower or "ppt" in title_lower or "screen" in title_lower:
            return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <rect width="320" height="180" fill="#0f172a"/>
  <!-- Presentation slide mockup -->
  <rect x="40" y="30" width="240" height="120" rx="6" fill="#1e293b" stroke="#334155" stroke-width="2"/>
  <rect x="55" y="45" width="90" height="12" rx="3" fill="#38bdf8"/>
  <rect x="55" y="65" width="130" height="6" rx="2" fill="#64748b"/>
  <rect x="55" y="77" width="110" height="6" rx="2" fill="#64748b"/>
  <rect x="55" y="89" width="120" height="6" rx="2" fill="#64748b"/>
  <!-- Mini chart -->
  <rect x="195" y="80" width="12" height="40" rx="2" fill="#10b981"/>
  <rect x="213" y="60" width="12" height="60" rx="2" fill="#3b82f6"/>
  <rect x="231" y="45" width="12" height="75" rx="2" fill="#f59e0b"/>
  <rect x="249" y="70" width="12" height="50" rx="2" fill="#8b5cf6"/>
  <rect x="0" y="0" width="320" height="180" fill="none" stroke="{border_stroke}" stroke-width="6"/>
  <rect x="10" y="10" width="55" height="24" rx="4" fill="{tally_bg}"/>
  <text x="37" y="27" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#fff" text-anchor="middle">IN {input_id}</text>
  <rect x="10" y="146" width="300" height="24" rx="4" fill="rgba(0,0,0,0.7)"/>
  <text x="160" y="163" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#f8fafc" text-anchor="middle">{title[:28]}</text>
</svg>'''

        # 4. Video Clip
        if "video" in type_lower or "clip" in title_lower or "intro" in title_lower:
            return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <defs>
    <linearGradient id="vidbg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1e1b4b" />
      <stop offset="100%" stop-color="#0f172a" />
    </linearGradient>
  </defs>
  <rect width="320" height="180" fill="url(#vidbg)"/>
  <circle cx="160" cy="80" r="26" fill="rgba(255,255,255,0.15)"/>
  <polygon points="152,66 174,80 152,94" fill="#ffffff"/>
  <!-- Progress bar -->
  <rect x="30" y="130" width="260" height="4" rx="2" fill="#334155"/>
  <rect x="30" y="130" width="110" height="4" rx="2" fill="#a855f7"/>
  <rect x="0" y="0" width="320" height="180" fill="none" stroke="{border_stroke}" stroke-width="6"/>
  <rect x="10" y="10" width="55" height="24" rx="4" fill="{tally_bg}"/>
  <text x="37" y="27" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#fff" text-anchor="middle">IN {input_id}</text>
  <rect x="10" y="146" width="300" height="24" rx="4" fill="rgba(0,0,0,0.7)"/>
  <text x="160" y="163" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#f8fafc" text-anchor="middle">{title[:28]}</text>
</svg>'''

        # 5. NDI Video Source (Live IP Feed)
        if "ndi" in type_lower or "ndi" in title_lower:
            time_tc = time.strftime("%H:%M:%S")
            tc_frame = int((time.time() * 10) % 60)
            return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <defs>
    <linearGradient id="ndibg{input_id}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#042f2e"/>
      <stop offset="100%" stop-color="#021a19"/>
    </linearGradient>
  </defs>
  <rect width="320" height="180" fill="url(#ndibg{input_id})"/>
  <!-- NDI Video Matrix Grid -->
  <path d="M 30 50 L 290 50 M 30 90 L 290 90 M 30 130 L 290 130" stroke="#0d9488" stroke-width="0.75" opacity="0.3"/>
  <path d="M 80 20 L 80 160 M 160 20 L 160 160 M 240 20 L 240 160" stroke="#0d9488" stroke-width="0.75" opacity="0.3"/>
  <!-- NDI Badge & Network Pulse -->
  <rect x="25" y="65" width="60" height="28" rx="4" fill="#0d9488"/>
  <text x="55" y="84" font-family="-apple-system, sans-serif" font-size="14" font-weight="900" fill="#ffffff" text-anchor="middle">NDI®</text>
  <circle cx="160" cy="80" r="26" fill="#115e59" stroke="#14b8a6" stroke-width="2"/>
  <polygon points="152,68 174,80 152,92" fill="#2dd4bf"/>
  <!-- Live Signal Pill -->
  <rect x="220" y="68" width="75" height="22" rx="3" fill="rgba(13, 148, 136, 0.25)" stroke="#14b8a6" stroke-width="1"/>
  <circle cx="230" cy="79" r="4" fill="#2dd4bf"/>
  <text x="260" y="83" font-family="-apple-system, sans-serif" font-size="10" font-weight="bold" fill="#2dd4bf" text-anchor="middle">IP: LIVE</text>
  <!-- Frame & Tally -->
  <rect x="0" y="0" width="320" height="180" fill="none" stroke="{border_stroke}" stroke-width="6"/>
  <rect x="10" y="10" width="55" height="24" rx="4" fill="{tally_bg}"/>
  <text x="37" y="27" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#fff" text-anchor="middle">IN {input_id}</text>
  <!-- Top Right Timecode -->
  <rect x="195" y="10" width="115" height="20" rx="3" fill="rgba(0,0,0,0.6)"/>
  <text x="252" y="24" font-family="monospace" font-size="10" font-weight="bold" fill="#2dd4bf" text-anchor="middle">NDI {time_tc}:{tc_frame:02d}</text>
  <!-- Bottom info bar -->
  <rect x="10" y="146" width="300" height="24" rx="4" fill="rgba(0,0,0,0.8)"/>
  <text x="160" y="163" font-family="-apple-system, sans-serif" font-size="13" font-weight="bold" fill="#ffffff" text-anchor="middle">{title[:28]}</text>
</svg>'''

        # 6. Studio Camera (Default)
        cam_colors = ["#1e293b", "#0f172a", "#172554", "#14532d", "#312e81"]
        bg_c = cam_colors[int(input_id) % len(cam_colors)] if str(input_id).isdigit() else "#0f172a"
        time_tc = time.strftime("%H:%M:%S")
        tc_frame = int((time.time() * 10) % 60)

        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <defs>
    <radialGradient id="camlight{input_id}" cx="50%" cy="40%" r="60%">
      <stop offset="0%" stop-color="#3b82f6" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="{bg_c}" stop-opacity="1"/>
    </radialGradient>
  </defs>
  <rect width="320" height="180" fill="url(#camlight{input_id})"/>
  <!-- Viewfinder reticle -->
  <path d="M 25 35 L 25 25 L 35 25 M 295 25 L 305 25 L 305 35 M 25 125 L 25 135 L 35 135 M 295 135 L 305 135 L 305 125" stroke="#94a3b8" stroke-width="2" fill="none" opacity="0.6"/>
  <!-- Center crosshair -->
  <line x1="150" y1="80" x2="170" y2="80" stroke="#94a3b8" stroke-width="1.5" opacity="0.4"/>
  <line x1="160" y1="70" x2="160" y2="90" stroke="#94a3b8" stroke-width="1.5" opacity="0.4"/>
  <!-- Camera icon & number -->
  <circle cx="160" cy="78" r="28" fill="#1e293b" stroke="#334155" stroke-width="2"/>
  <text x="160" y="87" font-family="-apple-system, sans-serif" font-size="24" font-weight="900" fill="#f8fafc" text-anchor="middle">C{input_id}</text>
  <!-- Frame & Tally -->
  <rect x="0" y="0" width="320" height="180" fill="none" stroke="{border_stroke}" stroke-width="6"/>
  <rect x="10" y="10" width="55" height="24" rx="4" fill="{tally_bg}"/>
  <text x="37" y="27" font-family="-apple-system, sans-serif" font-size="12" font-weight="bold" fill="#fff" text-anchor="middle">IN {input_id}</text>
  <!-- Top Right Live TC & 1080p Badge -->
  <rect x="195" y="10" width="115" height="20" rx="3" fill="rgba(0,0,0,0.6)"/>
  <text x="252" y="24" font-family="monospace" font-size="10" font-weight="bold" fill="#38bdf8" text-anchor="middle">REC {time_tc}:{tc_frame:02d}</text>
  <!-- Bottom info bar -->
  <rect x="10" y="146" width="300" height="24" rx="4" fill="rgba(0,0,0,0.75)"/>
  <text x="160" y="163" font-family="-apple-system, sans-serif" font-size="13" font-weight="bold" fill="#ffffff" text-anchor="middle">{title[:28]}</text>
</svg>'''

vmix_client = VMixClient()

