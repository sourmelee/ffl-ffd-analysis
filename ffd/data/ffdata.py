"""Central :class:`FFData` model.

Holds raw bytes from .sp / .obb / .apk / .jar / .jam sources and
exposes lookup helpers used by every viewer tab. Listeners get
notified whenever a slot changes so tabs can refresh.
"""

from __future__ import annotations

import traceback
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from ..constants import SP_SLOTS
from ..containers import parse_sp, load_zip_container, load_jam_manifest
from ..maps.mc_overrides import (
    MC_OVERRIDES_FILENAME,
    CPK_TO_MC_FILENAME,
    load_mc_overrides,
    save_mc_overrides,
    load_cpk_to_mc,
    invert_cpk_to_mc,
)


class FFData:
    """
    Central data store. Holds raw bytes from .sp / .obb / .apk / .jar / .jam
    sources and exposes lookup helpers used by every viewer tab.
    """

    def __init__(self):
        # slot_label -> OrderedDict[filename, bytes]   (or None if not loaded)
        self.sp_slots = OrderedDict((label, None) for label in SP_SLOTS)
        self.sp_paths = OrderedDict((label, None) for label in SP_SLOTS)

        # path strings for the container archives
        self.obb_path = None
        self.apk_path = None
        self.jar_path = None
        self.jam_path = None

        # archive contents (filename -> bytes)
        self.obb_files: Optional[OrderedDict] = None
        self.apk_files: Optional[OrderedDict] = None
        self.jar_files: Optional[OrderedDict] = None
        self.jam_files: Optional[OrderedDict] = None

        # Android tileset overrides (loaded lazily from the same folder as
        # the .obb, or the workspace folder if no .obb is loaded yet).
        self._mc_overrides_cache = None
        self._mc_overrides_path_cache = None

        # change-listeners (called with no args)
        self._listeners = []

    # ---- mc_overrides -----------------------------------------------------
    def mc_overrides_path(self):
        """Resolve where mc_overrides.json lives. Preference order:
          1. Next to any loaded archive (where the user originally created it)
          2. The PROJECT ROOT (one level up — this is where the toolkit's
             seed_mc_overrides_from_engine script writes it, and where
             cross-chapter project-scoped JSONs typically belong)
          3. The current working directory
        Returns the first existing path, or candidate-0 as default."""
        candidates = []
        for p in (self.obb_path, self.apk_path, self.jar_path, self.jam_path):
            if not p:
                continue
            try:
                parent = Path(p).resolve().parent
            except Exception:
                continue
            candidates.append(parent / MC_OVERRIDES_FILENAME)
            candidates.append(parent.parent / MC_OVERRIDES_FILENAME)
        candidates.append(Path.cwd() / MC_OVERRIDES_FILENAME)
        for c in candidates:
            if c.exists():
                return c
        return candidates[0] if candidates else (
            Path.cwd() / MC_OVERRIDES_FILENAME)

    def mc_overrides(self, reload: bool = False):
        """Return the cached mc_overrides dict, loading lazily from disk."""
        path = self.mc_overrides_path()
        if (reload or self._mc_overrides_cache is None
                or str(path) != self._mc_overrides_path_cache):
            self._mc_overrides_cache = load_mc_overrides(path)
            self._mc_overrides_path_cache = str(path)
        return self._mc_overrides_cache

    def save_mc_overrides(self) -> bool:
        """Persist the cached overrides to disk. Returns True on success."""
        if self._mc_overrides_cache is None:
            return False
        return save_mc_overrides(self.mc_overrides_path(),
                                 self._mc_overrides_cache)

    # ---- cpk_to_mc translation table --------------------------------------
    def cpk_to_mc_path(self):
        """Where cpk_to_mc.json lives.

        Searches multiple candidate locations:
          1. Next to the loaded .obb / .apk / .jar / .jam
          2. The PROJECT ROOT (one level above any of those archives) — this
             is where the JSON typically lives because the table covers
             cross-chapter matches and conceptually belongs at the project
             scope, not nested under Android/.
          3. The current working directory.
        Returns the first candidate that actually exists, or the cwd path
        as a last-resort default (so write paths still work for a fresh
        save).
        """
        candidates = []
        for p in (self.obb_path, self.apk_path, self.jar_path, self.jam_path):
            if not p:
                continue
            try:
                parent = Path(p).resolve().parent
            except Exception:
                continue
            candidates.append(parent / CPK_TO_MC_FILENAME)
            candidates.append(parent.parent / CPK_TO_MC_FILENAME)
        candidates.append(Path.cwd() / CPK_TO_MC_FILENAME)
        for c in candidates:
            if c.exists():
                return c
        return candidates[0] if candidates else Path.cwd() / CPK_TO_MC_FILENAME

    def cpk_to_mc(self):
        """Lazy-loaded cpk_to_mc dict (chapter -> {cpk_entry_id: info})."""
        cache = getattr(self, "_cpk_to_mc_cache", None)
        if cache is None:
            path = self.cpk_to_mc_path()
            self._cpk_to_mc_cache = load_cpk_to_mc(path)
            if self._cpk_to_mc_cache:
                print(f"[ffd_toolkit] loaded cpk_to_mc.json from {path}  "
                      f"({len(self._cpk_to_mc_cache)} chapters)")
            else:
                print(f"[ffd_toolkit] cpk_to_mc.json not found — checked "
                      f"path: {path}")
        return self._cpk_to_mc_cache

    def cpk_to_mc_inverse(self):
        """Reverse lookup: (mc_id, variant) -> list of (chapter, cpk_id, sad)."""
        cache = getattr(self, "_cpk_to_mc_inv_cache", None)
        if cache is None:
            self._cpk_to_mc_inv_cache = invert_cpk_to_mc(self.cpk_to_mc())
        return self._cpk_to_mc_inv_cache

    # ---- slot management --------------------------------------------------
    def set_sp(self, slot_label: str, path):
        files = parse_sp(path)
        self.sp_slots[slot_label] = files
        self.sp_paths[slot_label] = path
        self._notify()

    def clear_sp(self, slot_label: str):
        self.sp_slots[slot_label] = None
        self.sp_paths[slot_label] = None
        self._notify()

    def set_archive(self, kind: str, path):
        # JAM is a manifest, not an archive
        if kind == "jam":
            files = load_jam_manifest(path)
        else:
            files = load_zip_container(path)
        if kind == "obb":
            self.obb_files = files; self.obb_path = path
        elif kind == "apk":
            self.apk_files = files; self.apk_path = path
        elif kind == "jar":
            self.jar_files = files; self.jar_path = path
        elif kind == "jam":
            self.jam_files = files; self.jam_path = path
        self._invalidate_aux_caches()
        self._notify()

    def clear_archive(self, kind: str):
        if kind == "obb": self.obb_files = None; self.obb_path = None
        elif kind == "apk": self.apk_files = None; self.apk_path = None
        elif kind == "jar": self.jar_files = None; self.jar_path = None
        elif kind == "jam": self.jam_files = None; self.jam_path = None
        self._invalidate_aux_caches()
        self._notify()

    def _invalidate_aux_caches(self):
        """Drop caches that point at sidecar JSONs (mc_overrides, cpk_to_mc)
        so they'll reload from the new archive's neighbor next time."""
        self._mc_overrides_cache = None
        self._mc_overrides_path_cache = None
        if hasattr(self, "_cpk_to_mc_cache"):
            self._cpk_to_mc_cache = None
        if hasattr(self, "_cpk_to_mc_inv_cache"):
            self._cpk_to_mc_inv_cache = None

    def clear(self, kind: str):
        """Compatibility shim — the GUI's File -> Clear all menu calls
        ``self.data.clear(kind)``. Dispatches to ``clear_archive`` for
        archive kinds and to ``clear_sp`` for every loaded scratchpad
        slot when ``kind == "sp"``."""
        if kind == "sp":
            for label in list(self.sp_slots):
                if self.sp_slots.get(label) is not None:
                    self.clear_sp(label)
        else:
            self.clear_archive(kind)

    # ---- listeners --------------------------------------------------------
    def add_listener(self, cb):
        self._listeners.append(cb)

    def _notify(self):
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:
                traceback.print_exc()

    # ---- queries ----------------------------------------------------------
    def loaded_sp_slots(self):
        return [s for s in SP_SLOTS if self.sp_slots.get(s) is not None]

    def missing_sp_slots(self):
        return [s for s in SP_SLOTS if self.sp_slots.get(s) is None]

    def find_in_sp(self, filename: str):
        """Return (slot_label, bytes) for the first .sp containing filename."""
        for label, files in self.sp_slots.items():
            if files and filename in files:
                return label, files[filename]
        return None, None

    def find_in_sp_any_chapter(self, filename: str):
        """Yield (slot_label, bytes) for every .sp containing filename."""
        for label, files in self.sp_slots.items():
            if files and filename in files:
                yield label, files[filename]

    def in_obb(self, filename: str):
        if self.obb_files and filename in self.obb_files:
            return self.obb_files[filename]
        return None

    def list_obb_pngs(self, prefix: str):
        if not self.obb_files:
            return []
        return sorted(n for n in self.obb_files
                      if n.endswith(".png") and Path(n).name.startswith(prefix))

    def boot_data_mobile(self):
        """Pick a boot_data.dat from any loaded .sp slot."""
        for files in self.sp_slots.values():
            if files and "boot_data.dat" in files:
                return files["boot_data.dat"]
        return None

    def boot_data_android(self):
        if self.obb_files and "boot_data.dat" in self.obb_files:
            return self.obb_files["boot_data.dat"]
        # Android boot_data.dat is sometimes inside the APK assets/ tree
        if self.apk_files:
            for k, v in self.apk_files.items():
                if k.endswith("boot_data.dat"):
                    return v
        return None

    def has_anything(self):
        return (any(self.sp_slots.values())
                or self.obb_files or self.apk_files
                or self.jar_files or self.jam_files)

    def archives_loaded(self):
        out = []
        if self.obb_files: out.append("obb")
        if self.apk_files: out.append("apk")
        if self.jar_files: out.append("jar")
        if self.jam_files: out.append("jam")
        return out

    def list_obb_all(self):
        if not self.obb_files:
            return []
        return sorted(self.obb_files.items(), key=lambda kv: kv[0].lower())
