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
from ..gui_core.image_panel import ImagePanel
from ..gui_core.thumb_list import ThumbList
from ..gui_core.base   import TabBase



# ============================================================================
# TAB — MONSTERS (ene.dat sprites + boot_data stats)
# ============================================================================

class MonsterTab(TabBase):
    LABEL = "Monsters"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.on_data_change()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=4)
        self.src = tk.StringVar(value="mobile")
        ttk.Radiobutton(top, text="Mobile (ene.dat)", variable=self.src,
                        value="mobile",
                        command=self.on_data_change).pack(side="left",
                                                          padx=4)
        ttk.Radiobutton(top, text="Android (mon*.png)", variable=self.src,
                        value="android",
                        command=self.on_data_change).pack(side="left",
                                                          padx=4)
        self.warn = ttk.Label(top, text="", foreground="#a40")
        self.warn.pack(side="left", padx=12)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        self.thumbs = ThumbList(body, on_select=self._select, thumb_size=56)
        body.add(self.thumbs, weight=1)

        right = ttk.Frame(body)
        body.add(right, weight=4)

        # Top half: image
        self.viewer = ImagePanel(right)
        self.viewer.pack(fill="both", expand=True)

        # Bottom half: stats
        self.stats_frame = ttk.LabelFrame(right, text="Stats")
        self.stats_frame.pack(fill="x", padx=2, pady=4)
        self.stats_text = ScrolledText(self.stats_frame, height=10,
                                       wrap="word",
                                       font=("TkFixedFont", 9))
        self.stats_text.pack(fill="both", expand=True, padx=2, pady=2)
        self.stats_text.configure(state="disabled")

        self._items = {}    # key -> (image, stats_dict|None, name)
        self._enemies = []  # list of dicts (parallel to mobile sprite ids)

    def _refresh_enemies(self):
        boot = self.data.boot_data_mobile()
        self._enemies = parse_enemies_mobile(boot) if boot else []

    def on_data_change(self):
        self.thumbs.clear(); self._items.clear()
        self._refresh_enemies()
        if self.src.get() == "mobile":
            # Scan ALL loaded .sp slots; each chapter has its own ene.dat
            # with a different (overlapping) enemy roster.
            ene_sources = list(self.data.find_in_sp_any_chapter("ene.dat"))
            if not ene_sources:
                self.warn.configure(
                    text="ene.dat not found in any loaded .sp slot.")
                return

            # Pair enemy records with sprites by sprite_id
            sprite_to_enemies = {}
            for en in self._enemies:
                sprite_to_enemies.setdefault(en["sprite_id"], []).append(en)

            n_total_sprites = 0
            n_failed = 0
            seen_keys = set()  # avoid showing identical sprite from many slots

            for slot, blob in ene_sources:
                try:
                    entries = list(parse_sprite_container(blob))
                except Exception as exc:
                    self.warn.configure(
                        text=f"parse_sprite_container failed on {slot}: {exc}")
                    continue

                for (e, var, ic, _) in entries:
                    n_total_sprites += 1
                    try:
                        img = render_ic(ic)
                    except Exception:
                        n_failed += 1
                        continue
                    # Dedup: same (entry_index, variant, dimensions) across
                    # chapters is usually the same sprite; show only once
                    # but tag with all the chapters that have it.
                    dedup_key = (e, var, ic.width, ic.height)
                    if dedup_key in seen_keys:
                        continue
                    seen_keys.add(dedup_key)

                    key = f"{slot}_ene_{e}_{var}"
                    stats = None
                    if e in sprite_to_enemies:
                        stats = sprite_to_enemies[e][0]
                    name = stats["name"] if stats else f"sprite #{e}"
                    label = f"[{slot}]\n{name}\n  entry {e} v{var}"
                    self._items[key] = (img, stats, name)
                    self.thumbs.add(key, img, label)

            # Status line
            n_added = len(self._items)
            stats_msg = (f"  ·  {len(self._enemies)} enemy stat records"
                         if self._enemies
                         else "  ·  no enemy stats (load boot_data.dat)")
            self.warn.configure(
                text=f"{n_added} sprites from {len(ene_sources)} "
                     f"chapter(s){stats_msg}"
                     + (f"  ·  {n_failed} render errors" if n_failed else ""))
        else:
            if not self.data.obb_files:
                self.warn.configure(text="No .obb loaded.")
                return
            self.warn.configure(text="Sprites from .obb")
            and_monsters = []
            and_boot = self.data.boot_data_android()
            if and_boot:
                and_monsters = parse_monsters_android(and_boot)
            for k in self.data.list_obb_pngs("mon"):
                try:
                    img = Image.open(
                        io.BytesIO(self.data.obb_files[k])).convert("RGBA")
                except Exception:
                    continue
                # mon{N}_{V}.png
                stem = Path(k).stem
                rest = stem[3:]
                try:
                    parts = rest.split("_")
                    eid = int(parts[0])
                except Exception:
                    eid = -1
                rec = (and_monsters[eid]
                       if 0 <= eid < len(and_monsters) else None)
                name = rec["name"] if rec else stem
                self._items[k] = (img, rec, name)
                self.thumbs.add(k, img, f"{name}\n  {stem}")

    def _format_bitmask(self, val, names):
        if not val:
            return "-"
        return ", ".join(n for i, n in enumerate(names) if val & (1 << i)) \
               or f"0x{val:x}"

    def _select(self, key):
        item = self._items.get(key)
        if not item: return
        img, stats, name = item
        self.viewer.show(img, f"{name}  ·  {img.width}×{img.height}")
        self.stats_text.configure(state="normal")
        self.stats_text.delete("1.0", "end")
        if stats and "desc" in stats:
            # Mobile record format (full enemy stats)
            lines = [
                f"Name:       {stats['name']}",
                f"Description: {stats['desc']}",
                f"Level:      {stats['level']}",
                f"HP:         {stats['max_hp']}",
                f"MP:         {stats['max_mp']}",
                f"Attack:     {stats['attack']}",
                f"Defense:    {stats['defense']}",
                f"Magic:      {stats['magic']}",
                f"Magic Def:  {stats['magic_def']}",
                f"Evade:      {stats['evade']}",
                f"AI type:    {stats['ai_type']}",
                f"EXP:        {stats['exp']}",
                f"Gil:        {stats['gil']}",
                f"Size:       {stats['size']}",
                f"Sprite ID:  {stats['sprite_id']}",
                "",
                f"Weak to:   {self._format_bitmask(stats['elem_weak'], ELEMENTS)}",
                f"Halves:    {self._format_bitmask(stats['elem_half'], ELEMENTS)}",
                f"Nullifies: {self._format_bitmask(stats['elem_null'], ELEMENTS)}",
                f"Status flags:   {self._format_bitmask(stats['status_flg'], STATUSES)}",
                f"Status immune:  {self._format_bitmask(stats['status_imm'], STATUSES)}",
            ]
            self.stats_text.insert("1.0", "\n".join(lines))
        elif stats and "max_hp" in stats:
            # Android record format (parse_monsters_android)
            lines = [
                f"Name:       {stats['name']}",
                f"Sprite ID:  {stats['sprite_id']}",
                f"field9:     {stats['field9']}",
                f"HP / stat A: {stats['max_hp']}",
                f"Stat B:     {stats['stat_b']}",
                f"Stat C:     {stats['stat_c']}",
                f"field14:    {stats['field14']}",
                f"Skills (18 raw bytes):  {stats['skills'].hex(' ')}",
                "",
                "(Android-only record — full field meanings still being",
                " decoded from libjniproxy.so. Raw body for inspection:)",
                f"{stats['_body'].hex(' ')}",
            ]
            self.stats_text.insert("1.0", "\n".join(lines))
        else:
            self.stats_text.insert(
                "1.0",
                "(No stats parsed for this monster. The slot may be a "
                "deleted/placeholder entry in the boot_data monster table.)\n")
        self.stats_text.configure(state="disabled")


# ============================================================================
# TAB — MAPS (mobile + Android)
# ============================================================================
