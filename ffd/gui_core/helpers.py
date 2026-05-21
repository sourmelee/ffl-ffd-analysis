"""Small GUI helpers shared by every tab."""

from __future__ import annotations

import os
import subprocess
import sys

from PIL import Image

from ..gui_stub import ImageTk, messagebox


def pil_to_photo(img: Image.Image):
    return ImageTk.PhotoImage(img)


def _scaled(img: Image.Image, max_side: int) -> Image.Image:
    if max(img.size) <= max_side:
        return img
    s = max_side / max(img.size)
    return img.resize((max(1, int(img.width*s)), max(1, int(img.height*s))),
                      Image.NEAREST)


def open_in_default_app(path: str):
    """Open a file with the OS default handler, cross-platform."""
    try:
        if sys.platform.startswith("darwin"):
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("Open failed", str(e))


# ----------------------------------------------------------------------------
# Bit-flag formatters used by the Ability/Item/Job tabs.
# ----------------------------------------------------------------------------

def format_element_bits(bits: int) -> str:
    from ..constants import ELEMENTS
    if not bits:
        return "-"
    return ", ".join(n for j, n in enumerate(ELEMENTS) if bits & (1 << j)) or f"0x{bits:02x}"


def format_status_bits(bits: int) -> str:
    from ..constants import STATUSES
    if not bits:
        return "-"
    return ", ".join(n for j, n in enumerate(STATUSES) if bits & (1 << j)) or f"0x{bits:04x}"


def hex_dump(data: bytes, width: int = 16) -> str:
    """Classic hex+ASCII dump used by the event-script and animation tabs."""
    if not data:
        return "(empty)"
    out = []
    for off in range(0, len(data), width):
        chunk = data[off:off + width]
        hexpart = " ".join(f"{b:02x}" for b in chunk).ljust(width * 3)
        ascpart = "".join(chr(b) if 0x20 <= b < 0x7f else "." for b in chunk)
        out.append(f"{off:08x}  {hexpart}  {ascpart}")
    return "\n".join(out)


# Legacy alias — older internal callers used the underscored name.
_hex_dump = hex_dump
