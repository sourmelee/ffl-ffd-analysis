"""User-managed Android tileset overrides (``mc_overrides.json``).

Background: per-cell tile words in Android map chunks have a high byte
that is only ever 0x00 or 0x01 in the actual data. The original
interpretation of ``(hb<<1)|variant`` makes mc_type always 0, which
means every tile would render against ``mc0_0.png`` — wrong for the
majority of maps.

The real encoding: ``high_byte == variant`` (0 or 1) and the *primary
tileset* (mc_id) is implicit at the map level. Until that header field
is decoded, we let the user annotate maps via ``mc_overrides.json``,
which is a JSON file living next to the .obb / workspace. The toolkit
consults it before rendering. Annotation lookup is two-tiered:

  1. ``by_map["g{group}p{pack}m{map_id}"]`` — explicit per-map override
  2. ``by_group["0xXX_Y"]`` — default for that ``(chunk[18], chunk[5])``
     bucket

Both records carry ``{mc_id, variant, user_confirmed, ...}``. Either
may be missing — callers should fall back gracefully (typically to
mc0_0).
"""

from __future__ import annotations

import json as _json
import os


MC_OVERRIDES_FILENAME = "mc_overrides.json"
CPK_TO_MC_FILENAME = "cpk_to_mc.json"


def empty_mc_overrides() -> dict:
    return {
        "format_version": 1,
        "comment": ("Per-(chunk[18], chunk[5]) defaults override mc_id when "
                    "rendering Android maps. by_map entries override "
                    "by_group for that specific map."),
        "by_group": {},
        "by_map": {},
    }


def load_mc_overrides(path) -> dict:
    """Load mc_overrides.json from `path`. Returns an empty structure if the
    file does not exist or fails to parse."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if not isinstance(data, dict):
            return empty_mc_overrides()
        data.setdefault("format_version", 1)
        data.setdefault("by_group", {})
        data.setdefault("by_map", {})
        return data
    except FileNotFoundError:
        return empty_mc_overrides()
    except Exception:
        return empty_mc_overrides()


def save_mc_overrides(path, overrides: dict) -> bool:
    """Atomically save mc_overrides.json. Returns True on success."""
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(overrides, f, indent=1, ensure_ascii=False)
        os.replace(tmp, str(path))
        return True
    except Exception:
        return False


def map_key(group: int, pack: int, map_id: int) -> str:
    return f"g{group}p{pack}m{map_id}"


def bucket_key(chunk18: int, chunk5: int) -> str:
    return f"0x{chunk18:02x}_{chunk5}"


def load_cpk_to_mc(path) -> dict:
    """Load cpk_to_mc.json — a per-chapter table from the SAD matcher that
    maps mobile chapter-local cpk entry IDs to Android (mc_id, variant)
    pairs.

    Returns {chapter: {cpk_entry_id (str): {mc_id, variant, best_sad, ...}}}
    or an empty dict if the file is missing/invalid.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def invert_cpk_to_mc(cpk_to_mc: dict) -> dict:
    """Build the reverse map: (mc_id, variant) -> list of (chapter,
    cpk_entry_id, best_sad). Sorted ascending by best_sad so the most
    confident chapter wins."""
    out = {}
    for chap, entries in cpk_to_mc.items():
        for eid_str, info in entries.items():
            try:
                eid = int(eid_str)
                mc_id = int(info["mc_id"])
                var = int(info.get("variant", 0))
            except Exception:
                continue
            best_sad = info.get("best_sad", 10**9)
            out.setdefault((mc_id, var), []).append((chap, eid, best_sad))
    for key in out:
        out[key].sort(key=lambda t: t[2])
    return out


def lookup_primary_mc(overrides: dict, group: int, pack: int, map_id: int,
                      chunk18: int, chunk5: int,
                      default_mc_id: int = 0,
                      default_variant: int = 0):
    """Resolve (mc_id, variant) for an Android map. Order:
       1. by_map["g{group}p{pack}m{map_id}"]
       2. by_group["0xchunk18_chunk5"]
       3. (default_mc_id, default_variant)
    Returns (mc_id, variant, source) where source is one of
    "by_map" | "by_group" | "default" — useful for UI hints.
    """
    bm = overrides.get("by_map", {})
    bg = overrides.get("by_group", {})
    mk = map_key(group, pack, map_id)
    if mk in bm and bm[mk].get("mc_id") is not None:
        e = bm[mk]
        return int(e["mc_id"]), int(e.get("variant", 0)), "by_map"
    gk = bucket_key(chunk18, chunk5)
    if gk in bg and bg[gk].get("mc_id") is not None:
        e = bg[gk]
        return int(e["mc_id"]), int(e.get("variant", 0)), "by_group"
    return default_mc_id, default_variant, "default"
