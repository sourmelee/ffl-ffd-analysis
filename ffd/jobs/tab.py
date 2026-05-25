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
from ..jobs.parser  import parse_jobs_mobile, parse_jobs_android, decode_job_body
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
# Job Tab
# =============================================================================
class JobTab(TabBase):
    LABEL = "Jobs"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="Mobile")
        for val in ("Mobile", "Android"):
            ttk.Radiobutton(top, text=val, variable=self.src_var, value=val,
                            command=self._reload).pack(side="left", padx=2)
        self.note = ttk.Label(top, text="", foreground="#a00"); self.note.pack(side="right")
        pane = ttk.Panedwindow(self, orient="horizontal"); pane.pack(fill="both", expand=True, padx=6, pady=4)
        left = ttk.Frame(pane)
        cols = ("idx", "name")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=28)
        self.tree.heading("idx", text="#", command=lambda: self._sort_by("idx"))
        self.tree.heading("name", text="NAME", command=lambda: self._sort_by("name"))
        self.tree.column("idx", width=50, anchor="w"); self.tree.column("name", width=200, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(left, command=self.tree.yview); sb.pack(side="left", fill="y")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())
        pane.add(left)
        right = ttk.Frame(pane)
        ttk.Label(right, text="Job details / abilities:").pack(anchor="w")
        self.details = ScrolledText(right, height=28, wrap="word"); self.details.pack(fill="both", expand=True)
        pane.add(right)
        self.entries = []; self._sort_state = (None, False)

    def on_data_change(self):
        self._reload()

    def _reload(self):
        self.entries = []
        self.tree.delete(*self.tree.get_children())
        self.details.delete("1.0", "end")
        src = self.src_var.get()
        # Fixed 2026-05-22: dispatch by source radio (the old code
        # unconditionally called parse_jobs_mobile even for Android),
        # and use the new namedesc parser shape + decode_job_body.
        if src == "Mobile":
            bd = self.data.boot_data_mobile()
            if bd is None:
                self.note.config(text="boot_data.dat not found in any .sp slot.")
                return
            try:
                jobs = parse_jobs_mobile(bd)
            except Exception as exc:
                self.note.config(text="jobs parse error: %s" % exc); return
        else:
            bd = self.data.boot_data_android()
            if bd is None:
                self.note.config(text="Android boot_data.dat not found in .obb/.apk.")
                return
            try:
                jobs = parse_jobs_android(bd)
            except Exception as exc:
                self.note.config(text="jobs parse error: %s" % exc); return
        self.note.config(text="%d jobs loaded (%s)" % (len(jobs), src))
        for i, raw in enumerate(jobs):
            if raw is None:
                self.entries.append(None)
                self.tree.insert("", "end", iid=str(i),
                                 values=(str(i), "(deleted)"))
                continue
            jb = dict(raw); jb.update(decode_job_body(raw.get("body", b"")))
            row = (str(i), jb.get("name", "job_%d" % i))
            self.entries.append(jb)
            self.tree.insert("", "end", iid=str(i), values=row)

    def _on_select(self):
        sel = self.tree.selection()
        if not sel: return
        idx = int(self.tree.set(sel[0], "idx"))
        if idx >= len(self.entries): return
        jb = self.entries[idx]
        if jb is None:
            self.details.delete("1.0", "end")
            self.details.insert("1.0", "Job #%d: (deleted slot)" % idx)
            return
        lines = ["Job #%d: %s" % (idx, jb.get('name', '?'))]
        for k, v in jb.items():
            if k == "name": continue
            if isinstance(v, (bytes, bytearray)):
                preview = v[:32].hex(" ")
                lines.append("  %s: <%dB> %s%s" % (
                    k, len(v), preview, " ..." if len(v) > 32 else ""))
            else:
                lines.append("  %s: %s" % (k, v))
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))

    def _lookup_ability_names(self) -> dict:
        out = {}; best = -1
        for slot, blob in self.data.find_in_sp_any_chapter("bem.dat"):
            if len(blob) > best:
                best = len(blob)
                try:
                    abs_ = parse_bem(blob)
                    out = {i: (ab.get("name", str(i)) if isinstance(ab, dict) else str(ab))
                           for i, ab in enumerate(abs_)}
                except Exception:
                    pass
        return out

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
# Hex dump helper
# =============================================================================
def _hex_dump(data: bytes, width: int = 16) -> str:
    """Classic hex+ASCII dump."""
    if not data:
        return "(empty)"
    out = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk).ljust(width * 3)
        ascpart = "".join(chr(b) if 0x20 <= b < 0x7f else "." for b in chunk)
        out.append(f"{off:08x}  {hexpart}  {ascpart}")
    return "\n".join(out)


# =============================================================================
# Event Script Tab
# =============================================================================
