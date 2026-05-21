"""Top-level Tk application — notebook of all tabs + status bar + menu.

Restored from the user's backup of the original ``ffd_toolkit.py`` (the
working copy was truncated mid-``TAB_ORDER`` before this refactor). The
class body matches the backup with two differences:

* The duplicate ``_menu_load_archive`` / ``_menu_load_folder`` /
  ``_menu_clear_all`` / ``_show_about`` definitions the backup had
  accumulated from append-style edits are collapsed to a single canonical
  copy each (the later, fuller versions win).
* Tab construction now logs a loud ``[FFDApp] FAILED to build XxxTab``
  banner and inserts a visible red placeholder tab when a class fails,
  instead of silently producing a tiny error label. Easier to spot when
  a viewer regresses.
"""

from __future__ import annotations

import sys
import traceback

from ..gui_stub import tk, ttk, filedialog, messagebox
from ..data.ffdata import FFData

# Import every tab class — order here is import order, not notebook order.
from ..files_io.files_tab import FilesTab
from ..files_io.extract_tab import ExtractTab
from ..tilesets.tab import TilesetTab
from ..characters.tab import CharacterTab
from ..backgrounds.tab import BackgroundTab
from ..battle_effects.tab import BattleEffectTab
from ..monsters.tab import MonsterTab
from ..maps.tab import MapTab
from ..text.tab import TextTab
from ..music.tab import MusicTab
from ..abilities.tab import AbilityTab
from ..items.tab import ItemTab
from ..jobs.tab import JobTab
from ..events.tab import EventScriptTab
from ..animation.tab import AnimationTab
from ..cross_ref.tab import CrossRefTab
from ..maps.annotation_tab import MapAnnotationTab


class FFDApp(tk.Tk):
    """Top-level Tk application: notebook of all tabs + status bar + menu."""

    TAB_ORDER = [
        FilesTab, ExtractTab, MapTab, MapAnnotationTab, EventScriptTab,
        TextTab, CharacterTab, AnimationTab, TilesetTab, BackgroundTab,
        BattleEffectTab, MonsterTab, MusicTab, AbilityTab, ItemTab, JobTab,
        CrossRefTab,
    ]

    def __init__(self):
        super().__init__()
        self.title("FFD/FFL Toolkit — Reverse-Engineering GUI")
        self.geometry("1280x820")
        self.minsize(900, 600)
        style = ttk.Style()
        for cand in ("clam", "alt", "default"):
            if cand in style.theme_names():
                try:
                    style.theme_use(cand)
                    break
                except Exception:
                    pass
        self.data = FFData()
        self.data.add_listener(self._on_data_change)
        self._build_menu()
        self._build_notebook()
        self._build_status()

    # ---- menu --------------------------------------------------------------
    def _build_menu(self):
        bar = tk.Menu(self)
        m_file = tk.Menu(bar, tearoff=False)
        m_file.add_command(label="Load .sp into slot…", command=self._menu_load_sp)
        m_file.add_separator()
        m_file.add_command(label="Load .obb…",  command=lambda: self._menu_load_archive("obb"))
        m_file.add_command(label="Load .apk…",  command=lambda: self._menu_load_archive("apk"))
        m_file.add_command(label="Load .jar…",  command=lambda: self._menu_load_archive("jar"))
        m_file.add_command(label="Load .jam (manifest)…",
                           command=lambda: self._menu_load_archive("jam"))
        m_file.add_separator()
        m_file.add_command(label="Load folder as Android assets (.obb-equivalent)…",
                           command=lambda: self._menu_load_folder("obb"))
        m_file.add_command(label="Load folder as APK contents…",
                           command=lambda: self._menu_load_folder("apk"))
        m_file.add_command(label="Load folder as JAR contents…",
                           command=lambda: self._menu_load_folder("jar"))
        m_file.add_separator()
        m_file.add_command(label="Clear all", command=self._menu_clear_all)
        m_file.add_separator()
        m_file.add_command(label="Quit", command=self.destroy)
        bar.add_cascade(label="File", menu=m_file)
        m_help = tk.Menu(bar, tearoff=False)
        m_help.add_command(label="About", command=self._show_about)
        bar.add_cascade(label="Help", menu=m_help)
        self.config(menu=bar)

    # ---- notebook ----------------------------------------------------------
    def _build_notebook(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.tabs = []
        for cls in self.TAB_ORDER:
            label = getattr(cls, "LABEL", cls.__name__)
            try:
                frame = ttk.Frame(nb)
                # MapAnnotationTab needs the full app instance (it reads
                # self.data.mc_overrides and triggers refreshes across the
                # notebook). All other tabs just need FFData.
                tab = cls(frame, self) if cls is MapAnnotationTab else cls(frame, self.data)
                tab.pack(fill="both", expand=True)
                nb.add(frame, text=label)
                self.tabs.append(tab)
            except Exception as exc:
                # Loud per-tab failure: print a banner so you can see which
                # tabs failed and why, and visibly mark the slot in the
                # notebook (titled "! Label") with the exception text.
                print(f"\n[FFDApp] FAILED to build {cls.__name__}: "
                      f"{type(exc).__name__}: {exc}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                try:
                    frame = ttk.Frame(nb)
                    ttk.Label(
                        frame,
                        text=(f"{cls.__name__} failed to load.\n\n"
                              f"{type(exc).__name__}: {exc}\n\n"
                              "See the terminal for the full traceback."),
                        foreground="#a00", justify="left", padding=12,
                    ).pack(anchor="nw")
                    nb.add(frame, text=f"! {label}")
                except Exception:
                    pass

    # ---- status bar --------------------------------------------------------
    def _build_status(self):
        bar = ttk.Frame(self, relief="sunken")
        bar.pack(fill="x", side="bottom")
        self.status_var = tk.StringVar(
            value="Ready. Use the Files tab to load .sp / .obb data.")
        ttk.Label(bar, textvariable=self.status_var).pack(side="left", padx=4)

    def _on_data_change(self):
        loaded = self.data.loaded_sp_slots()
        archs = self.data.archives_loaded()
        parts = []
        if loaded:
            parts.append(f"{len(loaded)} .sp slots")
        else:
            parts.append("no .sp loaded")
        if archs:
            parts.append("archives: " + ", ".join(archs))
        self.status_var.set("  |  ".join(parts))

    # ---- menu handlers -----------------------------------------------------
    def _menu_load_sp(self):
        path = filedialog.askopenfilename(
            title="Choose a .sp scratchpad",
            filetypes=[("Scratchpad", "*.sp"), ("All", "*.*")])
        if not path:
            return
        try:
            self.data.set_archive("sp", path)
        except Exception as exc:
            messagebox.showerror("Load .sp failed", str(exc))

    def _menu_load_archive(self, kind: str):
        """Open an .obb/.apk/.jar/.jam archive via the File menu."""
        exts = {
            "obb": [("OBB", "*.obb")],
            "apk": [("APK", "*.apk")],
            "jar": [("JAR", "*.jar")],
            "jam": [("JAM manifest", "*.jam")],
        }
        path = filedialog.askopenfilename(
            title=f"Choose a .{kind} file",
            filetypes=exts.get(kind, []) + [("All", "*.*")])
        if not path:
            return
        try:
            self.data.set_archive(kind, path)
            self._on_data_change()
        except Exception as exc:
            messagebox.showerror(f"Load .{kind} failed", str(exc))

    def _menu_load_folder(self, kind: str):
        """Load a directory tree as the equivalent of an OBB/APK/JAR archive."""
        path = filedialog.askdirectory(
            title=f"Choose a folder to treat as .{kind} contents")
        if not path:
            return
        try:
            self.data.set_archive(kind, path)
            self._on_data_change()
        except Exception as exc:
            messagebox.showerror("Load folder failed", str(exc))

    def _menu_clear_all(self):
        """Reset every loaded archive / slot in FFData and refresh the tabs."""
        try:
            for kind in ("obb", "apk", "jar", "sp"):
                try:
                    self.data.clear(kind)
                except Exception:
                    pass
            self._on_data_change()
            for t in getattr(self, "tabs", []):
                fn = getattr(t, "on_data_change", None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
        except Exception as exc:
            messagebox.showerror("Clear failed", str(exc))

    def _show_about(self):
        messagebox.showinfo(
            "About",
            "Final Fantasy Dimensions / Legends — reverse-engineering toolkit.\n"
            "Pure Python 3.7+; requires Pillow.\n\n"
            "Use the Files tab (or this File menu) to load .sp scratchpads "
            "and an .obb / .apk / .jar / .jam archive, then explore via the "
            "other tabs.")
