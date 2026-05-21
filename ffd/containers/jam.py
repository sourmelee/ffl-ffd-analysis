"""DoCoMo ``.jam`` (JAD-like) manifest reader.

``.jam`` files are NOT archives — they're plain-text manifests that
describe the companion ``.jar`` (class names, sizes, MIDlet metadata).
We expose the raw bytes plus a best-effort UTF-8-decoded view so the
user can inspect them in the GUI.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path


def load_jam_manifest(path) -> "OrderedDict[str, bytes]":
    """
    DoCoMo .jam files are NOT archives — they're plain-text JAD-like
    manifests describing the JAR (class names, sizes, MIDlet metadata).
    We just expose the raw bytes under a single key so the user can
    inspect them.
    """
    p = Path(path)
    raw = p.read_bytes()
    out = OrderedDict()
    out[p.name] = raw
    # Best-effort decoded text view as a separate entry
    for enc in ("utf-8", "shift-jis", "latin-1"):
        try:
            out["_manifest.txt"] = raw.decode(enc).encode("utf-8")
            break
        except Exception:
            continue
    return out
