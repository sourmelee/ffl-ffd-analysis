"""GUI plumbing shared by every tab class.

Lazy ``FFDApp`` access: importing FFDApp eagerly here would create a
circular import (gui_core -> app -> every tab -> gui_core.helpers ->
back into gui_core). Callers should normally do
``from ffd.gui_core.app import FFDApp`` explicitly; ``ffd.gui_core.FFDApp``
also works thanks to the ``__getattr__`` hook below.
"""

from .helpers import pil_to_photo, _scaled, open_in_default_app
from .base import TabBase
from .image_panel import ImagePanel
from .thumb_list import ThumbList

__all__ = [
    "pil_to_photo", "_scaled", "open_in_default_app",
    "TabBase", "ImagePanel", "ThumbList", "FFDApp",
]


def __getattr__(name):
    """PEP 562 lazy module attribute access."""
    if name == "FFDApp":
        from .app import FFDApp
        return FFDApp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
