"""ComparisonTab -- side-by-side Mobile vs Android record viewer.

Layout:
    [Asset ▼]
    Mobile: [source ▼ if multi] [filter] [record ▼]
    Android: [source ▼ if multi] [filter] [record ▼]   [Link by id ☑]
    +-------- MOBILE --------+--------- ANDROID --------+
    |  parsed dict (scroll)  |  parsed dict (scroll)    |
    +------------------------+--------------------------+
    | [Semantic⦿ Raw◯] [Hide identical☑]  summary       |
    | Treeview: field | mobile | android                |
"""

from __future__ import annotations

from ..gui_stub import tk, ttk, ScrolledText
from ..gui_core.base import TabBase
from .registry import ASSET_KINDS, compare_records, list_asset_kinds, list_sources


class ComparisonTab(TabBase):
    LABEL = "Comparison"

    def __init__(self, parent, data):
        super().__init__(parent, data)

        # --- asset-type row --------------------------------------------------
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=(4, 2))
        ttk.Label(top, text="Asset:").pack(side="left")
        self.kind_var = tk.StringVar(value="Item")
        self.kind_cb = ttk.Combobox(top, textvariable=self.kind_var,
                                    values=list_asset_kinds(),
                                    state="readonly", width=12)
        self.kind_cb.pack(side="left", padx=(2, 12))
        self.kind_cb.bind("<<ComboboxSelected>>", lambda e: self._on_kind_change())
        self.link_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Link by id",
                        variable=self.link_var,
                        command=self._on_link_toggle).pack(side="left", padx=4)
        self.status_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.status_var,
                  foreground="#a00").pack(side="right")

        # --- mobile picker row -----------------------------------------------
        m_row = ttk.Frame(self); m_row.pack(fill="x", padx=6, pady=1)
        ttk.Label(m_row, text="Mobile:", width=8).pack(side="left")
        self.m_source_var = tk.StringVar(value="")
        self.m_source_cb = ttk.Combobox(m_row, textvariable=self.m_source_var,
                                        values=[], state="readonly", width=22)
        self.m_source_cb.pack(side="left", padx=2)
        self.m_source_cb.bind("<<ComboboxSelected>>",
                              lambda e: self._on_source_change("mobile"))
        self.m_filter_var = tk.StringVar()
        self.m_filter_var.trace_add("write",
                                    lambda *a: self._apply_filter("mobile"))
        ttk.Entry(m_row, textvariable=self.m_filter_var, width=14).pack(side="left", padx=2)
        self.m_idx_var = tk.StringVar(value="-")
        self.m_cb = ttk.Combobox(m_row, textvariable=self.m_idx_var,
                                 values=[], state="readonly", width=42)
        self.m_cb.pack(side="left", padx=2)
        self.m_cb.bind("<<ComboboxSelected>>",
                       lambda e: self._on_record_change("mobile"))

        # --- android picker row ----------------------------------------------
        a_row = ttk.Frame(self); a_row.pack(fill="x", padx=6, pady=(1, 4))
        ttk.Label(a_row, text="Android:", width=8).pack(side="left")
        self.a_source_var = tk.StringVar(value="")
        self.a_source_cb = ttk.Combobox(a_row, textvariable=self.a_source_var,
                                        values=[], state="readonly", width=22)
        self.a_source_cb.pack(side="left", padx=2)
        self.a_source_cb.bind("<<ComboboxSelected>>",
                              lambda e: self._on_source_change("android"))
        self.a_filter_var = tk.StringVar()
        self.a_filter_var.trace_add("write",
                                    lambda *a: self._apply_filter("android"))
        ttk.Entry(a_row, textvariable=self.a_filter_var, width=14).pack(side="left", padx=2)
        self.a_idx_var = tk.StringVar(value="-")
        self.a_cb = ttk.Combobox(a_row, textvariable=self.a_idx_var,
                                 values=[], state="readonly", width=42)
        self.a_cb.pack(side="left", padx=2)
        self.a_cb.bind("<<ComboboxSelected>>",
                       lambda e: self._on_record_change("android"))

        # --- side-by-side dict panels ----------------------------------------
        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=4)
        m_frame = ttk.LabelFrame(body, text="Mobile")
        self.m_text = ScrolledText(m_frame, height=14, wrap="word")
        self.m_text.pack(fill="both", expand=True)
        body.add(m_frame)
        a_frame = ttk.LabelFrame(body, text="Android")
        self.a_text = ScrolledText(a_frame, height=14, wrap="word")
        self.a_text.pack(fill="both", expand=True)
        body.add(a_frame)

        # --- diff controls + table -------------------------------------------
        ctrl = ttk.Frame(self); ctrl.pack(fill="x", padx=6, pady=(4, 0))
        self.diff_mode_var = tk.StringVar(value="semantic")
        ttk.Radiobutton(ctrl, text="Semantic",
                        variable=self.diff_mode_var, value="semantic",
                        command=self._refresh).pack(side="left")
        ttk.Radiobutton(ctrl, text="Raw bytes",
                        variable=self.diff_mode_var, value="raw",
                        command=self._refresh).pack(side="left", padx=(0, 12))
        self.hide_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(ctrl, text="Hide identical fields",
                        variable=self.hide_var,
                        command=self._refresh).pack(side="left")
        self.summary_var = tk.StringVar(value="")
        ttk.Label(ctrl, textvariable=self.summary_var).pack(side="right")

        diff_frame = ttk.Frame(self); diff_frame.pack(fill="both", expand=True,
                                                      padx=6, pady=(2, 6))
        cols = ("field", "mobile", "android")
        self.tree = ttk.Treeview(diff_frame, columns=cols, show="headings",
                                 height=12)
        for c, w in (("field", 260), ("mobile", 240), ("android", 240)):
            self.tree.heading(c, text=c.capitalize())
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(diff_frame, command=self.tree.yview)
        sb.pack(side="left", fill="y")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.tag_configure("diff", foreground="#a00")
        self.tree.tag_configure("same", foreground="#777")

        # --- state -----------------------------------------------------------
        self._m_records = []
        self._a_records = []
        self._m_filtered_indices = []
        self._a_filtered_indices = []
        self._m_idx = -1
        self._a_idx = -1
        self._m_sources = []   # [(key, label), ...]
        self._a_sources = []

        self._on_kind_change()

    # ---- FFData listener ---------------------------------------------------
    def on_data_change(self):
        self._on_kind_change()

    # ---- kind / source change ----------------------------------------------
    def _on_kind_change(self):
        kind = ASSET_KINDS.get(self.kind_var.get())
        if kind is None:
            self.status_var.set("Unknown asset kind"); return
        # Refresh source lists -- list_sources() prepends "(All chapters)"
        # when the kind supports it.
        self._m_sources = list_sources(kind, self.data, "mobile")
        self._a_sources = list_sources(kind, self.data, "android")
        self.m_source_cb["values"] = [l for _, l in self._m_sources]
        self.a_source_cb["values"] = [l for _, l in self._a_sources]
        # Enable source combobox only when there's a choice.
        self.m_source_cb["state"] = ("readonly" if len(self._m_sources) > 1
                                     else "disabled")
        self.a_source_cb["state"] = ("readonly" if len(self._a_sources) > 1
                                     else "disabled")
        # Default to the first source on each side.
        if self._m_sources: self.m_source_cb.current(0)
        else: self.m_source_var.set("")
        if self._a_sources: self.a_source_cb.current(0)
        else: self.a_source_var.set("")

        self._reload_records()

    def _on_source_change(self, side):
        self._reload_records()

    def _selected_source_key(self, side):
        cb = self.m_source_cb if side == "mobile" else self.a_source_cb
        sources = self._m_sources if side == "mobile" else self._a_sources
        try:
            pos = cb.current()
        except Exception:
            pos = -1
        if 0 <= pos < len(sources):
            return sources[pos][0]
        return None

    def _reload_records(self):
        kind = ASSET_KINDS.get(self.kind_var.get())
        if kind is None: return
        m_src = self._selected_source_key("mobile")
        a_src = self._selected_source_key("android")
        self._m_records = self._safe_load(kind.load_mobile,  m_src, "mobile")
        self._a_records = self._safe_load(kind.load_android, a_src, "android")
        self._apply_filter("mobile", refresh=False)
        self._apply_filter("android", refresh=False)
        self._m_idx = self._first_non_null(self._m_records)
        self._a_idx = (self._m_idx if self.link_var.get()
                       else self._first_non_null(self._a_records))
        self._sync_combos()
        self._refresh()

    def _safe_load(self, loader, source_key, side):
        if loader is None:
            return []
        try:
            try:
                return loader(self.data, source_key=source_key) or []
            except TypeError:
                return loader(self.data) or []
        except NotImplementedError as exc:
            self.status_var.set("[%s] %s" % (side, exc)); return []
        except Exception as exc:
            self.status_var.set("[%s] %s: %s" % (side, type(exc).__name__, exc))
            return []

    def _first_non_null(self, recs):
        for i, r in enumerate(recs):
            if r is not None:
                return i
        return -1 if not recs else 0

    # ---- record list filter / select ---------------------------------------
    def _apply_filter(self, side, refresh=True):
        kind = ASSET_KINDS.get(self.kind_var.get())
        if kind is None: return
        recs = self._m_records if side == "mobile" else self._a_records
        q = (self.m_filter_var.get() if side == "mobile"
             else self.a_filter_var.get()).strip().lower()
        labels, indices = [], []
        labeler = kind.record_label or (lambda r: str(r))
        for i, r in enumerate(recs):
            lbl = labeler(r) if r is not None else "%d  (deleted)" % i
            if q and q not in lbl.lower():
                continue
            labels.append(lbl); indices.append(i)
        if side == "mobile":
            self._m_filtered_indices = indices
            self.m_cb["values"] = labels
        else:
            self._a_filtered_indices = indices
            self.a_cb["values"] = labels
        if refresh:
            self._sync_combos(); self._refresh()

    def _sync_combos(self):
        if self._m_idx in self._m_filtered_indices:
            self.m_cb.current(self._m_filtered_indices.index(self._m_idx))
        else:
            self.m_idx_var.set("-")
        if self._a_idx in self._a_filtered_indices:
            self.a_cb.current(self._a_filtered_indices.index(self._a_idx))
        else:
            self.a_idx_var.set("-")

    def _on_record_change(self, side):
        cb = self.m_cb if side == "mobile" else self.a_cb
        try: pos = cb.current()
        except Exception: pos = -1
        if pos < 0: return
        indices = self._m_filtered_indices if side == "mobile" else self._a_filtered_indices
        if pos >= len(indices): return
        new_idx = indices[pos]
        if side == "mobile":
            self._m_idx = new_idx
            if self.link_var.get() and 0 <= new_idx < len(self._a_records):
                self._a_idx = new_idx
        else:
            self._a_idx = new_idx
            if self.link_var.get() and 0 <= new_idx < len(self._m_records):
                self._m_idx = new_idx
        self._sync_combos()
        self._refresh()

    def _on_link_toggle(self):
        if self.link_var.get() and self._m_idx != self._a_idx:
            if 0 <= self._m_idx < len(self._a_records):
                self._a_idx = self._m_idx
                self._sync_combos()
        self._refresh()

    # ---- core refresh ------------------------------------------------------
    def _refresh(self):
        self.m_text.delete("1.0", "end")
        self.a_text.delete("1.0", "end")
        self.tree.delete(*self.tree.get_children())

        kind = ASSET_KINDS.get(self.kind_var.get())
        if kind is None: return

        m_src = self._selected_source_key("mobile")
        a_src = self._selected_source_key("android")
        try:
            result = compare_records(
                self.kind_var.get(), self._m_idx, self._a_idx, self.data,
                hide_identical=self.hide_var.get(),
                mode=self.diff_mode_var.get(),
                m_source=m_src, a_source=a_src,
            )
        except NotImplementedError as exc:
            self.status_var.set(str(exc)); return
        except Exception as exc:
            self.status_var.set("%s: %s" % (type(exc).__name__, exc)); return

        self.status_var.set("")
        self._render_dict(self.m_text, "Mobile",  result["m_dict"])
        self._render_dict(self.a_text, "Android", result["a_dict"])
        for row in result["rows"]:
            tag = "same" if row.same else "diff"
            self.tree.insert("", "end",
                             values=(row.field, row.mobile, row.android),
                             tags=(tag,))
        self.summary_var.set(
            result["summary"]
            + "   |   M total: %d   A total: %d" % (
                result["m_total"], result["a_total"]))

    def _render_dict(self, widget, label, d):
        if not d:
            widget.insert("1.0",
                "(no record decoded)\n\n"
                "Pick a record above, or load the relevant boot_data/"
                "chara_set.dat first.")
            return
        lines = []
        for k, v in d.items():
            if isinstance(v, (bytes, bytearray)):
                preview = v[:32].hex(" ")
                lines.append("%-14s <%dB> %s%s" % (
                    k, len(v), preview, " ..." if len(v) > 32 else ""))
            else:
                lines.append("%-14s %s" % (k, v))
        widget.insert("1.0", "\n".join(lines))
