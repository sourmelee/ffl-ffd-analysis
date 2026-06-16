"""Mobile cpk -> Android mc tileset-sheet converter.

Mirrors :mod:`mobile_to_android` (which handles character sprites) but
for *tilesets* (cpk*.dat / mc*.png). Tilesets are simpler than character
sheets:

* No ``field_anm.dat`` analog -- tiles are a uniform grid. The default
  conversion is just "2x nearest-neighbor upscale the Mobile sheet and
  paste it into an Android-sized canvas."
* No per-frame rectangles to resolve. Per-tile remapping is exposed as
  an optional ``cell_map`` for advanced cases where Android rearranges
  tiles relative to Mobile, but is not the default workflow.

Two wrinkles the converter handles
----------------------------------

1. **Missing tiles in Mobile source.** Some Mobile cpk sheets are
   smaller than their Android counterpart (e.g. Mobile 128x128 = 8x8
   tiles, Android 512x512 = 16x16 tiles). When ``fill_from_android``
   is on, every Android-cell-sized region in the converted output that
   is fully transparent gets back-filled from the original Android
   ``mc{id}_{variant}.png``. Result: a clean composite that uses
   Mobile pixels where they exist and Android pixels everywhere else.

2. **Color variants.** Each Android tileset has multiple palette
   variants (``mc{id}_0.png``, ``mc{id}_1.png``, ...). Mobile cpk
   usually only ships ONE color (the base, variant 0). Two strategies
   to generate variants 1..N:

   * ``palette_strategy='verbatim'`` (default): use the original
     ``Android/proper_obb/mc{id}_{variant}.png`` byte-for-byte. Simple
     and lossless but doesn't reflect Mobile-side edits.
   * ``palette_strategy='swap'``: extract a palette LUT by comparing
     ``mc{id}_0.png`` and ``mc{id}_{variant}.png`` (both paletted PNGs
     with the same indices, different RGB), then remap the converted
     Mobile base's colors accordingly. Lets a Mobile-sourced edit
     propagate across every variant.

Public API
----------

* :func:`convert_mobile_tileset_to_android` -- the main entry point
* :func:`apply_variant_palette_swap`        -- variant generator (a)
* :func:`make_tileset_starter_spec`         -- starter spec template
* :func:`lookup_mc_for_cpk`                 -- cpk_to_mc.json lookup
* :func:`load_android_mc_png`               -- decode mc*.png from OBB

Spec schema (``mode == 'tileset'``)
-----------------------------------

::

    {
      "name": "tileset_default",
      "mobile_source": {
        "chapter": null,
        "cpk_entry": 0,
        "palette": 0,
        "cell_w": 16, "cell_h": 16
      },
      "android_target": {
        "mode": "tileset",
        "mc_id": 0,
        "variant": 0,
        "output_size": [512, 512],
        "scale": 2,
        "cell_w": 32, "cell_h": 32,
        "fill_from_android": true,
        "palette_strategy": "verbatim"
      },
      "cell_map": {}
    }

``cell_map`` is an optional dict ``"{dst_col,dst_row}": {src_col,
src_row, flip_h}`` for advanced per-tile rearrangement. When empty
(the common case) the converter does the trivial 2x upscale.
"""

from __future__ import annotations

import io
import json
import os
from typing import Optional, Tuple

from PIL import Image


# ---------------------------------------------------------------------------
# Constants -- universal Mobile/Android cell sizes (confirmed by Jack).
# ---------------------------------------------------------------------------

MOBILE_TILE_CELL = 16    # Mobile cpk tiles are 16x16 pixels each.
ANDROID_TILE_CELL = 32   # Android mc tiles are 32x32 pixels each.
DEFAULT_SCALE = 2        # Integer NN upscale Mobile -> Android pixel size.

# Most Android mc PNGs are 512x512 (16x16 grid of 32x32). A few sheets
# (mc34_0, mc60_0) are RGBA at 512x512. The converter defers to the
# ORIGINAL Android sheet's dimensions when ``android_orig_img`` is
# supplied (per Jack: "match original Android mc dims").
DEFAULT_OUTPUT_SIZE = (512, 512)


# ---------------------------------------------------------------------------
# Spec loader / starter template
# ---------------------------------------------------------------------------

def make_tileset_starter_spec(
    name: str,
    cpk_entry: int,
    mc_id: int,
    variant: int = 0,
    palette: int = 0,
    chapter: Optional[str] = None,
    output_size: Tuple[int, int] = DEFAULT_OUTPUT_SIZE,
    fill_from_android: bool = True,
    palette_strategy: str = "verbatim",
) -> dict:
    """Build a starter tileset mapping spec.

    Most fields take sensible defaults so callers only need to pass
    identity info (cpk_entry, mc_id, variant). ``palette_strategy``
    only matters for non-zero variants; for variant 0 it's ignored
    (Mobile cpk IS the source).
    """
    return {
        "name": name,
        "mobile_source": {
            "chapter": chapter,
            "cpk_entry": cpk_entry,
            "palette": palette,
            "cell_w": MOBILE_TILE_CELL,
            "cell_h": MOBILE_TILE_CELL,
        },
        "android_target": {
            "mode": "tileset",
            "mc_id": mc_id,
            "variant": variant,
            "output_size": list(output_size),
            "scale": DEFAULT_SCALE,
            "cell_w": ANDROID_TILE_CELL,
            "cell_h": ANDROID_TILE_CELL,
            "fill_from_android": fill_from_android,
            "palette_strategy": palette_strategy,
        },
        "cell_map": {},
    }


def load_tileset_mapping_spec(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tileset_mapping_spec(spec: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# cpk -> mc auto-match using cpk_to_mc.json (with numeric fallback)
# ---------------------------------------------------------------------------

def lookup_mc_for_cpk(cpk_to_mc: dict, chapter: Optional[str],
                      cpk_entry: int,
                      palette: Optional[int] = None,
                      overrides: Optional[dict] = None
                      ) -> Tuple[Optional[int], int, str]:
    """Resolve (mc_id, variant) for a given (chapter, cpk_entry, palette).

    Order of preference:
      0. ``overrides`` (cpk_to_mc_overrides.json) — manual user
         overrides take precedence. Palette-specific entries beat
         chapter-level ones.
      0a. cpk_to_mc[chapter][cpk_entry].by_palette[palette] when the
          v3 JSON has per-palette data and palette is supplied.
      1. cpk_to_mc[chapter][str(cpk_entry)] when both keys exist.
      2. Aggregate match across ALL chapters: pick the entry with the
         lowest best_sad value for str(cpk_entry).
      3. Numeric identity fallback: cpk{N} -> mc{N}_0.

    Returns ``(mc_id, variant, source)``. Source tags: ``"override_*"``
    (manual), ``"palette"`` (v3 per-palette), ``"chapter"``,
    ``"aggregate"``, ``"numeric_fallback"``.
    """
    if cpk_entry is None or cpk_entry < 0:
        return (None, 0, "numeric_fallback")

    # (0) Manual overrides take absolute precedence.
    if overrides is not None:
        try:
            from ..maps.mc_overrides import lookup_cpk_to_mc_override
            mc, var, src = lookup_cpk_to_mc_override(
                overrides, chapter, cpk_entry, palette=palette)
            if mc is not None:
                return (mc, var, src)
        except Exception:
            pass

    eid_str = str(cpk_entry)

    # (1) Exact chapter+entry hit. Slot labels ("Chapter 5") have
    # spaces; cpk_to_mc.json uses the dense form ("Chapter5"). Try
    # both the literal and a strip-spaces variant so the GUI's
    # SP_SLOTS labels map correctly onto the JSON's chapter keys.
    if chapter and isinstance(cpk_to_mc, dict):
        keys_to_try = [chapter]
        dense = chapter.replace(" ", "")
        if dense != chapter:
            keys_to_try.append(dense)
        chap_entries = None
        for k in keys_to_try:
            chap_entries = cpk_to_mc.get(k)
            if chap_entries:
                break
        chap_entries = chap_entries or {}
        info = chap_entries.get(eid_str)
        if info and "mc_id" in info:
            try:
                return (int(info["mc_id"]),
                        int(info.get("variant", 0)),
                        "chapter")
            except (TypeError, ValueError):
                pass

    # (2) Aggregate across all chapters for this entry id.
    if isinstance(cpk_to_mc, dict):
        best = None  # (sad, mc_id, variant, chapter)
        for chap, entries in cpk_to_mc.items():
            if not isinstance(entries, dict):
                continue
            info = entries.get(eid_str)
            if not info or "mc_id" not in info:
                continue
            try:
                sad = int(info.get("best_sad", 10**12))
                mc_id = int(info["mc_id"])
                var = int(info.get("variant", 0))
            except (TypeError, ValueError):
                continue
            if best is None or sad < best[0]:
                best = (sad, mc_id, var, chap)
        if best is not None:
            return (best[1], best[2], "aggregate")

    # (3) Numeric fallback.
    return (cpk_entry, 0, "numeric_fallback")


def lookup_cpk_for_mc(cpk_to_mc: dict, mc_id: int,
                      variant: int = 0) -> Tuple[Optional[str],
                                                 Optional[int], str]:
    """Reverse: find (chapter, cpk_entry) most likely to be the
    Mobile source for a given Android ``mc_id``. Returns
    ``(chapter, cpk_entry, source)``. ``source`` is one of
    ``"exact" | "any_variant" | "numeric_fallback"``.
    """
    if mc_id is None or mc_id < 0:
        return (None, None, "numeric_fallback")

    if isinstance(cpk_to_mc, dict):
        best_exact = None     # (sad, chapter, cpk_entry)
        best_any = None       # (sad, chapter, cpk_entry)
        for chap, entries in cpk_to_mc.items():
            if not isinstance(entries, dict):
                continue
            for eid_str, info in entries.items():
                try:
                    if int(info["mc_id"]) != mc_id:
                        continue
                    var = int(info.get("variant", 0))
                    sad = int(info.get("best_sad", 10**12))
                    eid = int(eid_str)
                except (KeyError, TypeError, ValueError):
                    continue
                if var == variant:
                    if best_exact is None or sad < best_exact[0]:
                        best_exact = (sad, chap, eid)
                if best_any is None or sad < best_any[0]:
                    best_any = (sad, chap, eid)
        if best_exact is not None:
            return (best_exact[1], best_exact[2], "exact")
        if best_any is not None:
            return (best_any[1], best_any[2], "any_variant")

    # Numeric fallback: assume cpk{N} == mc{N}
    return (None, mc_id, "numeric_fallback")


# ---------------------------------------------------------------------------
# Core converter: Mobile cpk image -> Android mc image
# ---------------------------------------------------------------------------

def _all_transparent(region: Image.Image) -> bool:
    """True when every pixel's alpha channel is 0."""
    if region.mode != "RGBA":
        region = region.convert("RGBA")
    extrema = region.getextrema()
    # extrema is ((rmin,rmax),(gmin,gmax),(bmin,bmax),(amin,amax))
    if not extrema or len(extrema) < 4:
        return False
    amin, amax = extrema[3]
    return amax == 0


def _fill_missing_cells_from_android(
    converted: Image.Image,
    android_orig: Image.Image,
    cell_w: int = ANDROID_TILE_CELL,
    cell_h: int = ANDROID_TILE_CELL,
) -> Image.Image:
    """For every (cell_w x cell_h) tile-aligned region in ``converted``
    that is fully transparent, copy the corresponding region from
    ``android_orig``. Returns a NEW image; ``converted`` is not
    modified.
    """
    out = converted.convert("RGBA").copy()
    src = android_orig.convert("RGBA")
    w, h = out.size
    sw, sh = src.size
    n_filled = 0
    for y in range(0, h, cell_h):
        if y + cell_h > h:
            continue
        for x in range(0, w, cell_w):
            if x + cell_w > w:
                continue
            box = (x, y, x + cell_w, y + cell_h)
            region = out.crop(box)
            if not _all_transparent(region):
                continue
            # Sample matching region from Android orig (skip if OOB)
            if x + cell_w > sw or y + cell_h > sh:
                continue
            src_tile = src.crop(box)
            out.paste(src_tile, box)
            n_filled += 1
    return out


def _apply_cell_map(
    base: Image.Image,
    mobile_native: Image.Image,
    cell_map: dict,
    src_cell_w: int,
    src_cell_h: int,
    dst_cell_w: int,
    dst_cell_h: int,
    scale: int,
) -> Image.Image:
    """Apply per-tile rearrangement on top of an already-upscaled base.

    ``cell_map`` keys are ``"col,row"`` (destination cell coords in the
    Android sheet). Values are ``{"mobile_col", "mobile_row",
    "flip_h"}`` describing which Mobile cell to draw at that
    destination. Cells not in the map are left as the base produced
    (which is just the identity 2x upscale).
    """
    if not cell_map:
        return base
    out = base.copy()
    mw, mh = mobile_native.size
    src_cols = mw // src_cell_w
    src_rows = mh // src_cell_h
    for key, val in cell_map.items():
        try:
            dc_s, dr_s = key.split(",", 1)
            dc, dr = int(dc_s), int(dr_s)
            mc = int(val.get("mobile_col", -1))
            mr = int(val.get("mobile_row", -1))
        except (ValueError, AttributeError, TypeError):
            continue
        if not (0 <= mc < src_cols and 0 <= mr < src_rows):
            continue
        sx = mc * src_cell_w
        sy = mr * src_cell_h
        cell = mobile_native.crop((sx, sy, sx + src_cell_w,
                                       sy + src_cell_h))
        if val.get("flip_h"):
            cell = cell.transpose(Image.FLIP_LEFT_RIGHT)
        scaled = cell.resize((src_cell_w * scale, src_cell_h * scale),
                             Image.NEAREST)
        dx = dc * dst_cell_w
        dy = dr * dst_cell_h
        out.paste(scaled, (dx, dy), scaled)
    return out


def convert_mobile_tileset_to_android(
    mobile_img: Image.Image,
    spec: Optional[dict] = None,
    android_orig_img: Optional[Image.Image] = None,
) -> Image.Image:
    """Convert a Mobile cpk tileset PNG into an Android mc PNG layout.

    Args:
      mobile_img: PIL image of the Mobile cpk tileset (any size that's
        a multiple of ``mobile_source.cell_w/cell_h``).
      spec: tileset mapping spec dict (see module docstring). If None,
        a default spec with identity 2x upscale is used.
      android_orig_img: original Android ``mc{id}_{variant}.png`` (used
        for ``fill_from_android`` and to infer ``output_size`` when the
        spec doesn't pin it). Optional.

    Returns:
      A new PIL Image in RGBA mode at ``output_size`` (defaults to
      ``android_orig_img.size`` when present, else 512x512).
    """
    spec = spec or {}
    ms = spec.get("mobile_source", {})
    at = spec.get("android_target", {})
    scale = int(at.get("scale", DEFAULT_SCALE) or DEFAULT_SCALE)
    src_cell_w = int(ms.get("cell_w", MOBILE_TILE_CELL) or MOBILE_TILE_CELL)
    src_cell_h = int(ms.get("cell_h", MOBILE_TILE_CELL) or MOBILE_TILE_CELL)
    dst_cell_w = int(at.get("cell_w", ANDROID_TILE_CELL) or ANDROID_TILE_CELL)
    dst_cell_h = int(at.get("cell_h", ANDROID_TILE_CELL) or ANDROID_TILE_CELL)
    fill_from_android = bool(at.get("fill_from_android", True))

    # Default to Android original sheet's dims when no explicit size in spec.
    if "output_size" in at and at["output_size"]:
        ow, oh = at["output_size"]
    elif android_orig_img is not None:
        ow, oh = android_orig_img.size
    else:
        ow, oh = DEFAULT_OUTPUT_SIZE

    # Step 1: 2x NN upscale entire Mobile sheet. Always integer NN
    # (feedback-pixel-art-scaling).
    src = mobile_img.convert("RGBA")
    mw, mh = src.size
    upscaled = src.resize((mw * scale, mh * scale), Image.NEAREST)

    # Step 2: paste upscaled Mobile into an Android-size canvas
    # (pasted at 0,0 -- Android sheets are Mobile-aligned in the
    # observed cases).
    out = Image.new("RGBA", (ow, oh), (0, 0, 0, 0))
    out.paste(upscaled, (0, 0), upscaled)

    # Step 3 (optional): apply per-cell rearrangement on top.
    cell_map = spec.get("cell_map") or {}
    if cell_map:
        out = _apply_cell_map(out, src, cell_map,
                              src_cell_w, src_cell_h,
                              dst_cell_w, dst_cell_h, scale)

    # Step 3.5 (optional): force-Android cells. For each "col,row" in
    # ``android_target.force_android_cells``, paste the Android original
    # tile at that position. Runs AFTER cell_map (so a force-Android
    # entry overrides a Mobile remap for the same cell) and BEFORE the
    # transparent-tile backfill (so explicit force takes priority over
    # the heuristic fill).
    force_cells = at.get("force_android_cells") or []
    if force_cells and android_orig_img is not None:
        out = _apply_force_android_cells(
            out, android_orig_img, force_cells,
            cell_w=dst_cell_w, cell_h=dst_cell_h)

    # Step 4 (optional): backfill transparent tiles from the Android
    # original sheet.
    if fill_from_android and android_orig_img is not None:
        out = _fill_missing_cells_from_android(out, android_orig_img,
                                               cell_w=dst_cell_w,
                                               cell_h=dst_cell_h)

    return out


def render_tileset_variant(mobile_img, android_fill_img, android_variant_img,
                           *, mc_id, variant, fill, strategy, obb, spec=None):
    """Single source of truth for converting one Mobile cpk tileset into one
    Android ``mc{id}_{variant}`` image.

    This is the EXACT logic the SpriteConverter preview pane uses
    (``converter_tab._render_tileset_preview``), factored out so the live
    preview and the Android-Export mass-convert produce identical pixels.

    Args:
      mobile_img:          rendered Mobile cpk (RGBA) at the chosen palette
                           (preview: ``self._mobile_img``).
      android_fill_img:    Android original consulted for ``fill_from_android``
                           (preview: ``self._tileset_android_orig_img``).
      android_variant_img: the Android ``mc{id}_{variant}`` image, used for
                           ``output_size`` and the verbatim pass-through
                           (preview: ``self._android_img``).
      mc_id, variant:      target tileset identity.
      fill:                fill-missing-cells-from-Android toggle.
      strategy:            ``"verbatim"`` | ``"swap"`` (only matters variant>0).
      obb:                 loaded OBB files dict (palette-swap source).
      spec:                optional working spec (carries cell_map /
                           force_android / mobile_source.palette); a starter
                           spec is synthesised when ``None``.

    Variant 0 always converts from Mobile.  variant>0 + ``verbatim`` returns the
    Android variant unchanged.  variant>0 + ``swap`` converts the Mobile base
    then applies the palette LUT.  Returns an RGBA Image, or ``None``.
    """
    if mobile_img is None:
        return None
    variant = int(variant or 0)
    spec = spec or make_tileset_starter_spec(
        "export", cpk_entry=0, mc_id=mc_id or 0, variant=variant)
    at = spec.setdefault("android_target", {})
    at["variant"] = variant
    at["fill_from_android"] = bool(fill)
    at["palette_strategy"] = strategy
    if android_variant_img is not None:
        at["output_size"] = list(android_variant_img.size)
    if variant > 0 and strategy == "verbatim":
        return (android_variant_img.convert("RGBA")
                if android_variant_img is not None else None)
    base_out = convert_mobile_tileset_to_android(
        mobile_img, spec, android_fill_img)
    if variant > 0 and strategy == "swap":
        base_pal_img = load_android_mc_png(obb, mc_id, 0, preserve_palette=True)
        target_pal_img = load_android_mc_png(
            obb, mc_id, variant, preserve_palette=True)
        if base_pal_img is not None and target_pal_img is not None:
            return apply_variant_palette_swap(
                base_out, base_pal_img, target_pal_img)
    return base_out


def _apply_force_android_cells(base: Image.Image,
                                android_orig: Image.Image,
                                force_cells,
                                cell_w: int = ANDROID_TILE_CELL,
                                cell_h: int = ANDROID_TILE_CELL
                                ) -> Image.Image:
    """For every ``"col,row"`` string in ``force_cells``, paste the
    corresponding ``(cell_w x cell_h)`` tile from ``android_orig`` into
    ``base``. Out-of-range coords are silently skipped (so a stale
    override from a different-sized sheet doesn't crash).
    """
    out = base.convert("RGBA").copy()
    src = android_orig.convert("RGBA")
    w, h = out.size
    sw, sh = src.size
    for key in force_cells:
        try:
            c_s, r_s = key.split(",", 1)
            c = int(c_s); r = int(r_s)
        except (ValueError, AttributeError):
            continue
        x = c * cell_w
        y = r * cell_h
        if (x < 0 or y < 0 or x + cell_w > w or y + cell_h > h
                or x + cell_w > sw or y + cell_h > sh):
            continue
        tile = src.crop((x, y, x + cell_w, y + cell_h))
        out.paste(tile, (x, y))
    return out


# ---------------------------------------------------------------------------
# Palette-swap variant generator (strategy 'swap')
# ---------------------------------------------------------------------------

def _paletted_to_palette_rgb(img: Image.Image):
    """Return a list of 256 (R,G,B) tuples for a paletted image, or
    None if the image isn't in P mode."""
    if img.mode != "P":
        return None
    pal = img.getpalette()
    if not pal:
        return None
    # Pad/truncate to 256 entries
    pal = pal[: 256 * 3] + [0] * max(0, 256 * 3 - len(pal))
    return [tuple(pal[i*3:i*3+3]) for i in range(256)]


def apply_variant_palette_swap(
    converted_base: Image.Image,
    android_base_variant_img: Image.Image,
    android_target_variant_img: Image.Image,
) -> Image.Image:
    """Generate a non-zero variant of a converted Mobile-sourced tile
    sheet by re-mapping its colors.

    Both ``android_base_variant_img`` (the Android variant 0 PNG) and
    ``android_target_variant_img`` (e.g. variant 1 PNG) should be in
    paletted mode (mc*.png are all 'P' mode 256-color). Their palette
    indices align 1:1 (same tile shapes), so the (base_rgb -> target_rgb)
    delta IS the palette swap LUT.

    For each pixel in ``converted_base`` (RGBA), we look up its RGB
    in the LUT; on hit we replace, on miss we keep the original pixel
    (so Mobile-sourced colors that don't exist in the Android palette
    survive unchanged).

    Returns a new RGBA image of the same size as ``converted_base``.
    """
    base_pal = _paletted_to_palette_rgb(android_base_variant_img)
    target_pal = _paletted_to_palette_rgb(android_target_variant_img)
    if base_pal is None or target_pal is None:
        # Non-paletted variant -- can't do a palette swap. Return base
        # unchanged so caller can decide what to do.
        return converted_base.convert("RGBA").copy()

    # Build LUT: base_rgb -> target_rgb. Index 0 in palette PNGs is
    # typically the transparent / sentinel color; we skip duplicates so
    # multiple indices with the same base color resolve to the FIRST
    # target color (whichever index won the dict slot first).
    lut = {}
    for i, base_rgb in enumerate(base_pal):
        if base_rgb in lut:
            continue
        lut[base_rgb] = target_pal[i]

    # Apply pixel-wise. PIL doesn't have a built-in fast LUT for RGBA
    # so we walk pixels via getdata/putdata -- acceptable for 512x512.
    src = converted_base.convert("RGBA")
    pixels = list(src.getdata())
    out_pixels = []
    for r, g, b, a in pixels:
        rgb = (r, g, b)
        if rgb in lut:
            nr, ng, nb = lut[rgb]
            out_pixels.append((nr, ng, nb, a))
        else:
            out_pixels.append((r, g, b, a))
    out = Image.new("RGBA", src.size)
    out.putdata(out_pixels)
    return out


# ---------------------------------------------------------------------------
# Android mc PNG helpers
# ---------------------------------------------------------------------------


def load_android_mc_png(obb_files: dict, mc_id: int,
                        variant: int = 0,
                        preserve_palette: bool = False
                        ) -> Optional[Image.Image]:
    """Load ``mc{mc_id}_{variant}.png`` from the loaded OBB files dict.

    Args:
      obb_files: dict of filename -> bytes (FFData.obb_files).
      mc_id, variant: target tileset identity.
      preserve_palette: when True, keep paletted P mode so the palette
        is accessible (used by the palette-swap path). When False
        (default), convert to RGBA for compositing.

    Returns:
      A PIL Image, or None if the file isn't present.
    """
    if not obb_files:
        return None
    name = f"mc{mc_id}_{variant}.png"
    blob = obb_files.get(name)
    if blob is None:
        return None
    try:
        img = Image.open(io.BytesIO(blob))
        if preserve_palette and img.mode == "P":
            return img.copy()
        return img.convert("RGBA")
    except Exception:
        return None


def list_android_mc_variants(obb_files: dict, mc_id: int) -> list:
    """Return sorted list of variant ints available for a given mc_id.
    Empty list when the OBB has no ``mc{mc_id}_*.png`` entries.
    """
    if not obb_files:
        return []
    prefix = f"mc{mc_id}_"
    variants = set()
    for name in obb_files:
        if not (name.startswith(prefix) and name.endswith(".png")):
            continue
        tail = name[len(prefix):-4]
        try:
            variants.add(int(tail))
        except ValueError:
            continue
    return sorted(variants)


def list_android_mc_ids(obb_files: dict) -> list:
    """Return sorted list of mc_id ints present in the OBB."""
    if not obb_files:
        return []
    ids = set()
    for name in obb_files:
        if not (name.startswith("mc") and name.endswith(".png")):
            continue
        body = name[2:-4]
        head = ""
        for ch in body:
            if ch.isdigit():
                head += ch
            else:
                break
        if head and "_" in body[len(head):]:
            try:
                ids.add(int(head))
            except ValueError:
                continue
    return sorted(ids)


# ---------------------------------------------------------------------------
# Mobile cpk palette enumeration
# ---------------------------------------------------------------------------

def count_cpk_palettes(sp_files: dict, entry_id: int) -> int:
    """Return how many palette variants the Mobile cpk entry has.

    The cpk chunk format stores N sub-records starting with N 4-byte
    offsets at byte 0; the first sub-record is the ic image (containing
    the default palette), and entries 1..N-1 are alternate palettes.
    So the count equals ``first4 // 4``.

    Returns 1 if anything fails to parse (the default palette is
    always available since it's embedded in the ic record).
    """
    if not sp_files or entry_id is None:
        return 1
    try:
        from ..tilesets.parser import (
            parse_cpk_index_mobile, flat_pack_index,
        )
        boot = sp_files.get("boot_data.dat")
        if not boot:
            return 1
        idx = flat_pack_index(parse_cpk_index_mobile(boot))
        if entry_id not in idx:
            return 1
        pack_n, off, sz = idx[entry_id]
        cpk_name = f"cpk{pack_n}.dat"
        chunk_blob = sp_files.get(cpk_name)
        if not chunk_blob:
            return 1
        chunk = chunk_blob[off:off + sz]
        if len(chunk) < 4:
            return 1
        import struct
        first4 = struct.unpack(">I", chunk[:4])[0]
        if first4 == 0 or first4 % 4 != 0 or first4 > len(chunk):
            return 1
        n = first4 // 4
        return max(1, int(n))
    except Exception:
        return 1


# ---------------------------------------------------------------------------
# Build-aware tile production (shared by Maps preview + map/tileset exports)
# ---------------------------------------------------------------------------

def _spec_for_build(build, output_size=(512, 512)):
    """Translate a stored build record into a convert_mobile_tileset_to_android
    spec dict. ``build`` may be None (plain identity 2x upscale)."""
    at = {
        "mode": "tileset",
        "output_size": [int(output_size[0]), int(output_size[1])],
        "scale": DEFAULT_SCALE,
        "cell_w": ANDROID_TILE_CELL, "cell_h": ANDROID_TILE_CELL,
        "fill_from_android": bool(build.get("fill_from_android")) if build else False,
    }
    if build and build.get("force_android_cells"):
        at["force_android_cells"] = list(build["force_android_cells"])
    spec = {
        "name": "build",
        "mobile_source": {"cell_w": MOBILE_TILE_CELL, "cell_h": MOBILE_TILE_CELL},
        "android_target": at,
        "cell_map": dict(build.get("cell_map") or {}) if build else {},
    }
    return spec


def produce_build_tile(resolver, cpk_id, mc_id, variant, builds_data,
                       obb=None, normalize=False, output_size=(512, 512)):
    """Produce an Android-layout tile sheet for (mc_id, variant) sourced
    from Mobile ``cpk_id`` via ``resolver``, honouring any stored build.

    Resolution (chapter-agnostic, highest-chapter-wins) is delegated to
    ``ffd.maps.mc_overrides.resolve_tileset_build``.

    * Build present -> render the cpk through the build's inline palette
      (or native palette 0), then run the converter with the build's
      cell_map / force_android_cells / fill_from_android. Output is a
      ``output_size`` RGBA sheet (32px tiles).
    * No build, ``normalize=True`` -> plain integer 2x upscale into an
      ``output_size`` canvas (no Android pixels) so the map renderer sees
      a uniform 32px tile size across every slot.
    * No build, ``normalize=False`` -> the raw resolver image (legacy
      16px), unchanged.

    Returns None if the underlying cpk image can't be produced (so callers
    can fall through to the next resolution tier).
    """
    chap = build = None
    if builds_data:
        try:
            from ..maps.mc_overrides import resolve_tileset_build
            chap, build = resolve_tileset_build(builds_data, cpk_id, variant)
        except Exception:
            chap = build = None

    if build is not None:
        pal = build.get("palette")
        try:
            if pal:
                base = resolver.get_with_palette(
                    cpk_id, [tuple(int(x) for x in c[:3]) for c in pal])
            else:
                base = resolver.get(cpk_id, 0)
        except Exception:
            base = resolver.get(cpk_id, 0)
        if base is None:
            return None
        spec = _spec_for_build(build, output_size)
        android_orig = None
        if obb is not None and (build.get("fill_from_android")
                                or build.get("force_android_cells")):
            android_orig = load_android_mc_png(obb, mc_id, variant)
            if android_orig is None:
                android_orig = load_android_mc_png(obb, mc_id, 0)
        try:
            return convert_mobile_tileset_to_android(
                base.convert("RGBA"), spec, android_orig)
        except Exception:
            return base.convert("RGBA")

    base = resolver.get(cpk_id, 0)
    if base is None:
        return None
    if normalize:
        spec = _spec_for_build(None, output_size)
        try:
            return convert_mobile_tileset_to_android(
                base.convert("RGBA"), spec, None)
        except Exception:
            return base.convert("RGBA")
    return base
