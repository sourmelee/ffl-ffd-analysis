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
from ..tilesets.parser import (
    MobileTilesetResolver,
)
from ..gui_core.image_panel import ImagePanel
from ..gui_core.thumb_list import ThumbList
from ..gui_core.base   import TabBase



# ============================================================================
# TAB — TILESETS (mobile cpk*.dat + Android mc*.png)
# ============================================================================

class TilesetTab(TabBase):
    LABEL = "Tilesets"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.on_data_change()

    def _build(self):
        top = ttk.Frame(self); top.pack(fill="x", padx=8, pady=4)
        self.src = tk.StringVar(value="mobile")
        ttk.Label(top, text="Source:").pack(side="left")
        ttk.Radiobutton(top, text="Mobile (cpk*.dat)", variable=self.src,
                        value="mobile",
                        command=self.refresh_list).pack(side="left", padx=4)
        ttk.Radiobutton(top, text="Android (mc*.png)", variable=self.src,
                        value="android",
                        command=self.refresh_list).pack(side="left", padx=4)
        self.warn = ttk.Label(top, text="", foreground="#a40")
        self.warn.pack(side="left", padx=12)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        self.thumbs = ThumbList(body, on_select=self._select, thumb_size=48)
        body.add(self.thumbs, weight=1)
        self.viewer = ImagePanel(body)
        body.add(self.viewer, weight=4)

        self._items = {}    # key -> Pillow image

    def on_data_change(self):
        self.refresh_list()

    def refresh_list(self):
        self.thumbs.clear()
        self._items.clear()
        src = self.src.get()
        warn = ""

        if src == "mobile":
            if not any(self.data.sp_slots.values()):
                warn = "No .sp scratchpads loaded."
            else:
                # Use the same boot_data-driven cpk index that the map
                # renderer uses (via MobileTilesetResolver). The previous
                # parse_sprite_container path silently dropped entries with
                # unrecognized layouts; the boot_data cpk index is the
                # engine's own ground-truth list — same coverage as the
                # rendered maps.
                total = 0
                for slot, files in self.data.sp_slots.items():
                    if not files: continue
                    try:
                        res = MobileTilesetResolver(files)
                    except Exception:
                        continue
                    # Iterate every entry the engine knows about, plus a few
                    # palette variants (entries can have up to ~4 palettes;
                    # MobileTilesetResolver returns None if a variant doesn't
                    # exist, so the loop self-terminates safely).
                    for eid in sorted(res.cpk_index):
                        for pal in range(8):
                            img = res.get(eid, pal)
                            if img is None:
                                if pal == 0:
                                    break  # entry truly absent — skip variants
                                break       # ran out of palette variants
                            key = f"{slot}|e{eid}|pal{pal}"
                            self._items[key] = img
                            self.thumbs.add(
                                key, img,
                                f"{slot}\nentry {eid} · pal {pal}")
                            total += 1
                if total == 0:
                    warn = ("No cpk entries decoded from any .sp slot. "
                            "boot_data.dat may be missing or unparseable.")
        else:
            if not self.data.obb_files:
                warn = "No .obb loaded."
            else:
                for k in sorted(self.data.obb_files):
                    n = Path(k).name
                    if n.startswith("mc") and n.endswith(".png"):
                        try:
                            img = Image.open(
                                io.BytesIO(self.data.obb_files[k])
                            ).convert("RGBA")
                        except Exception:
                            continue
                        self._items[k] = img
                        self.thumbs.add(k, img, n)

        self.warn.configure(text=warn)
        if not self._items:
            self.viewer.show(None)

    def _select(self, key):
        img = self._items.get(key)
        if img is None: return
        self.viewer.show(img, f"{img.width}×{img.height}  ·  {key}")


# ============================================================================
# TAB — CHARACTERS (chpk.dat + chara_set.dat naming)
# ============================================================================
