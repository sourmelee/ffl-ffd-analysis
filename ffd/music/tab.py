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
# Music Tab
# =============================================================================
class MusicTab(TabBase):
    LABEL = "Music"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        # Source toggle
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="Mobile")
        for v in ("Mobile", "Android"):
            ttk.Radiobutton(top, text=v, variable=self.src_var, value=v,
                            command=self.refresh).pack(side="left", padx=4)
        ttk.Label(top, text="(Mobile = .mld melodies in snd.dat; Android = OGG/MP3 inside .obb)").pack(side="left", padx=8)

        # Body: list + info
        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=6, pady=4)
        left = ttk.Frame(body); left.pack(side="left", fill="y")
        ttk.Label(left, text="Tracks").pack(anchor="w")
        self.lst = tk.Listbox(left, width=46, height=24, exportselection=False)
        self.lst.pack(side="left", fill="y")
        sb = ttk.Scrollbar(left, command=self.lst.yview); sb.pack(side="left", fill="y")
        self.lst.config(yscrollcommand=sb.set)
        self.lst.bind("<<ListboxSelect>>", lambda e: self._on_select())

        right = ttk.Frame(body); right.pack(side="left", fill="both", expand=True, padx=8)
        self.info = ScrolledText(right, height=12, wrap="word")
        self.info.pack(fill="both", expand=True)

        btns = ttk.Frame(self); btns.pack(fill="x", padx=6, pady=4)
        self.btn_save = ttk.Button(btns, text="Save…", command=self._save, state="disabled")
        self.btn_save.pack(side="left", padx=2)
        self.btn_open = ttk.Button(btns, text="Open in default app", command=self._open, state="disabled")
        self.btn_open.pack(side="left", padx=2)
        self.note = ttk.Label(btns, text="", foreground="#a00")
        self.note.pack(side="left", padx=12)

        self.entries = []  # list of dicts: {name, data, ext, info}

    def on_data_change(self):
        self.refresh()

    def refresh(self):
        self.entries = []
        self.lst.delete(0, "end")
        self.info.delete("1.0", "end")
        self.btn_save.config(state="disabled")
        self.btn_open.config(state="disabled")
        self.note.config(text="")

        if self.src_var.get() == "Mobile":
            self._load_mobile()
        else:
            self._load_android()

        for e in self.entries:
            self.lst.insert("end", e["name"])
        if not self.entries:
            self.note.config(text="No music tracks found in current sources.")

    def _load_mobile(self):
        snd = None
        slot_label = None
        for slot, blob in self.data.find_in_sp_any_chapter("snd.dat"):
            snd = blob; slot_label = slot
            break
        if snd is None:
            self.note.config(text="snd.dat not loaded — load any .sp file containing it.")
            return
        try:
            tracks = parse_snd(snd)
        except Exception as exc:
            self.note.config(text=f"snd.dat parse error: {exc}")
            return

        # Try to label tracks with res.bin audio names
        names = []
        if "obb" in self.data.archives_loaded():
            try:
                resbin = self.data.in_obb("res.bin")
                if resbin:
                    names = parse_audio_names_resbin(resbin)
            except Exception:
                names = []

        for i, raw in enumerate(tracks):
            label = names[i] if i < len(names) else f"track_{i:03d}"
            self.entries.append({
                "name": f"{i:03d}: {label}",
                "data": raw,
                "ext": ".mld",
                "info": (f"Mobile melody track #{i}  (from {slot_label}/snd.dat)\n"
                         f"Size: {len(raw)} bytes\n"
                         f"Header bytes: {raw[:8].hex(' ')}\n"
                         f"Note: .mld is a DoCoMo iMelody/SMAF variant;\n"
                         f"playback requires a compatible decoder.\n"),
            })

    def _load_android(self):
        if "obb" not in self.data.archives_loaded():
            self.note.config(text=".obb not loaded — Android audio lives inside the .obb.")
            return
        # Look for any audio-like files in obb
        audio_exts = (".ogg", ".mp3", ".wav", ".m4a", ".mid")
        found = []
        for fname, raw in self.data.list_obb_all():
            low = fname.lower()
            if low.endswith(audio_exts):
                found.append((fname, raw))
        # Sort
        found.sort(key=lambda x: x[0].lower())
        for fname, raw in found:
            ext = "." + fname.rsplit(".", 1)[-1]
            self.entries.append({
                "name": fname,
                "data": raw,
                "ext": ext,
                "info": (f"Android audio asset\n"
                         f"Path: {fname}\n"
                         f"Size: {len(raw)} bytes\n"
                         f"Format: {ext}\n"),
            })
        if not found:
            self.note.config(text="No audio files found inside .obb.")

    def _on_select(self):
        sel = self.lst.curselection()
        if not sel:
            return
        e = self.entries[sel[0]]
        self.info.delete("1.0", "end")
        self.info.insert("1.0", e["info"])
        self.btn_save.config(state="normal")
        self.btn_open.config(state="normal")

    def _save(self):
        sel = self.lst.curselection()
        if not sel: return
        e = self.entries[sel[0]]
        path = filedialog.asksaveasfilename(
            defaultextension=e["ext"],
            initialfile=e["name"].replace(": ", "_").replace("/", "_") + e["ext"]
                if not e["name"].endswith(e["ext"]) else e["name"].replace("/", "_"),
            filetypes=[(e["ext"][1:].upper(), f"*{e['ext']}"), ("All files", "*.*")])
        if not path: return
        try:
            Path(path).write_bytes(e["data"])
            messagebox.showinfo("Saved", f"Wrote {len(e['data'])} bytes to:\n{path}")
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))

    def _open(self):
        sel = self.lst.curselection()
        if not sel: return
        e = self.entries[sel[0]]
        # Write to a temp file and open
        try:
            tdir = tempfile.mkdtemp(prefix="ffd_audio_")
            safe_name = e["name"].replace(": ", "_").replace("/", "_")
            if not safe_name.endswith(e["ext"]):
                safe_name += e["ext"]
            p = Path(tdir) / safe_name
            p.write_bytes(e["data"])
            ok = open_in_default_app(str(p))
            if not ok:
                messagebox.showwarning("Open",
                                       "Could not open in default app. File saved to:\n" + str(p))
        except Exception as exc:
            messagebox.showerror("Open failed", str(exc))


# =============================================================================
# Ability Tab — bem.dat
# =============================================================================
