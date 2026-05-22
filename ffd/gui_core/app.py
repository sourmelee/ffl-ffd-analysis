"""Top-level Tk application -- notebook of all tabs + status bar + menu."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from .. import __version__
from ..gui_stub import tk, ttk, filedialog, messagebox
from ..data.ffdata import FFData
from ..project import (
    PROJECT_EXT,
    apply_project,
    cleanup_bundle_temp_dir,
    forget_project,
    get_last_project,
    get_recent_projects,
    load_project,
    save_project,
)

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
        self.title(f"FFD/FFL Toolkit v{__version__} -- Reverse-Engineering GUI")
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
        # Current project file (set by Load Project / Save Project so
        # subsequent saves can default to it). None means "unsaved".
        self._current_project_path: Path | None = None
        # Holds the dynamic Recent Projects submenu so the open-handler
        # can rebuild it after a save/load mutates the recent list.
        self._recent_menu: tk.Menu | None = None
        # Temp dir where bundle bytes are extracted when a .ffdproj bundle
        # is loaded. Tracked so we can wipe it on shutdown / next load.
        self._bundle_temp_dir: Path | None = None
        self._build_menu()
        self._build_notebook()
        self._build_status()
        # Intercept the window-close (X button) so we can clean up the
        # bundle temp dir before tearing the app down. The Quit menu
        # also goes through this code path via _on_close.
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Schedule auto-load *after* the mainloop is up so any error
        # dialogs render properly (filedialog/messagebox need an event
        # loop). `after_idle` runs as soon as the GUI is interactive.
        self.after_idle(self._maybe_auto_load_last_project)

    def _build_menu(self):
        bar = tk.Menu(self)
        m_file = tk.Menu(bar, tearoff=False)
        # ---- Project (save/load whole workspace) ------------------------
        m_file.add_command(label="Save Project...",
                           accelerator="Ctrl+S",
                           command=lambda: self._menu_save_project(bundle=False))
        m_file.add_command(label="Save Project Bundle (embed files)...",
                           command=lambda: self._menu_save_project(bundle=True))
        m_file.add_command(label="Load Project...",
                           accelerator="Ctrl+O",
                           command=self._menu_load_project)
        self._recent_menu = tk.Menu(m_file, tearoff=False)
        m_file.add_cascade(label="Recent Projects", menu=self._recent_menu)
        self._rebuild_recent_menu()
        # Keyboard accelerators for the two most-used actions.
        self.bind_all("<Control-s>",
                      lambda _e: self._menu_save_project(bundle=False))
        self.bind_all("<Control-o>", lambda _e: self._menu_load_project())
        m_file.add_separator()
        # ---- Per-file loading (unchanged) -------------------------------
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
        m_file.add_command(label="Quit", command=self._on_close)
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

    # ---- Project save / load ------------------------------------------
    def _menu_save_project(self, *, bundle: bool = False):
        """Prompt for a destination and write a .ffdproj snapshot."""
        if not self.data.has_anything():
            messagebox.showinfo(
                "Nothing to save",
                "No files are currently loaded — load some assets first, "
                "then save the project.")
            return
        title = "Save Project Bundle" if bundle else "Save Project"
        initialdir = None
        initialfile = None
        if self._current_project_path is not None:
            initialdir = str(self._current_project_path.parent)
            initialfile = self._current_project_path.name
        path = filedialog.asksaveasfilename(
            title=title,
            defaultextension=PROJECT_EXT,
            filetypes=[("FFD Toolkit project", "*" + PROJECT_EXT), ("All", "*.*")],
            initialdir=initialdir,
            initialfile=initialfile,
        )
        if not path:
            return
        try:
            written = save_project(self.data, path, bundle=bundle)
        except Exception as exc:
            messagebox.showerror("Save project failed",
                                 f"{type(exc).__name__}: {exc}")
            return
        self._current_project_path = Path(written)
        self._rebuild_recent_menu()
        self.status_var.set(
            f"Saved {'bundle ' if bundle else ''}project to {written}")

    def _menu_load_project(self, path: str | None = None):
        """Open a .ffdproj file (prompting if `path` is None) and apply it."""
        if path is None:
            path = filedialog.askopenfilename(
                title="Load Project",
                filetypes=[("FFD Toolkit project", "*" + PROJECT_EXT),
                           ("All", "*.*")],
            )
        if not path:
            return
        try:
            manifest = load_project(path)
        except FileNotFoundError:
            messagebox.showerror("Load project failed",
                                 f"File not found: {path}")
            forget_project(path)
            self._rebuild_recent_menu()
            return
        except Exception as exc:
            messagebox.showerror("Load project failed",
                                 f"{type(exc).__name__}: {exc}")
            return
        # Wipe any bundle temp dir from a previous load before applying
        # — otherwise long-running sessions that keep switching projects
        # would leak one mkdtemp per Load Project.
        cleanup_bundle_temp_dir(self._bundle_temp_dir)
        self._bundle_temp_dir = None
        try:
            result = apply_project(self.data, manifest, path)
        except Exception as exc:
            messagebox.showerror("Load project failed",
                                 f"{type(exc).__name__}: {exc}")
            return
        self._current_project_path = result.project_path
        self._bundle_temp_dir = result.temp_dir
        self._rebuild_recent_menu()
        # Refresh every tab so views populated from the now-loaded data
        # render their content (the FFData listener notification fires
        # per set_archive call, but some tabs only rebuild lazily).
        for t in getattr(self, "tabs", []):
            fn = getattr(t, "on_data_change", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        if result.warnings:
            # Surface non-fatal load problems but keep the toolkit usable
            # — the user can still work with whatever did load.
            messagebox.showwarning(
                "Loaded with warnings",
                "Project loaded, but some entries could not be applied:\n\n"
                + "\n".join(f"• {w}" for w in result.warnings))
        n_sp = len(result.loaded_sp)
        n_ar = len(result.loaded_archives)
        suffix = " (bundled)" if result.bundle else ""
        self.status_var.set(
            f"Loaded project{suffix}: {n_sp} SP slot(s), {n_ar} archive(s)"
            + (f", {len(result.warnings)} warning(s)" if result.warnings else "")
        )

    def _rebuild_recent_menu(self):
        """Repopulate the Recent Projects submenu from the user config."""
        if self._recent_menu is None:
            return
        self._recent_menu.delete(0, "end")
        recents = get_recent_projects()
        if not recents:
            self._recent_menu.add_command(label="(no recent projects)",
                                          state="disabled")
            return
        for path in recents:
            label = self._abbreviate_path(path)
            self._recent_menu.add_command(
                label=label,
                command=lambda p=path: self._menu_load_project(p))
        self._recent_menu.add_separator()
        self._recent_menu.add_command(label="Clear list",
                                      command=self._menu_clear_recent)

    def _menu_clear_recent(self):
        for p in get_recent_projects():
            forget_project(p)
        self._rebuild_recent_menu()

    @staticmethod
    def _abbreviate_path(path: str, width: int = 60) -> str:
        """Shorten a long path for display in the Recent menu."""
        if len(path) <= width:
            return path
        # Keep the drive/root and the filename, ellipsize the middle.
        p = Path(path)
        head = str(p.anchor or p.parents[-1] if p.parents else "")
        tail = "/".join(p.parts[-2:])
        return f"{head}...{tail}" if head else "..." + tail

    def _maybe_auto_load_last_project(self):
        """On startup, try to reopen whatever project was open last time."""
        last = get_last_project()
        if not last:
            return
        if not Path(last).exists():
            # File moved or deleted — drop it from the recent list silently
            # so we don't nag the user every time they start the toolkit.
            forget_project(last)
            self._rebuild_recent_menu()
            return
        try:
            manifest = load_project(last)
            result = apply_project(self.data, manifest, last)
        except Exception as exc:
            # Auto-load should never block startup. Surface the failure
            # in the status bar and the terminal but let the user keep going.
            print(f"[ffd_toolkit] auto-load of {last} failed: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr)
            self.status_var.set(
                f"Auto-load of last project failed: {type(exc).__name__}: {exc}")
            return
        self._current_project_path = result.project_path
        # Track the bundle temp dir (if any) so _on_close can wipe it.
        self._bundle_temp_dir = result.temp_dir
        for t in getattr(self, "tabs", []):
            fn = getattr(t, "on_data_change", None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        n_sp = len(result.loaded_sp)
        n_ar = len(result.loaded_archives)
        suffix = " (bundled)" if result.bundle else ""
        self.status_var.set(
            f"Auto-loaded last project{suffix}: {n_sp} SP slot(s), "
            f"{n_ar} archive(s)"
            + (f", {len(result.warnings)} warning(s)" if result.warnings else "")
        )

    def _on_close(self):
        """Shutdown handler: clean up bundle temp dirs, then destroy the window.

        Invoked from both the File > Quit menu and the window-manager
        close button (WM_DELETE_WINDOW protocol). Cleanup must be
        best-effort — if `rmtree` fails for any reason we still need
        the window to close.
        """
        try:
            cleanup_bundle_temp_dir(self._bundle_temp_dir)
        finally:
            self._bundle_temp_dir = None
            self.destroy()

    def _show_about(self):
        messagebox.showinfo(
            "About",
            f"FFD/FFL Toolkit v{__version__}\n"
            "Final Fantasy Dimensions / Legends -- reverse-engineering toolkit.\n"
            "Pure Python 3.7+; requires Pillow.\n\n"
            "Use the Files tab (or this File menu) to load .sp scratchpads "
            "and an .obb / .apk / .jar / .jam archive, then explore via the "
            "other tabs.")
