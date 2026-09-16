"""Per-input live tiles sliced from vMix's MultiView fullscreen output.

The endgame for switch-with-confidence: the operator must see EVERY
source's current state before cutting to it. Per-input snapshots can't
do that (serial renders, ~1 fresh frame/sec shared). But vMix can paint
every input onto ONE screen at once (Settings -> Outputs -> Fullscreen
-> MultiView on a second monitor) -- a single 25fps capture then carries
all sources, and this module slices it back into per-input live tiles.

Everything is automatic, no knobs:
* Layout learning tries uniform grids (2x2, 3x3, 4x4), matches each
  input's snapshot against each cell with the motion-proof combined
  signal (ZNCC structure + palette correlation), and greedily assigns
  exclusive best fits. Best layout above threshold wins.
* Cells are served as cropped MJPEG tiles; a shared crop cache keyed on
  (input, size, quality, master-frame timestamp) bounds CPU no matter
  how many crew devices watch.
* No confident layout -> no tiles, snapshots keep working. Never a
  wrong tile presented as live.

Single binary, zero external services: Pillow only.
"""

import io
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .liveaim import (
    MIN_MATCH_SCORE,
    PROBE_SIZE,
    hist_corr,
    match_score,
    probe,
    similarity,
)

GRIDS: List[Tuple[str, int, int]] = [("2x2", 2, 2), ("3x3", 3, 3), ("4x4", 4, 4)]
CELL_INSET = 0.02  # dodge multiview grid gaps/borders
MIN_LAYOUT_SCORE = 0.5
MIN_ASSIGNED = 2  # single-input shows are covered by the program path
MAX_INPUTS = 16

# Tile serve profile (fixed: the user asked for less config, not more).
TILE_W = 384
TILE_FPS = 10
TILE_Q = 62
MON_W = 960
MON_FPS = 25
MON_Q = 70


def grid_cells(cols: int, rows: int, inset: float = CELL_INSET) -> List[Tuple[float, float, float, float]]:
    """Cell rects as (x, y, w, h) fractions of the frame."""
    out = []
    for r in range(rows):
        for c in range(cols):
            out.append((
                (c / cols) + inset / cols,
                (r / rows) + inset / rows,
                (1 / cols) * (1 - 2 * inset),
                (1 / rows) * (1 - 2 * inset),
            ))
    return out


def _crop_frac(image, rect: Tuple[float, float, float, float]):
    w, h = image.size
    x, y, cw, ch = rect
    return image.crop((
        max(0, int(x * w)), max(0, int(y * h)),
        min(w, int((x + cw) * w)), min(h, int((y + ch) * h)),
    ))


def learn_layout(frame_image, refs: List[Tuple[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the grid + input->cell assignment best explaining this frame.

    refs: [(input_key, PIL image)] (JPEG snapshots only, never placeholders).
    Returns {layout, cols, rows, cells: {key: rect}, score} or None.
    """
    refs = [(k, im) for k, im in refs[:MAX_INPUTS] if im is not None]
    if len(refs) < MIN_ASSIGNED:
        return None
    try:
        fw, fh = frame_image.size
        if fw <= 0 or fh <= 0:
            return None
    except Exception:
        return None

    best: Optional[Dict[str, Any]] = None
    for name, cols, rows in GRIDS:
        cells = grid_cells(cols, rows)
        try:
            cell_imgs = [_crop_frac(frame_image, r) for r in cells]
        except Exception:
            continue
        # Score matrix with the motion-proof combined signal.
        scored: List[Tuple[float, int, int]] = []  # (score, ref_idx, cell_idx)
        for ri, (_key, ref) in enumerate(refs):
            for ci, cell in enumerate(cell_imgs):
                try:
                    scored.append((match_score(ref, cell), ri, ci))
                except Exception:
                    continue
        # Greedy exclusive assignment, best pair first.
        scored.sort(reverse=True)
        used_refs, used_cells, pairs = set(), set(), []
        for s, ri, ci in scored:
            if ri in used_refs or ci in used_cells:
                continue
            if s < MIN_MATCH_SCORE:
                break
            used_refs.add(ri)
            used_cells.add(ci)
            pairs.append((refs[ri][0], ci, s))
            if len(pairs) >= min(len(refs), len(cells)):
                break
        if len(pairs) < MIN_ASSIGNED:
            continue
        mean_s = sum(p[2] for p in pairs) / len(pairs)
        if mean_s < MIN_LAYOUT_SCORE:
            continue
        cand = {"layout": name, "cols": cols, "rows": rows,
                "cells": {k: cells[ci] for k, ci, _s in pairs},
                "score": round(mean_s, 3), "assigned": len(pairs)}
        if best is None or cand["score"] > best["score"]:
            best = cand
    return best


def scan_displays(refs: List[Tuple[str, bytes]], program_key: Optional[str]) -> Dict[str, Any]:
    """One mss session: score every display for program-fullscreen AND multiview.

    refs: [(input_key, snapshot JPEG bytes)]. Returns {mode, display,
    programScore, layout, monitorCount, error} where mode is
    'multi' | 'program' | 'none'. Multiview wins ties: it is a superset.
    """
    try:
        import mss  # type: ignore
    except Exception as err:
        return {"mode": "none", "display": None, "programScore": 0.0,
                "layout": None, "monitorCount": 0,
                "error": f"screen capture unavailable: {err}"}
    try:
        from PIL import Image  # type: ignore
    except Exception as err:
        return {"mode": "none", "display": None, "programScore": 0.0,
                "layout": None, "monitorCount": 0,
                "error": f"image lib unavailable: {err}"}

    try:
        decoded = [(k, Image.open(io.BytesIO(b)).convert("RGB")) for k, b in refs]
    except Exception as err:
        return {"mode": "none", "display": None, "programScore": 0.0,
                "layout": None, "monitorCount": 0,
                "error": f"bad reference pictures: {err}"}
    prog_ref = None
    if program_key is not None:
        for k, im in decoded:
            if k == program_key:
                prog_ref = im
                break

    try:
        import mss as _mss
        with _mss.mss() as sct:
            monitors = sct.monitors
            count = max(0, len(monitors) - 1)
            if count <= 0:
                return {"mode": "none", "display": None, "programScore": 0.0,
                        "layout": None, "monitorCount": 0, "error": "no displays found"}
            frames = []
            for idx in range(1, len(monitors)):
                try:
                    shot = sct.grab(monitors[idx])
                    frames.append((idx, Image.frombytes(
                        "RGB", shot.size, shot.bgra, "raw", "BGRX")))
                except Exception:
                    continue
    except Exception as err:
        return {"mode": "none", "display": None, "programScore": 0.0,
                "layout": None, "monitorCount": 0,
                "error": f"display scan failed: {err}"}
    if not frames:
        return {"mode": "none", "display": None, "programScore": 0.0,
                "layout": None, "monitorCount": count, "error": "could not grab any display"}

    best_multi = None
    best_prog: Tuple[Optional[int], float] = (None, 0.0)
    for idx, frame in frames:
        layout = learn_layout(frame, decoded)
        if layout is not None and (best_multi is None or layout["score"] > best_multi[1]["score"]):
            best_multi = (idx, layout)
        if prog_ref is not None:
            try:
                s = similarity(prog_ref, frame)
            except Exception:
                s = 0.0
            if s > best_prog[1]:
                best_prog = (idx, s)

    if best_multi is not None:
        idx, layout = best_multi
        return {"mode": "multi", "display": idx, "programScore": round(best_prog[1], 3),
                "layout": layout, "monitorCount": count, "error": None}
    if best_prog[0] is not None and best_prog[1] >= MIN_MATCH_SCORE:
        return {"mode": "program", "display": best_prog[0],
                "programScore": round(best_prog[1], 3), "layout": None,
                "monitorCount": count, "error": None}
    return {"mode": "none", "display": None, "programScore": round(best_prog[1], 3),
            "layout": None, "monitorCount": count, "error": None}


class TileState:
    """Learned layout + shared crop cache (bounds CPU across viewers)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cells: Dict[str, Tuple[float, float, float, float]] = {}
        self._layout: Optional[str] = None
        self._score: float = 0.0
        self._display: Optional[int] = None
        self._at: float = 0.0
        self._cache: Dict[Tuple[str, int, int], Tuple[float, bytes]] = {}

    def set(self, display: int, layout: Dict[str, Any]) -> None:
        with self._lock:
            self._cells = dict(layout.get("cells", {}))
            self._layout = layout.get("layout")
            self._score = float(layout.get("score") or 0.0)
            self._display = int(display)
            self._at = time.time()
            self._cache.clear()

    def clear(self) -> None:
        with self._lock:
            self._cells = {}
            self._layout = None
            self._score = 0.0
            self._display = None
            self._at = 0.0
            self._cache.clear()

    def has(self, key: str) -> bool:
        with self._lock:
            return str(key) in self._cells

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._cells.keys())

    def info(self) -> Dict[str, Any]:
        with self._lock:
            return {"layout": self._layout, "score": round(self._score, 3),
                    "display": self._display, "tiles": len(self._cells),
                    "ageSec": round(time.time() - self._at, 1) if self._at else None}

    def crop(self, frame_bytes: bytes, frame_ts: float, key: str,
             width: int, quality: int) -> Optional[bytes]:
        """Crop+encode one tile, reusing bytes for the same master frame."""
        with self._lock:
            rect = self._cells.get(str(key))
            if rect is None:
                return None
            hit = self._cache.get((str(key), width, quality))
            if hit is not None and hit[0] == frame_ts:
                return hit[1]
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
            tile = _crop_frac(img, rect)
            tw = max(1, min(width, tile.size[0]))
            if tile.size[0] > tw:
                tile = tile.resize((tw, max(1, round(tile.size[1] * tw / tile.size[0]))))
            buf = io.BytesIO()
            tile.save(buf, "JPEG", quality=quality)
            data = buf.getvalue()
        except Exception:
            return None
        with self._lock:
            if len(self._cache) > 64:
                self._cache.clear()
            self._cache[(str(key), width, quality)] = (frame_ts, data)
        return data


tile_state = TileState()
