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
CPK_TO_MC_OVERRIDES_FILENAME = "cpk_to_mc_overrides.json"
CUSTOM_PALETTES_FILENAME = "custom_palettes.json"


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


def invert_cpk_to_mc(cpk_to_mc: dict, overrides: dict = None) -> dict:
    """Build the reverse map: (mc_id, variant) -> list of (chapter,
    cpk_entry_id, best_sad). Sorted ascending by best_sad so the most
    confident chapter wins.

    When ``overrides`` is supplied (a ``cpk_to_mc_overrides.json``
    dict), each override entry is also pushed into the inverse map
    with ``best_sad = 0`` so it sorts FIRST — manual overrides win
    over SAD-matched candidates. Handles both top-level overrides
    (``{mc_id, variant}``) and per-palette overrides
    (``by_palette[N] = {mc_id, variant}``); both contribute reverse
    entries since either palette choice still maps the cpk to the
    same Mobile sheet."""
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

    # Overlay manual overrides with sad=0 so they sort first.
    if overrides and isinstance(overrides, dict):
        for chap, chap_entries in (overrides.get("entries") or {}).items():
            if not isinstance(chap_entries, dict):
                continue
            for eid_str, rec in chap_entries.items():
                if not isinstance(rec, dict):
                    continue
                try:
                    eid = int(eid_str)
                except (TypeError, ValueError):
                    continue
                # Top-level override
                if "mc_id" in rec:
                    try:
                        mc_id = int(rec["mc_id"])
                        var = int(rec.get("variant", 0))
                        out.setdefault((mc_id, var), []).insert(
                            0, (chap, eid, 0))
                    except (TypeError, ValueError):
                        pass
                # Per-palette overrides also contribute reverse entries
                for pal_rec in (rec.get("by_palette") or {}).values():
                    if not isinstance(pal_rec, dict) or "mc_id" not in pal_rec:
                        continue
                    try:
                        mc_id = int(pal_rec["mc_id"])
                        var = int(pal_rec.get("variant", 0))
                        out.setdefault((mc_id, var), []).insert(
                            0, (chap, eid, 0))
                    except (TypeError, ValueError):
                        pass

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


# ---------------------------------------------------------------------------
# cpk_to_mc_overrides.json — manual user overrides that take precedence
# over the SAD-matcher-generated cpk_to_mc.json.
# ---------------------------------------------------------------------------

def empty_cpk_to_mc_overrides() -> dict:
    """Return a fresh empty overrides structure.

    Format: ``{chapter_str: {cpk_entry_str: {mc_id, variant, palette?}}}``
    where ``palette`` is optional and pins the override to a specific
    Mobile palette. When absent, the override applies regardless of
    palette."""
    return {
        "format_version": 1,
        "comment": ("Manual user overrides for cpk -> mc auto-match. "
                    "Takes precedence over cpk_to_mc.json. Edit via "
                    "the GUI's Save override button or by hand."),
        "entries": {},
    }


def load_cpk_to_mc_overrides(path) -> dict:
    """Load cpk_to_mc_overrides.json from ``path``. Returns an empty
    structure if the file does not exist or fails to parse."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if not isinstance(data, dict):
            return empty_cpk_to_mc_overrides()
        data.setdefault("format_version", 1)
        data.setdefault("entries", {})
        return data
    except FileNotFoundError:
        return empty_cpk_to_mc_overrides()
    except Exception:
        return empty_cpk_to_mc_overrides()


def save_cpk_to_mc_overrides(path, overrides: dict) -> bool:
    """Atomically save the overrides file. Returns True on success."""
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(overrides, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(path))
        return True
    except Exception:
        return False


def set_cpk_to_mc_override(overrides: dict, chapter: str, cpk_entry: int,
                            mc_id: int, variant: int,
                            palette: int = None) -> None:
    """Mutate ``overrides`` to set the entry.

    Chapter labels are normalised to dense form on store so 'Chapter 5'
    and 'Chapter5' share the same entry. Palette-specific writes
    (``palette`` is not None) only update ``by_palette[N]`` and do NOT
    touch the overall ``mc_id/variant``."""
    entries = overrides.setdefault("entries", {})
    chap_key = str(chapter).replace(" ", "")
    chap = entries.setdefault(chap_key, {})
    key = str(cpk_entry)
    rec = chap.get(key) or {}
    if palette is None:
        rec["mc_id"] = int(mc_id)
        rec["variant"] = int(variant)
    else:
        by_pal = rec.setdefault("by_palette", {})
        by_pal[str(palette)] = {"mc_id": int(mc_id), "variant": int(variant)}
    chap[key] = rec


def lookup_cpk_to_mc_override(overrides: dict, chapter: str,
                               cpk_entry: int,
                               palette: int = None):
    """Return ``(mc_id, variant, source)`` if the overrides table has a
    matching entry, else ``(None, None, None)``. Tries chapter literally
    AND the dense (space-stripped) form so 'Chapter 5' finds 'Chapter5'.
    ``source`` is one of ``"override_palette" | "override_chapter"``."""
    if not isinstance(overrides, dict):
        return (None, None, None)
    entries = overrides.get("entries") or {}
    if not chapter:
        return (None, None, None)
    keys = [chapter, str(chapter).replace(" ", "")]
    eid_str = str(cpk_entry)
    for k in keys:
        chap_entries = entries.get(k) or {}
        rec = chap_entries.get(eid_str)
        if not rec:
            continue
        if palette is not None:
            by_pal = rec.get("by_palette") or {}
            pal_rec = by_pal.get(str(palette))
            if pal_rec and "mc_id" in pal_rec:
                return (int(pal_rec["mc_id"]),
                        int(pal_rec.get("variant", 0)),
                        "override_palette")
        if "mc_id" in rec:
            return (int(rec["mc_id"]),
                    int(rec.get("variant", 0)),
                    "override_chapter")
    return (None, None, None)


# ---------------------------------------------------------------------------
# custom_palettes.json — hand-built Mobile palettes for Android variants the
# Mobile build never shipped a palette for.
#
# Model: per-(chapter, cpk_entry) EXTRA palette indices. Each cpk entry can
# carry a list of custom palettes; a custom palette at list position ``i`` is
# selectable in the GUI as Mobile-palette index ``n_native + i`` (i.e. it
# extends the native palette dropdown). A custom palette is a flat list of
# ``[r, g, b]`` triplets of length ``nc`` (index 0 renders transparent, like
# every ic palette). See [[ffd-mobile-to-android-tileset-converter]].
# ---------------------------------------------------------------------------

def empty_custom_palettes() -> dict:
    """Return a fresh empty custom-palettes structure."""
    return {
        "format_version": 1,
        "comment": ("Hand-built Mobile cpk palettes for Android mc variants "
                    "the Mobile build never shipped. Each cpk entry's "
                    "'palettes' list extends its native palette dropdown: "
                    "custom palette i is selectable as index n_native + i. "
                    "Edit via the GUI's 'Build custom palette...' dialog."),
        "entries": {},
    }


def load_custom_palettes(path) -> dict:
    """Load custom_palettes.json from ``path``. Returns an empty structure
    if the file does not exist or fails to parse."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if not isinstance(data, dict):
            return empty_custom_palettes()
        data.setdefault("format_version", 1)
        data.setdefault("entries", {})
        return data
    except FileNotFoundError:
        return empty_custom_palettes()
    except Exception:
        return empty_custom_palettes()


def save_custom_palettes(path, data: dict) -> bool:
    """Atomically save custom_palettes.json. Returns True on success."""
    try:
        tmp = str(path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(path))
        return True
    except Exception:
        return False


def list_custom_palettes(data: dict, chapter, cpk_entry) -> list:
    """Return the list of custom-palette records for (chapter, cpk_entry).

    Tries the chapter label literally AND the dense (space-stripped) form
    so 'Chapter 5' finds 'Chapter5'. Each record is
    ``{"nc": int, "colors": [[r,g,b], ...], "note": str}``. Returns an
    empty list when none are stored."""
    if not isinstance(data, dict) or chapter is None:
        return []
    entries = data.get("entries") or {}
    eid_str = str(cpk_entry)
    for k in (chapter, str(chapter).replace(" ", "")):
        chap = entries.get(k)
        if not chap:
            continue
        rec = chap.get(eid_str)
        if rec and isinstance(rec.get("palettes"), list):
            return rec["palettes"]
    return []


def get_custom_palette(data: dict, chapter, cpk_entry, index):
    """Return the ``colors`` list (of ``[r,g,b]``) for custom palette
    ``index`` of (chapter, cpk_entry), or None if absent."""
    pals = list_custom_palettes(data, chapter, cpk_entry)
    if 0 <= index < len(pals):
        cols = pals[index].get("colors") or []
        return [tuple(int(x) for x in c[:3]) for c in cols]
    return None


def add_custom_palette(data: dict, chapter, cpk_entry, colors,
                       nc=None, note="", index=None) -> int:
    """Append (or overwrite at ``index``) a custom palette for
    (chapter, cpk_entry). Chapter is normalised to dense form on store.
    Returns the list position the palette ended up at."""
    entries = data.setdefault("entries", {})
    chap = entries.setdefault(str(chapter).replace(" ", ""), {})
    rec = chap.setdefault(str(cpk_entry), {})
    pals = rec.setdefault("palettes", [])
    entry = {
        "nc": int(nc) if nc else len(colors),
        "colors": [[int(c[0]), int(c[1]), int(c[2])] for c in colors],
        "note": note or "",
    }
    if index is None or not (0 <= index < len(pals)):
        pals.append(entry)
        return len(pals) - 1
    pals[index] = entry
    return index


def delete_custom_palette(data: dict, chapter, cpk_entry, index) -> bool:
    """Remove custom palette ``index`` for (chapter, cpk_entry). Returns
    True if something was removed."""
    if not isinstance(data, dict):
        return False
    entries = data.get("entries") or {}
    eid_str = str(cpk_entry)
    for k in (chapter, str(chapter).replace(" ", "")):
        chap = entries.get(k)
        if not chap:
            continue
        rec = chap.get(eid_str)
        if rec and isinstance(rec.get("palettes"), list):
            pals = rec["palettes"]
            if 0 <= index < len(pals):
                pals.pop(index)
                return True
    return False
