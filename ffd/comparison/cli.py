"""Headless --compare driver.

    python ffd_toolkit.py --compare <type> [m_id [a_id]]
                          [--sp PATH ...]
                          [--obb PATH] [--apk PATH]
                          [--m-source KEY] [--a-source KEY]
                          [--raw]
                          [--show-identical]
                          [--link-id]
                          [--list-sources]

If only one id is given, it's used for both sides. If neither, the first
non-deleted record on each side is picked.

`--m-source` / `--a-source` pick a specific source when the asset type
exposes more than one. The arg is a substring match against the source
labels (case-insensitive). Use `--list-sources <kind>` to see what's
available for the data currently loaded.

`--obb` and `--apk` accept either a real archive or a folder of
extracted contents (Android/proper_obb/, etc.).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..constants import SP_SLOTS
from ..containers import parse_sp, load_folder_as_archive, load_zip_container
from ..data.ffdata import FFData
from .registry import ASSET_KINDS, compare_records, list_asset_kinds


def _build_arg_parser(prog="ffd_toolkit.py"):
    p = argparse.ArgumentParser(
        prog=prog,
        description="Mobile vs Android asset comparison (headless).")
    p.add_argument("--compare", nargs="+", metavar="ARG",
                   help="<kind> [m_id [a_id]] -- run comparison and exit.")
    p.add_argument("--sp", action="append", default=[], metavar="PATH",
                   help="Path to a .sp scratchpad OR a folder of .dat files "
                        "(repeatable).")
    p.add_argument("--obb", metavar="PATH",
                   help="Path to .obb OR an extracted folder.")
    p.add_argument("--apk", metavar="PATH",
                   help="Path to .apk OR an extracted folder.")
    p.add_argument("--m-source", metavar="KEY", default=None,
                   help="Mobile source selector (substring of source label).")
    p.add_argument("--a-source", metavar="KEY", default=None,
                   help="Android source selector (substring of source label).")
    p.add_argument("--raw", action="store_true",
                   help="Raw byte diff instead of semantic field diff.")
    p.add_argument("--show-identical", action="store_true",
                   help="Don't hide identical fields/bytes.")
    p.add_argument("--link-id", action="store_true",
                   help="If only one id is given, use it for both sides.")
    p.add_argument("--list-kinds", action="store_true",
                   help="Print registered asset kinds and exit.")
    p.add_argument("--list-sources", metavar="KIND",
                   help="Print the sources the given kind exposes for the "
                        "currently loaded data and exit.")
    return p


def _slot_label_for(folder_name):
    """Normalise a folder name (Chapter1, ChapterGladiatorHall, ...) to the
    canonical SP_SLOTS label (Chapter 1, Prologue, ...) when there's a
    clean match. Returns None if no match -- caller picks the next free
    slot in that case."""
    import re
    if folder_name in SP_SLOTS:
        return folder_name
    # "Chapter1" -> "Chapter 1"
    m = re.match(r"^Chapter\s*(\d+)$", folder_name)
    if m:
        cand = "Chapter %s" % m.group(1)
        if cand in SP_SLOTS:
            return cand
    return None


def _load_sp_into(ffdata, path):
    label = None
    p_for_label = Path(path)
    hinted = _slot_label_for(p_for_label.stem if not p_for_label.is_dir()
                             else p_for_label.name)
    if hinted and ffdata.sp_slots.get(hinted) is None:
        label = hinted
    if label is None:
        for cand in SP_SLOTS:
            if ffdata.sp_slots.get(cand) is None:
                label = cand; break
    if label is None:
        print("WARN: all SP slots full, ignoring --sp %s" % path, file=sys.stderr)
        return
    p = Path(path)
    if p.is_dir():
        from collections import OrderedDict
        files = OrderedDict()
        # Walk recursively so chara_set.dat in _raw/ subdir is reachable
        # by basename (matches what parse_sp would have produced for
        # the equivalent .sp file).
        for entry in sorted(p.rglob("*")):
            if entry.is_file() and entry.name not in files:
                files[entry.name] = entry.read_bytes()
        ffdata.sp_slots[label] = files
        ffdata.sp_paths[label] = str(p)
        ffdata._notify()
    else:
        ffdata.set_sp(label, path)


def _load_archive_into(ffdata, kind, path):
    p = Path(path)
    if p.is_dir():
        files = load_folder_as_archive(path)
        if kind == "obb":
            ffdata.obb_files = files; ffdata.obb_path = path
        elif kind == "apk":
            ffdata.apk_files = files; ffdata.apk_path = path
        ffdata._invalidate_aux_caches()
        ffdata._notify()
    else:
        ffdata.set_archive(kind, path)


def _load_ffdata(args):
    ffdata = FFData()
    for path in args.sp or []:
        try:
            _load_sp_into(ffdata, path)
        except Exception as exc:
            print("WARN: failed to load --sp %s (%s)" % (path, exc), file=sys.stderr)
    if args.obb:
        try: _load_archive_into(ffdata, "obb", args.obb)
        except Exception as exc:
            print("WARN: failed to load --obb %s (%s)" % (args.obb, exc), file=sys.stderr)
    if args.apk:
        try: _load_archive_into(ffdata, "apk", args.apk)
        except Exception as exc:
            print("WARN: failed to load --apk %s (%s)" % (args.apk, exc), file=sys.stderr)
    return ffdata


def _dump_dict(label, d):
    print("--- %s ---" % label)
    if not d:
        print("  (empty / no record)"); return
    for k, v in d.items():
        if isinstance(v, (bytes, bytearray)):
            preview = v[:32].hex(" ")
            print("  %-14s <%dB> %s%s" % (k, len(v), preview,
                                          " ..." if len(v) > 32 else ""))
        else:
            print("  %-14s %s" % (k, v))


def _match_source(needle, sources):
    """Substring-match the user's --m-source / --a-source against the
    source list. Returns the matching key, or None if no match (defer to
    the loader's default)."""
    if not needle or not sources:
        return None
    q = needle.lower()
    for key, label in sources:
        if q in str(key).lower() or q in str(label).lower():
            return key
    return None


def run_cli(argv):
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_kinds:
        for nm in list_asset_kinds():
            kind = ASSET_KINDS[nm]
            n_src_m = "*" if kind.list_sources_mobile  else "-"
            n_src_a = "*" if kind.list_sources_android else "-"
            print("%-12s mob:%s and:%s  %s" % (nm, n_src_m, n_src_a, kind.notes or ""))
        return 0

    if args.list_sources:
        kind = ASSET_KINDS.get(args.list_sources)
        if kind is None:
            print("Unknown kind %r" % args.list_sources, file=sys.stderr); return 2
        ffdata = _load_ffdata(args)
        m_src = kind.list_sources_mobile(ffdata)  if kind.list_sources_mobile  else []
        a_src = kind.list_sources_android(ffdata) if kind.list_sources_android else []
        print("Mobile sources for %s:" % args.list_sources)
        for k, l in m_src or []: print("  %s  -- %s" % (k, l))
        if not m_src: print("  (none / single implicit source)")
        print("Android sources for %s:" % args.list_sources)
        for k, l in a_src or []: print("  %s  -- %s" % (k, l))
        if not a_src: print("  (none / single implicit source)")
        return 0

    if not args.compare:
        parser.print_help(); return 1

    kind_name = args.compare[0]
    if kind_name not in ASSET_KINDS:
        print("Unknown kind %r. Known: %s" %
              (kind_name, ", ".join(list_asset_kinds())), file=sys.stderr)
        return 2

    try:
        m_id = int(args.compare[1]) if len(args.compare) > 1 else -1
        if len(args.compare) > 2:
            a_id = int(args.compare[2])
        elif args.link_id or len(args.compare) == 2:
            a_id = m_id
        else:
            a_id = -1
    except ValueError as exc:
        print("Could not parse record ids: %s" % exc, file=sys.stderr); return 2

    ffdata = _load_ffdata(args)

    kind = ASSET_KINDS[kind_name]
    m_src = _match_source(getattr(args, "m_source", None),
                          kind.list_sources_mobile(ffdata)
                          if kind.list_sources_mobile else [])
    a_src = _match_source(getattr(args, "a_source", None),
                          kind.list_sources_android(ffdata)
                          if kind.list_sources_android else [])

    try:
        result = compare_records(
            kind_name, m_id, a_id, ffdata,
            hide_identical=not args.show_identical,
            mode="raw" if args.raw else "semantic",
            m_source=m_src, a_source=a_src,
        )
    except NotImplementedError as exc:
        print("Not implemented: %s" % exc, file=sys.stderr); return 3
    except Exception as exc:
        print("Comparison failed: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 4

    src_suffix = ""
    if m_src or a_src:
        src_suffix = "  [m_source=%s a_source=%s]" % (m_src or "default",
                                                     a_src or "default")
    print("=== %s ===  mobile=%d  android=%d%s" % (
        kind_name, m_id, a_id, src_suffix))
    print("Mobile total records:  %d" % result["m_total"])
    print("Android total records: %d" % result["a_total"])
    print()
    _dump_dict("Mobile decoded", result["m_dict"])
    print()
    _dump_dict("Android decoded", result["a_dict"])
    print()
    print("--- Diff (%s) ---" % ("raw bytes" if args.raw else "semantic"))
    print("  %-30s %-30s %-30s" % ("field", "mobile", "android"))
    print("  %s" % ("-" * 92))
    for row in result["rows"]:
        marker = "" if row.same else "  DIFF"
        print("  %-30s %-30s %-30s%s" % (
            row.field, row.mobile, row.android, marker))
    print()
    print(result["summary"])

    if result["m_record"] is None and result["a_record"] is None:
        return 2
    return 0
