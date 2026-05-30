#!/usr/bin/env python3
"""
One-shot: pre-seed mc_overrides.json with engine-parser answers.

For every parsable Android map (1,679), run parse_android_map_engine() and
write the (mc_id_slot0, variant_slot0) result into mc_overrides.json["by_map"]
with auto_from="engine_parser" and auto_confidence=1.0.

Rules (in priority order — first match wins):
  1. If existing entry has user_confirmed=True → PRESERVE untouched.
     Manual annotation is ground truth.
  2. If engine returns slot0 == -1 (no tileset for this map) → SKIP, do not
     auto-fill. Renderer will fall back to by_group / default.
  3. If existing entry matches the engine's answer (mc_id + variant) → bump
     the metadata to auto_from="engine_parser", auto_confidence=1.0 (so
     future readers know it's deterministic), but leave the mc_id/variant.
  4. Otherwise → WRITE a new entry overwriting the existing low-confidence
     guess. Mark it as engine-derived.

A timestamped backup of the original mc_overrides.json is saved before any
write. The script is idempotent — running it twice yields identical output.

Usage:
    python3 seed_mc_overrides_from_engine.py            # dry-run preview
    python3 seed_mc_overrides_from_engine.py --apply    # actually write
    python3 seed_mc_overrides_from_engine.py --apply --proper-obb PATH
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

# Import the toolkit module from the parent folder. This script now lives
# in ``Python/tools/`` after the package refactor; the launcher (and the
# ffd/ package itself) sit one level up.
THIS_DIR = Path(__file__).resolve().parent
PYTHON_DIR = THIS_DIR.parent              # contains ffd_toolkit.py + ffd/
sys.path.insert(0, str(PYTHON_DIR))

import ffd_toolkit as tk  # type: ignore  # noqa: E402

PROJECT_ROOT = PYTHON_DIR.parent          # the actual project root
DEFAULT_OBB = PROJECT_ROOT / "Android" / "proper_obb"
# Sidecar JSONs now live in Python/data/ so they ship inside the toolkit
# folder for git tracking. See Python/ffd/data/ffdata.py:_data_dir().
OVERRIDES_PATH = PYTHON_DIR / "data" / "mc_overrides.json"


def collect_engine_answers(obb_folder: Path):
    """
    Walk every mpkh*.dat → mpk{group}_{pack}.dat → chunk in the OBB folder,
    run the engine parser, and yield (g, p, m, engine_info_dict).
    """
    fd = tk.FFData()
    fd.set_archive("obb", str(obb_folder))

    for mpkh_key in sorted(fd.obb_files):
        name = Path(mpkh_key).name
        if not (name.startswith("mpkh") and name.endswith(".dat")):
            continue
        g_str = name[4:].split(".")[0]
        if not g_str.isdigit():
            continue
        g = int(g_str)

        try:
            packs = tk.parse_mpkh_index(fd.obb_files[mpkh_key])
        except Exception as e:
            print(f"  [warn] mpkh{g} parse failed: {e}", file=sys.stderr)
            continue

        for pi, entries in enumerate(packs):
            pack_name = f"mpk{g_str}_{pi}.dat"
            pk_key = next(
                (k for k in fd.obb_files if Path(k).name == pack_name), None
            )
            if not pk_key:
                continue
            pk = fd.obb_files[pk_key]

            for (mid, off, sz) in entries:
                if off + sz > len(pk) or sz < 30:
                    continue
                chunk = pk[off : off + sz]
                info = tk.parse_android_map_engine(chunk)
                if info is None:
                    continue
                yield (g, pi, mid, info)


def make_engine_entry(info: dict, prev: dict | None) -> dict:
    """Build the override dict to store for this map."""
    entry = {
        "mc_id": info["mc_id_slot0"],
        "variant": info["variant_slot0"] & 0xFF,
        "mc_id_slot1": info["mc_id_slot1"],
        "variant_slot1": info["variant_slot1"] & 0xFF,
        "user_confirmed": False,
        "auto_from": "engine_parser",
        "auto_confidence": 1.0,
    }
    # Preserve render_band / alt fields if previously computed — they're
    # rendering hints derived elsewhere, orthogonal to mc_id selection.
    if prev:
        for k in ("render_band", "render_rel_gap", "render_alt_mc_id"):
            if k in prev:
                entry[k] = prev[k]
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Actually write mc_overrides.json. Default is dry-run.")
    ap.add_argument("--proper-obb", type=Path, default=DEFAULT_OBB,
                    help=f"Path to proper_obb folder (default: {DEFAULT_OBB})")
    ap.add_argument("--overrides", type=Path, default=OVERRIDES_PATH,
                    help=f"Path to mc_overrides.json (default: {OVERRIDES_PATH})")
    args = ap.parse_args()

    if not args.proper_obb.exists():
        print(f"FATAL: proper_obb folder not found: {args.proper_obb}",
              file=sys.stderr)
        return 2
    if not args.overrides.exists():
        print(f"FATAL: mc_overrides.json not found: {args.overrides}",
              file=sys.stderr)
        return 2

    overrides = json.loads(args.overrides.read_text(encoding="utf-8"))
    by_map: dict = overrides.setdefault("by_map", {})
    # Snapshot original keys/data so we can categorize each map.
    original_by_map = {k: dict(v) for k, v in by_map.items()}

    # Stats
    seen = 0
    preserved_user = 0
    skipped_no_signal = 0  # engine returned slot0 = -1
    confirmed_match = 0    # engine agrees with existing override
    replaced = 0           # engine overrides an existing low-confidence guess
    added = 0              # new map (was not in by_map)

    # For diff preview
    sample_replacements = []   # capped
    sample_additions = []

    for (g, p, m, info) in collect_engine_answers(args.proper_obb):
        seen += 1
        key = tk.map_key(g, p, m)
        prev = original_by_map.get(key)

        # Rule 1: preserve user_confirmed
        if prev and prev.get("user_confirmed"):
            preserved_user += 1
            continue

        # Rule 2: engine has no signal for this map
        if info["mc_id_slot0"] == -1:
            skipped_no_signal += 1
            continue

        new_entry = make_engine_entry(info, prev)

        if prev is None:
            added += 1
            by_map[key] = new_entry
            if len(sample_additions) < 5:
                sample_additions.append((key, new_entry))
            continue

        # Rule 3: engine matches existing — refresh metadata only
        if (prev.get("mc_id") == info["mc_id_slot0"]
                and prev.get("variant") == (info["variant_slot0"] & 0xFF)):
            confirmed_match += 1
            by_map[key] = new_entry          # idempotent metadata refresh
            continue

        # Rule 4: replace low-confidence existing guess
        replaced += 1
        if len(sample_replacements) < 5:
            sample_replacements.append((key, prev, new_entry))
        by_map[key] = new_entry

    print(f"Maps engine-parsed:              {seen}")
    print(f"  preserved (user_confirmed):    {preserved_user}")
    print(f"  skipped (engine slot0 = -1):   {skipped_no_signal}")
    print(f"  agreed (refreshed metadata):   {confirmed_match}")
    print(f"  replaced low-confidence guess: {replaced}")
    print(f"  newly added (was unmapped):    {added}")
    print()
    print(f"by_map size before: {len(original_by_map)}")
    print(f"by_map size after:  {len(by_map)}")

    if sample_replacements:
        print("\nSample replacements (engine disagreed with existing):")
        for k, prev, new in sample_replacements:
            print(f"  {k}: mc_id {prev.get('mc_id')} → {new['mc_id']}"
                  f"  (was auto_confidence={prev.get('auto_confidence'):.3f}"
                  f" user_confirmed={prev.get('user_confirmed')})")
    if sample_additions:
        print("\nSample additions (newly resolved by engine):")
        for k, new in sample_additions:
            print(f"  {k}: mc_id={new['mc_id']} variant={new['variant']}"
                  f"  slot1=({new['mc_id_slot1']}, {new['variant_slot1']})")

    if not args.apply:
        print("\n(dry-run — re-run with --apply to write changes)")
        return 0

    # Back up before writing
    timestamp = time.strftime("%Y%m%dT%H%M%S")
    backup = args.overrides.with_suffix(f".json.bak-{timestamp}")
    shutil.copy2(args.overrides, backup)
    args.overrides.write_text(
        encoding="utf-8",
    )
    print(f"Wrote {args.overrides}")
    print(f"Backup at {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
