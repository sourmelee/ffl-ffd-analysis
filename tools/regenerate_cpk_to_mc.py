"""Regenerate ``cpk_to_mc.json`` with palette-aware SAD matching.

For every (chapter, cpk_entry, palette_idx) combination, compute the
sum-of-absolute-differences against every Android (mc_id, variant)
sheet and record the best (and second-best) match. The resulting JSON
has two layers:

* The top-level per-cpk-entry record keeps the OLD structure
  (``mc_id``, ``variant``, ``best_sad``, ``second_*``, ``gap``) so
  legacy callers still work. The values reflect the BEST palette --
  whichever (palette, mc_id, variant) triple has the lowest SAD.
* A new ``by_palette`` sub-dict carries per-palette best matches. This
  lets the GUI auto-match Mobile palette 0 to mc{N}_0 and Mobile
  palette 2 to mc{N}_2 (for example).

SAD details
-----------
* Both sheets compared at 512x512 (Mobile 2x NN upscaled).
* Mask: only pixels where Mobile alpha > 0 contribute. Sheets that
  cover different regions don't penalise each other for non-overlap.
* Channels: alpha+luminance (1 byte each) summed. Per-pixel cost
  range ~0..255 per channel; total over 512*512 = 262144 pixels
  capped at ~67M.
* SAD is then divided by opaque pixel count for a normalised score
  used in TIE-BREAKING; the absolute ``best_sad`` recorded is the
  raw sum to remain comparable with the v2 JSON's values.

Usage
-----
::

    python3 Python/tools/regenerate_cpk_to_mc.py \\
        --sp-dir Mobile/Scratchpads \\
        --obb Android/main.obb \\
        --out cpk_to_mc.json
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

# Make the ffd package importable when run from project root
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..")))

from ffd.containers import parse_sp, load_zip_container
from ffd.tilesets.parser import MobileTilesetResolver
from ffd.sprites.mobile_tile_to_android import (
    count_cpk_palettes, load_android_mc_png,
    list_android_mc_ids, list_android_mc_variants,
)


SHEET_DIM = 512
UPSCALE = 2


def _to_rgba_array(img: Image.Image, target_dim: int = SHEET_DIM
                   ) -> np.ndarray:
    """Convert a PIL image to a (H, W, 4) uint8 array, padded with
    zeros up to (target_dim, target_dim)."""
    rgba = img.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.uint8)
    h, w = arr.shape[:2]
    if h == target_dim and w == target_dim:
        return arr
    padded = np.zeros((target_dim, target_dim, 4), dtype=np.uint8)
    padded[:min(h, target_dim), :min(w, target_dim)] = \
        arr[:target_dim, :target_dim]
    return padded


def _mobile_upscaled_array(mobile_img: Image.Image,
                           target_dim: int = SHEET_DIM) -> np.ndarray:
    """2x NN upscale the Mobile image and pad to ``target_dim``."""
    w, h = mobile_img.size
    up = mobile_img.resize((w * UPSCALE, h * UPSCALE), Image.NEAREST)
    return _to_rgba_array(up, target_dim)


def _sad(mobile_arr: np.ndarray, android_arr: np.ndarray) -> tuple:
    """Return (raw_sad, opaque_pixel_count). Computes alpha+luminance
    SAD over pixels where mobile alpha > 0. RGB channels are averaged
    to luminance via (R+G+B)//3 for cheap-and-cheerful comparison."""
    mob_alpha = mobile_arr[:, :, 3].astype(np.int16)
    and_alpha = android_arr[:, :, 3].astype(np.int16)
    mask = mob_alpha > 0
    if not mask.any():
        return (10**12, 0)
    mob_lum = (mobile_arr[:, :, 0].astype(np.int16)
               + mobile_arr[:, :, 1].astype(np.int16)
               + mobile_arr[:, :, 2].astype(np.int16)) // 3
    and_lum = (android_arr[:, :, 0].astype(np.int16)
               + android_arr[:, :, 1].astype(np.int16)
               + android_arr[:, :, 2].astype(np.int16)) // 3
    diff_lum = np.abs(mob_lum - and_lum)
    diff_alpha = np.abs(mob_alpha - and_alpha)
    masked_lum = diff_lum * mask
    masked_alpha = diff_alpha * mask
    sad = int(masked_lum.sum() + masked_alpha.sum())
    n_opaque = int(mask.sum())
    return (sad, n_opaque)


def _record_per_palette(
    mobile_arr: np.ndarray,
    android_arrs: dict,  # {(mc_id, variant): np.array}
) -> dict:
    """For one Mobile rendering, compute best + second-best Android
    match across all (mc_id, variant) candidates and return the dict
    in the schema used by the old cpk_to_mc.json."""
    scored = []
    for (mc_id, variant), aarr in android_arrs.items():
        sad, n_opq = _sad(mobile_arr, aarr)
        # Normalise SAD for tie-breaking: divide by opaque count
        norm = sad / max(1, n_opq)
        scored.append((norm, sad, mc_id, variant, n_opq))
    scored.sort()
    best = scored[0]
    second = scored[1] if len(scored) > 1 else best
    return {
        "mc_id": int(best[2]),
        "variant": int(best[3]),
        "best_sad": int(best[1]),
        "second_mc_id": int(second[2]),
        "second_variant": int(second[3]),
        "second_sad": int(second[1]),
        "gap": int(second[1]) - int(best[1]),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sp-dir", default="Mobile/Scratchpads",
                    help="Folder of .sp scratchpads")
    ap.add_argument("--obb", default="Android/main.obb",
                    help="Android OBB archive path (only used if "
                         "--mc-dir is not supplied or has no mc PNGs)")
    ap.add_argument("--mc-dir", default="Android/proper_obb",
                    help="Folder containing extracted mc*.png files "
                         "(MUCH faster than loading the OBB archive). "
                         "Falls back to --obb if not found.")
    ap.add_argument("--out",
                    default=str(Path(__file__).resolve().parent.parent
                                / "data" / "cpk_to_mc.json"),
                    help="Output JSON path (default: Python/data/cpk_to_mc.json)")
    ap.add_argument("--max-cpk-per-chapter", type=int, default=0,
                    help="If >0, only process the first N cpks per chapter"
                         " (for quick smoke runs)")
    ap.add_argument("--resume", action="store_true",
                    help="If the --out file exists, load it and skip any "
                         "chapters already present (lets you build the JSON"
                         " across multiple shorter runs).")
    ap.add_argument("--only-chapters", default="",
                    help="Comma-separated list of chapter labels to process"
                         " (matches the .sp filename stem). When empty,"
                         " all .sp files are processed.")
    args = ap.parse_args()

    t0 = time.time()
    # Prefer loading mc PNGs from --mc-dir (extracted) -- it's ~200x
    # faster than re-decrypting the OBB archive on every run.
    android_arrs = {}
    if args.mc_dir and os.path.isdir(args.mc_dir):
        print(f"Loading mc PNGs from {args.mc_dir}...")
        for fn in sorted(os.listdir(args.mc_dir)):
            if not (fn.startswith("mc") and fn.endswith(".png")):
                continue
            body = fn[2:-4]  # "{id}_{variant}"
            try:
                id_s, var_s = body.split("_", 1)
                mc_id = int(id_s); variant = int(var_s)
            except (ValueError, IndexError):
                continue
            try:
                img = Image.open(os.path.join(args.mc_dir, fn))
                android_arrs[(mc_id, variant)] = _to_rgba_array(img,
                                                                SHEET_DIM)
            except Exception as e:
                print(f"  skip {fn}: {e}")
        print(f"  {len(android_arrs)} mc PNGs loaded "
              f"({time.time()-t0:.1f}s)")
    if not android_arrs:
        print(f"Loading OBB: {args.obb}")
        obb_files = load_zip_container(args.obb)
        mc_ids = list_android_mc_ids(obb_files)
        for mc_id in mc_ids:
            for variant in list_android_mc_variants(obb_files, mc_id):
                img = load_android_mc_png(obb_files, mc_id, variant)
                if img is None:
                    continue
                android_arrs[(mc_id, variant)] = _to_rgba_array(img,
                                                                 SHEET_DIM)
        print(f"  {len(android_arrs)} variant arrays loaded "
              f"({time.time()-t0:.1f}s)")

    # Resume support: load existing JSON if any
    out_data = {}
    if args.resume and os.path.exists(args.out):
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                out_data = json.load(f)
            print(f"Resume: loaded existing {args.out} with chapters "
                  f"{list(out_data.keys())}")
        except Exception as e:
            print(f"Resume: could not load existing JSON: {e}")
            out_data = {}
    only_chapters = set(
        c.strip() for c in args.only_chapters.split(",") if c.strip()
    )
    n_comparisons = 0

    sp_paths = sorted(glob.glob(os.path.join(args.sp_dir, "*.sp")))
    print(f"\nProcessing {len(sp_paths)} scratchpads...")
    for sp_path in sp_paths:
        chapter_label = os.path.splitext(os.path.basename(sp_path))[0]
        if only_chapters and chapter_label not in only_chapters:
            continue
        if args.resume and chapter_label in out_data:
            print(f"  {chapter_label}: SKIP (already in resume file)")
            continue
        t_chap = time.time()
        sp_files = parse_sp(sp_path)
        resolver = MobileTilesetResolver(sp_files)
        cpks = sorted(resolver.cpk_index.keys())
        if args.max_cpk_per_chapter > 0:
            cpks = cpks[:args.max_cpk_per_chapter]
        chap_data = {}

        for eid in cpks:
            n_palettes = count_cpk_palettes(sp_files, eid)
            by_palette = {}
            best_overall = None  # (sad, palette_idx, record)
            for pal_idx in range(n_palettes):
                try:
                    mob_img = resolver.get(eid, pal_idx)
                except Exception:
                    mob_img = None
                if mob_img is None:
                    continue
                mob_arr = _mobile_upscaled_array(mob_img, SHEET_DIM)
                rec = _record_per_palette(mob_arr, android_arrs)
                by_palette[str(pal_idx)] = rec
                n_comparisons += len(android_arrs)
                if best_overall is None or rec["best_sad"] < best_overall[0]:
                    best_overall = (rec["best_sad"], pal_idx, rec)
            if best_overall is None:
                continue
            top_rec = dict(best_overall[2])
            top_rec["best_palette"] = best_overall[1]
            top_rec["by_palette"] = by_palette
            chap_data[str(eid)] = top_rec
        out_data[chapter_label] = chap_data
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out_data, f, indent=1, ensure_ascii=False)
        print(f"  {chapter_label}: {len(cpks)} cpks  "
              f"({time.time()-t_chap:.1f}s, total {n_comparisons:,} comparisons)")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=1, ensure_ascii=False)
    print(f"\nWrote {args.out} ({time.time()-t0:.1f}s total, "
          f"{n_comparisons:,} SAD comparisons)")


if __name__ == "__main__":
    main()
