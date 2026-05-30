"""Auto-extracted from the legacy ``ffd_toolkit.py`` mega-module.

Imports below cover the full set of names the original file made
available at module scope. Unused imports are kept rather than pruned
so the relocated class body remains byte-for-byte identical to the
original code; we apply only light tidy (a module docstring and
consolidated import block).
"""

from __future__ import annotations

from typing import Optional

from PIL import Image

from ..gui_stub import (
    tk, ttk, ImageTk,
)



# ============================================================================
# REUSABLE: thumbnail-grid sidebar with scrollable list
# ============================================================================

class ThumbList(ttk.Frame):
    """Scrollable list of (label, thumbnail) pairs; click selects."""

    def __init__(self, parent, on_select, thumb_size=64):
        super().__init__(parent)
        self.on_select = on_select
        self.thumb_size = thumb_size

        self._canvas = tk.Canvas(self, width=240, bg="#222",
                                 highlightthickness=0)
        self._sb = ttk.Scrollbar(self, orient="vertical",
                                 command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._sb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._sb.pack(side="left", fill="y")

        self._inner = ttk.Frame(self._canvas)
        self._inner_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor="nw")
        self._inner.bind(
            "<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind_all("<MouseWheel>", self._on_wheel)
        self._canvas.bind_all("<Button-4>", lambda e:
                              self._canvas.yview_scroll(-1, "units"))
        self._canvas.bind_all("<Button-5>", lambda e:
                              self._canvas.yview_scroll(1, "units"))

        self._photos = []
        self._items = []     # list of (frame, key, label_text)
        self._selected = None

    def _on_wheel(self, event):
        try:
            self._canvas.yview_scroll(int(-event.delta/120), "units")
        except Exception:
            pass

    def clear(self):
        for it in self._items:
            it[0].destroy()
        self._items = []
        self._photos = []
        self._selected = None

    def add(self, key, image: Optional[Image.Image], label: str):
        row = ttk.Frame(self._inner, padding=2, relief="flat")
        row.grid(sticky="ew", padx=2, pady=1)
        row.bind("<Button-1>", lambda e, k=key: self._click(k))

        if image is not None and image.width > 0 and image.height > 0:
            thumb = image.copy()
            thumb.thumbnail((self.thumb_size, self.thumb_size), Image.NEAREST)
            # Pillow's thumbnail can produce a 1×N or N×1 image for very
            # extreme aspect ratios. Guard against that — guarantee at
            # least 8 px in either dimension by upscaling.
            if thumb.width < 8 or thumb.height < 8:
                scale = max(8.0 / max(thumb.width, 1),
                            8.0 / max(thumb.height, 1))
                new_w = max(8, int(thumb.width * scale))
                new_h = max(8, int(thumb.height * scale))
                thumb = thumb.resize((new_w, new_h), Image.NEAREST)
            ph = ImageTk.PhotoImage(thumb)
            self._photos.append(ph)
            lbl = ttk.Label(row, image=ph)
            lbl.pack(side="left", padx=2)
            lbl.bind("<Button-1>", lambda e, k=key: self._click(k))
        else:
            ttk.Label(row, text="—", width=4).pack(side="left", padx=2)

        text_lbl = ttk.Label(row, text=label, anchor="w", justify="left",
                             wraplength=160)
        text_lbl.pack(side="left", fill="x", expand=True)
        text_lbl.bind("<Button-1>", lambda e, k=key: self._click(k))

        self._items.append((row, key, label))

    def _click(self, key):
        for fr, k, _ in self._items:
            fr.configure(relief="flat")
        for fr, k, _ in self._items:
            if k == key:
                fr.configure(relief="solid")
                break
        self._selected = key
        self.on_select(key)


# ============================================================================
# TAB — TILESETS (mobile cpk*.dat + Android mc*.png)
# ============================================================================
