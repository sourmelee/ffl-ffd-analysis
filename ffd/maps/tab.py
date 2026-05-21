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
from ..files_io.extract_tab import ExtractTab
from ..gui_core.base   import TabBase



# ============================================================================
# TAB — MAPS (mobile + Android)
# ============================================================================

class MapTab(TabBase):
    """
    Map browser. The renderer is shared with ExtractTab — for the GUI we
    render lazily on selection.
    """

    LABEL = "Maps"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._extract_helper = None      # to share map-render code
        self._mob_tiles = None           # entry_id -> ICImage
        self._and_tiles = None           # entry_id -> Pillow image
        self._mob_maps = []              # list of (slot, mpk_name, off, parsed)
        self._and_maps = []              # list of (mid, parsed)
        self._build()
        self.on_data_change()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=4)
        self.src = tk.StringVar(value="mobile")
        ttk.Label(top, text="Source:").pack(side="left")
        ttk.Radiobutton(top, text="Mobile (.sp mpk*.dat)",
                        variable=self.src, value="mobile",
                        command=self._on_source_change).pack(side="left", padx=4)
        ttk.Radiobutton(top, text="Android (.obb mpkh+mpk)",
                        variable=self.src, value="android",
                        command=self._on_source_change).pack(side="left", padx=4)
        ttk.Radiobutton(top, text="Android, mobile tilesets",
                        variable=self.src, value="android_mobile_ts",
                        command=self._on_source_change).pack(side="left", padx=4)
        ttk.Button(top, text="Obb inventory...",
                   command=self._show_obb_inventory).pack(side="left", padx=8)
        ttk.Button(top, text="Chunk hex...",
                   command=self._show_chunk_hex).pack(side="left", padx=2)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)

        # Left: list of maps
        leftf = ttk.Frame(body); body.add(leftf, weight=1)
        ttk.Label(leftf, text="Maps:").pack(anchor="w")
        list_holder = ttk.Frame(leftf); list_holder.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_holder, exportselection=False,
                                  font=("TkDefaultFont", 9))
        sb = ttk.Scrollbar(list_holder, orient="vertical",
                           command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # Right: image viewer + info + tileset picker
        rightf = ttk.Frame(body); body.add(rightf, weight=4)

        self.viewer = ImagePanel(rightf)
        self.viewer.pack(fill="both", expand=True)

        # Bind click on the viewer canvas for tile inspection (Android only)
        self.viewer.canvas.bind("<Button-1>", self._on_tile_click)
        self.viewer.canvas.bind("<Double-Button-1>", self._on_tile_click)

        # Wrapping status label below the image
        self.warn = ttk.Label(rightf, text="", foreground="#a40",
                              justify="left", wraplength=800, anchor="w")
        self.warn.pack(fill="x", padx=4, pady=(2, 0))
        rightf.bind("<Configure>",
                    lambda e: self.warn.configure(wraplength=max(200, e.width - 16)))

        # Hint label
        ttk.Label(rightf,
                  text="Tip: click any tile in the map to inspect it",
                  foreground="#666").pack(anchor="w", padx=4)

        # Layer toggles + decoder mode (Android only diagnostics)
        diag_row = ttk.Frame(rightf)
        diag_row.pack(fill="x", padx=4, pady=(4, 0))
        ttk.Label(diag_row, text="Show layers:",
                  font=("TkDefaultFont", 9, "bold")).pack(side="left")
        self._layer_visible = [tk.BooleanVar(value=True) for _ in range(2)]
        for i, var in enumerate(self._layer_visible):
            ttk.Checkbutton(diag_row, text=f"Layer {i}",
                            variable=var,
                            command=self._on_layer_toggle).pack(side="left", padx=4)

        ttk.Label(diag_row, text="    Layer count:").pack(side="left", padx=(12, 0))
        self._force_layers = tk.StringVar(value="auto")
        for v in ("auto", "1", "2"):
            ttk.Radiobutton(diag_row, text=v, variable=self._force_layers,
                            value=v,
                            command=self._on_layer_toggle).pack(side="left")
        ttk.Label(diag_row,
                  text="(force 1 if extra tiles look like NPC overlays)",
                  foreground="#666").pack(side="left", padx=4)

        # Experimental tile-routing rule. NOTE: kept for diagnostic / legacy
        # use only. In real data the high byte is variant (0/1) and never
        # selects a per-cell tileset — the map's tileset lives in
        # mc_overrides.json. Use the Map Annotations tab to set it.
        diag_row2 = ttk.Frame(rightf)
        diag_row2.pack(fill="x", padx=4, pady=(2, 0))
        ttk.Label(diag_row2, text="Routing (legacy):",
                  font=("TkDefaultFont", 9, "bold")).pack(side="left")
        self._routing_mode = tk.StringVar(value="direct")
        for label, val in [
                ("Direct (no routing)", "direct"),
                ("lb≥192 → secondary", "high_half"),
                ("lb≥128 → secondary", "high_half_128"),
                ("lb≥64 → secondary",  "high_half_64"),
        ]:
            ttk.Radiobutton(diag_row2, text=label, variable=self._routing_mode,
                            value=val,
                            command=self._on_layer_toggle).pack(side="left", padx=2)

        sec_row = ttk.Frame(rightf)
        sec_row.pack(fill="x", padx=4, pady=(2, 0))
        ttk.Label(sec_row,
                  text="Secondary tileset (used when routing rule triggers):").pack(side="left")
        self._secondary_var = tk.StringVar(value="mc1_0")
        self._secondary_combo = ttk.Combobox(
            sec_row, textvariable=self._secondary_var,
            values=[], state="readonly", width=14)
        self._secondary_combo.pack(side="left", padx=4)
        self._secondary_combo.bind("<<ComboboxSelected>>",
                                   lambda e: self._on_layer_toggle())

        # Android tileset picker panel
        self._override_frame = ttk.LabelFrame(
            rightf, text="Android tileset variants (pick replacement from dropdowns, then Apply)")
        self._override_frame.pack(fill="x", padx=4, pady=(4, 4))

        # Column headers
        hdr_row = ttk.Frame(self._override_frame)
        hdr_row.pack(fill="x", padx=4, pady=(2, 0))
        for txt, w in [("High byte", 9), ("Current file", 16),
                        ("Override to", 22), ("Status", 8)]:
            ttk.Label(hdr_row, text=txt, width=w, anchor="w",
                      font=("TkDefaultFont", 9, "bold")).pack(side="left")

        # Scrollable rows
        rows_outer = ttk.Frame(self._override_frame)
        rows_outer.pack(fill="x", padx=4, pady=2)
        self._ov_canvas = tk.Canvas(rows_outer, height=120, highlightthickness=0)
        self._ov_canvas.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(rows_outer, orient="vertical",
                            command=self._ov_canvas.yview)
        vsb.pack(side="right", fill="y")
        self._ov_canvas.configure(yscrollcommand=vsb.set)
        self._ov_inner = ttk.Frame(self._ov_canvas)
        self._ov_canvas.create_window(0, 0, anchor="nw", window=self._ov_inner)
        self._ov_inner.bind("<Configure>",
            lambda e: self._ov_canvas.configure(
                scrollregion=self._ov_canvas.bbox("all")))

        btn_row = ttk.Frame(self._override_frame)
        btn_row.pack(fill="x", padx=4, pady=(2, 4))
        ttk.Button(btn_row, text="Apply overrides",
                   command=self._apply_override).pack(side="left", padx=2)
        ttk.Button(btn_row, text="Clear all",
                   command=self._clear_override).pack(side="left", padx=2)

        # Internal state
        self._ts_override = {}
        self._ov_row_vars = {}
        self._ov_available = []
        self._current_parsed = None      # for click inspector
        self._current_render_tile_size = 32  # px per tile in rendered image
        self._current_map_id = None

    def on_data_change(self):
        self._mob_tiles = None
        self._and_tiles = None
        self._mob_resolvers = {}
        self.refresh_list()

    def _on_source_change(self):
        """Radio button changed: drop the cached tilesets so the new source's
        cache gets built fresh on the next selection, then refresh the list."""
        self._and_tiles = None
        self._mob_tiles = None
        self.refresh_list()

    def refresh_list(self):
        self.listbox.delete(0, "end")
        self.viewer.show(None)
        if self.src.get() == "mobile":
            self._collect_mobile_maps()
            if not self._mob_maps:
                self.warn.configure(
                    text="No mobile maps found. Load .sp scratchpads with "
                         "mpk*.dat and cpk*.dat plus boot_data.dat.")
                return
            self.warn.configure(
                text=f"{len(self._mob_maps)} mobile maps")
            for slot, mpk_name, off, p in self._mob_maps:
                self.listbox.insert(
                    "end", f"[{slot}] {mpk_name}  {p['w']}×{p['h']}  "
                           f"{p['name']}")
        else:
            self._collect_android_maps()
            if not self._and_maps:
                self.warn.configure(
                    text="No Android maps. Load .obb (mpkh*.dat + mc*.png).")
                return
            self.warn.configure(text=f"{len(self._and_maps)} Android maps")
            # Sort by (mpkh source, pack, map_id) for stable, readable ordering
            try:
                self._and_maps.sort(
                    key=lambda x: (int(x[1].get("_mpkh", "999")),
                                    x[1].get("_pack", 999),
                                    x[0]))
            except Exception:
                pass
            for mid, p in self._and_maps:
                mpkh_label = p.get("_mpkh", "?")
                pack_label = p.get("_pack", "?")
                self.listbox.insert(
                    "end",
                    f"mpkh{mpkh_label}/p{pack_label}/map{mid}  "
                    f"{p['w']}×{p['h']}  L{p['n_layers']}")

    def _show_chunk_hex(self):
        """Show a hex dump of the currently selected Android map chunk,
        with annotations marking the header / tile data / event regions."""
        if (self.src.get() not in ("android", "android_mobile_ts")
                or not self._current_parsed
                or "_raw_chunk" not in self._current_parsed):
            messagebox.showinfo("Chunk hex",
                                "Select an Android map first.")
            return

        parsed = self._current_parsed
        raw = parsed["_raw_chunk"]
        w = parsed["w"]; h = parsed["h"]; n = w * h
        import struct as st
        end_field = st.unpack(">I", raw[:4])[0]
        n_layers = parsed["n_layers"]
        if n_layers == 2 and end_field >= n*4 + 12:
            tile_start = end_field - n*4
        else:
            tile_start = end_field - n*2

        win = tk.Toplevel(self)
        mpkh_lbl = parsed.get("_mpkh", "?")
        pack_lbl = parsed.get("_pack", "?")
        win.title(f"Chunk hex: mpkh{mpkh_lbl}/p{pack_lbl}/map{self._current_map_id}  "
                  f"({len(raw)} bytes)")
        win.geometry("980x680")

        info = ttk.Label(win,
            text=(f"Chunk size: {len(raw)} bytes  ·  "
                  f"end_field (BE u32 @ +0): {end_field}  ·  "
                  f"map dims: {w}×{h} = {n} cells  ·  "
                  f"layers: {n_layers}  ·  "
                  f"tile_start: {tile_start}  ·  "
                  f"event region: {end_field}..{len(raw)} "
                  f"({max(0, len(raw)-end_field)} bytes)"),
            justify="left", font=("TkDefaultFont", 9, "bold"))
        info.pack(fill="x", padx=8, pady=(8, 4))

        # Color regions: header=cyan, tiles=yellow, events=pink
        txt = ScrolledText(win, wrap="none", font=("Courier", 9))
        txt.pack(fill="both", expand=True, padx=8, pady=4)
        txt.tag_configure("header", background="#cef")
        txt.tag_configure("tiles", background="#ffe")
        txt.tag_configure("events", background="#fcc")
        txt.tag_configure("special", background="#f80", foreground="white")

        # Build hex dump
        lines = []
        for off in range(0, len(raw), 16):
            row_b = raw[off:off+16]
            hex_s = " ".join(f"{b:02x}" for b in row_b)
            asc_s = "".join(chr(b) if 32 <= b < 127 else "." for b in row_b)
            lines.append((off, f"+{off:6d}: {hex_s:<48}  {asc_s}\n"))

        for off, line in lines:
            line_start = txt.index("end-1c")
            txt.insert("end", line)
            line_end = txt.index("end-1c")
            # Tag region
            if off < tile_start:
                txt.tag_add("header", line_start, line_end)
            elif off < end_field:
                txt.tag_add("tiles", line_start, line_end)
            else:
                txt.tag_add("events", line_start, line_end)

        # Legend
        legend = ttk.Frame(win); legend.pack(fill="x", padx=8, pady=4)
        ttk.Label(legend, text="Legend:",
                  font=("TkDefaultFont", 9, "bold")).pack(side="left")
        for txt_, bg in [("Header", "#cef"),
                          ("Tile data", "#ffe"),
                          ("Events / post-data", "#fcc")]:
            lbl = tk.Label(legend, text=f" {txt_} ", bg=bg, width=18)
            lbl.pack(side="left", padx=4)

        ttk.Button(win, text="Close",
                   command=win.destroy).pack(pady=4)

    def _show_obb_inventory(self):
        """Pop up a window listing all mc*.png files found in the obb,
        so the user can see which tileset entry_ids are available and
        which are absent (explaining why some maps render wrong)."""
        obb = self.data.obb_files
        if not obb:
            messagebox.showinfo("Obb inventory", "No .obb loaded.")
            return

        # Collect mc*.png entries
        mc_entries = {}   # eid -> list of variant indices
        other_files = []
        for k in sorted(obb):
            name = Path(k).name
            if name.startswith("mc") and name.endswith(".png"):
                try:
                    stem = name[2:-4]
                    parts = stem.split("_")
                    eid  = int(parts[0])
                    var  = int(parts[1]) if len(parts) > 1 else 0
                    mc_entries.setdefault(eid, []).append(var)
                except Exception:
                    other_files.append(k)
            elif not name.endswith(".png"):
                other_files.append(k)

        win = tk.Toplevel(self)
        win.title("Obb file inventory")
        win.geometry("700x500")
        ttk.Label(win,
                  text=f"mc*.png tilesets: {len(mc_entries)} unique entry_ids   "
                       f"Other files: {len(other_files)}",
                  anchor="w").pack(fill="x", padx=8, pady=4)

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=8, pady=4)

        # Tab 1: mc*.png entry_ids
        mc_frame = ttk.Frame(nb); nb.add(mc_frame, text="mc*.png tilesets")
        mc_txt = ScrolledText(mc_frame, wrap="none", font=("Courier", 10))
        mc_txt.pack(fill="both", expand=True)
        if mc_entries:
            lines = ["entry_id  variants"]
            lines.append("--------  --------")
            for eid in sorted(mc_entries):
                vars_str = ", ".join(str(v) for v in sorted(mc_entries[eid]))
                lines.append(f"{eid:8d}  [{vars_str}]")
            mc_txt.insert("1.0", "\n".join(lines))
        else:
            mc_txt.insert("1.0", "(no mc*.png files found in obb)")

        # Tab 2: other files
        other_frame = ttk.Frame(nb); nb.add(other_frame, text="Other files")
        other_txt = ScrolledText(other_frame, wrap="none", font=("Courier", 10))
        other_txt.pack(fill="both", expand=True)
        other_txt.insert("1.0", "\n".join(sorted(other_files))
                         if other_files else "(none)")

        ttk.Button(win, text="Close", command=win.destroy).pack(pady=6)

    def _collect_mobile_maps(self):
        self._mob_maps = []
        for slot, files in self.data.sp_slots.items():
            if not files: continue
            boot = files.get("boot_data.dat")
            mpk_index = (flat_pack_index(parse_mpk_index_mobile(boot))
                         if boot else {})
            by_pack = {}
            for mid, (pi, off, sz) in mpk_index.items():
                by_pack.setdefault(pi, []).append((mid, off, sz))
            mpks = sorted(n for n in files
                          if n.startswith("mpk") and n.endswith(".dat"))
            for mi, mpk_name in enumerate(mpks):
                blob = files[mpk_name]
                pack_entries = by_pack.get(mi)
                for entry in scan_mobile_mpk_chunks(blob, pack_entries):
                    self._mob_maps.append(
                        (slot, mpk_name, entry["offset"], entry["parsed"]))

    def _collect_android_maps(self):
        self._and_maps = []
        if not self.data.obb_files:
            return
        mpkhs = sorted(k for k in self.data.obb_files
                       if Path(k).name.startswith("mpkh"))
        for mpkh_key in mpkhs:
            mpkh_blob = self.data.obb_files[mpkh_key]
            packs = parse_mpkh_index(mpkh_blob)
            base_idx = "".join(c for c in Path(mpkh_key).stem if c.isdigit())
            for pi, entries in enumerate(packs):
                pname = f"mpk{base_idx}_{pi}.dat"
                pk_key = next((k for k in self.data.obb_files
                               if Path(k).name == pname), None)
                if not pk_key: continue
                pk = self.data.obb_files[pk_key]
                for (mid, off, sz) in entries:
                    if off + sz > len(pk): continue
                    raw = pk[off:off+sz]
                    parsed = parse_android_map_chunk(raw)
                    if parsed:
                        parsed["_hdr"] = raw[:min(40, len(raw))].hex(" ")
                        parsed["_raw_chunk"] = raw
                        parsed["_mpkh"] = base_idx       # which mpkh{N}.dat
                        parsed["_pack"] = pi             # which pack within mpkh
                        self._and_maps.append((mid, parsed))

    def _on_select(self, _ev=None):
        sel = self.listbox.curselection()
        if not sel: return
        idx = sel[0]
        if self.src.get() == "mobile":
            if idx >= len(self._mob_maps): return
            slot, mpk_name, off, parsed = self._mob_maps[idx]
            if self._mob_tiles is None:
                self.warn.configure(text="Loading mobile tilesets…")
                self.update_idletasks()
                self._mob_tiles = self._collect_mobile_tilesets()
            img = self._render_mobile(parsed, slot)
            if img is not None:
                self.viewer.show(
                    img,
                    f"{slot} · {mpk_name} · @0x{off:x} · {parsed['name']}")
        else:
            if idx >= len(self._and_maps): return
            mid, parsed = self._and_maps[idx]
            # Set the active map id BEFORE rendering — _render_android()
            # reads self._current_map_id when looking up overrides / running
            # the engine parser. If we set it after the render call, slot 0/1
            # would be resolved against the *previous* map's id.
            self._current_map_id = mid
            mode = self.src.get()
            if self._and_tiles is None:
                self.warn.configure(text="Loading Android tilesets…")
                self.update_idletasks()
                if mode == "android_mobile_ts":
                    base_cb = self._collect_android_with_mobile_tilesets()
                    # Wrap so missing tilesets render as MAGENTA — a strong
                    # visual cue that this mc_id has no mobile cpk equivalent
                    # (i.e. content the mobile version is missing). Without
                    # this, missing tiles silently fell through to transparent
                    # and made the whole map look empty.
                    self._and_tiles = self._wrap_with_magenta_fallback(base_cb)
                else:
                    self._and_tiles = self._collect_android_tilesets()

            # --- build available mc*.png inventory from obb ---
            obb = self.data.obb_files or {}
            avail_eids = set()
            for k in obb:
                name = Path(k).name
                if name.startswith("mc") and name.endswith(".png"):
                    try:
                        stem = name[2:-4]           # strip "mc" and ".png"
                        eid  = int(stem.split("_")[0])
                        avail_eids.add(eid)
                    except Exception:
                        pass

            img = self._render_android(parsed)
            if img is not None:
                # Report the ACTUAL slot tilesets the engine will use, not
                # the raw (mc_type=0, high_byte) pairs from the parser. The
                # cell high_byte is a slot selector (0 = slot 0, 1 = slot 1),
                # NOT a variant of the same mc_id.
                ts = self._and_tiles
                slots = []
                missing = set()
                raw_chunk = parsed.get("_raw_chunk")
                engine_info = parse_android_map_engine(raw_chunk) if raw_chunk else None
                # Figure out which high_bytes actually appear in cells.
                hbs_in_use = set()
                for layer in parsed["layers"]:
                    for (mc_type, hb, _) in layer:
                        hbs_in_use.add(hb)
                # For the magenta-fallback wrapper used in android_mobile_ts
                # mode, the wrapper exposes `.missing` directly — we have to
                # ask it explicitly because the call NEVER returns None
                # there (a magenta placeholder is always returned).
                fallback_missing = getattr(ts, "missing", None)
                if engine_info is not None:
                    for slot_idx, hb in ((0, 0), (1, 1)):
                        mc = engine_info[f"mc_id_slot{slot_idx}"]
                        v  = engine_info[f"variant_slot{slot_idx}"]
                        if mc < 0:
                            continue
                        if hb not in hbs_in_use:
                            continue  # slot configured but no cells use it
                        slots.append((mc, v))
                        if callable(ts):
                            # First, sanity-call the cache so the wrapper's
                            # `.missing` set is populated for this slot.
                            ts(mc, v)
                            if fallback_missing is not None:
                                if (mc, v) in fallback_missing:
                                    missing.add((mc, v))
                            elif ts(mc, v) is None:
                                missing.add((mc, v))
                else:
                    # Engine parse failed — fall back to legacy display
                    for layer in parsed["layers"]:
                        for (mc_type, variant, _) in layer:
                            key = (mc_type, variant)
                            if key not in slots:
                                slots.append(key)
                                if callable(ts):
                                    ts(mc_type, variant)
                                    if fallback_missing is not None:
                                        if key in fallback_missing:
                                            missing.add(key)
                                    elif ts(mc_type, variant) is None:
                                        missing.add(key)
                used_str = " ".join(f"mc{t}_{v}" for t, v in slots)
                if mode == "android_mobile_ts":
                    miss_str = (
                        f" | NO MOBILE CPK FOR: "
                        + " ".join(f"mc{t}_{v}" for t, v in sorted(missing))
                        if missing else "")
                else:
                    miss_str = (
                        " | MISSING: "
                        + " ".join(f"mc{t}_{v}" for t, v in sorted(missing))
                        if missing else "")
                self.warn.configure(
                    text=f"map{mid} {parsed['w']}×{parsed['h']}  "
                         f"tilesets: {used_str}{miss_str}")
                self.viewer.show(img, f"map{mid}")
                self._current_parsed = parsed
                self._current_map_id = mid
                # Detect rendered tile size by sampling first non-None ts
                ts = self._and_tiles
                self._current_render_tile_size = 32
                if callable(ts):
                    for layer in parsed["layers"]:
                        for (mc_type, variant, _) in layer:
                            tsi = ts(mc_type, variant)
                            if tsi is not None:
                                self._current_render_tile_size = (
                                    32 if tsi.width >= 512 else 16)
                                break
                        if self._current_render_tile_size != 32:
                            break
                self._rebuild_tileset_picker(parsed)

    def _collect_mobile_tilesets(self):
        """Build per-chapter MobileTilesetResolvers; return flat by_global dict."""
        self._mob_resolvers = {}
        out = {}
        for slot, files in self.data.sp_slots.items():
            if not files:
                continue
            res = MobileTilesetResolver(files)
            self._mob_resolvers[slot] = res
            for eid, img in res.get_all_tilesets().items():
                if eid not in out:
                    out[eid] = img
        return out

    def _collect_android_tilesets(self):
        """Return a callable (mc_type, variant) -> PIL Image, lazy-loaded from obb."""
        png_cache = {}   # (mc_type, variant) -> Image or None
        obb = self.data.obb_files or {}

        def get(mc_type, variant=0):
            key = (mc_type, variant)
            if key in png_cache:
                return png_cache[key]
            # Try mc{type}_{variant}.png, fall back to mc{type}_0.png
            for try_var in (variant, 0):
                target = f"mc{mc_type}_{try_var}.png"
                for k in obb:
                    if Path(k).name == target:
                        try:
                            img = Image.open(io.BytesIO(obb[k])).convert("RGBA")
                            png_cache[key] = img
                            return img
                        except Exception:
                            break
            png_cache[key] = None
            return None

        return get

    def _wrap_with_magenta_fallback(self, base_cb):
        """
        Wrap a (mc_id, variant) -> Image|None callable so that None becomes a
        512×512 magenta image. Used for the 'Android, mobile tilesets' mode:
        when a requested mc_id has no mobile cpk equivalent in any loaded
        .sp slot, the resulting magenta tiles immediately show the user
        which parts of the map have no mobile counterpart — exactly the
        kind of 'what's missing from the mobile version?' information that
        powers the reverse-engineering workflow.

        The returned callable also has two attributes the caller can inspect
        to render a coverage report:
            `.matched` — set of (mc_id, variant) tuples that resolved to a
                         real mobile tileset
            `.missing` — set of (mc_id, variant) tuples that fell back to
                         magenta because no mobile cpk matches
        """
        magenta = Image.new("RGBA", (512, 512), (255, 0, 255, 255))
        matched = set()
        missing = set()

        def get(mc_id, variant=0):
            img = base_cb(mc_id, variant)
            key = (mc_id, variant)
            if img is None:
                missing.add(key)
                return magenta
            matched.add(key)
            return img

        get.matched = matched
        get.missing = missing
        return get

    def _collect_android_with_mobile_tilesets(self):
        """Return a callable (mc_id, variant) -> PIL Image, where the image is
        rendered from the *mobile* cpk pack of whichever loaded .sp slot
        contains a matching cpk entry. Uses cpk_to_mc.json (the SAD-matcher
        translation table) to invert mc_id back to a (chapter, cpk_id) pair.

        Key fix (2026-05-13): the previous version compared `cpk_to_mc.json`
        chapter keys (e.g. "ChapterOnline", "ChapterGladiatorHall") against
        the toolkit's slot LABELS (e.g. "Prologue", "Postgame"). Those don't
        match for any non-numbered chapter, so the lookup silently returned
        nothing and the map rendered as a black canvas. We now use the
        loaded .sp file's stem (via `data.sp_paths[slot].stem`) as the join
        key — the JSON's keys match those stems exactly.
        """
        # Build (or reuse) per-chapter mobile resolvers
        resolvers = getattr(self, "_mob_resolvers", None)
        if not resolvers:
            self._mob_resolvers = resolvers = {}
            for slot, files in self.data.sp_slots.items():
                if not files:
                    continue
                try:
                    resolvers[slot] = MobileTilesetResolver(files)
                except Exception:
                    pass

        # Build slot → JSON-chapter-key map using the actual loaded .sp path
        # stem. Example: slot label "Prologue" with sp_paths["Prologue"] =
        # ".../ChapterOnline.sp" gives chapter_stem "ChapterOnline", which
        # matches the cpk_to_mc.json top-level key. Fall back to the slot
        # label itself if no path is recorded (e.g. file loaded from memory).
        slot_to_stem = {}
        stem_to_slot = {}
        for slot in resolvers:
            path = self.data.sp_paths.get(slot)
            if path:
                stem = Path(path).stem
            else:
                stem = slot.replace(" ", "")     # last-resort fallback
            slot_to_stem[slot] = stem
            stem_to_slot[stem.lower()] = slot
            # Also accept whitespace-stripped slot label as a key, so old
            # behaviour ("Chapter 1" → "Chapter1") still works.
            stem_to_slot[slot.replace(" ", "").lower()] = slot

        # Inverse lookup table (mc_id, variant) -> [(chapter_stem, cpk_id, sad), ...]
        inv = self.data.cpk_to_mc_inverse()

        # Diagnostic: log which JSON chapters have no matching loaded slot,
        # and which loaded slots have no matching JSON chapter. This is a
        # one-shot informational print so users can spot misalignment.
        json_chapters = set(self.data.cpk_to_mc().keys())
        loaded_stems = {st.lower() for st in slot_to_stem.values()}
        unmatched_json = [c for c in json_chapters
                          if c.lower() not in loaded_stems]
        unmatched_slot = [slot for slot, st in slot_to_stem.items()
                          if st.lower() not in {c.lower()
                                                 for c in json_chapters}]
        if unmatched_json or unmatched_slot:
            print(f"[android_mobile_ts] cpk_to_mc.json chapters with no "
                  f"loaded .sp: {unmatched_json}")
            print(f"[android_mobile_ts] loaded slots with no matching "
                  f"JSON chapter: {unmatched_slot}")

        def find_resolver(chap_stem: str):
            slot = stem_to_slot.get(chap_stem.lower())
            return resolvers.get(slot) if slot else None

        # Build (mc_id, any_variant) lookup for the second-pass fallback.
        # Different variants of the same mc_id are usually palette swaps of
        # the same physical tileset — visually meaningful as a preview even
        # if not pixel-perfect to what the Android engine would show.
        any_variant_match = {}     # mc_id -> first (chap, cpk_id) found
        for (mc, var), entries in inv.items():
            for chap, cpk_id, sad in entries:
                if mc not in any_variant_match:
                    any_variant_match[mc] = (chap, cpk_id, var, sad)
                else:
                    # Prefer lower-SAD entries
                    if sad < any_variant_match[mc][3]:
                        any_variant_match[mc] = (chap, cpk_id, var, sad)

        img_cache = {}
        missing_log = set()

        def get(mc_id, variant=0):
            key = (mc_id, variant)
            if key in img_cache:
                return img_cache[key]

            # Tier 1: exact (mc_id, variant)
            for (chap, cpk_id, _sad) in inv.get(key, []):
                res = find_resolver(chap)
                if res is None: continue
                img = res.get(cpk_id, 0)
                if img is not None:
                    img_cache[key] = img
                    return img

            # Tier 2: (mc_id, 0) — the canonical / palette-0 form
            for (chap, cpk_id, _sad) in inv.get((mc_id, 0), []):
                res = find_resolver(chap)
                if res is None: continue
                img = res.get(cpk_id, 0)
                if img is not None:
                    img_cache[key] = img
                    return img

            # Tier 3: ANY variant of the same mc_id. Different variants are
            # usually palette swaps — gives a meaningful preview even when
            # the SAD matcher didn't catalog the requested variant. This is
            # what unblocks maps like mpkh0/p0/map400 where the engine
            # returns mc13_0 but the JSON only has mc13_2.
            if mc_id in any_variant_match:
                chap, cpk_id, found_var, _sad = any_variant_match[mc_id]
                res = find_resolver(chap)
                if res is not None:
                    img = res.get(cpk_id, 0)
                    if img is not None:
                        img_cache[key] = img
                        if key not in missing_log:
                            missing_log.add(key)
                            print(f"[android_mobile_ts] mc{mc_id}_{variant} "
                                  f"→ {chap}.cpk{cpk_id} (variant {found_var}, "
                                  f"palette substitution)")
                        return img

            # Tier 4: naive id-equals-id rule across all loaded chapters —
            # try cpk_id == mc_id directly, and PASS THROUGH THE VARIANT so
            # mc{N}_{V} maps to cpk{N} palette V. Each cpk typically has up
            # to ~8 palette variants (different in-game tints of the same
            # artwork), and the variant the Android engine asks for is
            # almost always available on the corresponding Mobile cpk.
            # No blacklist: even when the SAD matcher cataloged this cpk
            # under a different mc_id, the naive rule's render is the user-
            # preferred behaviour — full maps render, even if a few tile
            # positions land in transparent regions of the chosen sheet.
            for slot, res in resolvers.items():
                img = res.get(mc_id, variant)
                if img is None and variant != 0:
                    # cpk may not carry this exact palette — try palette 0
                    img = res.get(mc_id, 0)
                if img is not None:
                    img_cache[key] = img
                    if key not in missing_log:
                        missing_log.add(key)
                        print(f"[android_mobile_ts] mc{mc_id}_{variant} → "
                              f"{slot}.cpk{mc_id} (naive id-equals-id rule, "
                              f"unverified by SAD)")
                    return img

            # Truly missing — log once, return None
            if key not in missing_log:
                missing_log.add(key)
                print(f"[android_mobile_ts] mc{mc_id}_{variant} not "
                      f"present in cpk_to_mc.json AND no loaded chapter "
                      f"has a cpk{mc_id} entry — probably content unique "
                      f"to the Android version")
            img_cache[key] = None
            return None

        return get

    def _render_mobile(self, parsed, slot_label=None):
        # delegate to ExtractTab.render with our cached tilesets
        helper = self._extract_helper
        if helper is None:
            helper = self._extract_helper = ExtractTab(self, self.data)
            helper.pack_forget()  # invisible — we just borrow its methods
        helper._mob_resolvers = getattr(self, "_mob_resolvers", {}) or {}
        return helper._render_mobile_map(parsed, slot_label=slot_label)

    def _rebuild_tileset_picker(self, parsed):
        """Repopulate the tileset picker table for the currently selected Android map."""
        # Destroy old rows
        for child in self._ov_inner.winfo_children():
            child.destroy()
        self._ov_row_vars.clear()

        if self.src.get() not in ("android", "android_mobile_ts") or not parsed:
            return

        # Build sorted list of available mc files from obb (once per session)
        if not self._ov_available:
            obb = self.data.obb_files or {}
            mc_files = set()
            for k in obb:
                nm = Path(k).name
                if nm.startswith("mc") and nm.endswith(".png"):
                    mc_files.add(nm[:-4])   # "mc3_1" etc.
            self._ov_available = sorted(mc_files,
                key=lambda s: (int(s.split("_")[0][2:]),
                               int(s.split("_")[1]) if "_" in s else 0))
            # Populate secondary tileset dropdown too
            if hasattr(self, "_secondary_combo"):
                self._secondary_combo.configure(values=self._ov_available)

        # The per-cell `variant` slot in the parser tuple is the cell's
        # high_byte (0 = slot 0, 1 = slot 1). For each high_byte actually
        # USED by the map, show one row mapping to that slot's tileset
        # (mc_id + variant) as resolved by the engine parser.
        ts = self._and_tiles
        hbs_in_use = set()
        for layer in parsed["layers"]:
            for (_mc, hb, _) in layer:
                hbs_in_use.add(hb)

        # Resolve slot 0 and slot 1 from the engine. User-confirmed overrides
        # take precedence for slot 0.
        raw_chunk = parsed.get("_raw_chunk", b"")
        try:
            group = int(str(parsed.get("_mpkh", "")).strip() or -1)
        except Exception:
            group = -1
        pack = parsed.get("_pack", -1)
        map_id = getattr(self, "_current_map_id", None)
        slot0_mc = slot0_v = slot1_mc = slot1_v = None
        engine_info = parse_android_map_engine(raw_chunk) if raw_chunk else None
        if engine_info is not None:
            slot0_mc = engine_info["mc_id_slot0"]
            slot0_v  = engine_info["variant_slot0"]
            slot1_mc = engine_info["mc_id_slot1"]
            slot1_v  = engine_info["variant_slot1"]
        ov_entry = (self.data.mc_overrides().get("by_map", {}).get(
                    map_key(group, pack, map_id))
                    if (map_id is not None and group >= 0 and pack != -1)
                    else None)
        if ov_entry and ov_entry.get("user_confirmed"):
            slot0_mc = ov_entry.get("mc_id", slot0_mc)
            slot0_v  = ov_entry.get("variant", slot0_v)

        # Build the row list: one per high_byte actually used
        rows = []
        for hb in sorted(hbs_in_use):
            if hb == 0 and slot0_mc is not None and slot0_mc >= 0:
                rows.append((hb, slot0_mc, slot0_v))
            elif hb == 1 and slot1_mc is not None and slot1_mc >= 0:
                rows.append((hb, slot1_mc, slot1_v))
            else:
                # Fallback: no engine info; show placeholder
                rows.append((hb, 0, hb))

        for high_byte, mc_type, orig_var in rows:
            row = ttk.Frame(self._ov_inner)
            row.pack(fill="x", pady=1)

            cur_file  = f"mc{mc_type}_{orig_var}"
            present   = ts is not None and callable(ts) and ts(mc_type, orig_var) is not None
            status    = "✓ OK" if present else "✗ missing"
            status_fg = "#080" if present else "#a00"

            ttk.Label(row, text=f"high_byte {high_byte} (slot {high_byte})",
                      width=20, anchor="w").pack(side="left")
            ttk.Label(row, text=cur_file, width=16, anchor="w").pack(side="left")

            # Combo: default to current (or override target if set)
            key = (mc_type, orig_var)
            if key in self._ts_override:
                new_mc, new_var = self._ts_override[key]
                default_choice = f"mc{new_mc}_{new_var}"
            else:
                default_choice = cur_file
            combo_var = tk.StringVar(value=default_choice)
            combo = ttk.Combobox(row, textvariable=combo_var,
                                 values=self._ov_available,
                                 state="readonly", width=20)
            combo.pack(side="left", padx=4)

            status_lbl = ttk.Label(row, text=status, width=8,
                                   foreground=status_fg, anchor="w")
            status_lbl.pack(side="left")

            self._ov_row_vars[key] = (combo_var, orig_var)

        # Scroll to top
        self._ov_canvas.yview_moveto(0)

    def _on_layer_toggle(self):
        """Re-render current map with new layer settings."""
        self._and_tiles = None
        self._on_select()

    def _on_tile_click(self, event):
        """Handler for clicks on the rendered map; shows tile inspector."""
        if (self.src.get() not in ("android", "android_mobile_ts") or
                self._current_parsed is None):
            return
        # Translate canvas click → image coords (account for scroll + zoom)
        canvas = self.viewer.canvas
        cx = canvas.canvasx(event.x)
        cy = canvas.canvasy(event.y)
        zoom = max(1, int(getattr(self.viewer, "_zoom", 1)))
        ix = int(cx) // zoom
        iy = int(cy) // zoom

        TS = self._current_render_tile_size
        col = ix // TS
        row = iy // TS

        parsed = self._current_parsed
        if not (0 <= col < parsed["w"] and 0 <= row < parsed["h"]):
            return

        cell_idx = row * parsed["w"] + col
        layer_data = []
        for L, layer in enumerate(parsed["layers"]):
            if cell_idx < len(layer):
                mc_type, variant, tile_num = layer[cell_idx]
                hb = (mc_type << 1) | variant
                layer_data.append((L, mc_type, variant, tile_num, hb))

        self._show_tile_inspector(col, row, cell_idx, layer_data)

    def _show_tile_inspector(self, col, row, cell_idx, layer_data):
        """Pop a window showing the clicked tile's raw data + tileset preview."""
        parsed = self._current_parsed
        mpkh_lbl = parsed.get("_mpkh", "?")
        pack_lbl = parsed.get("_pack", "?")
        win = tk.Toplevel(self)
        win.title(f"Tile inspector: cell ({col}, {row})  "
                  f"[mpkh{mpkh_lbl}/p{pack_lbl}/map{self._current_map_id}]")
        win.geometry("860x720")

        info = ttk.Frame(win); info.pack(fill="x", padx=8, pady=6)
        ttk.Label(info,
                  text=f"Cell position: ({col}, {row})    "
                       f"linear index: {cell_idx}    "
                       f"map: {self._current_map_id} "
                       f"({self._current_parsed['w']}×{self._current_parsed['h']})    "
                       f"layers: {self._current_parsed['n_layers']}",
                  font=("TkDefaultFont", 10, "bold")).pack(anchor="w")

        # Resolve slot tilesets from the engine parser (slot 0 / slot 1).
        # The cell high_byte selects which slot's tileset to load.
        raw_chunk = parsed.get("_raw_chunk", b"")
        engine_info = parse_android_map_engine(raw_chunk) if raw_chunk else None
        if engine_info is not None:
            slot_mc = (engine_info["mc_id_slot0"], engine_info["mc_id_slot1"])
            slot_v  = (engine_info["variant_slot0"], engine_info["variant_slot1"])
        else:
            slot_mc = (0, 0); slot_v = (0, 0)

        # Per-layer breakdown
        for (L, mc_type, variant, tile_num, hb) in layer_data:
            frm = ttk.LabelFrame(win, text=f"Layer {L}")
            frm.pack(fill="x", expand=False, padx=8, pady=4)

            # high_byte is the slot selector (0 or 1). The actual mc_id +
            # variant come from the engine-parsed slot table in the map header.
            slot_idx = hb if hb in (0, 1) else 0
            sm = slot_mc[slot_idx]
            sv = slot_v[slot_idx]
            if sm < 0:
                ts_label = f"(slot {slot_idx} unconfigured — mc_id = -1)"
                file_label = "(no tileset)"
            else:
                ts_label = f"slot {slot_idx} → mc{sm}_{sv}"
                file_label = f"mc{sm}_{sv}.png"
            txt = (
                f"Raw tile word:  high_byte=0x{hb:02x} ({hb})    "
                f"low_byte=0x{tile_num:02x} ({tile_num})\n"
                f"High byte:      slot selector → {ts_label}\n"
                f"Loads file:     {file_label}\n"
                f"Tile in sheet:  column={tile_num % 16}, row={tile_num // 16}"
            )
            ttk.Label(frm, text=txt, justify="left",
                      font=("Courier", 9)).pack(anchor="w", padx=6, pady=4)

            # Show the actual tile image at 4× scale (use slot tileset, not raw cell)
            ts_callable = self._and_tiles
            preview_mc, preview_var = (sm, sv) if sm >= 0 else (mc_type, variant)
            ts_img = (ts_callable(preview_mc, preview_var)
                      if callable(ts_callable) else None)
            if ts_img is not None:
                TS_src = 32 if ts_img.width >= 512 else 16
                tcols = max(1, ts_img.width // TS_src)
                tx = (tile_num % tcols) * TS_src
                ty = (tile_num // tcols) * TS_src
                if (tx + TS_src <= ts_img.width and
                        ty + TS_src <= ts_img.height):
                    crop = ts_img.crop((tx, ty, tx+TS_src, ty+TS_src))
                    crop = crop.resize((TS_src*4, TS_src*4), Image.NEAREST)
                    photo = ImageTk.PhotoImage(crop)
                    img_lbl = ttk.Label(frm, image=photo)
                    img_lbl.image = photo
                    img_lbl.pack(anchor="w", padx=6, pady=4)

            # Per-layer override — key on the SLOT tileset (sm, sv), not on
            # the cell's raw (mc_type=0, hb) pair, since that's what the
            # renderer queries the tileset cache with.
            ov_row = ttk.Frame(frm); ov_row.pack(fill="x", padx=6, pady=4)
            if sm >= 0:
                ov_orig_mc, ov_orig_var = sm, sv
            else:
                ov_orig_mc, ov_orig_var = mc_type, variant
            ttk.Label(ov_row,
                      text=f"Replace mc{ov_orig_mc}_{ov_orig_var} with:"
                      ).pack(side="left")
            key = (ov_orig_mc, ov_orig_var)
            if key in self._ts_override:
                nm, nv = self._ts_override[key]
                cur_choice = f"mc{nm}_{nv}"
            else:
                cur_choice = f"mc{ov_orig_mc}_{ov_orig_var}"
            cv = tk.StringVar(value=cur_choice)
            cb = ttk.Combobox(ov_row, textvariable=cv,
                              values=self._ov_available,
                              state="readonly", width=18)
            cb.pack(side="left", padx=4)

            def apply_local(orig_mc=ov_orig_mc, orig_var=ov_orig_var, var=cv):
                val = var.get()
                try:
                    stem = val[2:]  # strip "mc"
                    parts = stem.split("_")
                    new_mc = int(parts[0])
                    new_var = int(parts[1]) if len(parts) > 1 else 0
                    if (new_mc, new_var) != (orig_mc, orig_var):
                        self._ts_override[(orig_mc, orig_var)] = (new_mc, new_var)
                    else:
                        self._ts_override.pop((orig_mc, orig_var), None)
                    self._and_tiles = None
                    self._on_select()
                except Exception:
                    pass
            ttk.Button(ov_row, text="Apply & re-render",
                       command=apply_local).pack(side="left", padx=4)

        # ── Neighbor bytes table ────────────────────────────────────────────
        nbr_frm = ttk.LabelFrame(win, text="Neighboring cells (raw tile words)")
        nbr_frm.pack(fill="both", expand=True, padx=8, pady=4)
        nbr_txt = ScrolledText(nbr_frm, wrap="none", font=("Courier", 8),
                               height=10)
        nbr_txt.pack(fill="both", expand=True)

        parsed = self._current_parsed
        w_map = parsed["w"]; h_map = parsed["h"]
        out_lines = []
        for L, layer in enumerate(parsed["layers"]):
            out_lines.append(f"--- Layer {L} ---  "
                             f"(showing 9×9 around cell ({col},{row})):")
            header = "        " + "".join(f" col{c:3d}" for c in
                                          range(max(0, col-4),
                                                min(w_map, col+5)))
            out_lines.append(header)
            for r in range(max(0, row-4), min(h_map, row+5)):
                cells_str = []
                for c in range(max(0, col-4), min(w_map, col+5)):
                    ci = r * w_map + c
                    if ci < len(layer):
                        mt, vr, tn = layer[ci]
                        hb_ = (mt << 1) | vr
                        marker = "*" if (c == col and r == row) else " "
                        cells_str.append(f"{marker}{hb_:02x}{tn:02x} ")
                    else:
                        cells_str.append("       ")
                out_lines.append(f"row{r:3d}: " + "".join(cells_str))
            out_lines.append("")
        out_lines.append("(* = clicked cell. Format: high_byte+low_byte hex)")
        nbr_txt.insert("1.0", "\n".join(out_lines))
        nbr_txt.configure(state="disabled")

        # ── Chunk header dump ───────────────────────────────────────────────
        hdr_frm = ttk.LabelFrame(win, text="Chunk header (first 80 bytes)")
        hdr_frm.pack(fill="x", padx=8, pady=4)
        hdr_txt = ScrolledText(hdr_frm, wrap="none", font=("Courier", 9),
                               height=6)
        hdr_txt.pack(fill="x")
        raw_chunk = parsed.get("_raw_chunk", b"")
        if raw_chunk:
            lines = []
            for o in range(0, min(80, len(raw_chunk)), 16):
                row_b = raw_chunk[o:o+16]
                hex_s = " ".join(f"{b:02x}" for b in row_b)
                asc_s = "".join(chr(b) if 32 <= b < 127 else "."
                                for b in row_b)
                lines.append(f"+{o:3d}: {hex_s:<48}  {asc_s}")
            hdr_txt.insert("1.0", "\n".join(lines))
        hdr_txt.configure(state="disabled")

        ttk.Button(win, text="Close",
                   command=win.destroy).pack(pady=8)

    def _apply_override(self):
        """Read all combo selections and re-render.
        _ts_override maps (orig_mc_type, orig_variant) -> (new_mc_type, new_variant)
        so the user can route a tile to a totally different mc file."""
        new_ov = {}
        for (orig_mc, orig_var), (combo_var, _) in self._ov_row_vars.items():
            val = combo_var.get()   # "mc{N}_{V}"
            try:
                # Parse mc_type AND variant from the selection
                stem = val[2:]  # strip "mc"
                parts = stem.split("_")
                new_mc = int(parts[0])
                new_var = int(parts[1]) if len(parts) > 1 else 0
                if (new_mc, new_var) != (orig_mc, orig_var):
                    new_ov[(orig_mc, orig_var)] = (new_mc, new_var)
            except Exception:
                pass
        self._ts_override = new_ov
        self._and_tiles = None
        self._on_select()

    def _clear_override(self):
        self._ts_override = {}
        self._and_tiles = None
        # Reset all combo vars to their original values
        for (orig_mc, orig_var), (combo_var, _) in self._ov_row_vars.items():
            combo_var.set(f"mc{orig_mc}_{orig_var}")
        self._on_select()

    def _render_android(self, parsed):
        helper = self._extract_helper
        if helper is None:
            helper = self._extract_helper = ExtractTab(self, self.data)
            helper.pack_forget()

        # If user has forced a specific layer count, re-parse the raw chunk
        forced = getattr(self, "_force_layers", None)
        forced_n = forced.get() if forced is not None else "auto"
        raw_chunk = parsed.get("_raw_chunk")
        if forced_n in ("1", "2") and raw_chunk:
            re_parsed = parse_android_map_chunk(raw_chunk,
                                                force_layers=int(forced_n))
            if re_parsed:
                # Preserve ALL bookkeeping metadata that _collect_android_maps
                # attached to the original parsed dict — otherwise lookups
                # like mc_overrides resolution silently fail because _mpkh /
                # _pack go missing in the re-parse path.
                for k in ("_hdr", "_raw_chunk", "_mpkh", "_pack"):
                    if k in parsed:
                        re_parsed[k] = parsed[k]
                re_parsed["_raw_chunk"] = raw_chunk  # ensure even if absent
                parsed = re_parsed
                # Update the cached map list entry too
                for i, (mid, p) in enumerate(self._and_maps):
                    if p is self._current_parsed:
                        self._and_maps[i] = (mid, parsed)
                        self._current_parsed = parsed
                        break

        # Apply layer visibility toggles
        visible = getattr(self, "_layer_visible", None)
        layers = list(parsed["layers"])
        if visible is not None:
            layers = [layer for i, layer in enumerate(layers)
                      if i >= len(visible) or visible[i].get()]

        # Apply routing rule (experimental): possibly remap (mc_type, variant)
        # based on the low byte (tile number).
        routing = getattr(self, "_routing_mode", None)
        routing_mode = routing.get() if routing is not None else "direct"
        threshold = None
        if routing_mode == "high_half":
            threshold = 192
        elif routing_mode == "high_half_128":
            threshold = 128
        elif routing_mode == "high_half_64":
            threshold = 64

        if threshold is not None:
            # Parse secondary tileset selection
            sec_str = getattr(self, "_secondary_var", None)
            sec_str = sec_str.get() if sec_str is not None else "mc1_0"
            try:
                sec_type = int(sec_str.split("_")[0][2:])
                sec_var = int(sec_str.split("_")[1])
            except Exception:
                sec_type, sec_var = 1, 0
            # Remap any cell with low_byte >= threshold to secondary tileset
            new_layers = []
            for layer in layers:
                new_layer = []
                for (mc_type, variant, tile_num) in layer:
                    if tile_num >= threshold:
                        new_layer.append((sec_type, sec_var, tile_num))
                    else:
                        new_layer.append((mc_type, variant, tile_num))
                new_layers.append(new_layer)
            layers = new_layers

        rendered_parsed = dict(parsed)
        rendered_parsed["layers"] = layers
        rendered_parsed["n_layers"] = len(layers)

        # Build a ts_cache that respects (mc_type, variant) overrides
        base_ts = self._and_tiles if self._and_tiles is not None else (lambda a,b: None)
        override = getattr(self, "_ts_override", {})
        if override and callable(base_ts):
            def ts_with_override(mc_type, variant=0):
                key = (mc_type, variant)
                if key in override:
                    new_mc, new_var = override[key]
                    return base_ts(new_mc, new_var)
                return base_ts(mc_type, variant)
            ts_cache = ts_with_override
        else:
            ts_cache = base_ts
        helper._map_ts_override = {}

        # Resolve the map's TWO tileset slots:
        #   slot 0 (cells with high_byte = 0) → primary_mc_id / primary_variant
        #   slot 1 (cells with high_byte = 1) → slot1_mc_id   / slot1_variant
        #
        # Source priority:
        #   1. mc_overrides.json by_map entry with user_confirmed=True (user is GT)
        #   2. The engine parser (deterministic — mirrors FieldClass::LoadMapInfo)
        #   3. by_group / by_map fallback for legacy by-bucket heuristics
        primary_mc_id = primary_variant = None
        slot1_mc_id   = slot1_variant   = None
        if raw_chunk is None:
            raw_chunk = parsed.get("_raw_chunk", b"")
        try:
            group = int(str(parsed.get("_mpkh", "")).strip() or -1)
        except Exception:
            group = -1
        pack = parsed.get("_pack", -1)
        map_id = getattr(self, "_current_map_id", None)

        # Engine parse is cheap and always tried — gives us slot 1 too.
        engine_info = None
        if raw_chunk and len(raw_chunk) > 30:
            engine_info = parse_android_map_engine(raw_chunk)

        # Look up override entry (full record, not just primary)
        override_entry = None
        if (map_id is not None and group >= 0 and pack != -1):
            override_entry = self.data.mc_overrides().get("by_map", {}).get(
                map_key(group, pack, map_id))

        if override_entry and override_entry.get("user_confirmed"):
            # User is ground truth for slot 0; slot 1 falls back to engine.
            primary_mc_id = override_entry.get("mc_id")
            primary_variant = override_entry.get("variant", 0)
            if engine_info is not None:
                slot1_mc_id = engine_info["mc_id_slot1"]
                slot1_variant = engine_info["variant_slot1"]
        elif engine_info is not None:
            # Trust the engine for both slots
            primary_mc_id = engine_info["mc_id_slot0"]
            primary_variant = engine_info["variant_slot0"]
            slot1_mc_id = engine_info["mc_id_slot1"]
            slot1_variant = engine_info["variant_slot1"]
        elif (raw_chunk and len(raw_chunk) > 18
                and map_id is not None and group >= 0 and pack != -1):
            # Legacy by_group / by_map lookup (no engine result available)
            overrides = self.data.mc_overrides()
            mc_id, variant, _src = lookup_primary_mc(
                overrides, group, pack, map_id,
                raw_chunk[18], raw_chunk[5],
                default_mc_id=None, default_variant=None)
            if mc_id is not None:
                primary_mc_id = mc_id
                primary_variant = variant if variant is not None else 0

        return helper._render_android_map(
            rendered_parsed, ts_cache,
            primary_mc_id=primary_mc_id,
            primary_variant=primary_variant,
            slot1_mc_id=slot1_mc_id,
            slot1_variant=slot1_variant)


# ============================================================================
# TAB — TEXT (message.dat sections, names, audio, etc.)
# ============================================================================
