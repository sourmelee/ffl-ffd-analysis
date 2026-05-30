"""Command-line driver for the Android export + ICP encoder.

Wired up from ffd_toolkit.py main() so a user can do batch work without
spinning up the GUI:

    python ffd_toolkit.py --android-export --sp Chapter1.sp --out ./out
    python ffd_toolkit.py --android-export --sp-dir ./Mobile/Scratchpads --out ./out
    python ffd_toolkit.py --android-encode --png-dir ./png --dat-dir ./dat
    python ffd_toolkit.py --android-encode --png-dir ./png --dat-dir ./dat --ref-raw ./raw_obb
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .exporter import (
    AndroidExportOptions, export_all_chapters,
)
from .icp import encode_icp_directory


# Flag names that should route into this CLI (checked from main()).
EXPORT_FLAGS = {"--android-export"}
ENCODE_FLAGS = {"--android-encode"}


def is_android_cli(argv):
    return any(a in EXPORT_FLAGS or a in ENCODE_FLAGS for a in argv)


def _build_export_parser():
    p = argparse.ArgumentParser(
        prog="ffd_toolkit.py --android-export",
        description="Extract Mobile .sp data to Android-formatted PNGs.")
    p.add_argument("--android-export", action="store_true",
                   help="(dispatch flag, always required)")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--sp", action="append", default=[],
                   help="A single .sp file (repeatable)")
    g.add_argument("--sp-dir",
                   help="A folder containing one or more .sp files")
    p.add_argument("--out", required=True,
                   help="Output folder (per-chapter subfolders created here)")
    p.add_argument("--scale", type=int, default=2,
                   help="Nearest-neighbor upscale factor (default 2)")
    p.add_argument("--no-monsters", action="store_true")
    p.add_argument("--no-characters", action="store_true")
    p.add_argument("--no-tilesets", action="store_true")
    p.add_argument("--no-gifs", action="store_true",
                   help="Skip hidden-GIF entries in sprite containers")
    return p


def _build_encode_parser():
    p = argparse.ArgumentParser(
        prog="ffd_toolkit.py --android-encode",
        description="Encode a folder of PNGs back into ICP-wrapped .dat files.")
    p.add_argument("--android-encode", action="store_true",
                   help="(dispatch flag, always required)")
    p.add_argument("--png-dir", required=True, help="Folder of PNGs to encode")
    p.add_argument("--dat-dir", required=True, help="Output folder for .dat")
    p.add_argument("--ref-raw", default=None,
                   help="Optional folder of original raw .dat files "
                        "(for byte-faithful header preservation)")
    p.add_argument("--filter-flag", type=int, default=1, choices=(0, 1),
                   help="ICP filter flag when no reference (0=GL_LINEAR, "
                        "1=GL_NEAREST). Default 1.")
    return p


def run(argv):
    """Dispatch and return an exit code."""
    if any(a in EXPORT_FLAGS for a in argv):
        args = _build_export_parser().parse_args(argv)
        # Gather slot -> {filename: bytes} from the inputs
        from ..containers import parse_sp
        sources = []
        for sp_path in args.sp:
            sources.append(Path(sp_path))
        if args.sp_dir:
            for p in sorted(Path(args.sp_dir).glob("*.sp")):
                sources.append(p)
        if not sources:
            print("No .sp files supplied.", file=sys.stderr)
            return 2

        opts = AndroidExportOptions(
            scale=max(1, args.scale),
            include_monsters=not args.no_monsters,
            include_characters=not args.no_characters,
            include_tilesets=not args.no_tilesets,
            include_hidden_gifs=not args.no_gifs,
        )
        slots = {}
        for sp_path in sources:
            try:
                files = parse_sp(sp_path)
            except Exception as exc:
                print(f"  FAIL  {sp_path}: {type(exc).__name__}: {exc}",
                      file=sys.stderr)
                continue
            slots[sp_path.stem] = dict(files)
        export_all_chapters(slots, args.out, opts)
        return 0

    if any(a in ENCODE_FLAGS for a in argv):
        args = _build_encode_parser().parse_args(argv)
        n = encode_icp_directory(
            args.png_dir, args.dat_dir,
            ref_raw_dir=args.ref_raw,
            filter_flag=args.filter_flag,
            log=print,
        )
        print(f"\nEncoded {n} files.")
        return 0

    print("usage: --android-export | --android-encode  (see --help)",
          file=sys.stderr)
    return 2
