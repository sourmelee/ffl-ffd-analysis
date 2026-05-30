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
    tk, ttk, filedialog, ImageTk,
)


# ============================================================================
# REUSABLE: image-viewer panel with zoom + scroll
# ============================================================================

class ImagePanel(ttk.Frame):
    """Scrollable canvas that shows a Pillow image with zoom controls."""

    def __init__(self, parent):
        super().__init__(parent)
        self._zoom = 1
        self._img: Optional[Image.Image] = None
        self._photo: Optional[ImageTk.PhotoImage] = None

        # Toolbar
        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Button(bar, text="−", width=3,
                   command=self.zoom_out).pack(side="left", padx=2, pady=2)
        ttk.Button(bar, text="+", width=3,
                   command=self.zoom_in).pack(side="left", padx=2, pady=2)
        ttk.Button(bar, text="Fit", width=4,
                   command=self.fit).pack(side="left", padx=2, pady=2)
        self._zoom_lbl = ttk.Label(bar, text="100%")
        self._zoom_lbl.pack(side="left", padx=4)
        self._info = ttk.Label(bar, text="", foreground="#666")
        self._info.pack(side="left", padx=8)
        self._save_btn = ttk.Button(bar, text="Save PNG…",
                                    command=self.save_png)
        self._save_btn.pack(side="right", padx=2, pady=2)

        # Scroll canvas
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, bg="#222",
                                highlightthickness=0)
        hbar = ttk.Scrollbar(body, orient="horizontal",
                             command=self.canvas.xview)
        vbar = ttk.Scrollbar(body, orient="vertical",
                             command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set,
                              yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self._image_item = None

    def show(self, img: Optional[Image.Image], info: str = ""):
        self._img = img
        self._info.configure(text=info)
        if img is None:
            self.canvas.delete("all")
            self._photo = None
            self._image_item = None
            return
        self._render()

    def _render(self):
        if self._img is None:
            return
        z = max(1, int(self._zoom))
        if z != 1:
            disp = self._img.resize(
                (self._img.width * z, self._img.height * z), Image.NEAREST)
        else:
            disp = self._img
        self._photo = ImageTk.PhotoImage(disp)
        self.canvas.delete("all")
        self._image_item = self.canvas.create_image(0, 0, anchor="nw",
                                                    image=self._photo)
        self.canvas.configure(scrollregion=(0, 0, disp.width, disp.height))
        self._zoom_lbl.configure(text=f"{z*100}%")

    def zoom_in(self):
        self._zoom = min(16, self._zoom + 1); self._render()
    def zoom_out(self):
        self._zoom = max(1, self._zoom - 1); self._render()
    def fit(self):
        self._zoom = 1; self._render()

    def save_png(self):
        if self._img is None:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")])
        if not path:
            return
        self._img.save(path)


# ============================================================================
# REUSABLE: thumbnail-grid sidebar with scrollable list
# ============================================================================
