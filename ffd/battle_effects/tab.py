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
# TAB — BATTLE EFFECTS (bip.dat 3 groups, efcimg*.png)
# ============================================================================

class BattleEffectTab(TabBase):
    LABEL = "Battle Effects"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.on_data_change()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=4)
        self.src = tk.StringVar(value="mobile")
        ttk.Radiobutton(top, text="Mobile (bip.dat)", variable=self.src,
                        value="mobile",
                        command=self.on_data_change).pack(side="left",
                                                          padx=4)
        ttk.Radiobutton(top, text="Android (efcimg*.png)", variable=self.src,
                        value="android",
                        command=self.on_data_change).pack(side="left",
                                                          padx=4)
        self.warn = ttk.Label(top, text="", foreground="#a40")
        self.warn.pack(side="left", padx=12)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.thumbs = ThumbList(body, on_select=self._select, thumb_size=56)
        body.add(self.thumbs, weight=1)
        self.viewer = ImagePanel(body)
        body.add(self.viewer, weight=4)
        self._items = {}

    def on_data_change(self):
        self.thumbs.clear(); self._items.clear()
        if self.src.get() == "mobile":
            # Same logic as CharacterTab — iterate every loaded .sp slot and
            # dedup by (group, entry, variant, image dims) so different
            # chapters' identical effects don't appear N times.
            slots_with_bip = list(self.data.find_in_sp_any_chapter("bip.dat"))
            if not slots_with_bip:
                self.warn.configure(text="bip.dat not found in any .sp.")
                return
            seen = set()
            total = 0
            for slot, blob in slots_with_bip:
                for (g, e, var, ic) in parse_bip(blob):
                    img = render_ic(ic)
                    dedup = (g, e, var, img.width, img.height)
                    if dedup in seen:
                        continue
                    seen.add(dedup)
                    key = f"{slot}|g{g}_e{e}_v{var}"
                    self._items[key] = img
                    self.thumbs.add(
                        key, img,
                        f"[{slot}] group {g} · entry {e} · v{var}")
                    total += 1
            slot_list = ", ".join(s for s, _ in slots_with_bip)
            self.warn.configure(
                text=f"From {len(slots_with_bip)} slot(s) "
                     f"({slot_list}) — {total} unique effects")
        else:
            if not self.data.obb_files:
                self.warn.configure(text="No .obb loaded.")
                return
            self.warn.configure(text="From .obb")
            for k in self.data.list_obb_pngs("efcimg"):
                try:
                    img = Image.open(
                        io.BytesIO(self.data.obb_files[k])).convert("RGBA")
                except Exception:
                    continue
                self._items[k] = img
                self.thumbs.add(k, img, Path(k).name)

    def _select(self, key):
        img = self._items.get(key)
        if img is not None:
            self.viewer.show(img, f"{img.width}×{img.height}")



# ============================================================================
# TAB — MONSTERS (ene.dat sprites + boot_data stats)
# ============================================================================
