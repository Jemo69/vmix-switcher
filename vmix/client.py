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
            "switcherMode": cfg.get("switcherMode", "direct")
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
            full_state.get("defaultTransition"),
            full_state.get("transitionDuration"),
            full_state.get("switcherMode"),
            len(visible_inputs),
            tuple((i["number"], i.get("isActive"), i.get("isPreview"), tuple(i.get("activeOverlays", [])), i.get("muted"), i.get("customTitle"), i.get("isIgnored")) for i in all_inputs)
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
        now = time.time()
        cache_key = str(input_id)
        if cache_key in self._thumb_cache:
            ts, data, mime = self._thumb_cache[cache_key]
            if now - ts < 1.0:  # 1s cache
                return data, mime

        cfg = config_manager.get()
        if cfg.get("mockMode", False) or not self.connected:
            # Generate SVG placeholder
            svg = self._generate_mock_svg(str(input_id))
            data = svg.encode("utf-8")
            self._thumb_cache[cache_key] = (now, data, "image/svg+xml")
            return data, "image/svg+xml"

        host = cfg.get("vmixHost", "127.0.0.1")
        port = cfg.get("vmixPort", 8088)
        # vMix Thumbnail URL: Thumbnail.aspx?Input=X
        param_name = "Key" if "-" in str(input_id) else "Input"
        url = f"http://{host}:{port}/Thumbnail.aspx?{param_name}={urllib.parse.quote(str(input_id))}"

        try:
            raw_bytes = await asyncio.to_thread(self._fetch_binary, url, 1.5)
            self._thumb_cache[cache_key] = (now, raw_bytes, "image/jpeg")
            return raw_bytes, "image/jpeg"
        except Exception:
            # Fallback to SVG
            svg = self._generate_mock_svg(str(input_id))
            data = svg.encode("utf-8")
            return data, "image/svg+xml"

    def _generate_mock_svg(self, input_id: str) -> str:
        # Find input title if available
        title = f"Input {input_id}"
        inp_type = "Source"
        if self.last_state:
            for inp in self.last_state.get("allInputs", []):
                if str(inp.get("number")) == input_id or str(inp.get("key")) == input_id:
                    title = inp.get("customTitle") or inp.get("shortTitle") or inp.get("title") or title
                    inp_type = inp.get("type", "Source")
                    break

        return f'''<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180" viewBox="0 0 320 180">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#182238" />
      <stop offset="100%" stop-color="#0b1120" />
    </linearGradient>
  </defs>
  <rect width="320" height="180" fill="url(#bg)"/>
  <circle cx="160" cy="75" r="32" fill="#2563eb" fill-opacity="0.2"/>
  <text x="160" y="83" font-family="-apple-system, sans-serif" font-size="28" font-weight="bold" fill="#60a5fa" text-anchor="middle">{input_id}</text>
  <text x="160" y="125" font-family="-apple-system, sans-serif" font-size="14" font-weight="600" fill="#e2e8f0" text-anchor="middle">{title[:28]}</text>
  <text x="160" y="145" font-family="-apple-system, sans-serif" font-size="11" fill="#94a3b8" text-anchor="middle">{inp_type}</text>
</svg>'''

vmix_client = VMixClient()
