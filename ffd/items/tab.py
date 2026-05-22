"""Item tab -- Mobile (BE section 4) / Android (LE section 5) viewer.

Columns mirror the field set decode_item_body() produces. The legacy
matk/mdef columns are gone (they were derived from a wrong body layout
the original parser used). Use ComparisonTab to inspect specific byte
positions side-by-side instead.
"""

from __future__ import annotations

from ..gui_stub import tk, ttk, ScrolledText
from ..items.parser import parse_items_mobile, parse_items_android, decode_item_body
from ..gui_core.helpers import format_element_bits, format_status_bits
from ..gui_core.base import TabBase


class ItemTab(TabBase):
    LABEL = "Items"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="Mobile")
        for val in ("Mobile", "Android"):
            ttk.Radiobutton(top, text=val, variable=self.src_var, value=val,
                            command=self._reload).pack(side="left", padx=2)
        self.note = ttk.Label(top, text="", foreground="#a00")
        self.note.pack(side="right")

        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=6, pady=4)
        cols = ("idx", "name", "type", "price", "atk", "def", "magic",
                "flags", "elem", "status")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=22)
        widths = {"idx": 48, "name": 200, "type": 60, "price": 70,
                  "atk": 50, "def": 50, "magic": 50, "flags": 60,
                  "elem": 110, "status": 60}
        for c in cols:
            self.tree.heading(c, text=c.upper(),
                              command=lambda cc=c: self._sort_by(cc))
            self.tree.column(c, width=widths.get(c, 60), anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(body, command=self.tree.yview)
        sb.pack(side="left", fill="y")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        ttk.Label(self, text="Details:").pack(anchor="w", padx=6)
        self.details = ScrolledText(self, height=8, wrap="word")
        self.details.pack(fill="x", padx=6, pady=(0, 6))
        self.entries = []
        self._sort_state = (None, False)

    def on_data_change(self):
        self._reload()

    def _reload(self):
        self.entries = []
        self.tree.delete(*self.tree.get_children())
        self.details.delete("1.0", "end")
        src = self.src_var.get()
        # Fixed 2026-05-22: the old code unconditionally called
        # parse_items_mobile regardless of source, and that parser was
        # itself broken (wrong section/body). Now dispatched by src and
        # decoded via decode_item_body() so each field column shows
        # endian-corrected values.
        if src == "Mobile":
            bd = self.data.boot_data_mobile()
            if bd is None:
                self.note.config(text="boot_data.dat not found in any .sp slot.")
                return
            try:
                items = parse_items_mobile(bd)
            except Exception as exc:
                self.note.config(text="items parse error: %s" % exc); return
            endian = "be"
        else:
            bd = self.data.boot_data_android()
            if bd is None:
                self.note.config(text="Android boot_data.dat not found in .obb/.apk.")
                return
            try:
                items = parse_items_android(bd)
            except Exception as exc:
                self.note.config(text="items parse error: %s" % exc); return
            endian = "le"

        self.note.config(text="%d items loaded (%s)" % (len(items), src))
        for i, raw in enumerate(items):
            if raw is None:
                row = (str(i), "(deleted)", "-", "-", "-", "-", "-", "-", "-", "-")
                self.entries.append(None)
                self.tree.insert("", "end", iid=str(i), values=row)
                continue
            decoded = decode_item_body(raw.get("body", b""), endian)
            it = dict(raw); it.update(decoded)
            elem_s = format_element_bits(it.get("element", 0) or 0)
            row = (str(i), it.get("name", "item_%d" % i),
                   str(it.get("item_type", "-")), str(it.get("price", "-")),
                   str(it.get("attack", "-")), str(it.get("defense", "-")),
                   str(it.get("magic", "-")), str(it.get("flags", "-")),
                   elem_s, str(it.get("status", "-")))
            self.entries.append(it)
            self.tree.insert("", "end", iid=str(i), values=row)

    def _on_select(self):
        sel = self.tree.selection()
        if not sel: return
        idx = int(self.tree.set(sel[0], "idx"))
        if idx >= len(self.entries): return
        it = self.entries[idx]
        if it is None:
            self.details.delete("1.0", "end")
            self.details.insert("1.0", "Item #%d: (deleted slot)" % idx)
            return
        lines = ["Item #%d: %s" % (idx, it.get('name', '?'))]
        for k, v in it.items():
            if k == "name": continue
            if k == "element" and isinstance(v, int):
                lines.append("  element bits: 0x%02x  (%s)" % (
                    v, format_element_bits(v)))
            elif k == "status" and isinstance(v, int):
                lines.append("  status bits:  0x%04x  (%s)" % (
                    v, format_status_bits(v)))
            elif isinstance(v, (bytes, bytearray)):
                preview = v[:32].hex(" ")
                lines.append("  %s: <%dB> %s%s" % (
                    k, len(v), preview, " ..." if len(v) > 32 else ""))
            else:
                lines.append("  %s: %s" % (k, v))
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))

    def _sort_by(self, col):
        cur, asc = self._sort_state
        asc = (not asc) if cur == col else True
        self._sort_state = (col, asc)
        items = [(self.tree.set(iid, col), iid)
                 for iid in self.tree.get_children("")]
        def keyf(t):
            v = t[0]
            try: return (0, float(v))
            except Exception: return (1, v.lower())
        items.sort(key=keyf, reverse=not asc)
        for i, (_, iid) in enumerate(items):
            self.tree.move(iid, "", i)
