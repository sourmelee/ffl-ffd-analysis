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
# Animation Tab
# =============================================================================
class AnimationTab(TabBase):
    """
    Character sprite animation playback.

    Android:
      - field_anm.dat contains 63 generic field animations (idle, walk N/S/E/W,
        sit, talk, etc.) — each entry is a list of (src_x, src_y, w, h) frame
        rects.  Every frame stores tex_id=0 because the engine binds whichever
        fldchr*_*.png sheet the active character needs at runtime, then plays
        the universal animation against it.  So the tab has TWO pickers:
          - Sheet:     pick which fldchr*_*.png to render against
          - Animation: pick which of the 63 field_anm entries to play
      - Defaults: first fldchr sheet, first non-empty animation.

    Mobile:
      - chpk.dat is an ic-container of character sprite atlases.  The original
        engine hardcodes the cell layout (typically 16x16 or 16x24, with rows
        per facing direction × walk frames per row).  No standalone animation
        metadata file exists.
      - Tab lists every chpk entry from every loaded .sp slot, slices the
        atlas into cells using the user-adjustable cell size, then plays the
        chosen sequence (full sheet, single row, ping-pong, etc.).
    """

    LABEL = "Animation"

    # Common Mobile cell-size candidates, ordered by likelihood for FFL
    # character sprites (16x16 is by far the most common on feature phones).
    _MOBILE_CELL_CANDIDATES = [
        (16, 16), (16, 24), (24, 16), (24, 24),
        (32, 32), (32, 24), (24, 32), (48, 48), (64, 64),
    ]

    def __init__(self, parent, data):
        super().__init__(parent, data)
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="Android")
        for val in ("Android", "Mobile"):
            ttk.Radiobutton(top, text=val, variable=self.src_var, value=val,
                            command=self._reload).pack(side="left", padx=2)
        ttk.Label(top, text="  Sheet:").pack(side="left")
        self.sheet_combo = ttk.Combobox(top, state="readonly", width=26)
        self.sheet_combo.pack(side="left", padx=4)
        self.sheet_combo.bind("<<ComboboxSelected>>",
                              lambda e: self._on_sheet_change())
        # Android-only: which field_anm entry (0..62) — selects the set of
        # sub-animations available in the Animation picker.
        self.entry_lbl = ttk.Label(top, text="  Entry:")
        self.entry_lbl.pack(side="left")
        self.fa_entry_combo = ttk.Combobox(top, state="readonly", width=20)
        self.fa_entry_combo.pack(side="left", padx=4)
        self.fa_entry_combo.bind("<<ComboboxSelected>>",
                                  lambda e: self._on_fa_entry_change())
        ttk.Label(top, text="  Animation:").pack(side="left")
        self.entry_combo = ttk.Combobox(top, state="readonly", width=34)
        self.entry_combo.pack(side="left", padx=4)
        self.entry_combo.bind("<<ComboboxSelected>>",
                              lambda e: self._show_entry())
        self.note = ttk.Label(top, text="", foreground="#a00")
        self.note.pack(side="right")

        # Mobile-only cell sizing row (hidden when source=Android).
        self.cell_row = ttk.Frame(self)
        self.cell_row.pack(fill="x", padx=6, pady=(0, 2))
        ttk.Label(self.cell_row, text="Mobile cell size:").pack(side="left")
        self.cw_var = tk.IntVar(value=16)
        self.ch_var = tk.IntVar(value=16)
        ttk.Label(self.cell_row, text=" w=").pack(side="left")
        ttk.Spinbox(self.cell_row, from_=4, to=128, textvariable=self.cw_var,
                    width=4,
                    command=self._on_cell_size_change).pack(side="left")
        ttk.Label(self.cell_row, text=" h=").pack(side="left")
        ttk.Spinbox(self.cell_row, from_=4, to=128, textvariable=self.ch_var,
                    width=4,
                    command=self._on_cell_size_change).pack(side="left")
        ttk.Label(self.cell_row, text="   Row filter:").pack(side="left",
                                                              padx=(12, 0))
        self.row_var = tk.StringVar(value="all")
        self.row_combo = ttk.Combobox(self.cell_row, state="readonly",
                                      width=18, textvariable=self.row_var,
                                      values=["all"])
        self.row_combo.pack(side="left", padx=4)
        self.row_combo.bind("<<ComboboxSelected>>",
                            lambda e: self._show_entry())

        sheet_frame = ttk.LabelFrame(
            self, text="Sprite sheet (frame regions overlaid)")
        sheet_frame.pack(fill="both", expand=True, padx=6, pady=2)
        self.sheet_canvas = tk.Canvas(sheet_frame, background="#222")
        self.sheet_canvas.pack(fill="both", expand=True)

        ctrl = ttk.Frame(self); ctrl.pack(fill="x", padx=6, pady=2)
        play_frame = ttk.LabelFrame(ctrl, text="Playback")
        play_frame.pack(side="left")
        self.btn_play = ttk.Button(play_frame, text="▶ Play",
                                   command=self._toggle_play)
        self.btn_play.grid(row=0, column=0, padx=2, pady=2)
        ttk.Button(play_frame, text="◄ Prev",
                   command=self._step_prev).grid(row=0, column=1, padx=2)
        ttk.Button(play_frame, text="Next ▶",
                   command=self._step_next).grid(row=0, column=2, padx=2)
        ttk.Label(play_frame, text="FPS:").grid(row=0, column=3, padx=(8, 0))
        self.fps_var = tk.IntVar(value=8)
        ttk.Spinbox(play_frame, from_=1, to=30, textvariable=self.fps_var,
                    width=4).grid(row=0, column=4)
        ttk.Label(play_frame, text="Zoom:").grid(row=0, column=5, padx=(8, 0))
        self.zoom_var = tk.IntVar(value=3)
        ttk.Spinbox(play_frame, from_=1, to=8, textvariable=self.zoom_var,
                    width=3,
                    command=self._on_zoom_change).grid(row=0, column=6)
        self.play_canvas = tk.Canvas(self, background="#222", height=128)
        self.play_canvas.pack(fill="x", padx=6, pady=2)
        self.frame_lbl = ttk.Label(self, text="Frame: -")
        self.frame_lbl.pack(anchor="w", padx=6)
        self.frame_info_lbl = ttk.Label(self, text="", font=("Courier", 8))
        self.frame_info_lbl.pack(anchor="w", padx=6)

        # State
        self.sheets = []          # list of (key, label, PIL.Image)
        # For Android: the 63 field_anm entries (each with sub_anims).
        # For Mobile: empty (we don't use this layer).
        self.fa_entries = []
        # 'entries' holds the list shown in the Animation combobox.
        #   Android: sub_anims of the currently picked fa_entry.
        #   Mobile:  generated sequences (all cells / per-row / ping-pong)
        #            based on the picked sheet and cell size.
        self.entries = []
        self.current_entry = None
        self.current_sheet = None
        self.current_frames = []  # list of PhotoImage (per visible frame)
        self.playing = False
        self._after_id = None
        self.frame_idx = 0
        self._sheet_photo = None

    # ---- public hook -------------------------------------------------------
    def on_data_change(self):
        self._reload()

    # ---- main reload -------------------------------------------------------
    def _reload(self):
        self._stop()
        self.sheets = []
        self.fa_entries = []
        self.entries = []
        self.sheet_combo["values"] = []
        self.fa_entry_combo["values"] = []
        self.fa_entry_combo.set("")
        self.entry_combo["values"] = []
        self.sheet_canvas.delete("all")
        self.play_canvas.delete("all")
        self.frame_lbl.config(text="Frame: -")
        self.frame_info_lbl.config(text="")
        self.note.config(text="")
        self.current_entry = None
        self.current_sheet = None
        self.current_frames = []

        src = self.src_var.get()
        if src == "Android":
            # Show entry picker, hide Mobile-only cell-size row.
            self._set_widget_visibility(android=True)
            self._load_android()
        else:
            self._set_widget_visibility(android=False)
            self._load_mobile()

        # Populate sheet combobox
        sheet_labels = [lbl for (_k, lbl, _img) in self.sheets]
        self.sheet_combo["values"] = sheet_labels
        if sheet_labels:
            self.sheet_combo.set(sheet_labels[0])

        if src == "Android":
            # Populate field_anm entry picker
            fa_labels = [fe["label"] for fe in self.fa_entries]
            self.fa_entry_combo["values"] = fa_labels
            if fa_labels:
                # Default to first non-empty entry (skipping anm 0 which is
                # the global "table of contents" entry with 0 frames)
                default_idx = next(
                    (i for i, fe in enumerate(self.fa_entries)
                     if fe.get("frames")),
                    0)
                self.fa_entry_combo.set(fa_labels[default_idx])
                self._populate_entries_from_fa(self.fa_entries[default_idx])

        # Populate animation combobox
        entry_labels = [e.get("label", f"Entry {i}")
                        for i, e in enumerate(self.entries)]
        self.entry_combo["values"] = entry_labels
        if entry_labels:
            # Mobile: default to "Row 0" (first directional walk cycle) to
            # show a coherent animation immediately.
            # Android: default to first multi-frame cycle.
            if src == "Mobile":
                default_lbl = next(
                    (l for l in entry_labels if l.startswith("Row 0")),
                    entry_labels[0])
                self.entry_combo.set(default_lbl)
            else:
                default_idx = 0
                for i, e in enumerate(self.entries):
                    sa = e.get("sub_anim")
                    if sa and sa.get("kind") == "cycle":
                        default_idx = i; break
                self.entry_combo.set(entry_labels[default_idx])

        if sheet_labels and entry_labels:
            self._show_entry()

    def _set_widget_visibility(self, android: bool):
        """Show/hide Android-only and Mobile-only widgets based on source."""
        if android:
            # Entry picker visible
            try:
                self.entry_lbl.pack_info()
            except Exception:
                self.entry_lbl.pack(side="left",
                                    before=self.fa_entry_combo)
            try:
                self.fa_entry_combo.pack_info()
            except Exception:
                self.fa_entry_combo.pack(side="left", padx=4)
            try:
                self.cell_row.pack_forget()
            except Exception:
                pass
        else:
            # Hide Entry picker, show cell-size row
            try:
                self.entry_lbl.pack_forget()
            except Exception:
                pass
            try:
                self.fa_entry_combo.pack_forget()
            except Exception:
                pass
            try:
                self.cell_row.pack(fill="x", padx=6, pady=(0, 2),
                                   after=self.sheet_canvas.master)
            except Exception:
                self.cell_row.pack(fill="x", padx=6, pady=(0, 2))

    # ---- Android loader ----------------------------------------------------
    def _load_android(self):
        if not self.data.archives_loaded():
            self.note.config(
                text=".obb not loaded — Android animations need it.")
            return
        anm_blob = self.data.in_obb("field_anm.dat")
        if anm_blob is None:
            self.note.config(text="field_anm.dat not in .obb.")
            return
        try:
            anm_entries = parse_field_anm(anm_blob)
        except Exception as exc:
            self.note.config(text=f"field_anm.dat parse failed: {exc}")
            return

        # Collect all fldchr*.png sheets, sorted by (char_id, palette).
        png_names = self.data.list_obb_pngs("fldchr")

        def _parse_name(name):
            stem = Path(name).stem  # e.g. "fldchr12_3"
            try:
                trail = stem[len("fldchr"):]
                cid_str, pal_str = trail.split("_", 1)
                return int(cid_str), int(pal_str)
            except Exception:
                return (1 << 30, 0)

        png_names = sorted(png_names, key=_parse_name)
        for png_name in png_names:
            blob = self.data.obb_files.get(png_name)
            if blob is None:
                continue
            try:
                img = Image.open(io.BytesIO(blob)).convert("RGBA")
            except Exception:
                continue
            cid, pal = _parse_name(png_name)
            # Look up a character name from CHARA_TABLE (chpk column happens
            # to share the same id for the player party — best effort).
            char_name = None
            for (_ci, _jp, romaji, chpk, p) in CHARA_TABLE:
                if chpk == cid and (p == pal or p is None):
                    char_name = romaji; break
                if chpk == cid and char_name is None:
                    char_name = romaji
            label = f"fldchr{cid}_{pal} ({img.size[0]}×{img.size[1]})"
            if char_name:
                label = f"{char_name} — " + label
            self.sheets.append((png_name, label, img))

        if not self.sheets:
            self.note.config(
                text="field_anm.dat parsed but no fldchr*.png sheets in .obb.")
            return

        # Build field_anm entry list (63 entries).  Each entry has a flat
        # frame table (sub[1]) plus a list of decoded sub_anims (sub[2..5]).
        # The Animation combobox lists sub_anims of the picked entry.
        for i, fa in enumerate(anm_entries):
            n_frames = fa.get("n_frames", len(fa.get("frames", [])))
            n_subanims = len(fa.get("sub_anims", []))
            label = (f"entry {i:2d}  ({n_frames} frame"
                     f"{'s' if n_frames != 1 else ''}, "
                     f"{n_subanims} anim"
                     f"{'s' if n_subanims != 1 else ''})")
            self.fa_entries.append({
                "label": label, "frames": fa.get("frames", []),
                "sub_anims": fa.get("sub_anims", []), "index": i,
                "anm": fa,
            })

        total_subanims = sum(len(fe["sub_anims"]) for fe in self.fa_entries)
        self.note.config(
            text=f"{len(self.sheets)} fldchr sheets · "
                 f"{len(self.fa_entries)} field_anm entries · "
                 f"{total_subanims} sub-animations total")

    def _populate_entries_from_fa(self, fa_entry):
        """Given a field_anm entry, populate self.entries with its sub_anims
        plus a synthetic 'All frames (atlas)' entry that lists every unique
        frame in the entry — useful for inspecting the flat frame table."""
        self.entries = []
        frames = fa_entry.get("frames", [])
        sub_anims = fa_entry.get("sub_anims", [])

        # Synthetic "atlas" view at the top — shows every frame
        if frames:
            self.entries.append({
                "label": f"(atlas)  all {len(frames)} unique frames",
                "frames": list(frames),
                "kind": "android_atlas",
                "fa_index": fa_entry.get("index", -1),
            })

        # Each sub_anim becomes a separate playable entry
        for sa in sub_anims:
            # Build the frame list in playback order using each keyframe's
            # frame rect (already resolved during parse_field_anm).
            playback = []
            for kf in sa.get("keyframes", []):
                fr = kf.get("frame")
                if fr is None:
                    continue
                # Pull duration/position into the frame dict so _show_frame
                # can display them.
                playback.append({
                    **fr,
                    "duration": kf.get("duration", 4),
                    "part_x": kf.get("part_x", 0),
                    "part_y": kf.get("part_y", 0),
                    "sprite_idx": kf.get("sprite_idx", -1),
                })
            self.entries.append({
                "label": sa.get("label", f"anm {sa.get('index', '?')}"),
                "frames": playback,
                "kind": "android_sub_anim",
                "sub_anim": sa,
                "fa_index": fa_entry.get("index", -1),
            })

    # ---- Mobile loader -----------------------------------------------------
    def _load_mobile(self):
        # Pull chpk.dat from every loaded .sp slot, dedup by (entry, var, dims).
        slots = list(self.data.find_in_sp_any_chapter("chpk.dat"))
        if not slots:
            self.note.config(
                text="chpk.dat not found in any .sp slot.")
            return

        seen = set()
        for slot, raw in slots:
            try:
                items = list(parse_sprite_container(raw))
            except Exception as exc:
                self.note.config(text=f"chpk.dat parse failed: {exc}")
                return
            for (e_idx, var, ic, _raw) in items:
                try:
                    # parse_sprite_container already bakes the chosen palette
                    # variant into the ICImage — render_ic takes no var arg.
                    img = render_ic(ic).convert("RGBA")
                except Exception:
                    continue
                dedup = (e_idx, var, img.width, img.height)
                if dedup in seen:
                    continue
                seen.add(dedup)
                # Look up the character name if this is a known party-member
                # chpk entry.
                char_name = None
                for (_ci, _jp, romaji, chpk, pal) in CHARA_TABLE:
                    if chpk == e_idx and (pal == var or pal is None):
                        char_name = romaji; break
                key = f"{slot}|chpk[{e_idx}]_v{var}"
                label = (f"chpk[{e_idx:2d}] v{var}  "
                         f"({img.size[0]}×{img.size[1]}, {slot})")
                if char_name:
                    label = f"{char_name} — " + label
                self.sheets.append((key, label, img))

        if not self.sheets:
            self.note.config(text="chpk.dat had no parseable entries.")
            return

        # Pre-seed cell size from the first sheet (content-based detection
        # falls back to divisor-based guessing on plain atlases).
        first_img = self.sheets[0][2]
        cw, ch = self._guess_mobile_cell_size(first_img)
        self.cw_var.set(cw)
        self.ch_var.set(ch)

        # The animation entries for Mobile are SLICES of the picked sheet.
        # We populate the entries list after the sheet is chosen because
        # frame count depends on (sheet_size, cell_size).
        self._rebuild_mobile_entries()

        self.note.config(
            text=f"{len(self.sheets)} chpk sprites · cell {cw}×{ch}")

    def _rebuild_mobile_entries(self):
        """Slice the current sheet into cells, producing N sequence entries:
        'all rows', 'row 0', 'row 1', ... plus a ping-pong walk cycle."""
        self.entries = []
        if not self.sheets:
            return
        # Determine which sheet to slice
        sel = self.sheet_combo.get()
        idx = next((i for i, (_k, lbl, _img) in enumerate(self.sheets)
                    if lbl == sel), 0)
        _key, _lbl, img = self.sheets[idx]
        cw = max(1, int(self.cw_var.get()))
        ch = max(1, int(self.ch_var.get()))
        cols = max(1, img.width // cw)
        rows = max(1, img.height // ch)

        def _row_frames(r):
            return [{"x": c * cw, "y": r * ch, "w": cw, "h": ch}
                    for c in range(cols)]

        # "All cells" sequence
        all_frames = []
        for r in range(rows):
            all_frames.extend(_row_frames(r))
        self.entries.append({
            "label": f"All cells ({rows}×{cols})",
            "frames": all_frames, "kind": "mobile",
        })
        # Per-row sequences
        for r in range(rows):
            self.entries.append({
                "label": f"Row {r}  ({cols} frames)",
                "frames": _row_frames(r), "kind": "mobile",
            })
        # Ping-pong walk per row: frames 0..N-1..1 (typical 2-frame walk
        # rendered as A-B-A-B... by ping-ponging when N=2 collapses to the
        # natural alternation).
        for r in range(rows):
            base = _row_frames(r)
            if len(base) >= 2:
                pp = list(base) + list(reversed(base[1:-1])) if len(base) > 2 \
                    else list(base)
                self.entries.append({
                    "label": f"Row {r} ping-pong  ({len(pp)} frames)",
                    "frames": pp, "kind": "mobile",
                })
        # Update row-filter dropdown to mirror row count
        try:
            self.row_combo["values"] = (
                ["all"] + [f"row {r}" for r in range(rows)])
        except Exception:
            pass

    def _guess_mobile_cell_size(self, sheet_size_or_img):
        """
        Two-pass guess:
          1. CONTENT-BASED — if a PIL image is passed, scan the alpha
             channel for fully-transparent rows and columns.  The gap
             period reveals the actual cell size.  This is robust for
             16×24 character sprites that the naive divisor list would
             mis-fit as 16×16.
          2. DIVISOR-BASED fallback — only the sheet size was passed (or
             no alpha gaps detected); pick the first candidate from
             _MOBILE_CELL_CANDIDATES that divides cleanly.
        """
        # Accept either a (w,h) tuple or a PIL image
        if hasattr(sheet_size_or_img, "width"):
            img = sheet_size_or_img
            content_cw, content_ch = self._content_cell_size(img)
            if content_cw and content_ch:
                return content_cw, content_ch
            w, h = img.size
        else:
            w, h = sheet_size_or_img

        for cw, ch in self._MOBILE_CELL_CANDIDATES:
            if w % cw == 0 and h % ch == 0 and (w // cw) <= 16 and (h // ch) <= 16:
                return cw, ch
        for cw in (16, 24, 32, 48, 64):
            if w % cw == 0:
                return cw, cw
        return max(1, w), max(1, h)

    @staticmethod
    def _content_cell_size(img):
        """
        Inspect the RGBA sheet's alpha channel and find the dominant
        periodicity of (mostly-)transparent rows/columns — that's the cell
        grid pitch.  Returns (cw, ch) on success, or (None, None) if no
        clean vertical structure could be found.

        FF mobile chpk character sheets pack rows of sprites separated
        by a short transparent gap (typical: 16 px sprite content + 8 px
        gap = 24 px row pitch).  Columns are packed tight with no
        horizontal gap, so we only require *vertical* periodicity from
        the content; horizontal cell width is inferred from common
        divisors of the sheet width.
        """
        try:
            w, h = img.size
            if w < 8 or h < 8:
                return None, None
            alpha = img.split()[-1] if img.mode == "RGBA" else None
            if alpha is None:
                return None, None
            pix = alpha.load()
        except Exception:
            return None, None

        ALPHA_THRESHOLD = 8

        # row_gap[y] = True if (nearly) every pixel in this row is transparent.
        # We allow up to MAX_SOLID_IN_GAP solid pixels to forgive 1-2px
        # spillover from neighbouring sprites.
        MAX_SOLID_IN_GAP = max(2, w // 40)
        row_solid_count = [0] * h
        for y in range(h):
            n = 0
            for x in range(w):
                if pix[x, y] >= ALPHA_THRESHOLD:
                    n += 1
            row_solid_count[y] = n
        row_gap = [c <= MAX_SOLID_IN_GAP for c in row_solid_count]

        def find_v_period(total, candidates):
            best = None; best_score = 0.65
            for c in candidates:
                if c <= 0 or c > total or total % c != 0:
                    continue
                n_lines = total // c
                if n_lines < 2:
                    continue
                hits = 0
                for i in range(1, n_lines):
                    y = i * c
                    # Hit if exactly at gap, or within 2 px of one
                    for off in (0, -1, 1, -2, 2):
                        yy = y + off
                        if 0 <= yy < total and row_gap[yy]:
                            hits += 1; break
                score = hits / max(1, n_lines - 1)
                if score >= best_score:
                    best_score = score
                    best = c
            return best

        height_candidates = [48, 40, 32, 24, 16, 12, 8]
        ch = find_v_period(h, height_candidates)
        if ch is None:
            return None, None

        # Horizontal: tight-packed; just pick the first common cell width
        # that divides cleanly and gives a sensible cell aspect ratio.
        # Prefer cw close to ch (square or slightly portrait).
        width_candidates = [16, 24, 32, 48, 64]
        # Sort: prefer widths >= ch//2 and <= ch, then smaller, then larger.
        def cw_score(cw):
            if w % cw != 0:
                return 999
            ar = ch / cw
            # Most FFL chars have aspect ratio 1..1.5 (cw=16, ch=16..24)
            if 0.8 <= ar <= 2.0:
                return abs(ar - 1.5)
            return 5 + abs(ar - 1.5)
        cw = min(width_candidates, key=cw_score)
        if w % cw != 0:
            cw = None
        return cw, ch

    # ---- handlers ----------------------------------------------------------
    def _on_fa_entry_change(self):
        """User picked a different field_anm entry — repopulate the
        Animation picker with that entry's sub-animations."""
        if self.src_var.get() != "Android":
            return
        sel = self.fa_entry_combo.get()
        fe = next((f for f in self.fa_entries if f["label"] == sel), None)
        if fe is None:
            return
        self._populate_entries_from_fa(fe)
        labels = [e["label"] for e in self.entries]
        self.entry_combo["values"] = labels
        if labels:
            # Default to the first cycle (multi-frame anim) if any exist,
            # otherwise the atlas view.
            default_idx = 0
            for i, e in enumerate(self.entries):
                sa = e.get("sub_anim")
                if sa and sa.get("kind") == "cycle":
                    default_idx = i; break
            self.entry_combo.set(labels[default_idx])
            self._show_entry()

    def _on_sheet_change(self):
        if self.src_var.get() == "Mobile":
            # Re-derive cell size from the freshly picked sheet (content-based)
            sel = self.sheet_combo.get()
            idx = next((i for i, (_k, lbl, _img) in enumerate(self.sheets)
                        if lbl == sel), 0)
            _k, _lbl, img = self.sheets[idx]
            cw, ch = self._guess_mobile_cell_size(img)
            self.cw_var.set(cw); self.ch_var.set(ch)
            self._rebuild_mobile_entries()
            labels = [e["label"] for e in self.entries]
            self.entry_combo["values"] = labels
            if labels:
                # Default to Row 0 rather than "all cells" so the user
                # immediately sees a walk cycle instead of the whole sheet.
                default_lbl = next(
                    (l for l in labels if l.startswith("Row 0")),
                    labels[0])
                self.entry_combo.set(default_lbl)
        self._show_entry()

    def _on_cell_size_change(self):
        if self.src_var.get() != "Mobile":
            return
        # Preserve current entry selection if possible
        cur_label = self.entry_combo.get()
        self._rebuild_mobile_entries()
        labels = [e["label"] for e in self.entries]
        self.entry_combo["values"] = labels
        if cur_label in labels:
            self.entry_combo.set(cur_label)
        elif labels:
            self.entry_combo.set(labels[0])
        self._show_entry()

    def _on_zoom_change(self):
        # Rebuild scaled frame cache and redraw
        if self.current_entry is not None and self.current_sheet is not None:
            self._build_frame_cache(self.current_entry)
            self._show_frame()

    def _current_sheet_image(self):
        sel = self.sheet_combo.get()
        for (_k, lbl, img) in self.sheets:
            if lbl == sel:
                return img
        if self.sheets:
            return self.sheets[0][2]
        return None

    def _show_entry(self):
        if not self.entries:
            return
        sel = self.entry_combo.get()
        idx = next((i for i, e in enumerate(self.entries)
                    if e.get("label") == sel), None)
        if idx is None:
            return
        ent = self.entries[idx]
        self.current_entry = ent
        self.current_sheet = self._current_sheet_image()
        self.frame_idx = 0
        self._draw_sheet(ent)
        self._build_frame_cache(ent)
        self._show_frame()

    def _draw_sheet(self, ent):
        self.sheet_canvas.delete("all")
        sheet = self.current_sheet
        if sheet is None:
            self.sheet_canvas.create_text(60, 20, text="(no sheet image)",
                                          fill="#aaa")
            return
        max_w = max(4, self.sheet_canvas.winfo_width() or 600)
        max_h = max(4, self.sheet_canvas.winfo_height() or 400)
        scale = min(max_w / sheet.width, max_h / sheet.height, 3.0)
        scale = max(scale, 0.5)
        disp = sheet.resize(
            (max(1, int(sheet.width * scale)),
             max(1, int(sheet.height * scale))),
            resample=Image.NEAREST)
        from PIL import ImageTk as _ITk
        self._sheet_photo = _ITk.PhotoImage(disp)
        self.sheet_canvas.create_image(0, 0, anchor="nw",
                                       image=self._sheet_photo)
        for i, f in enumerate(ent.get("frames", [])):
            x0 = int(f.get("x", 0) * scale); y0 = int(f.get("y", 0) * scale)
            x1 = int((f.get("x", 0) + f.get("w", 0)) * scale)
            y1 = int((f.get("y", 0) + f.get("h", 0)) * scale)
            self.sheet_canvas.create_rectangle(
                x0, y0, x1, y1, outline="#ff0", width=1)

    def _build_frame_cache(self, ent):
        self.current_frames = []
        sheet = self.current_sheet
        if sheet is None:
            return
        zoom = max(1, int(self.zoom_var.get()))
        for f in ent.get("frames", []):
            try:
                x = f.get("x", 0); y = f.get("y", 0)
                w = max(1, f.get("w", 16)); h = max(1, f.get("h", 16))
                # Clamp to sheet bounds — Android field_anm rects sometimes
                # spill past the sheet edge for unused frames.
                x = max(0, min(x, max(0, sheet.width - 1)))
                y = max(0, min(y, max(0, sheet.height - 1)))
                w = min(w, sheet.width - x)
                h = min(h, sheet.height - y)
                if w <= 0 or h <= 0:
                    self.current_frames.append(None)
                    continue
                crop = sheet.crop((x, y, x + w, y + h))
                disp = crop.resize(
                    (max(1, crop.width * zoom),
                     max(1, crop.height * zoom)),
                    resample=Image.NEAREST)
                from PIL import ImageTk as _ITk2
                self.current_frames.append(_ITk2.PhotoImage(disp))
            except Exception:
                self.current_frames.append(None)

    def _show_frame(self, idx=None):
        ent = self.current_entry
        if ent is None:
            return
        frames_data = ent.get("frames", [])
        if not frames_data:
            self.play_canvas.delete("all")
            self.play_canvas.create_text(60, 30, text="(no frames)",
                                         fill="#aaa")
            self.frame_lbl.config(text="Frame: -")
            return
        n = len(frames_data)
        if idx is None:
            idx = max(0, min(self.frame_idx, n - 1))
        self.frame_idx = idx % n
        if len(self.current_frames) != n:
            self._build_frame_cache(ent)
        self.play_canvas.delete("all")
        photo = (self.current_frames[self.frame_idx]
                 if self.current_frames else None)
        if photo is None:
            self.play_canvas.create_text(60, 30, text="(no frame)",
                                         fill="#aaa")
            self.frame_lbl.config(text="Frame: -")
            return
        # Centre the sprite horizontally in the play canvas
        cx = max(8, (self.play_canvas.winfo_width() or 400) // 2
                  - photo.width() // 2)
        self.play_canvas.create_image(cx, 8, anchor="nw", image=photo)
        f = frames_data[self.frame_idx]
        self.frame_lbl.config(text=f"Frame: {self.frame_idx + 1} / {n}")
        info_bits = [
            f"src=({f.get('x', 0)},{f.get('y', 0)})",
            f"size={f.get('w', 0)}\xd7{f.get('h', 0)}",
        ]
        if "tex_id" in f:
            info_bits.insert(0, f"tex={f['tex_id']}")
        self.frame_info_lbl.config(text="  " + "   ".join(info_bits))

    def _toggle_play(self):
        if self.playing: self._stop()
        else: self._start()

    def _start(self):
        if not self.current_entry or not self.current_frames: return
        self.playing = True; self.btn_play.config(text="■ Stop"); self._tick()

    def _stop(self):
        self.playing = False; self.btn_play.config(text="▶ Play")
        if self._after_id:
            try: self.after_cancel(self._after_id)
            except Exception: pass
            self._after_id = None

    def _tick(self):
        if not self.playing: return
        frames_data = self.current_entry.get("frames", []) if self.current_entry else []
        if not frames_data: return
        self.frame_idx = (self.frame_idx + 1) % len(frames_data)
        self._show_frame()
        fps = max(1, self.fps_var.get())
        self._after_id = self.after(int(1000 / fps), self._tick)

    def _step_prev(self):
        self._stop()
        frames_data = self.current_entry.get("frames", []) if self.current_entry else []
        if not frames_data: return
        self.frame_idx = (self.frame_idx - 1) % len(frames_data); self._show_frame()

    def _step_next(self):
        self._stop()
        frames_data = self.current_entry.get("frames", []) if self.current_entry else []
        if not frames_data: return
        self.frame_idx = (self.frame_idx + 1) % len(frames_data); self._show_frame()


# =============================================================================
# Cross-Ref Tab
# =============================================================================
