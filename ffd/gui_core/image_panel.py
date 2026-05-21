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
# REUSABLE: image-viewer panel with zoom + scroll
# ============================================================================

class ImagePanel(ttk.Frame):
    """Scrollable canvas that shows a Pillow image with zoom controls."""

    def __init__(self, parent):
        super().__init__(parent)
        self._zoom = 1
        self._img: Optional[Image.Image] = None
        self._photo: Optional[ImageTk.PhotoImage] = None

        # Toolbar
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="−", width=3,
                   command=self.zoom_out).pack(side="left", padx=2, pady=2)
        ttk.Button(bar, text="+", width=3,
                   command=self.zoom_in).pack(side="left", padx=2, pady=2)
        ttk.Button(bar, text="Fit", width=4,
                   command=self.fit).pack(side="left", padx=2, pady=2)
        self._zoom_lbl = ttk.Label(bar, text="100%")
        self._zoom_lbl.pack(side="left", padx=4)
        self._info = ttk.Label(bar, text="", foreground="#666")
        self._info.pack(side="left", padx=8)
        self._save_btn = ttk.Button(bar, text="Save PNG…",
                                    command=self.save_png)
        self._save_btn.pack(side="right", padx=2, pady=2)

        # Scroll canvas
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="#222",
                                highlightthickness=0)
        hbar = ttk.Scrollbar(body, orient="horizontal",
                             command=self.canvas.xview)
        vbar = ttk.Scrollbar(body, orient="vertical",
                             command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set,
                              yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self._image_item = None

    def show(self, img: Optional[Image.Image], info: str = ""):
        self._img = img
        self._info.configure(text=info)
        if img is None:
            self.canvas.delete("all")
            self._photo = None
            self._image_item = None
            return
        self._render()

    def _render(self):
        if self._img is None:
            return
        z = max(1, int(self._zoom))
        if z != 1:
            disp = self._img.resize(
                (self._img.width * z, self._img.height * z), Image.NEAREST)
        else:
            disp = self._img
        self._photo = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self._image_item = self.canvas.create_image(0, 0, anchor="nw",
                                                    image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, disp.width, disp.height))
        self._zoom_lbl.configure(text=f"{z*100}%")

    def zoom_in(self):
        self._zoom = min(16, self._zoom + 1); self._render()
    def zoom_out(self):
        self._zoom = max(1, self._zoom - 1); self._render()
    def fit(self):
        self._zoom = 1; self._render()

    def save_png(self):
        if self._img is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")])
        if not path:
            return
        self._img.save(path)


# ============================================================================
# REUSABLE: thumbnail-grid sidebar with scrollable list
# ============================================================================
