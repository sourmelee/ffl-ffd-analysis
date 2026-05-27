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
import traceback

from PIL import Image

from ..gui_stub import tk, ttk, filedialog, messagebox, ImageTk
from ..gui_core.base import TabBase
from ..animation.parser import parse_field_anm
from .mobile_to_android import (
    MOBILE_COLS, MOBILE_ROWS, MOBILE_CELL_W, MOBILE_CELL_H,
    MOBILE_NATIVE_W, MOBILE_NATIVE_H,
    make_starter_spec, load_mapping_spec, save_mapping_spec,
    convert_mobile_sheet_to_android,
)


MOBILE_ZOOM  = 4     # 80x144 source -> 320x576 view (clear cells, 16x24 -> 64x96)
ANDROID_ZOOM = 2     # 256x512 source -> 512x1024 view (cells 96x96)
PREVIEW_ZOOM = 2     # same as Android so they align


class SpriteConverterTab(TabBase):

    TAB_LABEL = "Sprite Converter"

    # Anchor positions matching the spec strings used by the converter.
    H_ALIGNS = ("left", "center", "right")
    V_ALIGNS = ("top",  "center", "bottom")
    SCALES   = ("1", "2", "3")

    def __init__(self, parent, data):
        super().__init__(parent, data)

        # --- State ------------------------------------------------------
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

        self._build_top_bars()
        self._build_three_panes()
        self._build_action_bar()
        self.bind_all_arrow_keys()

    # ------------------------------------------------------------------
    # Top bars (file pickers + spec controls)
    # ------------------------------------------------------------------

    def _build_top_bars(self):
        bar = ttk.Frame(self); bar.pack(side="top", fill="x", padx=4, pady=2)
        ttk.Button(bar, text="Pick Mobile chpk PNG",
                   command=self._pick_mobile).pack(side="left")
        self._mobile_label = ttk.Label(bar, text="(none)", width=30,
                                       relief="sunken", anchor="w")
        self._mobile_label.pack(side="left", padx=4)

        ttk.Button(bar, text="Pick Android sheet PNG",
                   command=self._pick_android).pack(side="left")
        self._android_label = ttk.Label(bar, text="(none)", width=24,
                                        relief="sunken", anchor="w")
        self._android_label.pack(side="left", padx=4)

        ttk.Button(bar, text="Pick field_anm.dat",
                   command=self._pick_field_anm).pack(side="left")
        self._fanm_label = ttk.Label(bar, text="(none)", width=20,
                                     relief="sunken", anchor="w")
        self._fanm_label.pack(side="left", padx=4)

        ttk.Label(bar, text="Entry:").pack(side="left", padx=(8,0))
        self._entry_var = tk.StringVar(value="1")
        self._entry_combo = ttk.Combobox(bar, textvariable=self._entry_var,
                                         width=4, state="readonly")
        self._entry_combo.pack(side="left")
        self._entry_combo.bind("<<ComboboxSelected>>",
                               lambda e: self._on_entry_change())

        bar2 = ttk.Frame(self); bar2.pack(side="top", fill="x", padx=4, pady=2)
        ttk.Button(bar2, text="New starter spec",
                   command=self._new_spec).pack(side="left")
        ttk.Button(bar2, text="Load spec...",
                   command=self._load_spec).pack(side="left", padx=4)
        ttk.Button(bar2, text="Save spec",
                   command=self._save_spec).pack(side="left")
        ttk.Button(bar2, text="Save spec as...",
                   command=lambda: self._save_spec(prompt_path=True)).pack(side="left", padx=4)
        self._spec_label = ttk.Label(bar2, text="No spec loaded", width=40,
                                     relief="sunken", anchor="w")
        self._spec_label.pack(side="left", padx=4)

    # ------------------------------------------------------------------
    # Three-pane layout: Mobile | Android | Preview, with right Inspector
    # ------------------------------------------------------------------

    def _build_three_panes(self):
        body = ttk.Frame(self); body.pack(fill="both", expand=True,
                                          padx=4, pady=4)

        # Mobile canvas
        m_frame = ttk.LabelFrame(body, text="Mobile (click to select; "
                                            "shift-click to extend wide)")
        m_frame.pack(side="left", fill="y", padx=2)
        self._mobile_canvas = tk.Canvas(
            m_frame, width=MOBILE_NATIVE_W * MOBILE_ZOOM,
            height=MOBILE_NATIVE_H * MOBILE_ZOOM,
            bg="#222", highlightthickness=0)
        self._mobile_canvas.pack()
        self._mobile_canvas.bind("<Button-1>", self._on_click_mobile)
        self._mobile_canvas.bind("<Shift-Button-1>",
                                 lambda e: self._on_click_mobile(e, shift=True))

        # Android canvas (scrollable -- 256x512 * 2 = 512x1024)
        a_frame = ttk.LabelFrame(body, text="Android (click frame to map / inspect)")
        a_frame.pack(side="left", fill="both", expand=True, padx=2)
        a_inner = ttk.Frame(a_frame); a_inner.pack(fill="both", expand=True)
        self._android_canvas = tk.Canvas(
            a_inner, bg="#222", highlightthickness=0,
            width=512, height=600)
        a_ys = ttk.Scrollbar(a_inner, orient="vertical",
                             command=self._android_canvas.yview)
        self._android_canvas.configure(yscrollcommand=a_ys.set)
        a_ys.pack(side="right", fill="y")
        self._android_canvas.pack(side="left", fill="both", expand=True)
        self._android_canvas.bind("<Button-1>", self._on_click_android)

        # Preview canvas (live render of converted output)
        p_frame = ttk.LabelFrame(body, text="Preview (live converted output)")
        p_frame.pack(side="left", fill="both", expand=True, padx=2)
        p_inner = ttk.Frame(p_frame); p_inner.pack(fill="both", expand=True)
        self._preview_canvas = tk.Canvas(
            p_inner, bg="#222", highlightthickness=0,
            width=512, height=600)
        p_ys = ttk.Scrollbar(p_inner, orient="vertical",
                             command=self._preview_canvas.yview)
        self._preview_canvas.configure(yscrollcommand=p_ys.set)
        p_ys.pack(side="right", fill="y")
        self._preview_canvas.pack(side="left", fill="both", expand=True)

        # Inspector sidebar
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
        p = filedialog.askopenfilename(title="Pick field_anm.dat",
                                       filetypes=[("DAT","*.dat"),("All","*.*")])
        if not p: return
        try:
            data = open(p, "rb").read()
            self._field_anm_entries = parse_field_anm(data)
            if not self._field_anm_entries:
                raise RuntimeError("No entries parsed")
            self._field_anm_path = p
            self._fanm_label.config(
                text=f"{os.path.basename(p)} ({len(self._field_anm_entries)} entries)")
            self._entry_combo.config(
                values=[str(i) for i,e in enumerate(self._field_anm_entries)
                        if e['n_frames'] > 0])
            self._on_entry_change()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load field_anm.dat:\n{e}")

    def _on_entry_change(self):
        try:
            self._field_anm_entry_idx = int(self._entry_var.get())
        except ValueError:
            return
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
        self._refresh_all()

    def _load_spec(self):
        p = filedialog.askopenfilename(title="Load mapping spec",
                                       filetypes=[("JSON","*.json")])
        if not p: return
        try:
            self._spec = load_mapping_spec(p)
            self._spec_path = p
            self._spec_label.config(text=os.path.basename(p))
            ent = self._spec.get("android_target",{}).get("field_anm_entry")
            if ent is not None:
                self._entry_var.set(str(ent))
                self._on_entry_change()
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
        native = _normalize_mobile_sheet(self._mobile_img)
        zoomed = native.resize((MOBILE_NATIVE_W*MOBILE_ZOOM,
                                MOBILE_NATIVE_H*MOBILE_ZOOM), Image.NEAREST)
        self._photo_mobile = ImageTk.PhotoImage(zoomed)
        c.create_image(0, 0, image=self._photo_mobile, anchor="nw")
        # Grid + cell labels
        for col in range(MOBILE_COLS):
            for row in range(MOBILE_ROWS):
                x = col * MOBILE_CELL_W * MOBILE_ZOOM
                y = row * MOBILE_CELL_H * MOBILE_ZOOM
                w = MOBILE_CELL_W * MOBILE_ZOOM
                h = MOBILE_CELL_H * MOBILE_ZOOM
                c.create_rectangle(x, y, x+w, y+h,
                                   outline="#c00", width=1)
                c.create_text(x+2, y+2, anchor="nw",
                              text=f"{col},{row}", fill="#ffff80",
                              font=("TkDefaultFont", 7))
        # Selection highlight (lime green)
        for (col, row) in self._sel_mobile:
            x = col * MOBILE_CELL_W * MOBILE_ZOOM
            y = row * MOBILE_CELL_H * MOBILE_ZOOM
            w = MOBILE_CELL_W * MOBILE_ZOOM
            h = MOBILE_CELL_H * MOBILE_ZOOM
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
        zoomed = self._android_img.resize(
            (self._android_img.size[0]*ANDROID_ZOOM,
             self._android_img.size[1]*ANDROID_ZOOM),
            Image.NEAREST)
        self._photo_android = ImageTk.PhotoImage(zoomed)
        c.create_image(0, 0, image=self._photo_android, anchor="nw")
        c.configure(scrollregion=(0, 0, zoomed.size[0], zoomed.size[1]))

        # Field_anm rects in RED with frame index
        for fi, f in enumerate(entry['frames']):
            x = f['x']*ANDROID_ZOOM; y = f['y']*ANDROID_ZOOM
            w = f['w']*ANDROID_ZOOM; h = f['h']*ANDROID_ZOOM
            sel = self._sel_android == ("frame", fi)
            color = "#0f0" if sel else "#f44"
            width = 3 if sel else 1
            c.create_rectangle(x, y, x+w, y+h, outline=color, width=width,
                               tags=("frame", str(fi)))
            c.create_text(x+2, y+2, anchor="nw", text=str(fi),
                          fill="#ffff80", font=("TkDefaultFont", 8, "bold"))

        # Extra-frame rects in CYAN with name
        if self._spec:
            for ei, ef in enumerate(self._spec.get("extra_frames", []) or []):
                rect = ef.get("android_rect")
                if not rect or len(rect) != 4:
                    continue
                ex, ey, ew, eh = rect
                x = ex*ANDROID_ZOOM; y = ey*ANDROID_ZOOM
                w = ew*ANDROID_ZOOM; h = eh*ANDROID_ZOOM
                sel = self._sel_android == ("extra", ei)
                color = "#0f0" if sel else "#0ff"
                width = 3 if sel else 1
                c.create_rectangle(x, y, x+w, y+h, outline=color, width=width,
                                   tags=("extra", str(ei)))
                c.create_text(x+2, y+2, anchor="nw",
                              text=ef.get("name","?")[:8],
                              fill="#0ff", font=("TkDefaultFont", 7))

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
        zoomed = out.resize((out.size[0]*PREVIEW_ZOOM,
                             out.size[1]*PREVIEW_ZOOM), Image.NEAREST)
        self._photo_preview = ImageTk.PhotoImage(zoomed)
        c.create_image(0, 0, image=self._photo_preview, anchor="nw")
        c.configure(scrollregion=(0, 0, zoomed.size[0], zoomed.size[1]))
        # Highlight selected android frame in preview too
        if self._sel_android:
            kind, idx = self._sel_android
            if kind == "frame":
                try:
                    f = entry['frames'][idx]
                    x = f['x']*PREVIEW_ZOOM; y = f['y']*PREVIEW_ZOOM
                    w = f['w']*PREVIEW_ZOOM; h = f['h']*PREVIEW_ZOOM
                    c.create_rectangle(x,y,x+w,y+h, outline="#0f0", width=3)
                except IndexError:
                    pass
            elif kind == "extra":
                try:
                    ef = self._spec['extra_frames'][idx]
                    ex, ey, ew, eh = ef['android_rect']
                    x = ex*PREVIEW_ZOOM; y = ey*PREVIEW_ZOOM
                    w = ew*PREVIEW_ZOOM; h = eh*PREVIEW_ZOOM
                    c.create_rectangle(x,y,x+w,y+h, outline="#0f0", width=3)
                except (IndexError, KeyError, TypeError):
                    pass

    # ==================================================================
    # Click handlers
    # ==================================================================

    def _on_click_mobile(self, ev, shift=False):
        if self._mobile_img is None: return
        col = ev.x // (MOBILE_CELL_W * MOBILE_ZOOM)
        row = ev.y // (MOBILE_CELL_H * MOBILE_ZOOM)
        if not (0 <= col < MOBILE_COLS and 0 <= row < MOBILE_ROWS):
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
        self._status.config(text=f"Mobile selection: {self._sel_mobile}")
        self._draw_mobile()
        # If an Android target is also selected, auto-apply
        if self._sel_android:
            self._apply_mapping()

    def _on_click_android(self, ev):
        if self._android_img is None or not self._field_anm_entries:
            return
        cx = self._android_canvas.canvasx(ev.x)
        cy = self._android_canvas.canvasy(ev.y)
        # Hit-test: scan all frames + extras
        ax = cx / ANDROID_ZOOM
        ay = cy / ANDROID_ZOOM
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
