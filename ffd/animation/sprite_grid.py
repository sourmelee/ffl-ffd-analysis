"""Pure (GUI-free) helpers for authoring FFSmith per-sprite object-geometry
overrides — ``sprite_grid.json`` — from the Animation tab.

The FFSmith baker (``ffd/android_export/ffsmith_bake.py:_bake_sprite_geo``)
seeds every field sprite's geometry from the per-sheet classification table
(``sheet_anim.json``), then merges ``sprite_grid.json`` over that seed.  FFSmith
only consults the baked geometry when ``isObject`` is set; otherwise it draws the
sprite on the hardcoded 48x48 character grid.  Marking a sprite as an object is
therefore a deliberate, manual act (Jack's "manual annotation > heuristics"
rule) — this module is the authoring side of that override file.

Kept entirely free of tkinter so the seed math, the FFSmith placement math, and
the JSON round-trip can be unit-tested headlessly; the Animation tab supplies
only the widgets.  ``render_tile_preview`` needs Pillow (always present) but no
GUI toolkit.
"""

from __future__ import annotations

import json
from pathlib import Path

# Persisted keys, in struct order (matches the FSGE record the baker writes:
# "<HBhhHHhh" = img, isObject, fx, fy, fw, fh, px, py).
GEO_KEYS = ("isObject", "fx", "fy", "fw", "fh", "px", "py")


def seed_geo_from_table(rec):
    """Seed a panel geo from a ``sheet_anim.json`` per-sheet record (the same
    table the baker keys ``spritegeo.bin``/FSG2 off of).  Mirrors
    ``_bake_sprite_geo``'s table path: frame 0 is the default rect, the anchor
    is centre-bottom for that frame (``px = -w/2``, ``py = -h``), and ``isObject``
    is set for everything except ``char``/``special``.

    ``rec`` is one value from :func:`ffd.animation.sheet_anim.load_table`.
    Returns a :data:`GEO_KEYS` dict, or ``None`` for char/empty sheets.
    """
    mode = rec.get("mode", "static")
    if mode == "char":
        return None
    if mode == "multifile":
        szs = rec.get("frame_sizes") or [rec.get("size", [0, 0])]
        w, h = int(szs[0][0]), int(szs[0][1])
        fx = fy = 0
    else:
        frames = rec.get("frames") or []
        if not frames:
            w, h = rec.get("size", [0, 0])
            fx = fy = 0
        else:
            fx, fy, w, h = (int(v) for v in frames[0])
    return {
        "isObject": 0 if mode in ("char", "special") else 1,
        "fx": int(fx), "fy": int(fy), "fw": int(w), "fh": int(h),
        "px": -(int(w) // 2), "py": -int(h),
    }


def seed_geo_from_fa_entry(fa_entry):
    """Mirror the OLD per-field_anm-entry seed so the legacy entry-browser
    preview shows the same default the baker once emitted before any override.

    Returns a dict carrying every :data:`GEO_KEYS` value, or ``None`` when the
    field_anm entry has no frames (nothing to draw).

    .. deprecated::
        Superseded by :func:`seed_geo_from_table` — geometry is now keyed by
        sprite img id from ``sheet_anim.json``, not by field_anm entry index
        (there are far more sheets than entries).
    """
    frames = fa_entry.get("frames") or []
    if not frames:
        return None
    subs = fa_entry.get("sub_anims") or []
    kf = subs[0]["keyframes"][0] if subs and subs[0].get("keyframes") else None
    fr = (kf.get("frame") if kf else None) or frames[0]
    return {
        "isObject": 0,
        "fx": int(fr.get("x", 0)), "fy": int(fr.get("y", 0)),
        "fw": int(fr.get("w", 0)), "fh": int(fr.get("h", 0)),
        "px": int(kf.get("part_x", 0)) if kf else 0,
        "py": int(kf.get("part_y", 0)) if kf else 0,
    }


def normalize_geo(geo):
    """Coerce a geo-like mapping to ints over :data:`GEO_KEYS` (missing -> 0)."""
    return {k: int(geo.get(k, 0) or 0) for k in GEO_KEYS}


def object_dest_rect(geo, tile=48):
    """FFSmith ``drawSprite`` object placement, in *tile-local* coordinates
    (relative to the tile's top-left ``lx,ly``).  Mirrors the engine exactly::

        odst = { lx + tile/2 + px,  ly + tile + py,  fw, fh }

    So ``(px,py) == (0,0)`` lands the frame's top-left at the tile's
    bottom-centre; to stand a ``fw x fh`` prop centred on the tile use
    ``px = -fw/2``, ``py = -fh``.  Returns ``(dx, dy, w, h)``.
    """
    return (tile // 2 + int(geo.get("px", 0)),
            tile + int(geo.get("py", 0)),
            int(geo.get("fw", 0)), int(geo.get("fh", 0)))


def default_override_path(obb_path):
    """Best-guess ``sprite_grid.json`` location so the baker's ``--proper`` dir
    picks it up without extra flags: ``<obb_dir>/proper_obb/`` if that exists,
    else next to the obb.  Returns a str path, or ``None`` if obb_path is unset.
    """
    if not obb_path:
        return None
    base = Path(obb_path).parent
    proper = base / "proper_obb"
    target = proper if proper.is_dir() else base
    return str(target / "sprite_grid.json")


def load_overrides(path):
    """Read ``sprite_grid.json`` -> ``{int img_id: {geo}}``.  A missing or
    malformed file yields ``{}`` (the panel treats that as "no overrides yet").
    Only recognised :data:`GEO_KEYS` survive; values are coerced to int.
    """
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        try:
            out[int(k)] = {kk: int(vv) for kk, vv in v.items() if kk in GEO_KEYS}
        except Exception:
            continue
    return out


def save_override(path, img_id, geo):
    """Merge one sprite's full geo into ``sprite_grid.json`` and write it back.
    Returns the updated ``{img_id: geo}`` dict.  Writing the complete record
    (not a partial) keeps the file self-describing and stable under re-edits.
    """
    ov = load_overrides(path)
    ov[int(img_id)] = normalize_geo(geo)
    _write(path, ov)
    return ov


def remove_override(path, img_id):
    """Drop one sprite's override (revert it to the field_anm seed) and rewrite."""
    ov = load_overrides(path)
    ov.pop(int(img_id), None)
    _write(path, ov)
    return ov


def _write(path, ov):
    obj = {str(k): ov[k] for k in sorted(ov)}
    Path(path).write_text(
        json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def render_tile_preview(sheet, geo, *, tile=48, pad=24, zoom=4,
                        bg=(34, 34, 34, 255)):
    """Compose a preview showing the sprite's frame placed against ONE tile
    cell, exactly where FFSmith would draw it (:func:`object_dest_rect`).

    Draws the tile boundary, the bottom-centre anchor crosshair (the ``(0,0)``
    landing point), and the cropped frame outlined in yellow.  ``sheet`` is the
    PIL RGBA fldchr atlas (or ``None`` to show just the guides).  Returns a PIL
    RGBA image already scaled by ``zoom`` (NEAREST — pixel-art safe).
    """
    from PIL import Image, ImageDraw
    cell = tile + 2 * pad
    canvas = Image.new("RGBA", (cell, cell), bg)
    draw = ImageDraw.Draw(canvas)

    # The tile cell itself.
    draw.rectangle([pad, pad, pad + tile - 1, pad + tile - 1],
                   outline=(96, 96, 96, 255))
    # Anchor guides: vertical tile-centre + horizontal tile-bottom. Their
    # intersection is where (px,py)=(0,0) puts the frame's top-left.
    ax, ay = pad + tile // 2, pad + tile
    draw.line([ax, pad // 2, ax, cell - pad // 2], fill=(72, 72, 120, 255))
    draw.line([pad // 2, ay, cell - pad // 2, ay], fill=(72, 72, 120, 255))

    dx, dy, w, h = object_dest_rect(geo, tile)
    if sheet is not None and w > 0 and h > 0:
        fx = max(0, min(int(geo.get("fx", 0)), max(0, sheet.width - 1)))
        fy = max(0, min(int(geo.get("fy", 0)), max(0, sheet.height - 1)))
        w = min(w, sheet.width - fx)
        h = min(h, sheet.height - fy)
        if w > 0 and h > 0:
            crop = sheet.crop((fx, fy, fx + w, fy + h)).convert("RGBA")
            canvas.alpha_composite(crop, (pad + dx, pad + dy))
            draw.rectangle([pad + dx, pad + dy, pad + dx + w - 1, pad + dy + h - 1],
                           outline=(255, 200, 0, 255))
    if zoom > 1:
        canvas = canvas.resize((cell * zoom, cell * zoom), Image.NEAREST)
    return canvas
