"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from ..gui_stub import (
    tk, ttk,
)
from ..constants import (
    CHARA_TABLE,
)
from ..images.ic import render_ic
from ..sprites.container import (
    parse_sprite_container,
)
from ..gui_core.image_panel import ImagePanel
from ..gui_core.thumb_list import ThumbList
from ..gui_core.base   import TabBase



# ============================================================================
# TAB — CHARACTERS (chpk.dat + chara_set.dat naming)
# ============================================================================

class CharacterTab(TabBase):
    LABEL = "Characters"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.on_data_change()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=4)
        self.src = tk.StringVar(value="mobile")
        ttk.Label(top, text="Source:").pack(side="left")
        ttk.Radiobutton(top, text="Mobile (chpk.dat)", variable=self.src,
                        value="mobile",
                        command=self.on_data_change).pack(side="left",
                                                          padx=4)
        ttk.Radiobutton(top, text="Android (fldchr*.png)", variable=self.src,
                        value="android",
                        command=self.on_data_change).pack(side="left",
                                                          padx=4)
        self.warn = ttk.Label(top, text="", foreground="#a40")
        self.warn.pack(side="left", padx=12)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.thumbs = ThumbList(body, on_select=self._select, thumb_size=64)
        body.add(self.thumbs, weight=1)
        self.viewer = ImagePanel(body)
        body.add(self.viewer, weight=4)
        self._items = {}

    def _entry_label(self, entry_id, variant):
        # Look up by chpk entry & palette
        for (ci, jp, romaji, chpk, pal) in CHARA_TABLE:
            if chpk == entry_id and (pal == variant or pal is None):
                return f"{romaji} ({jp})"
        return None

    def on_data_change(self):
        self.thumbs.clear()
        self._items.clear()
        src = self.src.get()
        warn = ""

        if src == "mobile":
            # Iterate every loaded .sp slot — chpk.dat is chapter-specific
            # and different chapters carry different character variants.
            # The old `find_in_sp` (singular) silently dropped all but the
            # first slot's data.
            slots_with_chpk = list(self.data.find_in_sp_any_chapter("chpk.dat"))
            if not slots_with_chpk:
                warn = "chpk.dat not found in any loaded .sp."
            else:
                # Dedup identical sprites across chapters by (entry, variant,
                # image dims) so the gallery isn't 6× the same character.
                seen = set()
                total = 0
                for slot, blob in slots_with_chpk:
                    for (e, var, ic, _) in parse_sprite_container(blob):
                        img = render_ic(ic)
                        dedup = (e, var, img.width, img.height)
                        if dedup in seen:
                            continue
                        seen.add(dedup)
                        key = f"{slot}|e{e}_v{var}"
                        self._items[key] = img
                        name = self._entry_label(e, var) or ""
                        label = f"[{slot}] entry {e} · v{var}"
                        if name:
                            label = f"{name}\n  ({label})"
                        self.thumbs.add(key, img, label)
                        total += 1
                slot_list = ", ".join(s for s, _ in slots_with_chpk)
                self.warn.configure(
                    text=f"From {len(slots_with_chpk)} slot(s) "
                         f"({slot_list}) — {total} unique sprites")
        else:
            if not self.data.obb_files:
                warn = "No .obb loaded."
            else:
                names = self.data.list_obb_pngs("fldchr")
                for k in names:
                    try:
                        img = Image.open(
                            io.BytesIO(self.data.obb_files[k])
                        ).convert("RGBA")
                    except Exception:
                        continue
                    self._items[k] = img
                    n = Path(k).name
                    self.thumbs.add(k, img, n)
        self.warn.configure(text=warn or self.warn.cget("text"))
        if warn:
            self.viewer.show(None)

    def _select(self, key):
        img = self._items.get(key)
        if img is not None:
            self.viewer.show(img, f"{img.width}×{img.height}  ·  {key}")


# ============================================================================
# TAB — BACKGROUNDS (bg.dat / btlbg*.png)
# ============================================================================
