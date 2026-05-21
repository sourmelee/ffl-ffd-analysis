"""ZIP-style container and on-disk folder loaders.

``.obb`` / ``.apk`` / ``.jar`` are real ZIPs and decode via :mod:`zipfile`.
The Android port's ``main.obb`` is a XOR-obfuscated custom container
(NOT a real ZIP); when ``ffd_obb_extractor`` is available we detect that
and decode in-memory so callers see the same flat ``{filename: bytes}``
dict regardless of source.
"""

from __future__ import annotations

import zipfile
from collections import OrderedDict
from pathlib import Path


def load_zip_container(path) -> "OrderedDict[str, bytes]":
    """
    Open an archive or folder and return {filename: bytes}.

    - Path is a directory: walk it recursively. Keys are paths relative to
      the directory (forward-slash separated).
    - Path is a ZIP-style file (.apk/.jar/...): open with zipfile.
    - Path is a Final Fantasy Dimensions .obb (XOR'd custom container, NOT
      a real ZIP): decode in-memory via ffd_obb_extractor.load_obb_as_dict
      so the returned dict matches what loading the proper_obb folder
      produces (graphics decoded to .png, audio to .ogg, text to .msd).
    - Path is some other non-ZIP file: store as a single entry under its
      basename.

    This is what every viewer expects: a flat dict of filename → raw bytes.
    """
    out = OrderedDict()
    p = Path(path)
    if p.is_dir():
        return load_folder_as_archive(p)

    # FFD .obb is NOT a ZIP - check this BEFORE trying zipfile so we don't
    # accidentally fall into the single-blob fallback when zipfile fails.
    try:
        from .obb import is_ffd_obb_path, load_obb_as_dict
        if is_ffd_obb_path(str(p)):
            return load_obb_as_dict(str(p), mode="proper")
    except ImportError:
        # ffd_obb_extractor module not present - fall through to other handlers
        pass

    # Try ZIP (handles .apk, .jar, generic .zip)
    try:
        with zipfile.ZipFile(str(p), "r") as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                try:
                    out[info.filename] = zf.read(info.filename)
                except Exception:
                    pass
        return out
    except zipfile.BadZipFile:
        pass

    # Not a ZIP and not a recognised .obb. Single-blob fallback.
    raw = p.read_bytes()
    out[p.name] = raw
    return out


def load_folder_as_archive(folder) -> "OrderedDict[str, bytes]":
    """
    Recursively walk a folder and return {relative_path: bytes}.
    Keys use forward-slash separators and are also exposed by basename
    (e.g. 'message.dat') so viewers that look up by simple filename
    succeed even when the file lives in a subdirectory.
    """
    out = OrderedDict()
    base = Path(folder)
    if not base.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    for child in sorted(base.rglob("*")):
        if not child.is_file():
            continue
        try:
            data = child.read_bytes()
        except Exception:
            continue
        rel = child.relative_to(base).as_posix()
        out[rel] = data
        # Also expose by simple basename for viewer lookups, but only if
        # not already taken (deeper-nested first wins gets overwritten by
        # shallower; this is fine because shallower is more "canonical").
        bn = child.name
        if bn not in out or rel == bn:
            out[bn] = data
    return out
