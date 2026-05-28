"""Mobile chpk -> Android fldchr sprite-sheet converter.

Problem solved
==============

The Android engine renders character sprites by reading explicit pixel
rectangles from ``field_anm.dat`` (sub[1] frame table). Every party-member
animation entry uses a 6 col x 5 row grid of 48x48 cells with 1-px border
and 50-px pitch -- 25 of the 30 grid positions are actually used.

Mobile sprite sheets use a transposed 5 col x 6 row grid of 16x24 cells
with no border and no spacing -- 30 cells total. Some Mobile poses
(carry-overhead, lying-down) span 2 adjacent cells horizontally, so
the converter supports multi-cell extracts via ``mobile_cells_w/h``.

If a 2x-upscaled Mobile sheet (160x288) is dropped into the Android slot
(256x512) without re-pagination, field_anm's pixel rects sample the wrong
region from the smaller texture and produce the "doubled sprite" artifact.

Public API
----------

* :func:`convert_mobile_sheet_to_android` -- the main entry point
* :func:`load_mapping_spec`               -- JSON mapping loader
* :func:`make_starter_spec`               -- generate a starter spec
* :func:`render_diagnostic_overlay`       -- side-by-side preview

Spec schema
-----------

* ``frame_map``: dict keyed by Android frame index (as string) from
  ``field_anm.dat`` sub[1]. Each entry has ``mobile_col``, ``mobile_row``,
  ``mobile_cells_w`` (default 1), ``mobile_cells_h`` (default 1),
  ``flip_h`` (default False), ``comment``.
* ``extra_frames``: list of dicts, each with ``name``, ``android_rect``
  ``[x, y, w, h]``, plus the same Mobile-source fields as ``frame_map``.
  Used for Android positions the engine accesses outside field_anm
  sub[1] -- KO/death lying-down sprites below the standard 5-row grid,
  unused-grid-position fillers, composite-part overlays.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from PIL import Image, ImageDraw


# ---------------------------------------------------------------------------
# Constants -- the canonical party-member layout on both platforms.
# ---------------------------------------------------------------------------

MOBILE_CELL_W = 16
MOBILE_CELL_H = 24
MOBILE_COLS   = 5
MOBILE_ROWS   = 6
MOBILE_NATIVE_W = MOBILE_COLS * MOBILE_CELL_W   # 80
MOBILE_NATIVE_H = MOBILE_ROWS * MOBILE_CELL_H   # 144

ANDROID_CELL_W = 48
ANDROID_CELL_H = 48
ANDROID_PITCH  = 50
ANDROID_BORDER = 1
ANDROID_SHEET_W = 256
ANDROID_SHEET_H = 512

DEFAULT_SCALE = 2  # 2x nearest-neighbor: 16x24 -> 32x48 (fills Android cell height)

# Standard cardinal-direction convention -- verified against engine code.
CARDINAL_X_MAP = {0: 1, 1: 51, 2: 101}
CARDINAL_LABELS = {
    0: "south idle", 1: "south walk A", 2: "south walk B",
    3: "north idle", 4: "north walk A", 5: "north walk B",
    6: "east idle",  7: "east walk A",  8: "east walk B",
}


# ---------------------------------------------------------------------------
# Spec loader / generator
# ---------------------------------------------------------------------------

def make_starter_spec(name: str, fldchr_id: int, chpk_entry: int,
                      palette: int = 1, field_anm_entry: int = 1) -> dict:
    """Build a starter mapping spec.

    The 3 cardinal directions (frames 0..8) are filled in via the
    standard convention; remaining frames (9..24) are left as null so
    the user can annotate them visually. ``extra_frames`` is pre-seeded
    with the 5 unreferenced grid positions and 2 lying-down slots
    typical of Sol-class characters; user fills in mobile_col/row.
    """
    frame_map = {}
    for android_idx in range(9):
        mobile_col = android_idx // 3
        mobile_row = android_idx % 3
        frame_map[str(android_idx)] = {
            "mobile_col": mobile_col,
            "mobile_row": mobile_row,
            "mobile_cells_w": 1,
            "mobile_cells_h": 1,
            "flip_h": False,
            "comment": CARDINAL_LABELS[android_idx],
        }
    for android_idx in range(9, 25):
        frame_map[str(android_idx)] = {
            "mobile_col": None,
            "mobile_row": None,
            "mobile_cells_w": 1,
            "mobile_cells_h": 1,
            "flip_h": False,
            "comment": "TODO: annotate manually",
        }
    extra_frames = [
        {"name": "grid_51_151_unused", "android_rect": [51, 151, 48, 48],
         "mobile_col": None, "mobile_row": None,
         "mobile_cells_w": 1, "mobile_cells_h": 1, "flip_h": False,
         "comment": "TODO: between Android frames 11 and 9 (col x=51 row 4)"},
        {"name": "grid_101_201_unused", "android_rect": [101, 201, 48, 48],
         "mobile_col": None, "mobile_row": None,
         "mobile_cells_w": 1, "mobile_cells_h": 1, "flip_h": False,
         "comment": "TODO: between Android frames 10 and 17 (col x=101 row 5)"},
        {"name": "grid_251_101", "android_rect": [251, 101, 48, 48],
         "mobile_col": None, "mobile_row": None,
         "mobile_cells_w": 1, "mobile_cells_h": 1, "flip_h": False,
         "comment": "TODO: col x=251 row 3"},
        {"name": "grid_251_151", "android_rect": [251, 151, 48, 48],
         "mobile_col": None, "mobile_row": None,
         "mobile_cells_w": 1, "mobile_cells_h": 1, "flip_h": False,
         "comment": "TODO: col x=251 row 4"},
        {"name": "grid_251_201", "android_rect": [251, 201, 48, 48],
         "mobile_col": None, "mobile_row": None,
         "mobile_cells_w": 1, "mobile_cells_h": 1, "flip_h": False,
         "comment": "TODO: col x=251 row 5"},
        {"name": "ko_lying_a", "android_rect": [1, 252, 48, 48],
         "mobile_col": None, "mobile_row": None,
         "mobile_cells_w": 2, "mobile_cells_h": 1, "flip_h": False,
         "comment": "TODO: KO/dead lying pose A (often Mobile 0,5 + 1,5 wide span)"},
        {"name": "ko_lying_b", "android_rect": [51, 252, 48, 48],
         "mobile_col": None, "mobile_row": None,
         "mobile_cells_w": 2, "mobile_cells_h": 1, "flip_h": False,
         "comment": "TODO: KO/dead lying pose B"},
    ]
    return {
        "name": name,
        "mobile_source": {
            "chpk_entry": chpk_entry,
            "palette":    palette,
            "cell_w":     MOBILE_CELL_W,
            "cell_h":     MOBILE_CELL_H,
            "cols":       MOBILE_COLS,
            "rows":       MOBILE_ROWS,
        },
        "android_target": {
            "fldchr_id":       fldchr_id,
            "field_anm_entry": field_anm_entry,
            "output_size":     [ANDROID_SHEET_W, ANDROID_SHEET_H],
            "scale":           DEFAULT_SCALE,
            "h_align":         "center",
            "v_align":         "bottom",
        },
        "frame_map":    frame_map,
        "extra_frames": extra_frames,
    }


def load_mapping_spec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_mapping_spec(spec: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Core converter
# ---------------------------------------------------------------------------

def _normalize_mobile_sheet(mobile_img: Image.Image,
                            cell_w: int = MOBILE_CELL_W,
                            cell_h: int = MOBILE_CELL_H,
                            cols: int = MOBILE_COLS,
                            rows: int = MOBILE_ROWS) -> Image.Image:
    """Return the Mobile sheet at its native size based on the cell
    grid dimensions. Default (16x24, 5x6) reproduces the legacy
    80x144 field-sheet behavior, but battle / monster / other sprites
    use different grids (e.g. 24x24 with 5x6 cols = 120x144).

    If the input image matches an integer-multiple of the native size
    (2x/3x/4x), it gets downscaled with nearest-neighbor (pixel-art
    safe). Otherwise the image is clipped / padded into the expected
    canvas.
    """
    img = mobile_img.convert("RGBA")
    native_w = cols * cell_w
    native_h = rows * cell_h
    w, h = img.size
    if (w, h) == (native_w, native_h):
        return img
    for scale in (2, 3, 4):
        if w == native_w * scale and h == native_h * scale:
            return img.resize((native_w, native_h), Image.NEAREST)
    out = Image.new("RGBA", (native_w, native_h), (0, 0, 0, 0))
    out.paste(img.crop((0, 0, min(w, native_w), min(h, native_h))), (0, 0))
    return out


def _extract_mobile_cell(mobile_native: Image.Image,
                         col: int, row: int,
                         cells_w: int = 1, cells_h: int = 1,
                         cell_w: int = MOBILE_CELL_W,
                         cell_h: int = MOBILE_CELL_H) -> Image.Image:
    """Extract a Mobile region spanning (cells_w x cells_h) cells from
    the top-left corner at (col, row). Cell dimensions default to the
    field convention (16x24); pass cell_w/cell_h overrides for battle
    or other sprite shapes (e.g. 24x24).

    Multi-cell extracts are needed for wide poses like carry-overhead
    (Mobile (3,1)+(4,1)) and lying-down KO (Mobile (0,5)+(1,5)).
    """
    x = col * cell_w
    y = row * cell_h
    w = cells_w * cell_w
    h = cells_h * cell_h
    x2 = min(x + w, mobile_native.size[0])
    y2 = min(y + h, mobile_native.size[1])
    return mobile_native.crop((x, y, x2, y2))


def _place_in_destination(cell: Image.Image, dst_w: int, dst_h: int,
                          scale: int, h_align: str, v_align: str,
                          flip_h: bool,
                          x_offset: int = 0,
                          y_offset: int = 0) -> Image.Image:
    """Scale a Mobile cell and place it inside the Android destination rect.

    Integer nearest-neighbor scaling only -- never resample pixel art at
    non-integer ratios. ``x_offset`` and ``y_offset`` are pixel nudges
    applied on top of the h_align/v_align base position. Negative offsets
    are valid; PIL clips paste overflow against the destination bounds,
    which is what we want for wide Mobile sprites (32x24 -> 64x48 at 2x)
    positioned inside a 48x48 Android slot.
    """
    src = cell
    if flip_h:
        src = src.transpose(Image.FLIP_LEFT_RIGHT)
    sw, sh = src.size
    scaled = src.resize((sw * scale, sh * scale), Image.NEAREST)
    dw, dh = scaled.size
    if h_align == "center":
        ox = (dst_w - dw) // 2
    elif h_align == "right":
        ox = dst_w - dw
    else:
        ox = 0
    if v_align == "bottom":
        oy = dst_h - dh
    elif v_align == "center":
        oy = (dst_h - dh) // 2
    else:
        oy = 0
    ox += int(x_offset)
    oy += int(y_offset)
    dst = Image.new("RGBA", (dst_w, dst_h), (0, 0, 0, 0))
    # PIL paste handles negative offsets + overflow correctly (clips against
    # the dest bounds), so we deliberately don't clamp with max(0, ...).
    dst.paste(scaled, (ox, oy), scaled)
    return dst


def _draw_missing_marker(dst_w: int, dst_h: int) -> Image.Image:
    """Magenta-with-? tile for unmapped frames -- pops in-game."""
    img = Image.new("RGBA", (dst_w, dst_h), (255, 0, 255, 128))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, dst_w - 1, dst_h - 1], outline=(255, 255, 0, 255))
    try:
        d.text((dst_w // 2 - 4, dst_h // 2 - 6), "?",
               fill=(255, 255, 0, 255))
    except Exception:
        pass
    return img


def convert_mobile_sheet_to_android(
    mobile_img: Image.Image,
    field_anm_entry: dict,
    mapping_spec: dict,
    fill_missing: bool = False,
) -> Image.Image:
    """Build an Android-layout PNG from a Mobile chpk sheet + mapping spec.

    Iterates the field_anm sub[1] frames AND any spec-defined
    ``extra_frames`` (engine-only positions outside the standard
    25-frame template). Each entry may use a multi-cell Mobile source
    via ``mobile_cells_w/h``.
    """
    # Read Mobile cell dimensions from the spec (default to legacy
    # 16x24/5x6 if missing -- preserves back-compat with old specs).
    ms = mapping_spec.get("mobile_source", {})
    m_cell_w = int(ms.get("cell_w", MOBILE_CELL_W))
    m_cell_h = int(ms.get("cell_h", MOBILE_CELL_H))
    m_cols   = int(ms.get("cols",   MOBILE_COLS))
    m_rows   = int(ms.get("rows",   MOBILE_ROWS))
    mobile_native = _normalize_mobile_sheet(mobile_img,
                                            cell_w=m_cell_w, cell_h=m_cell_h,
                                            cols=m_cols, rows=m_rows)
    target = mapping_spec.get("android_target", {})
    ow, oh = target.get("output_size", [ANDROID_SHEET_W, ANDROID_SHEET_H])
    scale = target.get("scale", DEFAULT_SCALE)
    h_align = target.get("h_align", "center")
    v_align = target.get("v_align", "bottom")

    out = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
    frame_map = mapping_spec.get("frame_map", {})
    extra_frames = mapping_spec.get("extra_frames", []) or []

    def _paint_one(ax: int, ay: int, aw: int, ah: int, entry: dict) -> None:
        m_col = entry.get("mobile_col")
        m_row = entry.get("mobile_row")
        m_cw = int(entry.get("mobile_cells_w", 1) or 1)
        m_ch = int(entry.get("mobile_cells_h", 1) or 1)
        flip_h = bool(entry.get("flip_h", False))
        # Per-frame overrides (fall back to spec-wide defaults)
        e_scale  = int(entry.get("scale", scale) or scale)
        e_halign = entry.get("h_align") or h_align
        e_valign = entry.get("v_align") or v_align
        x_off    = int(entry.get("x_offset", 0) or 0)
        y_off    = int(entry.get("y_offset", 0) or 0)

        if m_col is None or m_row is None:
            if fill_missing:
                tile = _draw_missing_marker(aw, ah)
                out.paste(tile, (ax, ay), tile)
            return
        if not (0 <= m_col < m_cols and 0 <= m_row < m_rows):
            if fill_missing:
                tile = _draw_missing_marker(aw, ah)
                out.paste(tile, (ax, ay), tile)
            return

        cell = _extract_mobile_cell(mobile_native, m_col, m_row,
                                    cells_w=m_cw, cells_h=m_ch,
                                    cell_w=m_cell_w, cell_h=m_cell_h)
        placed = _place_in_destination(cell, aw, ah, e_scale,
                                       e_halign, e_valign, flip_h,
                                       x_offset=x_off, y_offset=y_off)
        out.paste(placed, (ax, ay), placed)

    # field_anm-driven frames (indexed by frame_map "0".."N")
    for fi, frame in enumerate(field_anm_entry.get("frames", [])):
        x, y, w, h = frame["x"], frame["y"], frame["w"], frame["h"]
        _paint_one(x, y, w, h, frame_map.get(str(fi)) or {})

    # Spec-defined extra frames at custom Android (x,y,w,h) positions
    for ef in extra_frames:
        rect = ef.get("android_rect")
        if not rect or len(rect) != 4:
            continue
        x, y, w, h = rect
        _paint_one(int(x), int(y), int(w), int(h), ef)

    return out


# ---------------------------------------------------------------------------
# Diagnostic overlays for the GUI tab
# ---------------------------------------------------------------------------

def render_diagnostic_overlay(mobile_img: Image.Image,
                              android_img: Image.Image,
                              field_anm_entry: dict,
                              zoom: int = 3,
                              mapping_spec: Optional[dict] = None
                              ) -> Image.Image:
    """Side-by-side panel: Mobile (grid overlay) | Android (frame rects).

    Field_anm rects drawn in RED with frame indices. If ``mapping_spec``
    is supplied, its ``extra_frames`` are also drawn in CYAN with their
    ``name`` field as the label.

    Mobile cell dimensions are read from ``mapping_spec.mobile_source``
    (defaulting to 16x24/5x6 when no spec is supplied).
    """
    if mapping_spec:
        ms = mapping_spec.get("mobile_source", {})
        cell_w = int(ms.get("cell_w", MOBILE_CELL_W))
        cell_h = int(ms.get("cell_h", MOBILE_CELL_H))
        cols   = int(ms.get("cols",   MOBILE_COLS))
        rows   = int(ms.get("rows",   MOBILE_ROWS))
    else:
        cell_w, cell_h = MOBILE_CELL_W, MOBILE_CELL_H
        cols, rows = MOBILE_COLS, MOBILE_ROWS
    native_w, native_h = cols * cell_w, rows * cell_h
    mobile_native = _normalize_mobile_sheet(mobile_img,
                                            cell_w=cell_w, cell_h=cell_h,
                                            cols=cols, rows=rows)
    mz = mobile_native.resize((native_w * zoom, native_h * zoom), Image.NEAREST)
    md = ImageDraw.Draw(mz)
    for c in range(cols):
        for r in range(rows):
            x, y = c * cell_w * zoom, r * cell_h * zoom
            md.rectangle([x, y, x + cell_w * zoom - 1,
                              y + cell_h * zoom - 1],
                         outline=(255, 0, 0, 200))
            md.text((x + 2, y + 1), f"{c},{r}", fill=(255, 255, 0))

    az = android_img.convert("RGBA").copy()
    ad = ImageDraw.Draw(az)
    for fi, f in enumerate(field_anm_entry.get("frames", [])):
        ad.rectangle([f["x"], f["y"], f["x"] + f["w"] - 1,
                          f["y"] + f["h"] - 1],
                     outline=(255, 0, 0, 200))
        ad.text((f["x"] + 2, f["y"] + 1), str(fi),
                fill=(255, 255, 0, 255))
    if mapping_spec is not None:
        for ef in mapping_spec.get("extra_frames", []) or []:
            rect = ef.get("android_rect")
            if not rect or len(rect) != 4:
                continue
            x, y, w, h = rect
            ad.rectangle([x, y, x + w - 1, y + h - 1],
                         outline=(0, 255, 255, 220))
            label = ef.get("name", "?")
            ad.text((x + 2, y + 1), label[:6],
                    fill=(0, 255, 255, 255))

    gap = 16
    total_w = mz.size[0] + gap + az.size[0]
    total_h = max(mz.size[1], az.size[1])
    panel = Image.new("RGBA", (total_w, total_h), (40, 40, 40, 255))
    panel.paste(mz, (0, 0))
    panel.paste(az, (mz.size[0] + gap, 0))
    return panel
