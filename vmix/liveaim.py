"""Automatic aiming for the LIVE Program capture.

The problem this kills: the capture eats whole displays, and asking the
operator to guess which display number carries vMix's fullscreen Program
output is terrible UX (mirror loops, trial-and-error).

Instead the app matches what it sees: vMix already tells us which input
is on Program (the tally), and the snapshot pipeline can fetch that
input's picture. Whichever display looks most like the Program picture
IS the Program display. Zero knobs.

Matching uses zero-mean normalized cross-correlation (ZNCC) on a 64x36
probe -- deliberately invariant to brightness/gamma shifts between a
vMix-rendered JPEG snapshot and a screen-captured frame, and cheap
enough (~2k pixels) to score every display in milliseconds. No numpy,
no new dependencies: pure Pillow + math, bundles like everything else.

Honesty rules:
* A minimum score is required. No confident match -> report "not found"
  (operator still needs vMix fullscreen Program output on some display)
  instead of pointing at a random desktop.
* The browser-mirror scores low by construction: the Program picture
  inside our own hero tile is a few pixels across at probe size.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

PROBE_SIZE = (64, 36)
MIN_MATCH_SCORE = 0.45
AUTO_FRESH_SEC = 120.0


def probe(image) -> Tuple[List[float], List[float], List[float]]:
    """Downscale to probe size, return per-channel 0..1 pixel lists."""
    rgb = image.convert("RGB").resize(PROBE_SIZE)
    px = list(rgb.getdata())
    r = [p[0] / 255.0 for p in px]
    g = [p[1] / 255.0 for p in px]
    b = [p[2] / 255.0 for p in px]
    return r, g, b


def _center_crop_to_aspect(image, aspect: float):
    """Crop (centered, like a fullscreen 'fit' output) to target w/h."""
    w, h = image.size
    if w <= 0 or h <= 0 or aspect <= 0:
        return image
    cur = w / h
    if abs(cur - aspect) < 0.03:
        return image
    if cur > aspect:  # too wide: trim sides (pillarbox case)
        nw = max(1, int(h * aspect))
        x0 = max(0, (w - nw) // 2)
        return image.crop((x0, 0, x0 + nw, h))
    else:  # too tall: trim top/bottom (letterbox case)
        nh = max(1, int(w / aspect))
        y0 = max(0, (h - nh) // 2)
        return image.crop((0, y0, w, y0 + nh))


def _strip_bars(image):
    """Crop solid-black letter/pillarbox bars (vMix 'fit' output bars are pure black)."""
    g = image.convert("L").resize(PROBE_SIZE)
    w, h = g.size
    px = list(g.getdata())
    rows = [px[y * w:(y + 1) * w] for y in range(h)]
    cols = [[px[y * w + x] for y in range(h)] for x in range(w)]
    top = 0
    while top < h - 4 and sum(rows[top]) / w < 10:
        top += 1
    bot = h - 1
    while bot > top + 4 and sum(rows[bot]) / w < 10:
        bot -= 1
    left = 0
    while left < w - 4 and sum(cols[left]) / h < 10:
        left += 1
    right = w - 1
    while right > left + 4 and sum(cols[right]) / h < 10:
        right -= 1
    if top == 0 and bot == h - 1 and left == 0 and right == w - 1:
        return None  # no bars found
    # Map probe coords back to full resolution.
    fw, fh = image.size
    return image.crop((
        int(left / w * fw), int(top / h * fh),
        int((right + 1) / w * fw), int((bot + 1) / h * fh),
    ))
    """Crop (centered, like a fullscreen 'fit' output) to target w/h."""
    w, h = image.size
    if w <= 0 or h <= 0 or aspect <= 0:
        return image
    cur = w / h
    if abs(cur - aspect) < 0.03:
        return image
    if cur > aspect:  # too wide: trim sides (pillarbox case)
        nw = max(1, int(h * aspect))
        x0 = max(0, (w - nw) // 2)
        return image.crop((x0, 0, x0 + nw, h))
    else:  # too tall: trim top/bottom (letterbox case)
        nh = max(1, int(w / aspect))
        y0 = max(0, (h - nh) // 2)
        return image.crop((0, y0, w, y0 + nh))


def _zncc(a: List[float], b: List[float]) -> float:
    n = len(a)
    if n == 0:
        return 0.0
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a)
    db = sum((y - mb) ** 2 for y in b)
    if da <= 0 or db <= 0:
        return 1.0 if da == db else 0.0
    return max(-1.0, min(1.0, num / math.sqrt(da * db)))


def _sim_probes(rp, cp) -> float:
    rs = [_zncc(rp[i], cp[i]) for i in range(3)]
    return max(0.0, sum(rs) / 3.0)
    n = len(a)
    if n == 0:
        return 0.0
    ma = sum(a) / n
    mb = sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a)
    db = sum((y - mb) ** 2 for y in b)
    if da <= 0 or db <= 0:
        return 1.0 if da == db else 0.0
    return max(-1.0, min(1.0, num / math.sqrt(da * db)))


def similarity(ref_image, cand_image) -> float:
    """0..1 content match between two pictures (1 = identical content).

    Invariant to uniform brightness/contrast shifts, robust to small
    resizes and aspect crops. Different scenes score near ~0.2-0.4,
    same scene scores ~0.7-1.0 even across snapshot-vs-screen domains.
    """
    try:
        rp = probe(ref_image)
        cp = probe(cand_image)
    except Exception:
        return 0.0
    best = _sim_probes(rp, cp)
    # Fullscreen outputs letter/pillarbox non-matching aspects: also try
    # the candidate center-cropped to the reference aspect, plus explicit
    # black-bar stripping (same-aspect insets). Keep the max.
    try:
        w, h = cand_image.size
        if w > 0 and h > 0:
            aspect = ref_image.size[0] / max(1, ref_image.size[1])
            if abs((w / h) - aspect) >= 0.03:
                alt = _sim_probes(rp, probe(_center_crop_to_aspect(cand_image, aspect)))
                best = max(best, alt)
            stripped = _strip_bars(cand_image)
            if stripped is not None:
                sw, sh = stripped.size
                if sw >= 16 and sh >= 16:
                    alt2 = _sim_probes(rp, probe(_center_crop_to_aspect(stripped, aspect)))
                    best = max(best, alt2)
    except Exception:
        pass
    return best


def score_against_ref(ref_image, candidates) -> List[Tuple[int, float]]:
    """Score [(monitor_idx, score)] for candidate PIL images (index-aligned)."""
    out: List[Tuple[int, float]] = []
    for idx, cand in candidates:
        try:
            out.append((idx, similarity(ref_image, cand)))
        except Exception:
            out.append((idx, 0.0))
    return out


def aim_once(ref_image, exclude_idx: Optional[int] = None) -> Dict[str, Any]:
    """Grab every physical display and score it against the Program picture.

    Returns {monitorCount, bestIdx, bestScore, scores, error}. bestIdx is
    None when nothing passes MIN_MATCH_SCORE. exclude_idx (e.g. a display
    known to carry only this browser) is still scored for transparency
    but can never win.
    """
    try:
        import mss  # type: ignore
    except Exception as err:
        return {"monitorCount": 0, "bestIdx": None, "bestScore": 0.0,
                "scores": [], "error": f"screen capture unavailable: {err}"}
    try:
        from PIL import Image  # type: ignore
    except Exception as err:
        return {"monitorCount": 0, "bestIdx": None, "bestScore": 0.0,
                "scores": [], "error": f"image lib unavailable: {err}"}

    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            count = max(0, len(monitors) - 1)
            if count <= 0:
                return {"monitorCount": 0, "bestIdx": None, "bestScore": 0.0,
                        "scores": [], "error": "no displays found"}
            cands = []
            for idx in range(1, len(monitors)):
                try:
                    shot = sct.grab(monitors[idx])
                    img = Image.frombytes(
                        "RGB", shot.size, shot.bgra, "raw", "BGRX"
                    )
                    cands.append((idx, img))
                except Exception:
                    continue
    except Exception as err:
        return {"monitorCount": 0, "bestIdx": None, "bestScore": 0.0,
                "scores": [], "error": f"display scan failed: {err}"}

    scored = score_against_ref(ref_image, cands)
    scored.sort(key=lambda t: t[1], reverse=True)
    best_idx: Optional[int] = None
    best_score = 0.0
    for idx, score in scored:
        if exclude_idx is not None and idx == exclude_idx:
            continue
        best_idx, best_score = idx, score
        break
    if best_idx is None or best_score < MIN_MATCH_SCORE:
        return {"monitorCount": count, "bestIdx": None,
                "bestScore": round(best_score, 3),
                "scores": [(i, round(s, 3)) for i, s in scored],
                "error": None}
    return {"monitorCount": count, "bestIdx": best_idx,
            "bestScore": round(best_score, 3),
            "scores": [(i, round(s, 3)) for i, s in scored],
            "error": None}
