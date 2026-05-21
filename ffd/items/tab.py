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



# =============================================================================
# Item Tab
# =============================================================================
class ItemTab(TabBase):
    LABEL = "Items"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="Mobile")
        for val in ("Mobile", "Android"):
            ttk.Radiobutton(top, text=val, variable=self.src_var, value=val,
                            command=self._reload).pack(side="left", padx=2)
        self.note = ttk.Label(top, text="", foreground="#a00"); self.note.pack(side="right")
        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("idx", "name", "type", "price", "atk", "def", "matk", "mdef", "elem", "extra")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=22)
        widths = {"idx": 48, "name": 200, "type": 60, "price": 60,
                  "atk": 50, "def": 50, "matk": 50, "mdef": 50, "elem": 110, "extra": 80}
        for c in cols:
            self.tree.heading(c, text=c.upper(), command=lambda cc=c: self._sort_by(cc))
            self.tree.column(c, width=widths.get(c, 60), anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(body, command=self.tree.yview); sb.pack(side="left", fill="y")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        ttk.Label(self, text="Details:").pack(anchor="w", padx=6)
        self.details = ScrolledText(self, height=8, wrap="word")
        self.details.pack(fill="x", padx=6, pady=(0, 6))
        self.entries = []
        self._sort_state = (None, False)

    def on_data_change(self):
        self._reload()

    def _reload(self):
        self.entries = []
        self.tree.delete(*self.tree.get_children())
        self.details.delete("1.0", "end")
        src = self.src_var.get()
        bd = self.data.boot_data_mobile() if src == "Mobile" else self.data.boot_data_android()
        if bd is None:
            self.note.config(text="boot_data.dat not found in any .sp slot." if src == "Mobile"
                             else "Android boot_data.dat not found in .obb/.apk.")
            return
        try:
            items = parse_items_mobile(bd)
        except Exception as exc:
            self.note.config(text=f"items parse error: {exc}"); return
        self.note.config(text=f"{len(items)} items loaded ({src})")
        for i, it in enumerate(items):
            elem_s = format_element_bits(it.get("element", 0) or 0)
            row = (str(i), it.get("name", f"item_{i}"), str(it.get("type", "-")),
                   str(it.get("price", "-")), str(it.get("atk", "-")),
                   str(it.get("def", "-")), str(it.get("matk", "-")),
                   str(it.get("mdef", "-")), elem_s, str(it.get("extra", "-")))
            self.entries.append(it); self.tree.insert("", "end", iid=str(i), values=row)

    def _on_select(self):
        sel = self.tree.selection()
        if not sel: return
        idx = int(self.tree.set(sel[0], "idx"))
        if idx >= len(self.entries): return
        it = self.entries[idx]
        lines = [f"Item #{idx}: {it.get('name', '?')}"]
        for k, v in it.items():
            if k == "name": continue
            if k == "element" and isinstance(v, int):
                lines.append(f"  element bits: 0x{v:02x}  ({format_element_bits(v)})")
            elif k == "status" and isinstance(v, int):
                lines.append(f"  status bits:  0x{v:04x}  ({format_status_bits(v)})")
            elif k == "raw" and isinstance(v, (bytes, bytearray)):
                lines.append("  raw: " + v[:32].hex(" ") + ("…" if len(v) > 32 else ""))
            else:
                lines.append(f"  {k}: {v}")
        self.details.delete("1.0", "end"); self.details.insert("1.0", "\n".join(lines))

    def _sort_by(self, col):
        cur, asc = self._sort_state
        asc = (not asc) if cur == col else True
        self._sort_state = (col, asc)
        items = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children("")]
        def keyf(t):
            v = t[0]
            try: return (0, float(v))
            except Exception: return (1, v.lower())
        items.sort(key=keyf, reverse=not asc)
        for i, (_, iid) in enumerate(items):
            self.tree.move(iid, "", i)


# =============================================================================
# Job Tab
# =============================================================================
