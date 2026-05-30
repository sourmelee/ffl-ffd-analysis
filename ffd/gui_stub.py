"""Optional GUI dependency loader.

The toolkit is split into a parser layer (used headlessly by analysis
scripts) and a Tkinter GUI layer. When tkinter or PIL.ImageTk are
unavailable (e.g. CI / sandbox / Linux without ``python3-tk``) we fall
back to stub objects so ``import ffd`` still succeeds for parser-only
callers. Class definitions that inherit from ``tk.Tk`` / ``ttk.Frame``
resolve against these stubs; actual instantiation of GUI classes will
raise as soon as a real Tk widget call is made.
"""

from __future__ import annotations



class _GuiStub:
    def __init__(self, *a, **kw): pass
    def __getattr__(self, name): return _GuiStub
    def __call__(self, *a, **kw): return _GuiStub()


class _GuiStubModule:
    def __getattr__(self, name): return _GuiStub


try:
    from PIL import ImageTk  # type: ignore
    HAS_IMAGETK = True
except ImportError:
    ImageTk = _GuiStubModule()  # type: ignore
    HAS_IMAGETK = False

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
    HAS_TK = True
except ImportError:
    tk = _GuiStubModule()           # type: ignore
    ttk = _GuiStubModule()          # type: ignore
    filedialog = _GuiStubModule()   # type: ignore
    messagebox = _GuiStubModule()   # type: ignore
    ScrolledText = _GuiStub         # type: ignore
    HAS_TK = False

HAS_GUI = HAS_TK and HAS_IMAGETK


__all__ = [
    "_GuiStub", "_GuiStubModule",
    "tk", "ttk", "filedialog", "messagebox", "ScrolledText",
    "ImageTk",
    "HAS_TK", "HAS_IMAGETK", "HAS_GUI",
]
