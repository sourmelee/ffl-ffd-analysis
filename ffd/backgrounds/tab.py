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
from ..images.ic import render_ic
from ..sprites.container import (
    parse_sprite_container,
)
from ..gui_core.image_panel import ImagePanel
from ..gui_core.thumb_list import ThumbList
from ..gui_core.base   import TabBase



# ============================================================================
# TAB — BACKGROUNDS (bg.dat / btlbg*.png)
# ============================================================================

class BackgroundTab(TabBase):
    LABEL = "Backgrounds"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.on_data_change()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=4)
        self.src = tk.StringVar(value="mobile")
        ttk.Radiobutton(top, text="Mobile (bg.dat)", variable=self.src,
                        value="mobile",
                        command=self.on_data_change).pack(side="left",
                                                          padx=4)
        ttk.Radiobutton(top, text="Android (btlbg*.png)", variable=self.src,
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

    def on_data_change(self):
        self.thumbs.clear(); self._items.clear()
        src = self.src.get()
        if src == "mobile":
            # Iterate all .sp slots and dedup by (entry, variant, dims).
            slots_with_bg = list(self.data.find_in_sp_any_chapter("bg.dat"))
            if not slots_with_bg:
                self.warn.configure(text="bg.dat not found in any .sp.")
                return
            seen = set()
            total = 0
            for slot, blob in slots_with_bg:
                for (e, var, ic, _) in parse_sprite_container(blob):
                    img = render_ic(ic)
                    dedup = (e, var, img.width, img.height)
                    if dedup in seen:
                        continue
                    seen.add(dedup)
                    key = f"{slot}|bg_{e}_{var}"
                    self._items[key] = img
                    self.thumbs.add(key, img,
                                    f"[{slot}] entry {e} · v{var}")
                    total += 1
            slot_list = ", ".join(s for s, _ in slots_with_bg)
            self.warn.configure(
                text=f"From {len(slots_with_bg)} slot(s) "
                     f"({slot_list}) — {total} unique backgrounds")
        else:
            if not self.data.obb_files:
                self.warn.configure(text="No .obb loaded.")
                return
            self.warn.configure(text="From .obb")
            for k in self.data.list_obb_pngs("btlbg"):
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
# TAB — BATTLE EFFECTS (bip.dat 3 groups, efcimg*.png)
# ============================================================================
