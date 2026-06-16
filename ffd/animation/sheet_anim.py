"""Field-sprite (``fldchrN``) animation classification table.

Replaces the old "field_anm entry index == sprite img id" assumption in the
baker (there are only ~63 field_anm entries but ~218 ``fldchrN`` sheets, so
that mapping mis-keyed geometry and mis-aligned every non-character object).
Each sheet is classified **by its own pixels** into one of four modes:

* ``char``      -- 256x512 character atlas; frames come from ``field_anm``
                   entry 1 (walk) / 12 (KO) via the existing character path.
* ``static``    -- one image, drawn whole (its opaque bounding box).
* ``grid``      -- a single PNG packed with N frames; explicit per-frame rects
                   (uniform film-strips *and* the two irregular effect sheets).
* ``multifile`` -- the animation ships as separate ``fldchrN_0..K.png`` files;
                   frames are the files in order.

The classifier is deterministic and depends only on Pillow + numpy.  Two
hand-authored sheets (the fire-burst 93 and explosion 94) and a few
non-animation atlases (number font 178, palette 225, debug 203) carry embedded
overrides so the result is reproducible without scipy.

Authoritative table is baked to ``Python/data/sheet_anim.json``; regenerate with
``python -m ffd.animation.sheet_anim <proper_obb_dir>``.
"""

from __future__ import annotations

import glob
import json
import os
import re
import statistics
from pathlib import Path

# --- embedded hand-authored overrides (see discoveries.md 2026-06-15) ---------

# Sheets whose frames touch (no transparent gutter) so gutter-detection
# under-segments: force a uniform NxR grid.  ("seg") = relaxed column split.
_EXPLICIT_GRID = {
    7: ("grid", 2, 1), 103: ("grid", 2, 1), 105: ("grid", 2, 2),
    193: ("grid", 4, 1), 96: ("grid", 3, 1), 150: ("grid", 3, 1),
    212: ("seg",), 194: ("seg",),
    # 2-state doors (closed front | open side-view), 32x64 each -- frame 0 = closed.
    8: ("grid", 2, 1), 62: ("grid", 2, 1), 63: ("grid", 2, 1), 97: ("grid", 2, 1),
}

# Sheets that genuinely loop in the field (ambient effects: fire / flames).
# Everything else shows frame 0 by default -- doors/chests/props are STATE sheets,
# not animations, and must not auto-cycle (Jack's manual-annotation rule).
# Extend this set to opt a sheet into continuous animation.
_ANIM_IDS = {85, 92, 93, 94, 206, 10}  # 10 = swaying tree (multifile sway)

# Irregular effect atlases: explicit per-frame boxes (connected-component bboxes,
# verified visually 2026-06-15).  x,y,w,h.
_EXPLICIT_FRAMES = {
    93: [[3, 34, 22, 24], [6, 16, 15, 16], [28, 35, 24, 33], [35, 4, 10, 25],
         [54, 36, 21, 33], [55, 3, 18, 28], [76, 2, 34, 25], [76, 28, 89, 41],
         [4, 75, 40, 46], [50, 73, 42, 48], [98, 73, 44, 48], [148, 78, 40, 43]],
    94: [[0, 4, 26, 66], [34, 4, 95, 28], [34, 39, 93, 26], [134, 4, 87, 28],
         [136, 43, 78, 23], [224, 39, 87, 28], [226, 4, 77, 22], [2, 76, 25, 65],
         [29, 78, 103, 26], [73, 117, 14, 14], [94, 115, 18, 19], [140, 74, 28, 29],
         [180, 74, 28, 29], [218, 75, 28, 29]],
}

# Non-animation atlases: keep whole, flag the kind for the GUI.
_SPECIAL = {178: "font", 225: "palette", 203: "debug"}

# Battle-character sheets: driven by btlanm_sp.dat entry 0's 48x48-cell template
# (parse_btl_anm; verified 2026-05-27).  They are battle-only atlases, NOT field
# objects -- exclude them from field-object geometry so the engine doesn't try to
# animate them as props.
_BATTLE_CHAR_IDS = set(range(30, 50))

# Sheets that ship as multiple files BUT whose _0 is itself a packed frame atlas
# (e.g. fldchr77 airship: _0 is a 3x2 grid of 6 vehicle views; _1 is the
# propeller-spin variant). Slice _0 by its gutters instead of treating each file
# as one frame. Value is unused (marker set).
_SLICE_DESPITE_MULTIFILE = {77}

CHAR_SIZE = (256, 512)


def _runs(profile, minrun=1):
    out, s = [], None
    for i, v in enumerate(profile):
        if v and s is None:
            s = i
        elif not v and s is not None:
            if i - s >= minrun:
                out.append((s, i))
            s = None
    if s is not None and len(profile) - s >= minrun:
        out.append((s, len(profile)))
    return out


def _regular(runs):
    if len(runs) <= 1:
        return None
    widths = [e - s for s, e in runs]
    med = statistics.median(widths)
    if med > 0 and all(abs(w - med) <= max(3, 0.4 * med) for w in widths):
        return runs
    return None


def _tighten(a, fr):
    """Crop frame rect ``[x,y,w,h]`` to its opaque content bbox (alpha ``a``).
    Returns the tightened rect, or the original if the frame is empty."""
    import numpy as np
    x, y, w, h = fr
    sub = a[y:y + h, x:x + w]
    if not sub.any():
        return [int(x), int(y), int(w), int(h)]
    ys = np.where(sub.any(axis=1))[0]
    xs = np.where(sub.any(axis=0))[0]
    return [int(x + xs.min()), int(y + ys.min()),
            int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]


def _tighten_frames(a, frames, anim):
    """Tighten each frame to content for non-animated objects (doors/chests/props
    stand correctly when bottom-anchored). Looping effects keep uniform cells so
    they don't jiggle frame-to-frame."""
    if anim:
        return frames
    return [_tighten(a, f) for f in frames]


def classify_sheet(path):
    """Classify one ``fldchrN_0.png`` -> dict with ``mode`` + geometry.

    ``path`` is the ``_0`` frame; multi-file detection inspects siblings.
    """
    import numpy as np
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True

    m = re.match(r"fldchr(\d+)_0\.png$", os.path.basename(path))
    n = int(m.group(1)) if m else -1
    sibs = sorted(
        glob.glob(re.sub(r"_0\.png$", "_*.png", path)),
        key=lambda p: int(re.search(r"_(\d+)\.png$", p).group(1)))

    im = Image.open(path).convert("RGBA")
    W, H = im.size
    size = [W, H]

    if (W, H) == CHAR_SIZE:
        return {"mode": "char", "entry": 1, "size": size}
    if n in _SLICE_DESPITE_MULTIFILE:
        # _0 is a grid of vehicle views; _0/_1 are propeller-spin variants. Show the
        # first (front/down) view and ANIMATE by cycling the files at that crop, so
        # the propeller spins instead of the airship cycling through all 6 views.
        import numpy as np
        a = np.array(im)[..., 3] > 16
        col = _runs(a.any(axis=0))
        row = _runs(a.any(axis=1))
        cells = []
        for (y0, y1) in row:
            for (x0, x1) in col:
                if a[y0:y1, x0:x1].any():
                    cells.append(_tighten(a, [x0, y0, x1 - x0, y1 - y0]))
        cell0 = cells[0] if cells else [0, 0, W, H]
        return {"mode": "multifile", "nframes": len(sibs), "size": size,
                "anim": True, "frames": [list(cell0) for _ in sibs],
                "frame_sizes": [[cell0[2], cell0[3]] for _ in sibs]}
    if n in _BATTLE_CHAR_IDS:
        return {"mode": "battlechar", "btl_entry": 0, "size": size,
                "nframes": len(sibs)}
    if len(sibs) > 1:
        sizes = [list(Image.open(s).size) for s in sibs]
        return {"mode": "multifile", "nframes": len(sibs),
                "size": size, "frame_sizes": sizes, "anim": n in _ANIM_IDS}
    if n in _SPECIAL:
        return {"mode": "special", "kind": _SPECIAL[n],
                "frames": [[0, 0, W, H]], "size": size}
    if n in _EXPLICIT_FRAMES:
        return {"mode": "grid", "frames": _EXPLICIT_FRAMES[n], "size": size,
                "anim": n in _ANIM_IDS}

    a = np.array(im)[..., 3] > 16
    if not a.any():
        return {"mode": "static", "frames": [[0, 0, W, H]], "size": size}
    xs = np.where(a.any(axis=0))[0]
    ys = np.where(a.any(axis=1))[0]
    bb = [int(xs.min()), int(ys.min()),
          int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]

    if n in _EXPLICIT_GRID:
        spec = _EXPLICIT_GRID[n]
        if spec[0] == "grid":
            C, R = spec[1], spec[2]
            cw, ch = W // C, H // R
            fr = [[c * cw, r * ch, cw, ch] for r in range(R) for c in range(C)
                  if a[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw].sum() > 0]
        else:  # relaxed single-row column segmentation
            y0, y1 = int(ys.min()), int(ys.max() + 1)
            fr = [[x0, y0, x1 - x0, y1 - y0] for x0, x1 in _runs(a.any(axis=0))]
        anim = n in _ANIM_IDS
        return {"mode": "grid", "frames": _tighten_frames(a, fr, anim),
                "size": size, "anim": anim}

    xb = _regular(_runs(a.any(axis=0)))
    yb = _regular(_runs(a.any(axis=1)))
    if not xb and not yb:
        return {"mode": "static", "frames": [bb], "size": size}
    xb = xb or [(int(xs.min()), int(xs.max() + 1))]
    yb = yb or [(int(ys.min()), int(ys.max() + 1))]
    fr = [[int(x0), int(y0), int(x1 - x0), int(y1 - y0)]
          for y0, y1 in yb for x0, x1 in xb if a[y0:y1, x0:x1].sum() > 0]
    if len(fr) <= 1:
        return {"mode": "static", "frames": [bb], "size": size}
    anim = n in _ANIM_IDS
    return {"mode": "grid", "frames": _tighten_frames(a, fr, anim),
            "size": size, "anim": anim}


def generate_table(proper_obb_dir):
    """Scan ``proper_obb_dir`` -> ``{"fldchrN": {mode,...}}`` for every base sheet."""
    bases = sorted({
        int(re.match(r"fldchr(\d+)_", os.path.basename(f)).group(1))
        for f in glob.glob(os.path.join(proper_obb_dir, "fldchr*_*.png"))
        if re.match(r"fldchr\d+_\d", os.path.basename(f))})
    out = {}
    for nn in bases:
        p = os.path.join(proper_obb_dir, f"fldchr{nn}_0.png")
        if os.path.exists(p):
            out[f"fldchr{nn}"] = classify_sheet(p)
    return out


def load_table(path):
    """Load a baked ``sheet_anim.json`` -> dict (``{}`` if missing/malformed)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _main(argv):
    if not argv:
        print("usage: python -m ffd.animation.sheet_anim <proper_obb_dir> "
              "[out.json]")
        return 2
    src = argv[0]
    out = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "sheet_anim.json")
    table = generate_table(src)
    Path(out).write_text(json.dumps(table, indent=0) + "\n", encoding="utf-8")
    from collections import Counter
    c = Counter(v["mode"] for v in table.values())
    print(f"wrote {out}: {len(table)} sheets  " +
          "  ".join(f"{m}={k}" for m, k in c.most_common()))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
