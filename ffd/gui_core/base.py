"""Tab base class — subscribes to FFData change notifications."""

from __future__ import annotations

from ..data.ffdata import FFData
from ..gui_stub import ttk


class TabBase(ttk.Frame):
    def __init__(self, parent, data):
        super().__init__(parent)
        # Accept either an FFData directly (the normal case) or an object
        # that exposes a .data attribute (legacy wrapper case).
        if hasattr(data, "sp_slots") and hasattr(data, "add_listener"):
            self.data: FFData = data
        elif hasattr(data, "data"):
            self.data: FFData = data.data
        else:
            self.data: FFData = data
        self.data.add_listener(self.on_data_change)

    def on_data_change(self):
        """Override in subclasses to refresh from updated FFData."""
