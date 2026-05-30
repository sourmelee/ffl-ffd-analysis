"""Mobile (.sp) -> Android-formatted asset export.

For each loaded chapter scratchpad we render the three asset categories
the user asked about and write them under per-chapter folders with the
Android filename convention:

    <outdir>/<Chapter>/monsters/mon<E>_<V>.png        - from ene.dat
    <outdir>/<Chapter>/characters/fldchr<E>_<V>.png   - from chpk.dat
    <outdir>/<Chapter>/tilesets/mc<EID>_<PAL>.png     - from cpk*.dat (via MobileTilesetResolver)

All images are upscaled 2x with nearest-neighbor (pixel-perfect doubling
matches the Android port's source pixels for FFD).

Each chapter is exported into its own subfolder so files with the same
Android ID coming from different chapters don't overwrite each other.
The naming itself is the Android 1:1 form (zero-stripped IDs) so the
filenames can be dropped straight into a proper_obb-equivalent tree.
"""

from __future__ import annotations

import io
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from PIL import Image

from ..containers import parse_sp
from ..sprites.container import parse_sprite_container, extract_hidden_gifs
from ..images.ic import render_ic
from ..tilesets.parser import MobileTilesetResolver


SPRITE_SPECS = [
    # (kind_key,    source filename, output subdir,  Android filename prefix)
    ("monsters",    "ene.dat",       "monsters",     "mon"),
    ("characters",  "chpk.dat",      "characters",   "fldchr"),
]

TILESET_SUBDIR = "tilesets"
TILESET_PREFIX = "mc"


@dataclass
class AndroidExportOptions:
    """User-tunable options for the Android exporter.

    scale defaults to 2 to match the original Android port's source
    pixel dimensions. Passing 1 disables upscaling.
    """
    scale: int = 2
    include_monsters: bool = True
    include_characters: bool = True
    include_tilesets: bool = True
    include_hidden_gifs: bool = True
    max_palettes_per_tile: int = 8  # MobileTilesetResolver supports 0..7


@dataclass
class AndroidExportStats:
    monsters: int = 0
    characters: int = 0
    tilesets: int = 0
    gifs: int = 0
    skipped_collisions: int = 0
    errors: List[str] = field(default_factory=list)


def _safe_chapter_name(slot_label):
    """Turn a slot label into a filesystem-safe folder name."""
    bad = set('<>:"/\\|?*\n\r\t\0')
    out = "".join("_" if (c in bad or ord(c) < 0x20) else c
                  for c in slot_label.replace(" ", "_"))
    out = out.rstrip(". ")
    return out or "Chapter"


def _scale_nearest(img, scale):
    if scale == 1:
        return img
    w, h = img.size
    return img.resize((w * scale, h * scale), Image.NEAREST)


def _normalize_for_png(img):
    if img.mode == "RGBA":
        return img
    return img.convert("RGBA")


def _export_sprite_container(blob, out_dir, prefix, opts, log, stats, counter_attr):
    """Render every (entry, variant) pair to out_dir/<prefix><e>_<v>.png.

    Falls back to extract_hidden_gifs for entries that didn't parse as
    'ic', if opts.include_hidden_gifs is on. The ic parse runs FIRST
    so a clean ic interpretation wins over a GIF at the same slot.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    try:
        entries = list(parse_sprite_container(blob))
    except Exception as exc:
        log(f"      sprite-parse failed: {exc}")
        entries = []

    for (e, var, ic, _raw) in entries:
        try:
            img = _normalize_for_png(render_ic(ic))
        except Exception as exc:
            log(f"      entry {e:>3} v{var}: render_ic FAILED: {exc}")
            continue
        scaled = _scale_nearest(img, opts.scale)
        path = out_dir / f"{prefix}{e}_{var}.png"
        scaled.save(path)
        written[(e, var)] = path
        setattr(stats, counter_attr, getattr(stats, counter_attr) + 1)

    if opts.include_hidden_gifs:
        try:
            gifs = list(extract_hidden_gifs(blob))
        except Exception as exc:
            log(f"      gif-scan failed: {exc}")
            gifs = []
        for (gif_idx, _hdr_size, gif_bytes) in gifs:
            slot = (gif_idx, 0)
            if slot in written:
                stats.skipped_collisions += 1
                log(f"      gif idx {gif_idx}: collides with ic entry "
                    f"{gif_idx} v0 -- keeping ic version")
                continue
            try:
                gif_img = Image.open(io.BytesIO(gif_bytes))
                gif_img.seek(0)
                img = _normalize_for_png(gif_img)
            except Exception as exc:
                log(f"      gif idx {gif_idx}: open failed: {exc}")
                continue
            scaled = _scale_nearest(img, opts.scale)
            path = out_dir / f"{prefix}{gif_idx}_0.png"
            scaled.save(path)
            stats.gifs += 1


def _export_tilesets(files, out_dir, opts, log, stats):
    """Render every (eid, pal) tileset variant via MobileTilesetResolver."""
    try:
        res = MobileTilesetResolver(files)
    except Exception as exc:
        log(f"      MobileTilesetResolver init failed: {exc}")
        return
    if not res.cpk_index:
        log("      tileset index empty (no boot_data section 48 found?)")
        return

    out_dir.mkdir(parents=True, exist_ok=True)
    for eid in sorted(res.cpk_index):
        for pal in range(opts.max_palettes_per_tile):
            try:
                img = res.get(eid, pal)
            except Exception as exc:
                log(f"      tile {eid} pal{pal}: resolve failed: {exc}")
                break
            if img is None:
                break
            scaled = _scale_nearest(_normalize_for_png(img), opts.scale)
            path = out_dir / f"{TILESET_PREFIX}{eid}_{pal}.png"
            scaled.save(path)
            stats.tilesets += 1


def export_chapter_to_android(slot_label, files, out_root, opts=None, log=None):
    """Export one chapter's monsters/characters/tilesets to Android format."""
    if opts is None:
        opts = AndroidExportOptions()
    if log is None:
        log = print

    stats = AndroidExportStats()
    chapter_dir = Path(out_root) / _safe_chapter_name(slot_label)
    log(f"  [{slot_label}] -> {chapter_dir}")

    for (kind, src_name, subdir, prefix) in SPRITE_SPECS:
        flag = getattr(opts, f"include_{kind}")
        if not flag:
            continue
        blob = files.get(src_name)
        if blob is None:
            log(f"    {src_name} not in slot; skipping {kind}")
            continue
        before = getattr(stats, kind)
        before_gifs = stats.gifs
        try:
            _export_sprite_container(
                blob, chapter_dir / subdir, prefix, opts,
                log=lambda m: log(m),
                stats=stats, counter_attr=kind,
            )
        except Exception:
            tb = traceback.format_exc(limit=2)
            stats.errors.append(f"{slot_label}/{kind}: {tb}")
            log(f"    {kind}: ERROR\n{tb}")
            continue
        added = getattr(stats, kind) - before
        gif_added = stats.gifs - before_gifs
        extra = f" (+ {gif_added} from hidden GIFs)" if gif_added else ""
        log(f"    {kind}: {added} sprites{extra} -> {chapter_dir / subdir}")

    if opts.include_tilesets:
        before = stats.tilesets
        try:
            _export_tilesets(files, chapter_dir / TILESET_SUBDIR, opts,
                             log=lambda m: log(m), stats=stats)
        except Exception:
            tb = traceback.format_exc(limit=2)
            stats.errors.append(f"{slot_label}/tilesets: {tb}")
            log(f"    tilesets: ERROR\n{tb}")
        else:
            added = stats.tilesets - before
            log(f"    tilesets: {added} variants -> "
                f"{chapter_dir / TILESET_SUBDIR}")

    return stats


def export_all_chapters(sp_slots, out_root, opts=None, log=None):
    """Run export_chapter_to_android over every loaded SP slot."""
    if log is None:
        log = print
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    results = {}
    for slot_label, files in sp_slots.items():
        if not files:
            continue
        stats = export_chapter_to_android(slot_label, files, out_root, opts, log)
        results[slot_label] = stats
    total = sum(s.monsters + s.characters + s.tilesets + s.gifs
                for s in results.values())
    log(f"\nDone. Wrote {total} PNGs across {len(results)} chapter(s).")
    return results


def export_sp_file(sp_path, out_root, opts=None, log=None):
    """Open a .sp scratchpad from disk and export it. Handy for the CLI."""
    sp_path = Path(sp_path)
    files = parse_sp(sp_path)
    label = sp_path.stem
    return {label: export_chapter_to_android(label, files, out_root, opts, log)}
