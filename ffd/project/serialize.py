"""Save/load a toolkit project to a single ``.ffdproj`` JSON file.

Two save flavours
-----------------

* **Lightweight** (``save_project(data, path, bundle=False)``):
  stores only the file paths for each SP slot and each archive (.obb /
  .apk / .jar / .jam). Tiny file, easy to diff. Breaks if any source
  file is later moved or deleted.

* **Bundle** (``save_project(data, path, bundle=True)``): also embeds
  the bytes of every referenced file (base64) so the project is
  self-contained. For directory-style sources (e.g. ``Load folder as
  Android assets``) the folder is zipped on the fly before embedding.

Path-style policy
-----------------
Each saved entry carries both ``path_rel`` (relative to the .ffdproj
file's directory, when computable) and ``path_abs`` (the original full
path). On load the resolver tries ``path_rel`` first, then ``path_abs``,
then — for bundles — falls back to extracting the embedded bytes into a
process-local temp directory so the rest of the toolkit can treat them
as ordinary files on disk.

File-format outline (JSON)::

    {
      "format": "ffdproj",
      "version": 1,
      "saved_at": "2026-05-22T20:00:00Z",
      "bundle": false,
      "sp_slots": {
        "Chapter 1": {
          "path_rel": "../Mobile/Scratchpads/Chapter1.sp",
          "path_abs": "D:/.../Chapter1.sp",
          "source_kind": "file",     // or "dir" for folder-loaded
          "content_b64": null        // only set when bundle == true
        },
        ...
      },
      "archives": {
        "obb": { ...same shape... },
        "apk": null,
        "jar": null,
        "jam": null
      }
    }

User config
-----------
``Python/.ffd_toolkit_config.json`` (next to ``ffd_toolkit.py``) holds
``last_project`` and ``recent_projects``. The GUI consults it on
startup to auto-load whatever was open last session.
"""

from __future__ import annotations

import base64
import io
import json
import os
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import __version__ as _TOOLKIT_VERSION
from ..constants import SP_SLOTS


PROJECT_FORMAT = "ffdproj"
# Wire-format version of the .ffdproj file itself. Bump only on
# breaking schema changes; `toolkit_version` (below) tracks the
# release that wrote the file and is informational only.
PROJECT_VERSION = 1
PROJECT_EXT = ".ffdproj"
CONFIG_FILENAME = ".ffd_toolkit_config.json"
RECENT_LIMIT = 8

# Archive slot kinds tracked on FFData.
_ARCHIVE_KINDS = ("obb", "apk", "jar", "jam")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _python_dir() -> Path:
    """The ``Python/`` folder containing ``ffd_toolkit.py``.

    This file lives at ``Python/ffd/project/serialize.py`` so
    ``parents[2]`` resolves to ``Python/`` regardless of the user's CWD
    or how the script was launched.
    """
    return Path(__file__).resolve().parents[2]


def config_path() -> Path:
    """Path to the per-user toolkit config (last-project + recent list)."""
    return _python_dir() / CONFIG_FILENAME


def load_config() -> Dict[str, Any]:
    """Read the toolkit config, returning ``{}`` if missing or malformed."""
    p = config_path()
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except Exception as exc:
        print(f"[ffd_toolkit] config load failed ({p}): {exc}",
              file=sys.stderr)
    return {}


def save_config(cfg: Dict[str, Any]) -> None:
    """Atomically write the toolkit config to disk."""
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, p)


def remember_project(project_path) -> None:
    """Record a project as the most-recently-opened one."""
    p_str = str(Path(project_path).resolve())
    cfg = load_config()
    cfg["last_project"] = p_str
    recents = [x for x in cfg.get("recent_projects", []) if x != p_str]
    recents.insert(0, p_str)
    cfg["recent_projects"] = recents[:RECENT_LIMIT]
    save_config(cfg)


def forget_project(project_path) -> None:
    """Remove a project from the recent list (e.g. file no longer exists)."""
    p_str = str(Path(project_path).resolve())
    cfg = load_config()
    if cfg.get("last_project") == p_str:
        cfg["last_project"] = None
    cfg["recent_projects"] = [
        x for x in cfg.get("recent_projects", []) if x != p_str
    ]
    save_config(cfg)


def get_last_project() -> Optional[str]:
    return load_config().get("last_project")


def get_recent_projects() -> List[str]:
    items = load_config().get("recent_projects", [])
    return [x for x in items if isinstance(x, str)]


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def _relpath_or_none(src: Path, base: Path) -> Optional[str]:
    """Compute a relative path string from ``base`` to ``src``.

    Returns ``None`` if the two paths sit on different drives (common on
    Windows when project lives on D: but assets on C:).
    """
    try:
        return os.path.relpath(str(src), str(base)).replace("\\", "/")
    except ValueError:
        return None


def _bundle_source(path: Path) -> Tuple[str, bytes]:
    """Read a file path or zip-a-folder for embedding in a bundle.

    Returns ``(source_kind, raw_bytes)`` where source_kind is ``"file"``
    for ordinary files and ``"dir"`` for an on-the-fly zip of a folder.
    """
    p = Path(path)
    if p.is_dir():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for child in sorted(p.rglob("*")):
                if not child.is_file():
                    continue
                rel = child.relative_to(p).as_posix()
                try:
                    zf.write(str(child), rel)
                except Exception:
                    pass
        return "dir", buf.getvalue()
    return "file", p.read_bytes()


def _make_entry(src_path, project_dir: Path, bundle: bool
                ) -> Optional[Dict[str, Any]]:
    """Build a single manifest entry for one slot/archive path.

    Returns ``None`` if ``src_path`` is empty / falsy (i.e. the slot was
    not loaded).
    """
    if not src_path:
        return None
    src = Path(src_path)
    abs_str = str(src.resolve()) if src.exists() else str(src)
    rel_str = _relpath_or_none(
        Path(abs_str), project_dir) if Path(abs_str).is_absolute() else None
    source_kind = "dir" if src.is_dir() else "file"
    entry: Dict[str, Any] = {
        "path_rel": rel_str,
        "path_abs": abs_str,
        "source_kind": source_kind,
        "content_b64": None,
    }
    if bundle:
        try:
            kind, raw = _bundle_source(src)
            entry["source_kind"] = kind
            entry["content_b64"] = base64.b64encode(raw).decode("ascii")
        except Exception as exc:
            print(f"[ffd_toolkit] could not bundle {src}: {exc}",
                  file=sys.stderr)
    return entry


def save_project(data, project_path, *, bundle: bool = False) -> Path:
    """Serialize an :class:`FFData` snapshot to ``project_path``.

    Parameters
    ----------
    data
        The live :class:`~ffd.data.ffdata.FFData` instance.
    project_path
        Destination filename. If no suffix is given, ``.ffdproj`` is
        appended.
    bundle
        If ``True``, also embed every referenced file/folder as base64
        so the resulting project is self-contained.
    """
    project_path = Path(project_path)
    if project_path.suffix == "":
        project_path = project_path.with_suffix(PROJECT_EXT)
    project_dir = project_path.resolve().parent
    project_dir.mkdir(parents=True, exist_ok=True)

    sp_entries: Dict[str, Any] = {}
    for slot in SP_SLOTS:
        path = data.sp_paths.get(slot) if hasattr(data, "sp_paths") else None
        entry = _make_entry(path, project_dir, bundle)
        if entry is not None:
            sp_entries[slot] = entry

    archives: Dict[str, Any] = {}
    for kind in _ARCHIVE_KINDS:
        path = getattr(data, f"{kind}_path", None)
        archives[kind] = _make_entry(path, project_dir, bundle)

    manifest = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        # toolkit_version is informational — it lets us read a project
        # file later and know exactly which toolkit release wrote it,
        # which is invaluable for bug reports and for planning future
        # schema migrations. The loader does NOT gate on this field.
        "toolkit_version": _TOOLKIT_VERSION,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "bundle": bool(bundle),
        "sp_slots": sp_entries,
        "archives": archives,
    }

    tmp = project_path.with_suffix(project_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    os.replace(tmp, project_path)
    remember_project(project_path)
    return project_path


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

@dataclass
class ProjectLoadResult:
    """Outcome of applying a project file. Mainly used for status reporting.

    ``temp_dir`` is set when the project was a bundle and bytes had to
    be materialized to disk. The caller owns it and should remove it on
    app shutdown (or when loading a new project) via
    :func:`cleanup_bundle_temp_dir`.
    """
    project_path: Path
    bundle: bool = False
    loaded_sp: List[str] = field(default_factory=list)
    loaded_archives: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    temp_dir: Optional[Path] = None


def cleanup_bundle_temp_dir(temp_dir) -> None:
    """Best-effort recursive removal of a bundle-extraction temp dir.

    Silently swallows errors — this runs from shutdown handlers where
    raising would prevent the toolkit from closing cleanly.
    """
    if not temp_dir:
        return
    import shutil
    try:
        shutil.rmtree(str(temp_dir), ignore_errors=True)
    except Exception as exc:
        print(f"[ffd_toolkit] failed to clean bundle temp dir "
              f"{temp_dir}: {exc}", file=sys.stderr)


def load_project(project_path) -> Dict[str, Any]:
    """Read a ``.ffdproj`` file and return the parsed manifest dict."""
    p = Path(project_path)
    with p.open("r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    if not isinstance(manifest, dict) or manifest.get("format") != PROJECT_FORMAT:
        raise ValueError(f"{p}: not a {PROJECT_FORMAT} file")
    version = manifest.get("version")
    if not isinstance(version, int) or version > PROJECT_VERSION:
        raise ValueError(
            f"{p}: unsupported project version {version!r} "
            f"(this toolkit supports up to v{PROJECT_VERSION})")
    return manifest


def _resolve_entry(entry: Dict[str, Any], project_dir: Path,
                   tmp_root: Optional[Path]) -> Tuple[Optional[Path], str]:
    """Resolve a manifest entry to a usable on-disk path.

    Returns ``(path, source)`` where ``source`` is one of ``"rel"``,
    ``"abs"``, ``"bundled"``, or ``"missing"``. ``path`` is ``None`` only
    when the entry could not be resolved at all.

    The "prefer relative" policy: try the relative path first (so a
    project file that moves with its assets still works), then the
    absolute path (good when the user reorganises the project folder
    but the asset itself stayed put), then the bundled bytes.
    """
    rel = entry.get("path_rel")
    abs_ = entry.get("path_abs")
    if rel:
        candidate = (project_dir / rel).resolve()
        if candidate.exists():
            return candidate, "rel"
    if abs_:
        candidate = Path(abs_)
        if candidate.exists():
            return candidate, "abs"
    blob_b64 = entry.get("content_b64")
    if blob_b64 and tmp_root is not None:
        try:
            raw = base64.b64decode(blob_b64)
        except Exception:
            return None, "missing"
        kind = entry.get("source_kind", "file")
        # Pick a stable temp name based on the original basename so the
        # extension is preserved (load_zip_container sniffs by extension
        # for .obb XOR detection, etc.).
        basename = "asset"
        for cand in (rel, abs_):
            if cand:
                basename = Path(cand).name
                break
        tmp_root.mkdir(parents=True, exist_ok=True)
        if kind == "dir":
            target = tmp_root / (basename + "_dir")
            target.mkdir(parents=True, exist_ok=True)
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    zf.extractall(target)
            except Exception:
                return None, "missing"
            return target, "bundled"
        else:
            target = tmp_root / basename
            target.write_bytes(raw)
            return target, "bundled"
    return None, "missing"


def apply_project(data, manifest: Dict[str, Any], project_path
                  ) -> ProjectLoadResult:
    """Apply a parsed ``manifest`` to a live :class:`FFData`.

    This first clears every archive slot and SP slot on ``data`` so the
    application's state matches the project file exactly (rather than
    being a merge of whatever was previously loaded).
    """
    project_path = Path(project_path).resolve()
    project_dir = project_path.parent
    result = ProjectLoadResult(
        project_path=project_path,
        bundle=bool(manifest.get("bundle", False)),
    )

    # Per-process temp dir for any bundled bytes we may need to materialize.
    # Recorded on the result so the caller can clean it up at shutdown.
    tmp_root: Optional[Path] = None
    if result.bundle:
        tmp_root = Path(tempfile.mkdtemp(prefix="ffd_proj_"))
        result.temp_dir = tmp_root

    # Clear current state up front so the post-condition is "data matches
    # the project file" rather than a merge.
    for kind in _ARCHIVE_KINDS:
        try:
            data.clear_archive(kind)
        except Exception:
            pass
    if hasattr(data, "sp_slots"):
        for slot in list(data.sp_slots):
            try:
                if data.sp_slots.get(slot) is not None:
                    data.clear_sp(slot)
            except Exception:
                pass

    # ---- SP slots --------------------------------------------------------
    sp_entries = manifest.get("sp_slots") or {}
    if isinstance(sp_entries, dict):
        for slot, entry in sp_entries.items():
            if slot not in SP_SLOTS:
                result.warnings.append(
                    f"Ignored unknown SP slot {slot!r} in project file.")
                continue
            if not isinstance(entry, dict):
                continue
            path, source = _resolve_entry(entry, project_dir, tmp_root)
            if path is None:
                result.warnings.append(
                    f"SP slot {slot!r}: could not locate source file "
                    f"(tried path_rel, path_abs, bundled).")
                continue
            try:
                data.set_sp(slot, str(path))
                result.loaded_sp.append(slot)
            except Exception as exc:
                result.warnings.append(
                    f"SP slot {slot!r}: load failed ({type(exc).__name__}: "
                    f"{exc}). Path tried: {path}.")

    # ---- Archives --------------------------------------------------------
    archives = manifest.get("archives") or {}
    if isinstance(archives, dict):
        for kind in _ARCHIVE_KINDS:
            entry = archives.get(kind)
            if not entry:
                continue
            path, source = _resolve_entry(entry, project_dir, tmp_root)
            if path is None:
                result.warnings.append(
                    f"{kind.upper()} archive: could not locate source file "
                    f"(tried path_rel, path_abs, bundled).")
                continue
            try:
                data.set_archive(kind, str(path))
                result.loaded_archives.append(kind)
            except Exception as exc:
                result.warnings.append(
                    f"{kind.upper()} archive: load failed "
                    f"({type(exc).__name__}: {exc}). Path tried: {path}.")

    remember_project(project_path)
    return result
