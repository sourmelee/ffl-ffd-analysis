"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations



from ..gui_stub import (
    tk, ttk, ScrolledText,
)
from ..constants import (
    ELEMENTS, STATUSES,
)
from ..monsters.parser import (
    parse_bem,
)
from ..gui_core.helpers import (
    format_element_bits, format_status_bits,
)
from ..gui_core.base   import TabBase



# =============================================================================
# Ability Tab — bem.dat
# =============================================================================
class AbilityTab(TabBase):
    LABEL = "Abilities"

    def __init__(self, parent, data):
        super().__init__(parent, data)
        top = ttk.Frame(self); top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Source:").pack(side="left")
        self.src_var = tk.StringVar(value="(auto)")
        self.src_combo = ttk.Combobox(top, textvariable=self.src_var, width=28,
                                      state="readonly", values=["(auto)"])
        self.src_combo.pack(side="left", padx=4)
        self.src_combo.bind("<<ComboboxSelected>>", lambda e: self._reload())
        ttk.Label(top, text="(bem.dat per chapter; pick which slot to read)").pack(side="left", padx=8)
        self.note = ttk.Label(top, text="", foreground="#a00")
        self.note.pack(side="right")

        body = ttk.Frame(self); body.pack(fill="both", expand=True, padx=6, pady=4)

        cols = ("idx", "name", "tgt", "pwr", "elem", "mp", "type", "anim")
        self.tree = ttk.Treeview(body, columns=cols, show="headings", height=22)
        widths = {"idx": 50, "name": 220, "tgt": 60, "pwr": 60, "elem": 110,
                  "mp": 50, "type": 60, "anim": 60}
        for c in cols:
            self.tree.heading(c, text=c.upper(),
                              command=lambda cc=c: self._sort_by(cc))
            self.tree.column(c, width=widths.get(c, 80), anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(body, command=self.tree.yview); sb.pack(side="left", fill="y")
        self.tree.config(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._on_select())

        bottom = ttk.Frame(self); bottom.pack(fill="x", padx=6, pady=4)
        ttk.Label(bottom, text="Details:").pack(anchor="w")
        self.details = ScrolledText(self, height=8, wrap="word")
        self.details.pack(fill="x", padx=6, pady=(0, 6))

        self.entries = []
        self._sort_state = (None, False)

    def on_data_change(self):
        # Rebuild source list
        slots = []
        for slot, blob in self.data.find_in_sp_any_chapter("bem.dat"):
            slots.append(slot)
        vals = ["(auto)"] + slots
        self.src_combo["values"] = vals
        if self.src_var.get() not in vals:
            self.src_var.set("(auto)")
        self._reload()

    def _reload(self):
        self.entries = []
        self.tree.delete(*self.tree.get_children())
        self.details.delete("1.0", "end")
        self.note.config(text="")

        chosen = self.src_var.get()
        bem = None; slot_label = None
        if chosen == "(auto)":
            # Pick the largest bem.dat (most complete)
            best_size = -1
            for slot, blob in self.data.find_in_sp_any_chapter("bem.dat"):
                if len(blob) > best_size:
                    bem, slot_label, best_size = blob, slot, len(blob)
        else:
            for slot, blob in self.data.find_in_sp_any_chapter("bem.dat"):
                if slot == chosen:
                    bem, slot_label = blob, slot
                    break

        if bem is None:
            self.note.config(text="bem.dat not found — load .sp slots.")
            return
        try:
            abilities = parse_bem(bem)
        except Exception as exc:
            self.note.config(text=f"bem.dat parse error: {exc}")
            return

        self.note.config(text=f"Source: {slot_label}/bem.dat ({len(abilities)} abilities)")
        for i, ab in enumerate(abilities):
            # parse_bem returns plain strings; normalize to dict here
            if isinstance(ab, str):
                ab = {"name": ab}
            elem_bits = ab.get("element", 0) or 0
            elem_str = ", ".join(n for j, n in enumerate(ELEMENTS)
                                 if elem_bits & (1 << j)) if elem_bits else "-"
            row = (
                str(i),
                ab.get("name", "?"),
                str(ab.get("tgt", "-")),
                str(ab.get("pwr", "-")),
                elem_str,
                str(ab.get("mp", "-")),
                str(ab.get("type", "-")),
                str(ab.get("anim", "-")),
            )
            self.entries.append(ab)
            self.tree.insert("", "end", iid=str(i), values=row)

    def _on_select(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(self.tree.set(sel[0], "idx"))
        if idx >= len(self.entries):
            return
        ab = self.entries[idx]
        lines = [f"Ability #{idx}  —  {ab.get('name','?')}"]
        for k, v in ab.items():
            if k == "name":
                continue
            if k == "element" and isinstance(v, int):
                elem = ", ".join(n for j, n in enumerate(ELEMENTS)
                                 if v & (1 << j)) or "-"
                lines.append(f"  element bits: 0x{v:02x}  ({elem})")
            elif k == "status" and isinstance(v, int):
                stat = ", ".join(n for j, n in enumerate(STATUSES)
                                 if v & (1 << j)) or "-"
                lines.append(f"  status bits:  0x{v:04x}  ({stat})")
            elif k == "raw" and isinstance(v, (bytes, bytearray)):
                lines.append("  raw: " + v[:32].hex(" ") + ("…" if len(v) > 32 else ""))
            else:
                lines.append(f"  {k}: {v}")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", "\n".join(lines))

    def _sort_by(self, col):
        cur, asc = self._sort_state
        asc = (not asc) if cur == col else True
        self._sort_state = (col, asc)
        items = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children("")]
        def keyf(t):
            v = t[0]
            try:
                return (0, float(v))
            except Exception:
                return (1, v.lower())
        items.sort(key=keyf, reverse=not asc)
        for i, (_, iid) in enumerate(items):
            self.tree.move(iid, "", i)



# =============================================================================
# Bit-field formatters
# =============================================================================
def format_element_bits(bits: int) -> str:
    if not bits:
        return "-"
    return ", ".join(n for j, n in enumerate(ELEMENTS) if bits & (1 << j)) or f"0x{bits:02x}"


def format_status_bits(bits: int) -> str:
    if not bits:
        return "-"
    return ", ".join(n for j, n in enumerate(STATUSES) if bits & (1 << j)) or f"0x{bits:04x}"


# =============================================================================
# Item Tab
# =============================================================================
