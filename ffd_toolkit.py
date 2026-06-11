#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FF Dimensions / Legends Unified Toolkit -- launcher
====================================================

Loader and re-export shim for the historical single-file
``ffd_toolkit.py``. The implementation now lives in the ``ffd/`` package
(parsers split by domain, GUI tabs each in their own module). This file
exists to:

  1. Keep ``python ffd_toolkit.py`` working as the entry point.
  2. Re-export every public name the legacy module exposed, so external
     analysis scripts doing ``from ffd_toolkit import parse_ic`` continue
     to work without modification.

Run the GUI with:

    python ffd_toolkit.py
"""

from __future__ import annotations

import sys

# ---------------------------------------------------------------------------
# Public-API re-exports (verbatim from the legacy module's namespace).
# ---------------------------------------------------------------------------

from ffd import __version__

from ffd.constants import (
    SP_BASE, DIR_POS, SP_SLOTS, KNOWN_DAT_FILES,
    CPK_NAMES, MPK_NAMES, CHARA_TABLE, ELEMENTS, STATUSES,
)
from ffd.binary import (
    be_u8, be_s8, be_u16, be_u32, le_u16, le_u32,
    read_pstr_sjis, safe_decode_ascii,
)
from ffd.gui_stub import (
    HAS_GUI, HAS_TK, HAS_IMAGETK,
    tk, ttk, filedialog, messagebox, ScrolledText, ImageTk,
)
from ffd.containers import (
    parse_sp,
    load_zip_container, load_folder_as_archive,
    load_jam_manifest,
)
from ffd.containers.obb import (
    load_obb_as_dict, dict_to_obb, folder_to_obb,
)
from ffd.images.ic import (
    ICImage, parse_ic, render_ic, find_ic_offsets,
    _decode_palette_bgr, _decode_palette_rgb,
)
from ffd.sprites.container import (
    parse_sprite_container, iter_dat_entries,
    extract_hidden_gifs, parse_bip,
)
from ffd.maps.mobile import (
    parse_mobile_map_chunk, scan_mobile_mpk_chunks,
    parse_mobile_mpk, parse_mpkh_index,
)
from ffd.maps.android import (
    _RomReader, parse_android_map_engine, parse_android_map_chunk,
)
from ffd.maps.mc_overrides import (
    MC_OVERRIDES_FILENAME, CPK_TO_MC_FILENAME,
    empty_mc_overrides, load_mc_overrides, save_mc_overrides,
    map_key, bucket_key,
    load_cpk_to_mc, invert_cpk_to_mc, lookup_primary_mc,
)
from ffd.boot.sections import (
    boot_section_be, boot_section_le,
    detect_boot_endian, parse_boot_toc, boot_section_label,
    ANDROID_BOOT_SECTION_LABELS, MOBILE_BOOT_SECTION_LABELS,
    ANDROID_BOOT_LOADERS, _parse_android_namedesc_section,
)
from ffd.tilesets.parser import (
    parse_mpk_index_mobile, parse_cpk_index_mobile,
    parse_android_tileset_lookup, flat_pack_index,
    load_mobile_tileset, MobileTilesetResolver,
)
from ffd.monsters.parser import (
    parse_enemies_mobile, parse_monsters_android,
    parse_enemy_names_android, parse_bem,
)
from ffd.items.parser import parse_items_mobile, parse_items_android
from ffd.jobs.parser  import parse_jobs_mobile, parse_jobs_android
from ffd.abilities.parser import (
    parse_magic_android, parse_passive_abilities_android,
    parse_command_abilities_android,
)
from ffd.characters.parser import parse_chara_set
from ffd.text.parser import (
    MESSAGE_SECTION_LABELS, parse_message, parse_msd, _msd_read_strings,
)
from ffd.music.parser import (
    parse_snd, parse_resbin, parse_audio_names_resbin, SndEntry, BANK_ROLES,
)
from ffd.animation.parser import parse_field_anm, field_walk_entries
from ffd.formats.form_bin import parse_form_bin, parse_form_bin_android
from ffd.events.opcodes import (
    EVENT_SCRIPT_OPCODES, _decode_event_operands, disassemble_script_block,
)
from ffd.events.mobile import (
    map_event_script_region, _mobile_true_event_offset,
    parse_mobile_event_region, disassemble_event_region,
)
from ffd.events.android import (
    parse_android_event_pack, disassemble_android_event_pack,
    scan_android_event_packs,
)
from ffd.events.strings import extract_sjis_strings
from ffd.data.ffdata import FFData
from ffd.gui_core.helpers import (
    pil_to_photo, _scaled, open_in_default_app,
    format_element_bits, format_status_bits, hex_dump, _hex_dump,
)
from ffd.gui_core.base import TabBase
from ffd.gui_core.app  import FFDApp
from ffd.files_io.extract_tab import EXTRACT_OPTIONS

from ffd.comparison import (
    ASSET_KINDS, AssetKind, compare_records, list_asset_kinds,
    diff_dicts, diff_bytes, DiffRow, run_cli as _run_comparison_cli,
)

from ffd.android_export import (
    AndroidExportOptions, export_chapter_to_android, export_all_chapters,
    encode_icp_dat, encode_icp_directory, ICPEncodeError,
)


def _bake_ffsmith_cli(argv):
    """Handle --bake-ffsmith <out_dir> [--obb PATH | --proper DIR] [--limit N] [--only KEY]."""
    from ffd.android_export.ffsmith_bake import bake
    idx = argv.index("--bake-ffsmith")
    rest = argv[idx + 1:]
    usage = ("usage: python ffd_toolkit.py --bake-ffsmith <out_dir> "
             "[--obb PATH | --proper DIR] [--limit N] [--only KEY]")
    if not rest or rest[0].startswith("--"):
        print(usage, file=sys.stderr)
        return 2
    out_dir = rest[0]
    def get_opt(name):
        return rest[rest.index(name) + 1] if name in rest else None
    obb = get_opt("--obb")
    proper = get_opt("--proper")
    limit = get_opt("--limit")
    only = get_opt("--only")
    if obb is None and proper is None:
        print("error: provide --obb PATH or --proper DIR", file=sys.stderr)
        return 2
    man = bake(obb_path=obb, out_dir=out_dir, proper_dir=proper,
               limit=int(limit) if limit else None, only=only)
    print("Baked %d maps, %d tilesheets -> %s"
          % (len(man["maps"]), len(man["tilesheets"]), out_dir))
    return 0


def main():
    """Entry point: dispatch to a headless CLI if requested, else launch GUI."""
    argv = sys.argv[1:]
    if "--version" in argv or "-V" in argv:
        print(f"FFD/FFL Toolkit v{__version__}")
        sys.exit(0)
    from ffd.android_export.cli import is_android_cli, run as _run_android_cli
    if is_android_cli(argv):
        sys.exit(_run_android_cli(argv))
    if "--pack-obb" in argv:
        idx = argv.index("--pack-obb")
        rest = argv[idx+1:]
        if len(rest) < 2:
            print("usage: python ffd_toolkit.py --pack-obb <input-folder> <output.obb>",
                  file=sys.stderr)
            sys.exit(2)
        in_folder, out_obb = rest[0], rest[1]
        n = folder_to_obb(in_folder, out_obb)
        print(f"Packed {in_folder!r} -> {out_obb!r} ({n:,} bytes)")
        sys.exit(0)
    # Bake an FFSmith engine asset bundle from the Android OBB. The engine
    # consumes these directly; see Engine/docs/ASSET_PIPELINE.md.
    if "--bake-ffsmith" in argv:
        sys.exit(_bake_ffsmith_cli(argv))
    cli_flags = {"--compare", "--list-kinds", "--sp", "--obb", "--apk",
                 "--raw", "--show-identical", "--link-id"}
    if any(a in cli_flags or a.startswith("--compare=") for a in argv):
        sys.exit(_run_comparison_cli(argv))

    if not HAS_GUI:
        print("ERROR: Tkinter and/or PIL.ImageTk are not available; the GUI "
              "cannot start. Parser modules in `ffd.*` still import fine for "
              "headless analysis.", file=sys.stderr)
        sys.exit(1)
    print(f"FFD/FFL Toolkit v{__version__} -- starting GUI...")
    FFDApp().mainloop()


if __name__ == "__main__":
    main()
