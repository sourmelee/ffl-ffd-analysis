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
# TAB 1 — FILES (loader)
# ============================================================================

class FilesTab(TabBase):
    LABEL = "Files"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self):
        # Top: short instructions
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text=(
            "Load up to 14 .sp scratchpads (mobile) and the Android "
            ".obb / .apk plus the mobile .jar / .jam archives. Empty slots "
            "are flagged in every viewer."
        ), wraplength=800, justify="left").pack(anchor="w")

        # Splitter: left = .sp slot table, right = archive containers
        split = ttk.Frame(self)
        split.pack(fill="both", expand=True, padx=8, pady=4)

        # ---- left: .sp slots --------------------------------------------
        left = ttk.LabelFrame(split, text=".sp scratchpads (mobile)")
        left.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self._slot_rows = {}
        slots_frame = ttk.Frame(left)
        slots_frame.pack(fill="both", expand=True, padx=4, pady=4)

        # Header row
        ttk.Label(slots_frame, text="Slot", width=18,
                  font=("TkDefaultFont", 9, "bold")).grid(
                      row=0, column=0, sticky="w", padx=2, pady=2)
        ttk.Label(slots_frame, text="Status", width=20,
                  font=("TkDefaultFont", 9, "bold")).grid(
                      row=0, column=1, sticky="w", padx=2, pady=2)
        ttk.Label(slots_frame, text="File",
                  font=("TkDefaultFont", 9, "bold")).grid(
                      row=0, column=2, sticky="w", padx=2, pady=2)

        for i, label in enumerate(SP_SLOTS, start=1):
            ttk.Label(slots_frame, text=label, width=18).grid(
                row=i, column=0, sticky="w", padx=2, pady=1)

            status_var = tk.StringVar(value="(empty)")
            ttk.Label(slots_frame, textvariable=status_var, width=20,
                      foreground="#888").grid(
                row=i, column=1, sticky="w", padx=2, pady=1)

            path_var = tk.StringVar(value="")
            ttk.Label(slots_frame, textvariable=path_var,
                      foreground="#444").grid(
                row=i, column=2, sticky="w", padx=2, pady=1)

            btn_load = ttk.Button(
                slots_frame, text="Load…", width=8,
                command=lambda lbl=label: self._load_sp(lbl))
            btn_load.grid(row=i, column=3, padx=2, pady=1)

            btn_clr = ttk.Button(
                slots_frame, text="Clear", width=6,
                command=lambda lbl=label: self._clear_sp(lbl))
            btn_clr.grid(row=i, column=4, padx=2, pady=1)

            self._slot_rows[label] = (status_var, path_var)

        slots_frame.grid_columnconfigure(2, weight=1)

        # ---- right: archive containers ----------------------------------
        right = ttk.LabelFrame(split, text="Archive containers")
        right.pack(side="left", fill="both", expand=True, padx=(4, 0))

        self._arch_rows = {}
        for i, (kind, label, exts) in enumerate([
            ("obb", "Android .obb (ZIP archive or extracted folder)",
             [("OBB files", "*.obb"), ("All files", "*.*")]),
            ("apk", "Android .apk (ZIP archive or extracted folder)",
             [("APK files", "*.apk"), ("All files", "*.*")]),
            ("jar", "Mobile .jar (ZIP archive or extracted folder)",
             [("JAR files", "*.jar"), ("All files", "*.*")]),
            ("jam", "Mobile .jam (DoCoMo manifest, plain text)",
             [("JAM files", "*.jam"), ("All files", "*.*")]),
        ]):
            grp = ttk.Frame(right)
            grp.pack(fill="x", padx=4, pady=4)
            ttk.Label(grp, text=label,
                      font=("TkDefaultFont", 9, "bold")).pack(anchor="w")
            row = ttk.Frame(grp); row.pack(fill="x", pady=2)
            sv = tk.StringVar(value="(not loaded)")
            ttk.Label(row, textvariable=sv, foreground="#666").pack(
                side="left", fill="x", expand=True)
            ttk.Button(row, text="Load…", width=8,
                       command=lambda k=kind, e=exts:
                           self._load_arch(k, e)).pack(side="left", padx=2)
            ttk.Button(row, text="Folder…", width=8,
                       command=lambda k=kind:
                           self._load_arch_folder(k)).pack(side="left", padx=2)
            ttk.Button(row, text="Clear", width=6,
                       command=lambda k=kind:
                           self._clear_arch(k)).pack(side="left", padx=2)
            self._arch_rows[kind] = sv

        # Quick-summary panel
        sumf = ttk.LabelFrame(self, text="Detected content")
        sumf.pack(fill="x", padx=8, pady=8)
        self._summary = ScrolledText(sumf, height=8, wrap="word",
                                     font=("TkFixedFont", 9))
        self._summary.pack(fill="both", expand=True, padx=4, pady=4)
        self._summary.configure(state="disabled")

        self.on_data_change()

    # ---- callbacks -------------------------------------------------------
    def _load_sp(self, label):
        path = filedialog.askopenfilename(
            title=f"Load .sp for: {label}",
            filetypes=[("SP files", "*.sp"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.data.set_sp(label, path)
        except Exception as e:
            messagebox.showerror("Load .sp failed",
                                 f"{Path(path).name}\n\n{e}")

    def _clear_sp(self, label):
        self.data.clear_sp(label)

    def _load_arch(self, kind, exts):
        path = filedialog.askopenfilename(
            title=f"Load .{kind}", filetypes=exts)
        if not path:
            return
        try:
            self.data.set_archive(kind, path)
        except Exception as e:
            messagebox.showerror(f"Load .{kind} failed",
                                 f"{Path(path).name}\n\n{e}")

    def _load_arch_folder(self, kind):
        folder = filedialog.askdirectory(
            title=f"Choose a folder containing extracted .{kind} contents")
        if not folder:
            return
        try:
            self.data.set_archive(kind, folder)
        except Exception as e:
            messagebox.showerror(f"Load folder for .{kind} failed",
                                 f"{folder}\n\n{e}")

    def _clear_arch(self, kind):
        self.data.clear_archive(kind)

    # ---- refresh ---------------------------------------------------------
    def on_data_change(self):
        # Slot rows
        for label in SP_SLOTS:
            sv, pv = self._slot_rows[label]
            files = self.data.sp_slots.get(label)
            path  = self.data.sp_paths.get(label)
            if files is None:
                sv.set("(empty)")
                pv.set("")
            else:
                sv.set(f"loaded · {len(files)} entries")
                pv.set(Path(path).name if path else "")

        # Archives
        for kind, sv in self._arch_rows.items():
            files = getattr(self.data, f"{kind}_files")
            path  = getattr(self.data, f"{kind}_path")
            if files is None:
                sv.set("(not loaded)")
            else:
                sv.set(f"{Path(path).name if path else ''} · "
                       f"{len(files)} entries")

        # Summary
        self._render_summary()

    def _render_summary(self):
        lines = []
        loaded = self.data.loaded_sp_slots()
        missing = self.data.missing_sp_slots()
        lines.append(f"Loaded scratchpads:  {len(loaded)} / {len(SP_SLOTS)}")
        if loaded:
            lines.append("  · " + ", ".join(loaded))
        if missing:
            lines.append(f"Missing slots:  {', '.join(missing)}")
        lines.append("")
        for kind in ("obb", "apk", "jar", "jam"):
            files = getattr(self.data, f"{kind}_files")
            path = getattr(self.data, f"{kind}_path")
            if files is None:
                lines.append(f"  [.{kind}] not loaded")
            else:
                lines.append(f"  [.{kind}] {Path(path).name}  "
                             f"({len(files)} files)")

        # Detected key files across loaded sources
        present = set()
        for files in self.data.sp_slots.values():
            if files:
                present.update(files.keys())
        if present:
            lines.append("")
            lines.append("Mobile data files visible in any .sp:")
            interesting = [f for f in KNOWN_DAT_FILES if f in present]
            interesting += sorted(f for f in present
                                  if f.startswith(("cpk", "mpk")))
            if interesting:
                # 4 per line
                for i in range(0, len(interesting), 4):
                    lines.append("  " + "  ".join(
                        f"{n:<18}" for n in interesting[i:i+4]))

        if self.data.obb_files:
            obb_keys = list(self.data.obb_files.keys())
            mc   = sum(1 for k in obb_keys if Path(k).name.startswith("mc"))
            fld  = sum(1 for k in obb_keys
                       if Path(k).name.startswith("fldchr"))
            mon  = sum(1 for k in obb_keys if Path(k).name.startswith("mon"))
            mpkh = sum(1 for k in obb_keys if "mpkh" in k)
            mpk  = sum(1 for k in obb_keys
                       if Path(k).name.startswith("mpk")
                       and "mpkh" not in k)
            lines.append("")
            lines.append("Android .obb summary:")
            lines.append(f"  tilesets (mc*.png):     {mc}")
            lines.append(f"  field sprites:          {fld}")
            lines.append(f"  monsters (mon*.png):    {mon}")
            lines.append(f"  mpkh*.dat indexes:      {mpkh}")
            lines.append(f"  mpk*_*.dat map packs:   {mpk}")

        self._summary.configure(state="normal")
        self._summary.delete("1.0", "end")
        self._summary.insert("1.0", "\n".join(lines))
        self._summary.configure(state="disabled")


# ============================================================================
# TAB 2 — EXTRACT
# ============================================================================

EXTRACT_OPTIONS = [
    # (key, default_on, label, requires_mobile_sp, requires_obb, output_subdir)
    #
    # output_subdir is the RELATIVE folder under the user's chosen output
    # directory. Anything per-slot or per-source (mobile / android) appends
    # further subfolders at extract time. Names are kept in lowercase /
    # underscore form to match the option key style and to be filesystem-safe.

    # --- Raw passthrough --------------------------------------------------
    ("sp_raw",        False, "Raw files from each .sp",                  True,  False, "raw/sp"),
    ("obb_raw",       False, "Raw files from .obb (extract ZIP)",        False, True,  "raw/obb"),

    # --- Sprite atlases (Mobile sources) ----------------------------------
    ("characters",    True,  "Character sprites (chpk → PNG)",            True,  False, "sprites/characters"),
    ("monsters",      True,  "Monster sprites (ene → PNG)",               True,  False, "sprites/monsters"),
    ("battle_bg",     True,  "Battle backgrounds (bg → PNG)",             True,  False, "sprites/battle_backgrounds"),
    ("field_eff",     True,  "Field effects (feimg → PNG)",               True,  False, "sprites/field_effects"),
    ("system",        True,  "System / UI images (img_etc → PNG)",        True,  False, "sprites/system"),
    ("battle_eff",    True,  "Battle effects (bip → PNG, 3 groups)",      True,  False, "sprites/battle_effects"),

    # --- Tilesets ---------------------------------------------------------
    ("tilesets_mob",  True,  "Tilesets from .sp cpk*.dat (PNG)",          True,  False, "tilesets/mobile"),
    ("tilesets_and",  False, "Tilesets from .obb (mc*.png copy)",         False, True,  "tilesets/android"),

    # --- Maps -------------------------------------------------------------
    ("maps_mob",      True,  "Mobile maps (rendered as PNG)",             True,  False, "maps/mobile"),
    ("maps_and",      False, "Android maps (rendered, requires .obb tilesets)", False, True, "maps/android"),
    ("maps_and_mob",  False, "Android maps rendered with MOBILE tilesets (cross-port preview)", True, True, "maps/android_mobile_tilesets"),

    # --- Audio ------------------------------------------------------------
    ("audio_snd",     True,  "Audio: extract MFi/MLD from snd.dat",       True,  False, "audio/mobile"),

    # --- Text (Mobile sources) -------------------------------------------
    ("text_dialog",   True,  "Story text from message.dat (TXT)",         True,  False, "text/dialogue/mobile"),
    ("text_abilities",True,  "Ability names from bem.dat (TXT)",          True,  False, "text/abilities/mobile"),
    ("text_audio",    True,  "BGM/SFX names from res.bin (TXT)",          False, True,  "text/audio_names/android"),
    ("text_enemies",  True,  "Enemy names from boot_data (TXT)",          True,  True,  "text/enemies"),
    ("text_items",    True,  "Item list (TXT/CSV)",                       True,  False, "text/items/mobile"),
    ("text_jobs",     True,  "Job list (TXT/CSV)",                        True,  False, "text/jobs/mobile"),
    ("formations",    False, "Formations from form.bin (TXT)",            True,  False, "text/formations/mobile"),
    ("collision",     False, "Tile collision from capk.dat (TXT)",        True,  False, "text/collision/mobile"),

    # --- Text (Android boot_data — new in 2026-05-13 decoding pass) ------
    ("text_items_and",     True,  "Items (Android boot_data §5 → TSV)",        False, True, "text/items/android"),
    ("text_magic_and",     True,  "Magic / spells (Android §2 → TSV)",         False, True, "text/magic/android"),
    ("text_passive_and",   True,  "Passive abilities (Android §3 → TSV)",      False, True, "text/passive_abilities/android"),
    ("text_command_and",   True,  "Command abilities (Android §4 → TSV)",      False, True, "text/command_abilities/android"),
    ("text_jobs_and",      True,  "Jobs (Android §6 → TSV)",                   False, True, "text/jobs/android"),
    ("text_monsters_and",  True,  "Bestiary (Android §9 — name + HP + stats)", False, True, "text/monsters/android"),
]
