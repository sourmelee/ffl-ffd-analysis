"""GUI tab for the Mobile->Android sprite converter (click-to-map UI).

Layout (left to right):

  +---------+---------+----------+----------------+
  | Mobile  | Android | Preview  | Inspector      |
  | sheet   | sheet   | (live)   | (selected map) |
  | (zoom)  | (zoom)  |          |                |
  +---------+---------+----------+----------------+

Interaction:
* Click a Mobile cell -> highlights it (green).
* Shift-click an adjacent Mobile cell to extend the selection to a
  2-cell horizontal span (wide pose mode).
* Click an Android frame rect to assign the currently-selected Mobile
  cell(s) to that frame; or click without a Mobile selection to "load"
  that frame's existing mapping into the inspector.
* Arrow keys nudge the selected Android frame's placement by 1 px
  (x_offset / y_offset in the spec).
* Inspector exposes h_align, v_align, flip_h, scale, comment for the
  currently-selected Android frame.
* Preview re-renders on every change.

Spec extensions consumed:
* Per-frame ``x_offset``, ``y_offset`` (pixel nudge, default 0).
* Per-frame ``h_align``, ``v_align``, ``scale`` overrides (fall back
  to ``android_target`` defaults).
"""

from __future__ import annotations

import os
import json
import traceback

from PIL import Image

from ..gui_stub import tk, ttk, filedialog, messagebox, ImageTk
from ..gui_core.base import TabBase
from ..animation.parser import parse_field_anm, parse_btl_anm
from .mobile_to_android import (
    MOBILE_COLS, MOBILE_ROWS, MOBILE_CELL_W, MOBILE_CELL_H,
    MOBILE_NATIVE_W, MOBILE_NATIVE_H,
    make_starter_spec, load_mapping_spec, save_mapping_spec,
    convert_mobile_sheet_to_android,
)


# Default integer-only zoom levels (per-canvas, user-adjustable via the
# dropdown in each pane's LabelFrame title). Always integer nearest-neighbor.
ZOOM_CHOICES = ("1", "2", "3", "4", "6")
DEFAULT_MOBILE_ZOOM  = 4
DEFAULT_ANDROID_ZOOM = 2
DEFAULT_PREVIEW_ZOOM = 2


class SpriteConverterTab(TabBase):

    TAB_LABEL = "Sprite Converter"

    # Anchor positions matching the spec strings used by the converter.
    H_ALIGNS = ("left", "center", "right")
    V_ALIGNS = ("top",  "center", "bottom")
    SCALES   = ("1", "2", "3")

    def __init__(self, parent, data):
        super().__init__(parent, data)

        # --- State ------------------------------------------------------
        # Mode: "field" uses field_anm.dat (256x512 output);
        # "battle" uses btlanm_sp.dat (512x512 output, sub-block addressing).
        self._mode = tk.StringVar(value="field")
        self._mobile_path: str | None = None
        self._android_path: str | None = None
        self._field_anm_path: str | None = None
        self._field_anm_entries: list = []
        self._field_anm_entry_idx: int = 1
        self._spec: dict | None = None
        self._spec_path: str | None = None
        self._mobile_img: Image.Image | None = None
        self._android_img: Image.Image | None = None
        # Currently-selected Mobile cells: list of (col, row), 1 or 2 items
        self._sel_mobile: list[tuple[int,int]] = []
        # Currently-selected Android target: either ("frame", int_idx)
        # or ("extra", int_idx). None when nothing is selected.
        self._sel_android: tuple[str, int] | None = None
        # Photo references kept alive (Tk gc bug)
        self._photo_mobile = None
        self._photo_android = None
        self._photo_preview = None
        # Per-canvas zoom (integer nearest-neighbor only -- pixel art rule).
        self._zoom_mobile  = tk.IntVar(value=DEFAULT_MOBILE_ZOOM)
        self._zoom_android = tk.IntVar(value=DEFAULT_ANDROID_ZOOM)
        self._zoom_preview = tk.IntVar(value=DEFAULT_PREVIEW_ZOOM)
        for v, redraw in [
            (self._zoom_mobile,  self._draw_mobile),
            (self._zoom_android, self._draw_android),
            (self._zoom_preview, self._draw_preview),
        ]:
            v.trace_add("write", lambda *a, r=redraw: r())

        # Android grid controls: a configurable "what if this sheet were a
        # uniform grid" overlay. Cells not already covered by a field_anm
        # rect (red) or an extra_frame (cyan) are drawn in YELLOW. Clicking
        # a yellow cell auto-creates an extra_frame at that position.
        # Defaults match field_anm party-member layout (6x5 at pitch 50).
        self._a_cell_w = tk.StringVar(value="48")
        self._a_cell_h = tk.StringVar(value="48")
        self._a_pitch_x = tk.StringVar(value="50")
        self._a_pitch_y = tk.StringVar(value="50")
        self._a_cols   = tk.StringVar(value="6")
        self._a_rows   = tk.StringVar(value="5")
        self._a_origin_x = tk.StringVar(value="1")
        self._a_origin_y = tk.StringVar(value="1")
        self._a_grid_show = tk.BooleanVar(value=True)
        for v in (self._a_cell_w, self._a_cell_h,
                  self._a_pitch_x, self._a_pitch_y,
                  self._a_cols, self._a_rows,
                  self._a_origin_x, self._a_origin_y):
            v.trace_add("write", lambda *a: self._on_android_grid_change())
        self._a_grid_show.trace_add("write",
                                    lambda *a: self._draw_android())

        self._build_top_bars()
        self._build_three_panes()
        self._build_action_bar()
        self.bind_all_arrow_keys()

    # ------------------------------------------------------------------
    # Top bars (file pickers + spec controls)
    # ------------------------------------------------------------------

    def _build_top_bars(self):
        # --- Source type + loaded-entries pickers --------------------------
        bar = ttk.Frame(self); bar.pack(side="top", fill="x", padx=4, pady=2)

        ttk.Label(bar, text="Source type:").pack(side="left", padx=(0,2))
        self._source_type = tk.StringVar(value="Characters")
        st_combo = ttk.Combobox(bar, textvariable=self._source_type,
                                values=("Characters",), width=12,
                                state="readonly")
        st_combo.pack(side="left", padx=2)
        st_combo.bind("<<ComboboxSelected>>",
                      lambda e: self._refresh_source_pickers())

        ttk.Label(bar, text=" Mode:").pack(side="left", padx=(8,2))
        mode_combo = ttk.Combobox(bar, textvariable=self._mode,
                                  values=("field", "battle"), width=7,
                                  state="readonly")
        mode_combo.pack(side="left", padx=2)
        mode_combo.bind("<<ComboboxSelected>>",
                        lambda e: self._on_mode_change())

        ttk.Label(bar, text=" Mobile:").pack(side="left", padx=(8,2))
        self._mobile_pick_var = tk.StringVar()
        self._mobile_pick_combo = ttk.Combobox(
            bar, textvariable=self._mobile_pick_var, values=(),
            width=35, state="readonly")
        self._mobile_pick_combo.pack(side="left", padx=2)
        self._mobile_pick_combo.bind("<<ComboboxSelected>>",
            lambda e: self._on_mobile_pick_selected())

        ttk.Label(bar, text=" Android:").pack(side="left", padx=(8,2))
        self._android_pick_var = tk.StringVar()
        self._android_pick_combo = ttk.Combobox(
            bar, textvariable=self._android_pick_var, values=(),
            width=25, state="readonly")
        self._android_pick_combo.pack(side="left", padx=2)
        self._android_pick_combo.bind("<<ComboboxSelected>>",
            lambda e: self._on_android_pick_selected())

        ttk.Button(bar, text="Refresh from project",
                   command=self._refresh_source_pickers).pack(side="left", padx=4)

        # --- Disk fallback row (escape hatches for files not in project) ---
        bar_disk = ttk.Frame(self); bar_disk.pack(side="top", fill="x",
                                                  padx=4, pady=1)
        ttk.Label(bar_disk, text=" Disk fallback:",
                  foreground="#888").pack(side="left")
        ttk.Button(bar_disk, text="Pick Mobile PNG",
                   command=self._pick_mobile).pack(side="left", padx=2)
        self._mobile_label = ttk.Label(bar_disk, text="(none)", width=24,
                                       relief="sunken", anchor="w")
        self._mobile_label.pack(side="left", padx=2)
        ttk.Button(bar_disk, text="Pick Android PNG",
                   command=self._pick_android).pack(side="left", padx=2)
        self._android_label = ttk.Label(bar_disk, text="(none)", width=22,
                                        relief="sunken", anchor="w")
        self._android_label.pack(side="left", padx=2)
        ttk.Button(bar_disk, text="Pick field_anm.dat",
                   command=self._pick_field_anm).pack(side="left", padx=2)
        self._fanm_label = ttk.Label(bar_disk, text="(none)", width=18,
                                     relief="sunken", anchor="w")
        self._fanm_label.pack(side="left", padx=2)
        ttk.Label(bar_disk, text=" Entry:").pack(side="left", padx=(8,0))
        self._entry_var = tk.StringVar(value="1")
        self._entry_combo = ttk.Combobox(bar_disk,
                                         textvariable=self._entry_var,
                                         width=4, state="readonly")
        self._entry_combo.pack(side="left")
        self._entry_combo.bind("<<ComboboxSelected>>",
                               lambda e: self._on_entry_change())

        # Try to populate the source pickers from currently-loaded data.
        # (Called after_idle so listeners on FFData fire first if needed.)
        self.after_idle(self._refresh_source_pickers)
        # Try to auto-load field_anm.dat from the project's OBB on init.
        self.after_idle(self._try_autoload_field_anm)

        bar2 = ttk.Frame(self); bar2.pack(side="top", fill="x", padx=4, pady=2)
        ttk.Button(bar2, text="New starter spec",
                   command=self._new_spec).pack(side="left")
        ttk.Button(bar2, text="Load spec...",
                   command=self._load_spec).pack(side="left", padx=4)
        ttk.Button(bar2, text="Save spec",
                   command=self._save_spec).pack(side="left")
        ttk.Button(bar2, text="Save spec as...",
                   command=lambda: self._save_spec(prompt_path=True)).pack(side="left", padx=4)
        ttk.Button(bar2, text="Clone for new character...",
                   command=self._clone_for_new_character).pack(side="left", padx=4)
        self._spec_label = ttk.Label(bar2, text="No spec loaded", width=40,
                                     relief="sunken", anchor="w")
        self._spec_label.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Three-pane layout: Mobile | Android | Preview, with right Inspector
    # ------------------------------------------------------------------

    def _build_three_panes(self):
        body = ttk.Frame(self); body.pack(fill="both", expand=True,
                                          padx=4, pady=4)

        def make_scrollable_pane(parent, title, zoom_var,
                                 click_handler=None, shift_handler=None,
                                 width=320, height=600,
                                 extra_title_widgets=None):
            """Build a LabelFrame containing: a zoom dropdown in the title
            row + a Canvas with both H and V scrollbars.

            ``extra_title_widgets``: optional callable that takes the title
            row ttk.Frame and packs additional widgets into it (used by
            the Mobile pane to expose cell dim entries).
            """
            frame = ttk.LabelFrame(parent, text=title)
            frame.pack(side="left", fill="both", expand=True, padx=2)
            tr = ttk.Frame(frame); tr.pack(side="top", fill="x")
            ttk.Label(tr, text="Zoom:").pack(side="left", padx=(4,0))
            cb = ttk.Combobox(tr, textvariable=zoom_var, values=ZOOM_CHOICES,
                              width=3, state="readonly")
            cb.pack(side="left", padx=2)
            ttk.Label(tr, text="x",
                      foreground="#888").pack(side="left")
            if extra_title_widgets:
                extra_title_widgets(tr)
            # Canvas + scrollbars
            inner = ttk.Frame(frame); inner.pack(side="top", fill="both",
                                                 expand=True)
            canvas = tk.Canvas(inner, bg="#222", highlightthickness=0,
                               width=width, height=height)
            vsb = ttk.Scrollbar(inner, orient="vertical",
                                command=canvas.yview)
            hsb = ttk.Scrollbar(inner, orient="horizontal",
                                command=canvas.xview)
            canvas.configure(yscrollcommand=vsb.set,
                             xscrollcommand=hsb.set)
            # Place via grid so both scrollbars work together
            canvas.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            hsb.grid(row=1, column=0, sticky="ew")
            inner.rowconfigure(0, weight=1)
            inner.columnconfigure(0, weight=1)
            if click_handler:
                canvas.bind("<Button-1>", click_handler)
            if shift_handler:
                canvas.bind("<Shift-Button-1>", shift_handler)
            return canvas

        # Mobile pane: title row gets cell_w/cell_h/cols/rows entries
        # so the user can tune the grid for non-default sheets (battle,
        # monster, etc.). Changes sync into spec.mobile_source and trigger
        # an immediate redraw.
        self._cell_w_var = tk.StringVar(value=str(MOBILE_CELL_W))
        self._cell_h_var = tk.StringVar(value=str(MOBILE_CELL_H))
        self._cols_var   = tk.StringVar(value=str(MOBILE_COLS))
        self._rows_var   = tk.StringVar(value=str(MOBILE_ROWS))
        for v in (self._cell_w_var, self._cell_h_var,
                  self._cols_var, self._rows_var):
            v.trace_add("write", lambda *a: self._on_cell_dims_change())

        def _mobile_extras(tr):
            ttk.Label(tr, text="  cell:",
                      foreground="#888").pack(side="left", padx=(8,0))
            ttk.Entry(tr, textvariable=self._cell_w_var, width=3
                      ).pack(side="left")
            ttk.Label(tr, text="x").pack(side="left")
            ttk.Entry(tr, textvariable=self._cell_h_var, width=3
                      ).pack(side="left")
            ttk.Label(tr, text="  cols:",
                      foreground="#888").pack(side="left", padx=(8,0))
            ttk.Entry(tr, textvariable=self._cols_var, width=3
                      ).pack(side="left")
            ttk.Label(tr, text=" rows:",
                      foreground="#888").pack(side="left", padx=(4,0))
            ttk.Entry(tr, textvariable=self._rows_var, width=3
                      ).pack(side="left")

        self._mobile_canvas = make_scrollable_pane(
            body, "Mobile (click cell; shift-click adjacent to extend)",
            self._zoom_mobile,
            click_handler=self._on_click_mobile,
            shift_handler=lambda e: self._on_click_mobile(e, shift=True),
            width=340, height=600,
            extra_title_widgets=_mobile_extras)

        def _android_extras(tr):
            ttk.Label(tr, text="  cell:",
                      foreground="#888").pack(side="left", padx=(8,0))
            ttk.Entry(tr, textvariable=self._a_cell_w, width=3).pack(side="left")
            ttk.Label(tr, text="x").pack(side="left")
            ttk.Entry(tr, textvariable=self._a_cell_h, width=3).pack(side="left")
            ttk.Label(tr, text=" pitch:",
                      foreground="#888").pack(side="left", padx=(4,0))
            ttk.Entry(tr, textvariable=self._a_pitch_x, width=3).pack(side="left")
            ttk.Label(tr, text="x").pack(side="left")
            ttk.Entry(tr, textvariable=self._a_pitch_y, width=3).pack(side="left")
            ttk.Label(tr, text=" cols:",
                      foreground="#888").pack(side="left", padx=(4,0))
            ttk.Entry(tr, textvariable=self._a_cols, width=3).pack(side="left")
            ttk.Label(tr, text=" rows:",
                      foreground="#888").pack(side="left", padx=(4,0))
            ttk.Entry(tr, textvariable=self._a_rows, width=3).pack(side="left")
            ttk.Label(tr, text=" orig:",
                      foreground="#888").pack(side="left", padx=(4,0))
            ttk.Entry(tr, textvariable=self._a_origin_x, width=3).pack(side="left")
            ttk.Label(tr, text=",").pack(side="left")
            ttk.Entry(tr, textvariable=self._a_origin_y, width=3).pack(side="left")
            ttk.Checkbutton(tr, text="grid",
                            variable=self._a_grid_show).pack(side="left", padx=(8,0))

        self._android_canvas = make_scrollable_pane(
            body, "Android (click cell to map / inspect; yellow = grid extras)",
            self._zoom_android,
            click_handler=self._on_click_android,
            width=520, height=600,
            extra_title_widgets=_android_extras)

        self._preview_canvas = make_scrollable_pane(
            body, "Preview (live converted output)",
            self._zoom_preview,
            width=520, height=600)

        # Inspector sidebar (unchanged)
        ins = ttk.LabelFrame(body, text="Inspector (selected mapping)")
        ins.pack(side="left", fill="y", padx=2)
        self._build_inspector(ins)

    def _build_inspector(self, parent):
        self._ins_status = ttk.Label(parent, text="No selection",
                                     foreground="#666", wraplength=200)
        self._ins_status.pack(fill="x", padx=4, pady=4)

        grid = ttk.Frame(parent); grid.pack(fill="x", padx=4)

        # Mobile cell text (read-only display from selection)
        ttk.Label(grid, text="Mobile cell(s):").grid(row=0, column=0, sticky="w")
        self._ins_mobile_lbl = ttk.Label(grid, text="(none)",
                                         foreground="#0a0")
        self._ins_mobile_lbl.grid(row=0, column=1, sticky="w", padx=4)

        ttk.Label(grid, text="h_align:").grid(row=1, column=0, sticky="w")
        self._ins_halign = tk.StringVar(value="center")
        ttk.Combobox(grid, textvariable=self._ins_halign,
                     values=self.H_ALIGNS, state="readonly", width=10
                     ).grid(row=1, column=1, sticky="w", padx=4, pady=1)
        self._ins_halign.trace_add("write", lambda *a: self._on_ins_change("h_align"))

        ttk.Label(grid, text="v_align:").grid(row=2, column=0, sticky="w")
        self._ins_valign = tk.StringVar(value="bottom")
        ttk.Combobox(grid, textvariable=self._ins_valign,
                     values=self.V_ALIGNS, state="readonly", width=10
                     ).grid(row=2, column=1, sticky="w", padx=4, pady=1)
        self._ins_valign.trace_add("write", lambda *a: self._on_ins_change("v_align"))

        ttk.Label(grid, text="scale:").grid(row=3, column=0, sticky="w")
        self._ins_scale = tk.StringVar(value="2")
        ttk.Combobox(grid, textvariable=self._ins_scale,
                     values=self.SCALES, state="readonly", width=10
                     ).grid(row=3, column=1, sticky="w", padx=4, pady=1)
        self._ins_scale.trace_add("write", lambda *a: self._on_ins_change("scale"))

        ttk.Label(grid, text="x_offset:").grid(row=4, column=0, sticky="w")
        self._ins_xoff = tk.StringVar(value="0")
        ttk.Entry(grid, textvariable=self._ins_xoff, width=8
                  ).grid(row=4, column=1, sticky="w", padx=4, pady=1)
        self._ins_xoff.trace_add("write", lambda *a: self._on_ins_change("x_offset"))

        ttk.Label(grid, text="y_offset:").grid(row=5, column=0, sticky="w")
        self._ins_yoff = tk.StringVar(value="0")
        ttk.Entry(grid, textvariable=self._ins_yoff, width=8
                  ).grid(row=5, column=1, sticky="w", padx=4, pady=1)
        self._ins_yoff.trace_add("write", lambda *a: self._on_ins_change("y_offset"))

        self._ins_flip = tk.BooleanVar(value=False)
        ttk.Checkbutton(grid, text="flip horizontal",
                        variable=self._ins_flip,
                        command=lambda: self._on_ins_change("flip_h")
                        ).grid(row=6, column=0, columnspan=2,
                               sticky="w", padx=4, pady=2)

        ttk.Label(grid, text="comment:").grid(row=7, column=0, sticky="w")
        self._ins_comment = tk.StringVar()
        ttk.Entry(grid, textvariable=self._ins_comment, width=20
                  ).grid(row=7, column=1, sticky="w", padx=4, pady=1)
        self._ins_comment.trace_add("write", lambda *a: self._on_ins_change("comment"))

        # Arrow key tip
        ttk.Label(parent,
                  text="\nArrow keys nudge x/y_offset by 1px\n"
                       "(click the Preview pane first to focus)",
                  foreground="#888", justify="left").pack(padx=4, pady=4)

        # Clear / Map action buttons
        ab = ttk.Frame(parent); ab.pack(fill="x", padx=4, pady=4)
        ttk.Button(ab, text="Clear mapping",
                   command=self._clear_selected_mapping).pack(fill="x")
        ttk.Button(ab, text="Add as 'extra' frame",
                   command=self._add_extra_at_selection).pack(fill="x", pady=2)

    def bind_all_arrow_keys(self):
        # Arrow keys nudge the currently-selected Android frame's offset
        for canvas in (self._mobile_canvas, self._android_canvas,
                       self._preview_canvas):
            canvas.bind("<Up>",    lambda e: self._nudge(0, -1))
            canvas.bind("<Down>",  lambda e: self._nudge(0,  1))
            canvas.bind("<Left>",  lambda e: self._nudge(-1, 0))
            canvas.bind("<Right>", lambda e: self._nudge( 1, 0))
            # Focus on click so arrow keys work
            canvas.bind("<Enter>", lambda e, c=canvas: c.focus_set())

    # ------------------------------------------------------------------
    # Action bar
    # ------------------------------------------------------------------

    def _build_action_bar(self):
        ab = ttk.Frame(self); ab.pack(side="bottom", fill="x", padx=4, pady=4)
        ttk.Button(ab, text="Export converted PNG...",
                   command=self._export_png).pack(side="left")
        ttk.Button(ab, text="Manage extras (table)...",
                   command=self._manage_extras).pack(side="left", padx=4)
        self._status = ttk.Label(ab, text="", foreground="#888")
        self._status.pack(side="left", padx=8)

    # ==================================================================
    # File pickers
    # ==================================================================

    def _pick_mobile(self):
        p = filedialog.askopenfilename(title="Pick Mobile chpk PNG",
                                       filetypes=[("PNG","*.png")])
        if not p: return
        try:
            self._mobile_img = Image.open(p).convert("RGBA")
            self._mobile_path = p
            self._mobile_label.config(text=os.path.basename(p))
            self._refresh_all()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load Mobile sheet:\n{e}")

    def _pick_android(self):
        p = filedialog.askopenfilename(title="Pick Android sheet PNG",
                                       filetypes=[("PNG","*.png")])
        if not p: return
        try:
            self._android_img = Image.open(p).convert("RGBA")
            self._android_path = p
            self._android_label.config(text=os.path.basename(p))
            self._refresh_all()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load Android sheet:\n{e}")

    def _pick_field_anm(self):
        mode = self._mode.get()
        title = ("Pick field_anm.dat" if mode == "field"
                 else "Pick btlanm_sp.dat")
        p = filedialog.askopenfilename(title=title,
                                       filetypes=[("DAT","*.dat"),("All","*.*")])
        if not p: return
        try:
            data = open(p, "rb").read()
            self._field_anm_entries = self._parse_anim_data(data)
            if not self._field_anm_entries:
                raise RuntimeError("No entries parsed")
            self._field_anm_path = p
            self._fanm_label.config(
                text=f"{os.path.basename(p)} "
                     f"({len(self._field_anm_entries)} entries)")
            self._populate_entry_combo()
            self._on_entry_change()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load anim file:\n{e}")

    def _parse_anim_data(self, data: bytes):
        """Mode-aware parsing: field_anm vs btl_anm. Both return a list
        of entry dicts with 'frames' / 'sub_anims' / 'n_frames'. Battle
        entries are flat sub-blocks (each with btl_entry/btl_sub keys)."""
        if self._mode.get() == "battle":
            return parse_btl_anm(data)
        return parse_field_anm(data)

    def _populate_entry_combo(self):
        """Fill the entry combo. In field mode shows entry indices.
        In battle mode shows 'btl_entry.btl_sub' labels for the flat
        sub-block entries (more useful than the global index)."""
        if not self._field_anm_entries:
            self._entry_combo.config(values=())
            return
        labels = []
        for e in self._field_anm_entries:
            if e['n_frames'] <= 0:
                continue
            if "btl_entry" in e:
                labels.append(f"{e['btl_entry']}.{e['btl_sub']}")
            else:
                labels.append(str(e['index']))
        self._entry_combo.config(values=labels)

    def _on_entry_change(self):
        sel = self._entry_var.get().strip()
        if not sel or not self._field_anm_entries:
            return
        # Try resolving "N.M" battle label first, then plain "N" field index
        idx = None
        for i, e in enumerate(self._field_anm_entries):
            if "btl_entry" in e:
                if f"{e['btl_entry']}.{e['btl_sub']}" == sel:
                    idx = i; break
            else:
                if str(e['index']) == sel or str(i) == sel:
                    idx = i; break
        if idx is None:
            try:
                idx = int(sel)
            except ValueError:
                return
        self._field_anm_entry_idx = idx
        self._sel_android = None
        self._refresh_all()

    # ==================================================================
    # Spec management
    # ==================================================================

    def _new_spec(self):
        fldchr_id = self._infer_fldchr_id()
        chpk_entry = self._infer_chpk_entry()
        name = (os.path.splitext(os.path.basename(self._android_path or "char"))[0]
                .replace("fldchr","char"))
        self._spec = make_starter_spec(
            name=name, fldchr_id=fldchr_id, chpk_entry=chpk_entry,
            field_anm_entry=self._field_anm_entry_idx)
        self._spec_path = None
        self._spec_label.config(text=f"NEW: {name} (unsaved)")
        self._sync_dims_from_spec()
        self._sync_android_grid_from_spec()
        self._refresh_all()

    def _load_spec(self):
        p = filedialog.askopenfilename(title="Load mapping spec",
                                       filetypes=[("JSON","*.json")])
        if not p: return
        try:
            self._spec = load_mapping_spec(p)
            self._spec_path = p
            self._spec_label.config(text=os.path.basename(p))
            # Restore mode from spec (default field for back-compat)
            spec_mode = self._spec.get("android_target",{}).get("mode", "field")
            if spec_mode != self._mode.get():
                self._mode.set(spec_mode)
                self._on_mode_change()
            ent = self._spec.get("android_target",{}).get("field_anm_entry")
            if ent is not None:
                self._entry_var.set(str(ent))
                self._on_entry_change()
            self._sync_dims_from_spec()
            self._sync_android_grid_from_spec()
            self._refresh_all()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load spec:\n{e}")

    def _save_spec(self, prompt_path=False):
        if self._spec is None:
            messagebox.showinfo("No spec", "Create or load a spec first.")
            return
        p = self._spec_path
        if prompt_path or not p:
            p = filedialog.asksaveasfilename(
                title="Save mapping spec",
                defaultextension=".json",
                filetypes=[("JSON","*.json")],
                initialfile=f"{self._spec.get('name','char')}.json")
            if not p: return
        try:
            save_mapping_spec(self._spec, p)
            self._spec_path = p
            self._spec_label.config(text=os.path.basename(p))
            self._status.config(text=f"Saved {os.path.basename(p)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save spec:\n{e}")

    def _infer_fldchr_id(self):
        if not self._android_path: return 0
        base = os.path.basename(self._android_path)
        if not base.startswith("fldchr"): return 0
        digits = ""
        for ch in base[6:]:
            if ch.isdigit(): digits += ch
            else: break
        return int(digits) if digits else 0

    def _infer_chpk_entry(self):
        if not self._mobile_path: return 13
        parent = os.path.basename(os.path.dirname(self._mobile_path))
        if not parent.startswith("entry"): return 13
        digits = ""
        for ch in parent[5:]:
            if ch.isdigit(): digits += ch
            else: break
        return int(digits) if digits else 13

    # ==================================================================
    # Drawing the three canvases
    # ==================================================================

    def _refresh_all(self):
        self._draw_mobile()
        self._draw_android()
        self._draw_preview()
        self._refresh_inspector()

    def _draw_mobile(self):
        c = self._mobile_canvas
        c.delete("all")
        if self._mobile_img is None:
            return
        from .mobile_to_android import _normalize_mobile_sheet
        zoom = max(1, int(self._zoom_mobile.get() or 1))
        cell_w, cell_h, cols, rows = self._current_mobile_dims()
        native_w, native_h = cols * cell_w, rows * cell_h
        native = _normalize_mobile_sheet(self._mobile_img,
                                         cell_w=cell_w, cell_h=cell_h,
                                         cols=cols, rows=rows)
        zoomed = native.resize((native_w*zoom, native_h*zoom), Image.NEAREST)
        self._photo_mobile = ImageTk.PhotoImage(zoomed)
        c.create_image(0, 0, image=self._photo_mobile, anchor="nw")
        c.configure(scrollregion=(0, 0, zoomed.size[0], zoomed.size[1]))
        for col in range(cols):
            for row in range(rows):
                x = col * cell_w * zoom
                y = row * cell_h * zoom
                w = cell_w * zoom
                h = cell_h * zoom
                c.create_rectangle(x, y, x+w, y+h,
                                   outline="#c00", width=1)
                c.create_text(x+2, y+2, anchor="nw",
                              text=f"{col},{row}", fill="#ffff80",
                              font=("TkDefaultFont", 7))
        for (col, row) in self._sel_mobile:
            x = col * cell_w * zoom
            y = row * cell_h * zoom
            w = cell_w * zoom
            h = cell_h * zoom
            c.create_rectangle(x, y, x+w, y+h, outline="#0f0", width=3)

    def _draw_android(self):
        c = self._android_canvas
        c.delete("all")
        if self._android_img is None or not self._field_anm_entries:
            return
        try:
            entry = self._field_anm_entries[self._field_anm_entry_idx]
        except IndexError:
            return
        zoom = max(1, int(self._zoom_android.get() or 1))
        zoomed = self._android_img.resize(
            (self._android_img.size[0]*zoom,
             self._android_img.size[1]*zoom),
            Image.NEAREST)
        self._photo_android = ImageTk.PhotoImage(zoomed)
        c.create_image(0, 0, image=self._photo_android, anchor="nw")
        c.configure(scrollregion=(0, 0, zoomed.size[0], zoomed.size[1]))

        for fi, f in enumerate(entry['frames']):
            x = f['x']*zoom; y = f['y']*zoom
            w = f['w']*zoom; h = f['h']*zoom
            sel = self._sel_android == ("frame", fi)
            color = "#0f0" if sel else "#f44"
            width = 3 if sel else 1
            c.create_rectangle(x, y, x+w, y+h, outline=color, width=width,
                               tags=("frame", str(fi)))
            c.create_text(x+2, y+2, anchor="nw", text=str(fi),
                          fill="#ffff80", font=("TkDefaultFont", 8, "bold"))

        if self._spec:
            for ei, ef in enumerate(self._spec.get("extra_frames", []) or []):
                rect = ef.get("android_rect")
                if not rect or len(rect) != 4:
                    continue
                ex, ey, ew, eh = rect
                x = ex*zoom; y = ey*zoom
                w = ew*zoom; h = eh*zoom
                sel = self._sel_android == ("extra", ei)
                color = "#0f0" if sel else "#0ff"
                width = 3 if sel else 1
                c.create_rectangle(x, y, x+w, y+h, outline=color, width=width,
                                   tags=("extra", str(ei)))
                c.create_text(x+2, y+2, anchor="nw",
                              text=ef.get("name","?")[:8],
                              fill="#0ff", font=("TkDefaultFont", 7))

        # Yellow grid overlay for unmapped positions
        if self._a_grid_show.get():
            covered = self._covered_rects(entry)
            for gx, gy, gw, gh in self._iter_android_grid():
                if (gx, gy, gw, gh) in covered:
                    continue  # already mapped (red or cyan)
                # Skip cells that go off the sheet
                if (gx + gw > self._android_img.size[0]
                        or gy + gh > self._android_img.size[1]):
                    continue
                c.create_rectangle(gx*zoom, gy*zoom,
                                   (gx+gw)*zoom, (gy+gh)*zoom,
                                   outline="#ff0", width=1,
                                   tags=("grid", f"{gx},{gy}"))

    def _draw_preview(self):
        c = self._preview_canvas
        c.delete("all")
        if (self._mobile_img is None or not self._field_anm_entries
                or self._spec is None):
            return
        try:
            entry = self._field_anm_entries[self._field_anm_entry_idx]
            out = convert_mobile_sheet_to_android(
                self._mobile_img, entry, self._spec, fill_missing=True)
        except Exception as e:
            c.create_text(10, 10, anchor="nw",
                          text=f"Convert error: {e}", fill="red")
            return
        zoom = max(1, int(self._zoom_preview.get() or 1))
        zoomed = out.resize((out.size[0]*zoom,
                             out.size[1]*zoom), Image.NEAREST)
        self._photo_preview = ImageTk.PhotoImage(zoomed)
        c.create_image(0, 0, image=self._photo_preview, anchor="nw")
        c.configure(scrollregion=(0, 0, zoomed.size[0], zoomed.size[1]))
        if self._sel_android:
            kind, idx = self._sel_android
            if kind == "frame":
                try:
                    f = entry['frames'][idx]
                    x = f['x']*zoom; y = f['y']*zoom
                    w = f['w']*zoom; h = f['h']*zoom
                    c.create_rectangle(x,y,x+w,y+h, outline="#0f0", width=3)
                except IndexError:
                    pass
            elif kind == "extra":
                try:
                    ef = self._spec['extra_frames'][idx]
                    ex, ey, ew, eh = ef['android_rect']
                    x = ex*zoom; y = ey*zoom
                    w = ew*zoom; h = eh*zoom
                    c.create_rectangle(x,y,x+w,y+h, outline="#0f0", width=3)
                except (IndexError, KeyError, TypeError):
                    pass

    # ==================================================================
    # Click handlers
    # ==================================================================

    def _on_click_mobile(self, ev, shift=False):
        if self._mobile_img is None: return
        zoom = max(1, int(self._zoom_mobile.get() or 1))
        cell_w, cell_h, cols, rows = self._current_mobile_dims()
        cx = self._mobile_canvas.canvasx(ev.x)
        cy = self._mobile_canvas.canvasy(ev.y)
        col = int(cx // (cell_w * zoom))
        row = int(cy // (cell_h * zoom))
        if not (0 <= col < cols and 0 <= row < rows):
            return
        if shift and self._sel_mobile:
            first_col, first_row = self._sel_mobile[0]
            # Only extend if adjacent horizontally on the same row
            if row == first_row and abs(col - first_col) == 1:
                lo = min(first_col, col)
                self._sel_mobile = [(lo, row), (lo + 1, row)]
            else:
                self._sel_mobile = [(col, row)]
        else:
            self._sel_mobile = [(col, row)]
        # NOTE: do NOT auto-apply here even if Android is selected --
        # otherwise the first Mobile click clears the selection and the
        # user can't shift-click an adjacent cell to extend to 2-cell.
        # Apply is triggered explicitly by the next Android click.
        nshown = len(self._sel_mobile)
        hint = (" (shift-click adjacent to extend; then click Android to apply)"
                if nshown == 1 else
                " (click Android to apply)" if nshown == 2 else "")
        self._status.config(text=f"Mobile selection: {self._sel_mobile}{hint}")
        self._draw_mobile()

    def _on_click_android(self, ev):
        if self._android_img is None or not self._field_anm_entries:
            return
        cx = self._android_canvas.canvasx(ev.x)
        cy = self._android_canvas.canvasy(ev.y)
        zoom = max(1, int(self._zoom_android.get() or 1))
        ax = cx / zoom
        ay = cy / zoom
        entry = self._field_anm_entries[self._field_anm_entry_idx]
        hit = None
        for fi, f in enumerate(entry['frames']):
            if (f['x'] <= ax <= f['x']+f['w']
                    and f['y'] <= ay <= f['y']+f['h']):
                hit = ("frame", fi); break
        if hit is None and self._spec:
            for ei, ef in enumerate(self._spec.get("extra_frames", []) or []):
                rect = ef.get("android_rect")
                if not rect or len(rect) != 4:
                    continue
                ex, ey, ew, eh = rect
                if ex <= ax <= ex+ew and ey <= ay <= ey+eh:
                    hit = ("extra", ei); break

        # If no rect hit, try the Android grid overlay -- click on a yellow
        # grid cell auto-creates an extra_frame there.
        if hit is None and self._a_grid_show.get() and self._spec is not None:
            for gx, gy, gw, gh in self._iter_android_grid():
                if gx <= ax <= gx+gw and gy <= ay <= gy+gh:
                    # Create a new extra_frame for this grid cell
                    efs = self._spec.setdefault("extra_frames", [])
                    name = f"grid_{gx}_{gy}"
                    # Avoid duplicate names
                    n = name
                    suffix = 0
                    while any(e.get("name") == n for e in efs):
                        suffix += 1
                        n = f"{name}_{suffix}"
                    efs.append({"name": n,
                                "android_rect": [gx, gy, gw, gh],
                                "mobile_col": None, "mobile_row": None,
                                "mobile_cells_w": 1, "mobile_cells_h": 1,
                                "flip_h": False, "x_offset": 0, "y_offset": 0,
                                "comment": "added via Android grid click"})
                    hit = ("extra", len(efs) - 1)
                    self._status.config(
                        text=f"Created extra frame {n} at ({gx},{gy},{gw},{gh})")
                    break
        if hit is None:
            return
        self._sel_android = hit
        self._status.config(text=f"Android selection: {hit}")
        # If a Mobile cell selection exists, apply it; otherwise just inspect
        if self._sel_mobile and self._spec is not None:
            self._apply_mapping()
        else:
            self._draw_android()
            self._refresh_inspector()
            self._draw_preview()

    def _apply_mapping(self):
        if not self._sel_mobile or self._sel_android is None or self._spec is None:
            return
        cols = sorted(c for c,_ in self._sel_mobile)
        rows = sorted(r for _,r in self._sel_mobile)
        m_col = cols[0]
        m_row = rows[0]
        m_cw = len(cols) if len(cols) > 1 else 1
        # (Only horizontal spans supported per spec; vertical span would need m_ch)
        m_ch = 1
        kind, idx = self._sel_android
        if kind == "frame":
            fm = self._spec.setdefault("frame_map", {})
            row = fm.setdefault(str(idx), {})
        else:
            efs = self._spec.setdefault("extra_frames", [])
            row = efs[idx]
        row["mobile_col"] = m_col
        row["mobile_row"] = m_row
        row["mobile_cells_w"] = m_cw
        row["mobile_cells_h"] = m_ch
        row.setdefault("flip_h", False)
        row.setdefault("comment", "")
        row.setdefault("x_offset", 0)
        row.setdefault("y_offset", 0)
        # Clear Mobile selection after applying (avoids accidental re-map)
        self._sel_mobile = []
        self._status.config(text=f"Mapped {kind}[{idx}] <- Mobile ({m_col},{m_row})"
                                 + (f" wide x{m_cw}" if m_cw > 1 else ""))
        self._refresh_all()

    def _clear_selected_mapping(self):
        if self._sel_android is None or self._spec is None: return
        kind, idx = self._sel_android
        if kind == "frame":
            fm = self._spec.setdefault("frame_map", {})
            row = fm.setdefault(str(idx), {})
            row["mobile_col"] = None
            row["mobile_row"] = None
            row["mobile_cells_w"] = 1
            row["mobile_cells_h"] = 1
            row["x_offset"] = 0
            row["y_offset"] = 0
        else:
            efs = self._spec.get("extra_frames", [])
            if 0 <= idx < len(efs):
                ef = efs[idx]
                ef["mobile_col"] = None
                ef["mobile_row"] = None
                ef["mobile_cells_w"] = 1
                ef["mobile_cells_h"] = 1
                ef["x_offset"] = 0
                ef["y_offset"] = 0
        self._status.config(text="Mapping cleared")
        self._refresh_all()

    def _add_extra_at_selection(self):
        """Create a new extra frame at a custom Android position prompted
        from the user. Useful for engine-only positions not in field_anm."""
        if self._spec is None:
            messagebox.showinfo("No spec", "Create or load a spec first.")
            return
        d = tk.Toplevel(self); d.title("Add extra frame")
        d.geometry("280x200")
        rows = [("name","new_extra"), ("x","0"), ("y","0"),
                ("w","48"), ("h","48")]
        vars = {}
        for i, (lab, default) in enumerate(rows):
            ttk.Label(d, text=lab).grid(row=i, column=0, sticky="w", padx=6, pady=2)
            v = tk.StringVar(value=default)
            vars[lab] = v
            ttk.Entry(d, textvariable=v, width=20
                      ).grid(row=i, column=1, sticky="w", padx=6, pady=2)
        def commit():
            try:
                ef = {"name": vars["name"].get().strip() or "new_extra",
                      "android_rect": [int(vars["x"].get()), int(vars["y"].get()),
                                       int(vars["w"].get()), int(vars["h"].get())],
                      "mobile_col": None, "mobile_row": None,
                      "mobile_cells_w": 1, "mobile_cells_h": 1,
                      "flip_h": False, "x_offset": 0, "y_offset": 0,
                      "comment": "added via GUI"}
                self._spec.setdefault("extra_frames", []).append(ef)
                self._sel_android = ("extra", len(self._spec["extra_frames"])-1)
                d.destroy()
                self._refresh_all()
            except ValueError as e:
                messagebox.showerror("Invalid", str(e))
        ttk.Button(d, text="Add", command=commit).grid(row=len(rows),
                                                       column=0, columnspan=2,
                                                       pady=8)

    # ==================================================================
    # Inspector synchronization
    # ==================================================================

    def _current_entry_dict(self):
        if self._sel_android is None or self._spec is None:
            return None
        kind, idx = self._sel_android
        if kind == "frame":
            return self._spec.get("frame_map", {}).get(str(idx))
        else:
            try:
                return self._spec["extra_frames"][idx]
            except (KeyError, IndexError, TypeError):
                return None

    def _refresh_inspector(self):
        ent = self._current_entry_dict()
        if ent is None:
            self._ins_status.config(text="No selection", foreground="#666")
            self._ins_mobile_lbl.config(text="(none)")
            return
        kind, idx = self._sel_android
        label = f"{kind}[{idx}]"
        if kind == "extra":
            label += f"  {self._spec['extra_frames'][idx].get('name','?')}"
        self._ins_status.config(text=label, foreground="#000")

        # Mobile cell display
        mc, mr = ent.get("mobile_col"), ent.get("mobile_row")
        mw = int(ent.get("mobile_cells_w", 1) or 1)
        if mc is None or mr is None:
            self._ins_mobile_lbl.config(text="(unmapped)", foreground="#a00")
        else:
            txt = f"({mc},{mr})" + (f" x{mw}" if mw > 1 else "")
            self._ins_mobile_lbl.config(text=txt, foreground="#080")

        target = self._spec.get("android_target", {})
        # Update widgets without re-triggering callbacks
        self._suppress_ins_cb = True
        try:
            self._ins_halign.set(ent.get("h_align")
                                 or target.get("h_align", "center"))
            self._ins_valign.set(ent.get("v_align")
                                 or target.get("v_align", "bottom"))
            self._ins_scale.set(str(ent.get("scale")
                                    or target.get("scale", 2)))
            self._ins_xoff.set(str(ent.get("x_offset", 0)))
            self._ins_yoff.set(str(ent.get("y_offset", 0)))
            self._ins_flip.set(bool(ent.get("flip_h", False)))
            self._ins_comment.set(ent.get("comment", ""))
        finally:
            self._suppress_ins_cb = False

    def _on_ins_change(self, field):
        if getattr(self, "_suppress_ins_cb", False):
            return
        ent = self._current_entry_dict()
        if ent is None: return
        if field == "h_align":
            ent["h_align"] = self._ins_halign.get()
        elif field == "v_align":
            ent["v_align"] = self._ins_valign.get()
        elif field == "scale":
            try: ent["scale"] = int(self._ins_scale.get())
            except ValueError: return
        elif field == "x_offset":
            try: ent["x_offset"] = int(self._ins_xoff.get())
            except ValueError: return
        elif field == "y_offset":
            try: ent["y_offset"] = int(self._ins_yoff.get())
            except ValueError: return
        elif field == "flip_h":
            ent["flip_h"] = bool(self._ins_flip.get())
        elif field == "comment":
            ent["comment"] = self._ins_comment.get()
        self._draw_preview()

    def _nudge(self, dx, dy):
        ent = self._current_entry_dict()
        if ent is None: return
        ent["x_offset"] = int(ent.get("x_offset", 0) or 0) + dx
        ent["y_offset"] = int(ent.get("y_offset", 0) or 0) + dy
        self._refresh_inspector()
        self._draw_preview()
        self._status.config(text=f"Nudged ({ent['x_offset']}, {ent['y_offset']})")

    # ==================================================================
    # Export + extras-table fallback
    # ==================================================================

    def _export_png(self):
        if (self._mobile_img is None or not self._field_anm_entries
                or self._spec is None):
            messagebox.showinfo("Missing inputs",
                "Need Mobile sheet + field_anm.dat + a spec loaded.")
            return
        p = filedialog.asksaveasfilename(
            title="Export converted PNG",
            defaultextension=".png", filetypes=[("PNG","*.png")],
            initialfile=f"fldchr{self._spec.get('android_target',{}).get('fldchr_id',0)}_0.png")
        if not p: return
        try:
            entry = self._field_anm_entries[self._field_anm_entry_idx]
            out = convert_mobile_sheet_to_android(self._mobile_img, entry,
                                                  self._spec, fill_missing=True)
            out.save(p)
            self._status.config(text=f"Exported {os.path.basename(p)}")
        except Exception as e:
            messagebox.showerror("Error",
                f"Export failed:\n{e}\n\n{traceback.format_exc()}")

    def _manage_extras(self):
        """Legacy extras table for bulk editing (Add/Delete rows, edit
        every column). Click-to-map is the primary workflow now; this
        dialog is for managing the extras LIST (Add/Delete entries),
        which the canvas can't do directly."""
        if self._spec is None:
            messagebox.showinfo("No spec", "Create or load a spec first.")
            return
        d = tk.Toplevel(self)
        d.title(f"Extras list: {self._spec.get('name','char')}")
        d.geometry("520x320")
        d.transient(self.winfo_toplevel())
        tree = ttk.Treeview(d, columns=("name","rect","mobile"),
                            show="headings", height=12)
        for c, w in [("name",120),("rect",140),("mobile",200)]:
            tree.heading(c, text=c); tree.column(c, width=w, anchor="w")
        sb = ttk.Scrollbar(d, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); tree.pack(fill="both", expand=True)
        def refresh():
            for r in tree.get_children(): tree.delete(r)
            for i, ef in enumerate(self._spec.get("extra_frames", []) or []):
                rect = ef.get("android_rect") or [0,0,0,0]
                m = (f"({ef.get('mobile_col')},{ef.get('mobile_row')})"
                     f" x{ef.get('mobile_cells_w',1)}"
                     if ef.get("mobile_col") is not None else "(unmapped)")
                tree.insert("", "end", iid=str(i), values=(
                    ef.get("name",""),
                    f"({rect[0]},{rect[1]},{rect[2]},{rect[3]})", m))
        refresh()
        bb = ttk.Frame(d); bb.pack(fill="x")
        def add():
            self._spec.setdefault("extra_frames", []).append({
                "name": f"extra_{len(self._spec['extra_frames'])}",
                "android_rect": [0,0,48,48],
                "mobile_col": None, "mobile_row": None,
                "mobile_cells_w": 1, "mobile_cells_h": 1,
                "flip_h": False, "x_offset": 0, "y_offset": 0,
                "comment": "new"})
            refresh(); self._refresh_all()
        def delete():
            sel = tree.selection()
            if not sel: return
            i = int(sel[0])
            efs = self._spec.get("extra_frames", [])
            if 0 <= i < len(efs):
                efs.pop(i); refresh(); self._refresh_all()
        ttk.Button(bb, text="Add", command=add).pack(side="left")
        ttk.Button(bb, text="Delete", command=delete).pack(side="left", padx=4)
        ttk.Button(bb, text="Close", command=d.destroy).pack(side="right")

    # ------------------------------------------------------------------
    # Template-reuse: clone the current spec for a different character
    # ------------------------------------------------------------------

    def _clone_for_new_character(self):
        """Take the currently-loaded spec (which encodes character-type
        mappings like 'main party', 'chibi', 'frog') and clone it for
        a different character by changing only the source/target ids.

        All ``frame_map`` and ``extra_frames`` mappings are preserved
        unchanged -- they describe HOW the cells are laid out, which is
        per character-type, not per character. Only the Mobile chpk
        entry / palette and the Android fldchr_id need to change to
        retarget the spec at a new character.
        """
        if self._spec is None:
            messagebox.showinfo("No spec",
                "Load a template spec first (e.g. character_main.json).")
            return
        cur_target = self._spec.get("android_target", {})
        cur_src    = self._spec.get("mobile_source", {})

        d = tk.Toplevel(self)
        d.title("Clone spec for a new character")
        d.geometry("420x260")
        d.transient(self.winfo_toplevel()); d.grab_set()

        ttk.Label(d, text="Template:  "
                  + (os.path.basename(self._spec_path) if self._spec_path
                     else "(unsaved)"),
                  foreground="#666").grid(row=0, column=0, columnspan=2,
                                          sticky="w", padx=8, pady=(8,2))
        ttk.Label(d, text=f"Inherits {len(self._spec.get('frame_map',{}))} "
                          f"frame mappings + "
                          f"{len(self._spec.get('extra_frames',[]) or [])} extras.",
                  foreground="#080").grid(row=1, column=0, columnspan=2,
                                          sticky="w", padx=8)

        # Editable fields
        ttk.Separator(d).grid(row=2, column=0, columnspan=2,
                              sticky="ew", pady=8, padx=4)
        rows = [
            ("name", str(self._spec.get("name", "char"))),
            ("Mobile chpk_entry", str(cur_src.get("chpk_entry", 13))),
            ("Mobile palette",    str(cur_src.get("palette", 0))),
            ("Android fldchr_id", str(cur_target.get("fldchr_id", 13))),
            ("Android field_anm_entry", str(cur_target.get("field_anm_entry", 1))),
        ]
        vars = {}
        for i, (lab, default) in enumerate(rows):
            ttk.Label(d, text=lab).grid(row=3+i, column=0,
                                        sticky="w", padx=8, pady=2)
            v = tk.StringVar(value=default)
            vars[lab] = v
            ttk.Entry(d, textvariable=v, width=24
                      ).grid(row=3+i, column=1, sticky="w", padx=8, pady=2)

        def commit():
            try:
                new_spec = json.loads(json.dumps(self._spec))  # deep copy
                new_spec["name"] = vars["name"].get().strip() or "char"
                new_spec["mobile_source"]["chpk_entry"] = int(vars["Mobile chpk_entry"].get())
                new_spec["mobile_source"]["palette"]    = int(vars["Mobile palette"].get())
                new_spec["android_target"]["fldchr_id"] = int(vars["Android fldchr_id"].get())
                new_spec["android_target"]["field_anm_entry"] = int(vars["Android field_anm_entry"].get())
            except ValueError as e:
                messagebox.showerror("Invalid", f"Numeric field failed: {e}")
                return
            # Prompt save location
            default_name = f"{new_spec['name']}.json"
            init_dir = (os.path.dirname(self._spec_path)
                        if self._spec_path else None)
            p = filedialog.asksaveasfilename(
                title="Save cloned spec",
                defaultextension=".json", filetypes=[("JSON","*.json")],
                initialfile=default_name, initialdir=init_dir)
            if not p:
                return
            try:
                save_mapping_spec(new_spec, p)
            except Exception as e:
                messagebox.showerror("Save failed", str(e))
                return
            self._spec = new_spec
            self._spec_path = p
            self._spec_label.config(text=os.path.basename(p))
            self._entry_var.set(str(new_spec["android_target"]["field_anm_entry"]))
            self._on_entry_change()
            self._sync_dims_from_spec()
            self._sync_android_grid_from_spec()
            self._refresh_all()
            self._status.config(text=f"Cloned to {os.path.basename(p)}")
            d.destroy()

        bb = ttk.Frame(d); bb.grid(row=9, column=0, columnspan=2,
                                   sticky="ew", pady=8, padx=4)
        ttk.Button(bb, text="Clone and save",
                   command=commit).pack(side="left")
        ttk.Button(bb, text="Cancel",
                   command=d.destroy).pack(side="right")

    # ------------------------------------------------------------------
    # Cell-dim helpers (Mobile pane title-row entries <-> spec dims)
    # ------------------------------------------------------------------

    def _current_mobile_dims(self):
        """Return current (cell_w, cell_h, cols, rows) from the GUI vars,
        falling back to constants on parse error."""
        def _safe_int(var, default):
            try:
                v = int(var.get())
                return v if v > 0 else default
            except (ValueError, AttributeError):
                return default
        return (_safe_int(self._cell_w_var, MOBILE_CELL_W),
                _safe_int(self._cell_h_var, MOBILE_CELL_H),
                _safe_int(self._cols_var,   MOBILE_COLS),
                _safe_int(self._rows_var,   MOBILE_ROWS))

    def _on_cell_dims_change(self):
        """User edited cell_w/h/cols/rows: sync into spec.mobile_source
        and redraw Mobile + Preview."""
        if getattr(self, "_suppress_dim_cb", False):
            return
        cell_w, cell_h, cols, rows = self._current_mobile_dims()
        if self._spec is not None:
            ms = self._spec.setdefault("mobile_source", {})
            ms["cell_w"] = cell_w
            ms["cell_h"] = cell_h
            ms["cols"]   = cols
            ms["rows"]   = rows
        self._draw_mobile()
        self._draw_preview()

    def _sync_dims_from_spec(self):
        """When a spec is loaded, push its mobile_source dims into the
        GUI vars without triggering the change callback."""
        if self._spec is None:
            return
        ms = self._spec.get("mobile_source", {})
        self._suppress_dim_cb = True
        try:
            self._cell_w_var.set(str(ms.get("cell_w", MOBILE_CELL_W)))
            self._cell_h_var.set(str(ms.get("cell_h", MOBILE_CELL_H)))
            self._cols_var.set(str(ms.get("cols", MOBILE_COLS)))
            self._rows_var.set(str(ms.get("rows", MOBILE_ROWS)))
        finally:
            self._suppress_dim_cb = False

    # ------------------------------------------------------------------
    # Loaded-files pickers (Source type: Characters)
    # ------------------------------------------------------------------

    def _refresh_source_pickers(self):
        """Re-enumerate Mobile and Android source options from the loaded
        project data (FFData.sp_slots + obb_files). For Source type =
        'Characters', shows Mobile chpk party-member-shape entries and
        Android fldchr*.png files."""
        kind = self._source_type.get()
        mobile_opts = []
        android_opts = []
        if kind == "Characters":
            mobile_opts = self._enumerate_mobile_chpk_characters()
            android_opts = self._enumerate_android_fldchr()

        self._mobile_pick_options = mobile_opts
        self._android_pick_options = android_opts
        # Combobox shows only the labels; selection is matched by index
        self._mobile_pick_combo.config(values=[o["label"] for o in mobile_opts])
        self._android_pick_combo.config(values=[o["label"] for o in android_opts])

    def _enumerate_mobile_chpk_characters(self):
        """Walk every loaded .sp slot, find chpk.dat, and emit one option
        per (entry_idx, palette_idx) pair. Each option carries the
        loaded ICImage so we can render it on demand."""
        from .container import parse_sprite_container
        from ..images.ic import render_ic
        opts = []
        for slot_label, files in (self.data.sp_slots or {}).items():
            if not files:
                continue
            chpk = files.get("chpk.dat") if hasattr(files, "get") else None
            if chpk is None:
                continue
            try:
                for (e_idx, v_idx, ic, _raw) in parse_sprite_container(chpk):
                    label = (f"{slot_label} chpk[{e_idx:02d}] pal{v_idx:02d}  "
                             f"({ic.width}x{ic.height})")
                    opts.append({
                        "label": label, "kind": "mobile_chpk",
                        "sp_slot": slot_label,
                        "chpk_entry": e_idx, "palette": v_idx,
                        "width": ic.width, "height": ic.height,
                        "_ic": ic,
                    })
            except Exception:
                continue
        return opts

    def _enumerate_android_fldchr(self):
        """List every fldchr*.png in the loaded OBB. Each option carries
        the filename + bytes so we can render on demand."""
        opts = []
        files = self.data.obb_files or {}
        for name in sorted(files.keys()):
            n = name.lower()
            if not (n.startswith("fldchr") and n.endswith(".png")):
                continue
            blob = files[name]
            opts.append({
                "label": name, "kind": "android_fldchr",
                "filename": name, "bytes": blob,
            })
        return opts

    def _on_mobile_pick_selected(self):
        """User picked a Mobile source from the combo: render the entry's
        ic image, infer cell dims from the sheet shape (best-guess), and
        update the Mobile canvas."""
        from ..images.ic import render_ic
        sel = self._mobile_pick_var.get()
        opts = getattr(self, "_mobile_pick_options", [])
        for opt in opts:
            if opt["label"] == sel:
                try:
                    self._mobile_img = render_ic(opt["_ic"]).convert("RGBA")
                except Exception as e:
                    messagebox.showerror("Error",
                        f"Failed to render Mobile entry: {e}")
                    return
                self._mobile_label.config(text=opt["label"][:32])
                self._mobile_path = None
                # Try to infer cell dimensions from sheet shape: pick the
                # cell that gives integer cols+rows close to canonical
                # party-member shape (5x6) when possible.
                self._guess_mobile_dims_from_shape(opt["width"], opt["height"])
                # Also write source identity into the spec if loaded
                if self._spec is not None:
                    ms = self._spec.setdefault("mobile_source", {})
                    ms["chpk_entry"] = opt["chpk_entry"]
                    ms["palette"] = opt["palette"]
                self._refresh_all()
                self._status.config(text=f"Loaded Mobile: {opt['label']}")
                return

    def _guess_mobile_dims_from_shape(self, w, h):
        """Best-effort cell-dim inference from sheet pixel dimensions.

        Known patterns:
          80x144  -> cell 16x24, cols 5, rows 6   (field party-member)
          112x48  -> cell 16x16, cols 7, rows 3   (NPC roster)
          120x144 -> cell 24x24, cols 5, rows 6   (wider battle Sol?)

        Falls back to dividing by the current cols/rows values if no
        match is found (so user-edited dims are preserved when picking
        a sheet of the same shape).
        """
        guesses = {
            (80, 144):  (16, 24, 5, 6),
            (120, 144): (24, 24, 5, 6),
            (112, 48):  (16, 16, 7, 3),
            (64, 72):   (16, 24, 4, 3),
            (160, 288): (16, 24, 5, 6),  # 2x of 80x144
            (240, 288): (24, 24, 5, 6),  # 2x of 120x144
        }
        if (w, h) in guesses:
            cw, ch, c, r = guesses[(w, h)]
            self._suppress_dim_cb = True
            try:
                self._cell_w_var.set(str(cw))
                self._cell_h_var.set(str(ch))
                self._cols_var.set(str(c))
                self._rows_var.set(str(r))
            finally:
                self._suppress_dim_cb = False
            if self._spec is not None:
                ms = self._spec.setdefault("mobile_source", {})
                ms["cell_w"] = cw; ms["cell_h"] = ch
                ms["cols"]   = c;  ms["rows"]   = r

    def _on_android_pick_selected(self):
        sel = self._android_pick_var.get()
        opts = getattr(self, "_android_pick_options", [])
        from io import BytesIO
        for opt in opts:
            if opt["label"] == sel:
                try:
                    self._android_img = Image.open(BytesIO(opt["bytes"])
                                                   ).convert("RGBA")
                except Exception as e:
                    messagebox.showerror("Error",
                        f"Failed to load Android sheet: {e}")
                    return
                self._android_label.config(text=opt["filename"][:24])
                self._android_path = None
                # Update spec.android_target.fldchr_id from filename if
                # it matches the standard fldchrNN_M.png pattern
                if self._spec is not None:
                    digits = "".join(c for c in opt["filename"][6:]
                                     if c.isdigit())
                    if digits:
                        try:
                            self._spec.setdefault("android_target", {})\
                                ["fldchr_id"] = int(digits.split("_")[0]
                                                    if "_" in digits else digits)
                        except ValueError:
                            pass
                self._refresh_all()
                self._status.config(text=f"Loaded Android: {opt['filename']}")
                return

    def _try_autoload_field_anm(self):
        """Auto-load the anim file for the current mode from the loaded
        OBB. field mode -> field_anm.dat, battle mode -> btlanm_sp.dat."""
        files = self.data.obb_files or {}
        mode = self._mode.get()
        fname = "field_anm.dat" if mode == "field" else "btlanm_sp.dat"
        blob = files.get(fname)
        if not blob:
            return
        try:
            self._field_anm_entries = self._parse_anim_data(blob)
            self._field_anm_path = f"(loaded from OBB: {fname})"
            self._fanm_label.config(
                text=f"OBB {fname} ({len(self._field_anm_entries)} entries)")
            self._populate_entry_combo()
            self._on_entry_change()
        except Exception:
            pass

    def _on_mode_change(self):
        """Mode switched: reload the anim file, update output size, refresh."""
        # Clear current anim entries -- they're mode-specific
        self._field_anm_entries = []
        self._field_anm_path = None
        self._fanm_label.config(text="(none)")
        # Try auto-loading the right file for the new mode
        self._try_autoload_field_anm()
        # Default output size for the mode (only if no spec or spec hasn't overridden)
        if self._spec is not None:
            at = self._spec.setdefault("android_target", {})
            at["mode"] = self._mode.get()
            # Adjust output_size if it still matches the OTHER mode's default
            cur = tuple(at.get("output_size", [256, 512]))
            if self._mode.get() == "battle" and cur == (256, 512):
                at["output_size"] = [512, 512]
            elif self._mode.get() == "field" and cur == (512, 512):
                at["output_size"] = [256, 512]
        self._sel_android = None
        self._refresh_all()
        self._status.config(text=f"Mode: {self._mode.get()}")

    def on_data_change(self):
        """FFData listener: refresh source pickers when project data changes."""
        try:
            self._refresh_source_pickers()
            self._try_autoload_field_anm()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Android grid helpers
    # ------------------------------------------------------------------

    def _current_android_grid(self):
        """Return (cell_w, cell_h, pitch_x, pitch_y, cols, rows,
        origin_x, origin_y) parsed from the GUI vars (clamping to
        sane fallbacks on parse error)."""
        def _si(var, default):
            try:
                v = int(var.get())
                return v if v >= 0 else default
            except (ValueError, AttributeError):
                return default
        return (_si(self._a_cell_w, 48),  _si(self._a_cell_h, 48),
                _si(self._a_pitch_x, 50), _si(self._a_pitch_y, 50),
                _si(self._a_cols, 6),     _si(self._a_rows, 5),
                _si(self._a_origin_x, 1), _si(self._a_origin_y, 1))

    def _iter_android_grid(self):
        """Yield (x, y, w, h) for every grid cell currently configured."""
        cw, ch, px, py, cols, rows, ox, oy = self._current_android_grid()
        if cw <= 0 or ch <= 0 or cols <= 0 or rows <= 0:
            return
        for r in range(rows):
            for c in range(cols):
                yield (ox + c * px, oy + r * py, cw, ch)

    def _covered_rects(self, entry):
        """Set of (x, y, w, h) covered by field_anm rects + extra_frames."""
        covered = set()
        for f in entry.get("frames", []):
            covered.add((f["x"], f["y"], f["w"], f["h"]))
        if self._spec:
            for ef in self._spec.get("extra_frames", []) or []:
                rect = ef.get("android_rect")
                if rect and len(rect) == 4:
                    covered.add(tuple(rect))
        return covered

    def _on_android_grid_change(self):
        """User edited Android grid params: sync into spec and redraw."""
        if getattr(self, "_suppress_a_grid_cb", False):
            return
        if self._spec is not None:
            at = self._spec.setdefault("android_target", {})
            cw, ch, px, py, cols, rows, ox, oy = self._current_android_grid()
            at["grid"] = {
                "cell_w": cw, "cell_h": ch,
                "pitch_x": px, "pitch_y": py,
                "cols": cols, "rows": rows,
                "origin_x": ox, "origin_y": oy,
            }
        self._draw_android()

    def _sync_android_grid_from_spec(self):
        """Pull android_target.grid from spec into the GUI vars (no callbacks)."""
        if self._spec is None:
            return
        g = self._spec.get("android_target", {}).get("grid", {})
        if not g:
            return
        self._suppress_a_grid_cb = True
        try:
            self._a_cell_w.set(str(g.get("cell_w", 48)))
            self._a_cell_h.set(str(g.get("cell_h", 48)))
            self._a_pitch_x.set(str(g.get("pitch_x", 50)))
            self._a_pitch_y.set(str(g.get("pitch_y", 50)))
            self._a_cols.set(str(g.get("cols", 6)))
            self._a_rows.set(str(g.get("rows", 5)))
            self._a_origin_x.set(str(g.get("origin_x", 1)))
            self._a_origin_y.set(str(g.get("origin_y", 1)))
        finally:
            self._suppress_a_grid_cb = False

