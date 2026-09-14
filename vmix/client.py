import asyncio
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Callable, Dict, List, Optional

from .config import config_manager
from .mock import mock_vmix

class VMixClient:
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

    def _fetch_binary(self, url: str, timeout: float = 1.5) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "vMix-Web-Switcher/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

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
                "activeOverlays": active_overlays
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

            all_inputs.append({
                **inp,
                "customTitle": custom_title,
                "customColor": custom_color,
                "isIgnored": is_ignored
            })

        visible_inputs = [i for i in all_inputs if not i["isIgnored"]]

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
            "previewFps": self._preview_fps()
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
            len(visible_inputs),
            tuple((i["number"], i.get("isActive"), i.get("isPreview"), tuple(i.get("activeOverlays", [])), i.get("muted"), i.get("volume"), i.get("customTitle"), i.get("isIgnored")) for i in all_inputs)
        )

        now = time.time()
        if sig != self._last_signature or (now - self._last_broadcast_time > 5.0):
            self._last_signature = sig
            self._last_broadcast_time = now
            self._notify(full_state)

        return full_state

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

    def _thumb_cache_ttl(self) -> float:
        fps = self._preview_fps()
        return min(0.5, max(0.04, 0.25 / fps))

    def _preview_fps(self) -> float:
        try:
            fps = float(config_manager.get().get("previewFps", 4))
        except (TypeError, ValueError):
            fps = 4.0
        return min(10.0, max(0.5, fps))

    async def _load_thumbnail(self, target_id: Any, cache_key: str) -> tuple[bytes, str]:
        now = time.time()
        cfg = config_manager.get()

        if cfg.get("mockMode", False) or not self.connected:
            svg = self._generate_mock_svg(str(target_id))
            data = svg.encode("utf-8")
            self._thumb_cache[cache_key] = (now, data, "image/svg+xml")
            return data, "image/svg+xml"

        host = cfg.get("vmixHost", "127.0.0.1")
        port = cfg.get("vmixPort", 8088)
        param_name = "Key" if "-" in str(target_id) else "Input"
        url = f"http://{host}:{port}/Thumbnail.aspx?{param_name}={urllib.parse.quote(str(target_id))}"

        try:
            raw_bytes = await asyncio.to_thread(self._fetch_binary, url, max(0.8, 2.0 / self._preview_fps()))
            self._thumb_cache[cache_key] = (now, raw_bytes, "image/jpeg")
            return raw_bytes, "image/jpeg"
        except Exception:
            cached = self._thumb_cache.get(cache_key)
            if cached:
                return cached[1], cached[2]
            svg = self._generate_mock_svg(str(target_id))
            data = svg.encode("utf-8")
            return data, "image/svg+xml"

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

        # 5. Studio Camera (Default)
        cam_colors = ["#1e293b", "#0f172a", "#172554", "#14532d", "#312e81"]
        bg_c = cam_colors[int(input_id) % len(cam_colors)] if str(input_id).isdigit() else "#0f172a"

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
  <!-- Top Right 1080p Badge -->
  <rect x="240" y="10" width="70" height="20" rx="3" fill="rgba(0,0,0,0.6)"/>
  <text x="275" y="24" font-family="-apple-system, sans-serif" font-size="10" font-weight="bold" fill="#38bdf8" text-anchor="middle">1080p60</text>
  <!-- Bottom info bar -->
  <rect x="10" y="146" width="300" height="24" rx="4" fill="rgba(0,0,0,0.75)"/>
  <text x="160" y="163" font-family="-apple-system, sans-serif" font-size="13" font-weight="bold" fill="#ffffff" text-anchor="middle">{title[:28]}</text>
</svg>'''

vmix_client = VMixClient()

