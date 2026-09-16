"""Low-latency live Program capture for the vMix Web Switcher.

Why this module exists
----------------------
vMix's ``SnapshotInput`` HTTP API renders one JPEG at a time (serial,
~0.6-1.0s per render, shared across every input). That path can never
deliver motion video: ~1 fresh frame/sec TOTAL no matter how fast the
browser polls. Polling faster only re-receives the same bytes (HTTP 304).

This module takes a different, honest path: it captures the pixels vMix
is already rendering on the vMix PC's own display (the documented setup
runs this server ON the vMix PC) and serves them as an MJPEG stream:

* 10-30 real frames/sec (measured 27 fps @960x540 on a modest box),
* ~200-400ms glass-to-glass latency (vs ~10s for LiveLAN HLS),
* zero external services, zero new binaries: ``mss`` + ``Pillow`` bundle
  into the single-file exe like everything else.

Recommended production setup: in vMix, Settings -> Outputs -> Fullscreen
-> send Program to a second monitor, then point ``liveCapMonitor`` at
that monitor for a clean full-frame Program feed. Without a second
monitor it captures whatever is on the chosen monitor (vMix UI included)
-- still smooth, still current, just not a clean feed.

Safety rules (trust-critical, do NOT relax):
* Capture runs ONLY when the server is on the vMix PC (loopback or local
  interface IP) and mockMode is off. A remote server must never stream
  its own desktop pretending to be the Program feed.
* Failures degrade to an honest placeholder slate + status reason, never
  to a frozen frame presented as live.
"""

import io
import threading
import time
from typing import Any, Dict, Optional, Tuple

# Target bounds (also enforced on the /api/config lane).
MIN_FPS = 5
MAX_FPS = 30
MIN_WIDTH = 320
MAX_WIDTH = 1920
MIN_QUALITY = 40
MAX_QUALITY = 90
MAX_MONITOR = 16


def clamp_fps(v: Any) -> int:
    try:
        return min(MAX_FPS, max(MIN_FPS, int(float(v))))
    except (TypeError, ValueError):
        return 25


def clamp_monitor(v: Any) -> int:
    try:
        return min(MAX_MONITOR, max(0, int(float(v))))
    except (TypeError, ValueError):
        return 1


def clamp_width(v: Any) -> int:
    try:
        return min(MAX_WIDTH, max(MIN_WIDTH, int(float(v))))
    except (TypeError, ValueError):
        return 960


def clamp_quality(v: Any) -> int:
    try:
        return min(MAX_QUALITY, max(MIN_QUALITY, int(float(v))))
    except (TypeError, ValueError):
        return 70


class LiveCapture:
    """Threaded screen capture -> latest-JPEG holder.

    The worker loop owns one ``mss`` screenshotter and re-reads its
    targets every tick, so Settings changes (fps / monitor / size /
    quality) apply live with no restart. Readers always get the newest
    complete JPEG; a slow reader never blocks the capturer and a slow
    capturer just yields an older timestamp (surfaced via status).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[bytes] = None
        self._frame_time: float = 0.0
        self._frame_w: int = 0
        self._frame_h: int = 0
        self._fps_ema: Optional[float] = None
        self._grab_ms_ema: Optional[float] = None
        self._error: Optional[str] = None
        self._monitor_used: int = 1
        self._monitor_count: int = 0
        self._source: str = "idle"  # idle | monitor | stopped | error
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        # Live targets (written by configure(), read by the worker).
        self._target_fps = 25
        self._target_monitor = 1
        self._target_width = 960
        self._target_quality = 70
        self._placeholder_cache: Dict[str, bytes] = {}

    # -- control ----------------------------------------------------
    def configure(self, fps: int, monitor: int, width: int, quality: int) -> None:
        self._target_fps = clamp_fps(fps)
        self._target_monitor = clamp_monitor(monitor)
        self._target_width = clamp_width(width)
        self._target_quality = clamp_quality(quality)

    def start(self) -> bool:
        """Start the worker if not already running. True if running after."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return True
            self._stop.clear()
            self._error = None
            self._thread = threading.Thread(
                target=self._loop, name="vmix-livecap", daemon=True
            )
            self._thread.start()
            return True

    def stop(self, reason: str = "stopped") -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            self._source = "stopped"
            if reason and not self._error:
                self._error = reason

    def is_running(self) -> bool:
        t = self._thread
        return bool(t is not None and t.is_alive())

    # -- readers ----------------------------------------------------
    def latest(self) -> Tuple[Optional[bytes], float]:
        with self._lock:
            return self._frame, self._frame_time

    def frame_age(self) -> Optional[float]:
        with self._lock:
            if self._frame is None:
                return None
            return time.time() - self._frame_time

    def status(self) -> Dict[str, Any]:
        with self._lock:
            running = bool(
                self._thread is not None and self._thread.is_alive()
            )
            age = time.time() - self._frame_time if self._frame else None
            return {
                "running": running,
                "source": self._source if running else "stopped",
                "monitorRequested": self._target_monitor,
                "monitorUsed": self._monitor_used,
                "monitorCount": self._monitor_count,
                "fpsTarget": self._target_fps,
                "fpsActual": round(self._fps_ema, 1)
                if self._fps_ema is not None
                else 0.0,
                "grabMs": round(self._grab_ms_ema, 1)
                if self._grab_ms_ema is not None
                else 0.0,
                "width": self._frame_w,
                "height": self._frame_h,
                "frameAgeSec": round(age, 2) if age is not None else None,
                "frameBytes": len(self._frame) if self._frame else 0,
                "error": self._error,
            }

    def placeholder(self, reason: str) -> bytes:
        """Honest slate JPEG so an <img> never shows a stale 'live' frame."""
        key = (reason or "unavailable")[:80]
        with self._lock:
            hit = self._placeholder_cache.get(key)
        if hit:
            return hit
        try:
            from PIL import Image, ImageDraw
        except Exception:
            # Pillow missing (shouldn't happen -- it's required): tiny valid JPEG header fallback
            return (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                b"\xff\xd9"
            )
        w, h = 960, 540
        img = Image.new("RGB", (w, h), (9, 13, 22))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, w - 1, h - 1], outline=(51, 65, 85), width=6)
        d.text((40, 200), "LIVE UNAVAILABLE", fill=(248, 250, 252))
        d.text((40, 250), key[:90], fill=(148, 163, 184))
        d.text(
            (40, 300),
            "Run this server on the vMix PC and enable live capture.",
            fill=(148, 163, 184),
        )
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=60)
        data = buf.getvalue()
        with self._lock:
            if len(self._placeholder_cache) > 8:
                self._placeholder_cache.clear()
            self._placeholder_cache[key] = data
        return data

    # -- worker -----------------------------------------------------
    def _loop(self) -> None:
        try:
            import mss  # type: ignore
        except Exception as err:
            with self._lock:
                self._error = f"screen capture unavailable (mss import: {err})"
                self._source = "error"
            return
        try:
            from PIL import Image  # type: ignore
        except Exception as err:
            with self._lock:
                self._error = f"JPEG encoder unavailable (Pillow import: {err})"
                self._source = "error"
            return

        try:
            with mss.mss() as sct:
                monitors = sct.monitors  # [0] = virtual all-monitors
                with self._lock:
                    self._monitor_count = max(0, len(monitors) - 1)
                    self._source = "monitor"
                last_tick = time.time()
                while not self._stop.is_set():
                    tick = time.time()
                    fps = self._target_fps
                    want_mon = self._target_monitor
                    out_w = self._target_width
                    quality = self._target_quality
                    interval = 1.0 / max(1, fps)

                    # Resolve monitor: 0 = full virtual desktop, else clamp.
                    if want_mon <= 0 or len(monitors) <= 1:
                        idx = 0 if len(monitors) > 0 else -1
                    else:
                        idx = min(want_mon, len(monitors) - 1)
                    if idx < 0:
                        with self._lock:
                            self._error = "no displays found for capture"
                            self._source = "error"
                        self._stop.wait(1.0)
                        continue

                    t0 = time.time()
                    try:
                        shot = sct.grab(monitors[idx])
                        img = Image.frombytes(
                            "RGB", shot.size, shot.bgra, "raw", "BGRX"
                        )
                        sw, sh = img.size
                        if sw > out_w:
                            img = img.resize(
                                (out_w, max(1, round(sh * out_w / sw)))
                            )
                        buf = io.BytesIO()
                        img.save(buf, "JPEG", quality=quality)
                        data = buf.getvalue()
                    except Exception as err:
                        with self._lock:
                            self._error = f"capture failed: {err}"
                            self._source = "error"
                        self._stop.wait(1.0)
                        continue

                    grab_ms = (time.time() - t0) * 1000.0
                    dt = tick - last_tick
                    last_tick = tick
                    with self._lock:
                        self._frame = data
                        self._frame_time = time.time()
                        self._frame_w, self._frame_h = img.size
                        self._monitor_used = idx
                        self._error = None
                        self._source = "monitor"
                        if dt > 0:
                            inst = 1.0 / dt
                            self._fps_ema = (
                                inst
                                if self._fps_ema is None
                                else self._fps_ema + 0.2 * (inst - self._fps_ema)
                            )
                        self._grab_ms_ema = (
                            grab_ms
                            if self._grab_ms_ema is None
                            else self._grab_ms_ema + 0.2 * (grab_ms - self._grab_ms_ema)
                        )

                    # Pace to target fps; never sleep negative (overload sheds,
                    # readers just get the newest frame slightly less often).
                    spent = time.time() - tick
                    self._stop.wait(max(0.0, interval - spent))
        except Exception as err:  # keep the server alive no matter what
            with self._lock:
                self._error = f"capture loop crashed: {err}"
                self._source = "error"


live_capture = LiveCapture()
