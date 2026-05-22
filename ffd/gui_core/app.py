"""Top-level Tk application -- notebook of all tabs + status bar + menu."""

from __future__ import annotations

import sys
import traceback

from ..gui_stub import tk, ttk, filedialog, messagebox
from ..data.ffdata import FFData

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
from ..comparison.tab import ComparisonTab
from ..maps.annotation_tab import MapAnnotationTab


class FFDApp(tk.Tk):
    """Top-level Tk application: notebook of all tabs + status bar + menu."""

    TAB_ORDER = [
        FilesTab, ExtractTab, MapTab, MapAnnotationTab, EventScriptTab,
        TextTab, CharacterTab, AnimationTab, TilesetTab, BackgroundTab,
        BattleEffectTab, MonsterTab, MusicTab, AbilityTab, ItemTab, JobTab,
        CrossRefTab, ComparisonTab,
    ]

    def __init__(self):
        super().__init__()
        self.title("FFD/FFL Toolkit -- Reverse-Engineering GUI")
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

    def _build_menu(self):
        bar = tk.Menu(self)
        m_file = tk.Menu(bar, tearoff=False)
        m_file.add_command(label="Load .sp into slot...", command=self._menu_load_sp)
        m_file.add_separator()
        m_file.add_command(label="Load .obb...",  command=lambda: self._menu_load_archive("obb"))
        m_file.add_command(label="Load .apk...",  command=lambda: self._menu_load_archive("apk"))
        m_file.add_command(label="Load .jar...",  command=lambda: self._menu_load_archive("jar"))
        m_file.add_command(label="Load .jam (manifest)...",
                           command=lambda: self._menu_load_archive("jam"))
        m_file.add_separator()
        m_file.add_command(label="Load folder as Android assets (.obb-equivalent)...",
                           command=lambda: self._menu_load_folder("obb"))
        m_file.add_command(label="Load folder as APK contents...",
                           command=lambda: self._menu_load_folder("apk"))
        m_file.add_command(label="Load folder as JAR contents...",
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

    def _build_notebook(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        self.tabs = []
        for cls in self.TAB_ORDER:
            label = getattr(cls, "LABEL", cls.__name__)
            try:
                frame = ttk.Frame(nb)
                tab = cls(frame, self) if cls is MapAnnotationTab else cls(frame, self.data)
                tab.pack(fill="both", expand=True)
                nb.add(frame, text=label)
                self.tabs.append(tab)
            except Exception as exc:
                print("\n[FFDApp] FAILED to build %s: %s: %s" % (
                    cls.__name__, type(exc).__name__, exc), file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                try:
                    frame = ttk.Frame(nb)
                    ttk.Label(
                        frame,
                        text=("%s failed to load.\n\n%s: %s\n\n"
                              "See the terminal for the full traceback." %
                              (cls.__name__, type(exc).__name__, exc)),
                        foreground="#a00", justify="left", padding=12,
                    ).pack(anchor="nw")
                    nb.add(frame, text="! " + label)
                except Exception:
                    pass

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
            parts.append("%d .sp slots" % len(loaded))
        else:
            parts.append("no .sp loaded")
        if archs:
            parts.append("archives: " + ", ".join(archs))
        self.status_var.set("  |  ".join(parts))

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

    def _menu_load_archive(self, kind):
        exts = {
            "obb": [("OBB", "*.obb")],
            "apk": [("APK", "*.apk")],
            "jar": [("JAR", "*.jar")],
            "jam": [("JAM manifest", "*.jam")],
        }
        path = filedialog.askopenfilename(
            title="Choose a ." + kind + " file",
            filetypes=exts.get(kind, []) + [("All", "*.*")])
        if not path:
            return
        try:
            self.data.set_archive(kind, path)
            self._on_data_change()
        except Exception as exc:
            messagebox.showerror("Load ." + kind + " failed", str(exc))

    def _menu_load_folder(self, kind):
        path = filedialog.askdirectory(
            title="Choose a folder to treat as ." + kind + " contents")
        if not path:
            return
        try:
            self.data.set_archive(kind, path)
            self._on_data_change()
        except Exception as exc:
            messagebox.showerror("Load folder failed", str(exc))

    def _menu_clear_all(self):
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
            "Final Fantasy Dimensions / Legends -- reverse-engineering toolkit.\n"
            "Pure Python 3.7+; requires Pillow.\n\n"
            "Use the Files tab (or this File menu) to load .sp scratchpads "
            "and an .obb / .apk / .jar / .jam archive, then explore via the "
            "other tabs.")
