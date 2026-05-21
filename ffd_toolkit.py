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
from ffd.music.parser import parse_snd, parse_resbin, parse_audio_names_resbin
from ffd.animation.parser import parse_field_anm
from ffd.formats.form_bin import parse_form_bin
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


def main():
    """Launch the Tk GUI."""
    if not HAS_GUI:
        print("ERROR: Tkinter and/or PIL.ImageTk are not available; the GUI "
              "cannot start. Parser modules in `ffd.*` still import fine for "
              "headless analysis.", file=sys.stderr)
        sys.exit(1)
    FFDApp().mainloop()


if __name__ == "__main__":
    main()
