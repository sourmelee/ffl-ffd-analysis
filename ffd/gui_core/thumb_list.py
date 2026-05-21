"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations

import io
import os
import struct
import sys
import zipfile
import zlib
import threading
import traceback
import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Optional, Iterable

from PIL import Image, ImageDraw

from ..gui_stub import (
    tk, ttk, filedialog, messagebox, ScrolledText, ImageTk,
    HAS_GUI, HAS_TK, HAS_IMAGETK,
)
from ..constants import (
    SP_BASE, DIR_POS, SP_SLOTS, KNOWN_DAT_FILES,
    CPK_NAMES, MPK_NAMES, CHARA_TABLE, ELEMENTS, STATUSES,
)
from ..binary import (
    be_u8, be_s8, be_u16, be_u32, le_u16, le_u32,
    read_pstr_sjis, safe_decode_ascii,
)
from ..containers import parse_sp, load_zip_container, load_folder_as_archive, load_jam_manifest
from ..images.ic import ICImage, parse_ic, render_ic, find_ic_offsets, _decode_palette_bgr, _decode_palette_rgb
from ..sprites.container import (
    parse_sprite_container, iter_dat_entries, extract_hidden_gifs, parse_bip,
)
from ..maps.mobile import (
    parse_mobile_map_chunk, scan_mobile_mpk_chunks,
    parse_mobile_mpk, parse_mpkh_index,
)
from ..maps.android import (
    _RomReader, parse_android_map_engine, parse_android_map_chunk,
)
from ..maps.mc_overrides import (
    MC_OVERRIDES_FILENAME, CPK_TO_MC_FILENAME,
    empty_mc_overrides, load_mc_overrides, save_mc_overrides,
    map_key, bucket_key, load_cpk_to_mc, invert_cpk_to_mc, lookup_primary_mc,
)
from ..boot.sections import (
    boot_section_be, boot_section_le,
    detect_boot_endian, parse_boot_toc, boot_section_label,
    ANDROID_BOOT_SECTION_LABELS, MOBILE_BOOT_SECTION_LABELS,
    ANDROID_BOOT_LOADERS, _parse_android_namedesc_section,
)
from ..tilesets.parser import (
    parse_mpk_index_mobile, parse_cpk_index_mobile,
    parse_android_tileset_lookup, flat_pack_index,
    load_mobile_tileset, MobileTilesetResolver,
)
from ..monsters.parser import (
    parse_enemies_mobile, parse_monsters_android,
    parse_enemy_names_android, parse_bem,
)
from ..items.parser import parse_items_mobile, parse_items_android
from ..jobs.parser  import parse_jobs_mobile, parse_jobs_android
from ..abilities.parser import (
    parse_magic_android, parse_passive_abilities_android,
    parse_command_abilities_android,
)
from ..characters.parser import parse_chara_set
from ..text.parser    import MESSAGE_SECTION_LABELS, parse_message, parse_msd, _msd_read_strings
from ..music.parser   import parse_snd, parse_resbin, parse_audio_names_resbin
from ..animation.parser import parse_field_anm
from ..formats.form_bin import parse_form_bin
from ..events.opcodes  import (
    EVENT_SCRIPT_OPCODES, _decode_event_operands, disassemble_script_block,
)
from ..events.mobile   import (
    map_event_script_region, _mobile_true_event_offset,
    parse_mobile_event_region, disassemble_event_region,
)
from ..events.android  import (
    parse_android_event_pack, disassemble_android_event_pack, scan_android_event_packs,
)
from ..events.strings  import extract_sjis_strings
from ..data.ffdata     import FFData
from ..gui_core.helpers import (
    pil_to_photo, _scaled, open_in_default_app,
    format_element_bits, format_status_bits, hex_dump, _hex_dump,
)
from ..gui_core.base   import TabBase



# ============================================================================
# REUSABLE: thumbnail-grid sidebar with scrollable list
# ============================================================================

class ThumbList(ttk.Frame):
    """Scrollable list of (label, thumbnail) pairs; click selects."""

    def __init__(self, parent, on_select, thumb_size=64):
        super().__init__(parent)
        self.on_select = on_select
        self.thumb_size = thumb_size

        self._canvas = tk.Canvas(self, width=240, bg="#222",
                                 highlightthickness=0)
        self._sb = ttk.Scrollbar(self, orient="vertical",
                                 command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="left", fill="y")

        self._inner = ttk.Frame(self._canvas)
        self._inner_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)
        self._canvas.bind_all("<Button-4>", lambda e:
                              self._canvas.yview_scroll(-1, "units"))
        self._canvas.bind_all("<Button-5>", lambda e:
                              self._canvas.yview_scroll(1, "units"))

        self._photos = []
        self._items = []     # list of (frame, key, label_text)
        self._selected = None

    def _on_wheel(self, event):
        try:
            self._canvas.yview_scroll(int(-event.delta/120), "units")
        except Exception:
            pass

    def clear(self):
        for it in self._items:
            it[0].destroy()
        self._items = []
        self._photos = []
        self._selected = None

    def add(self, key, image: Optional[Image.Image], label: str):
        row = ttk.Frame(self._inner, padding=2, relief="flat")
        row.grid(sticky="ew", padx=2, pady=1)
        row.bind("<Button-1>", lambda e, k=key: self._click(k))

        if image is not None and image.width > 0 and image.height > 0:
            thumb = image.copy()
            thumb.thumbnail((self.thumb_size, self.thumb_size), Image.NEAREST)
            # Pillow's thumbnail can produce a 1×N or N×1 image for very
            # extreme aspect ratios. Guard against that — guarantee at
            # least 8 px in either dimension by upscaling.
            if thumb.width < 8 or thumb.height < 8:
                scale = max(8.0 / max(thumb.width, 1),
                            8.0 / max(thumb.height, 1))
                new_w = max(8, int(thumb.width * scale))
                new_h = max(8, int(thumb.height * scale))
                thumb = thumb.resize((new_w, new_h), Image.NEAREST)
            ph = ImageTk.PhotoImage(thumb)
            self._photos.append(ph)
            lbl = ttk.Label(row, image=ph)
            lbl.pack(side="left", padx=2)
            lbl.bind("<Button-1>", lambda e, k=key: self._click(k))
        else:
            ttk.Label(row, text="—", width=4).pack(side="left", padx=2)

        text_lbl = ttk.Label(row, text=label, anchor="w", justify="left",
                             wraplength=160)
        text_lbl.pack(side="left", fill="x", expand=True)
        text_lbl.bind("<Button-1>", lambda e, k=key: self._click(k))

        self._items.append((row, key, label))

    def _click(self, key):
        for fr, k, _ in self._items:
            fr.configure(relief="flat")
        for fr, k, _ in self._items:
            if k == key:
                fr.configure(relief="solid")
                break
        self._selected = key
        self.on_select(key)


# ============================================================================
# TAB — TILESETS (mobile cpk*.dat + Android mc*.png)
# ============================================================================
