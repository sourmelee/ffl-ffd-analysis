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


def _save_json_verified(path, data) -> bool:
    """Write ``data`` as pretty JSON with truncation guards: write to a temp
    file, read it back and confirm it round-trips byte-for-byte + parses, rotate
    the previous good file to ``<path>.bak``, then atomically replace. Returns
    False (leaving the existing file untouched) if the write didn't verify --
    so a silent short-write on this workspace's filesystem can never clobber a
    good overrides file."""
    path = str(path); tmp = path + ".tmp"
    try:
        payload = _json.dumps(data, indent=2, ensure_ascii=False)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass
        with open(tmp, "r", encoding="utf-8") as f:
            written = f.read()
        if written != payload:
            try: os.remove(tmp)
            except Exception: pass
            return False
        _json.loads(written)
        if os.path.exists(path):
            try:
                import shutil
                shutil.copy2(path, path + ".bak")
            except Exception:
                pass
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def load_cpk_to_mc_overrides(path) -> dict:
    """Load cpk_to_mc_overrides.json. On a parse error (e.g. a truncated write)
    preserves a ``<path>.corrupt`` copy, attempts an automatic structural
    repair, and warns loudly -- never silently discards saved routing
    overrides."""
    path = str(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return empty_cpk_to_mc_overrides()
    except Exception:
        return empty_cpk_to_mc_overrides()
    try:
        data = _json.loads(text)
    except Exception as e:
        import sys as _sys
        try:
            import shutil
            shutil.copy2(path, path + ".corrupt"); bak = path + ".corrupt"
        except Exception:
            bak = "(backup failed)"
        repaired = repair_custom_palettes(text)
        if repaired is not None:
            print(f"[mc_overrides] WARNING: {path} was corrupt ({e}); "
                  f"AUTO-REPAIRED in memory (corrupt copy at {bak}). Re-save to "
                  f"persist.", file=_sys.stderr)
            data = repaired
        else:
            print(f"[mc_overrides] ERROR: {path} unparseable ({e}); corrupt copy "
                  f"at {bak}. Loaded EMPTY.", file=_sys.stderr)
            return empty_cpk_to_mc_overrides()
    if not isinstance(data, dict):
        return empty_cpk_to_mc_overrides()
    data.setdefault("format_version", 1)
    data.setdefault("entries", {})
    return data


def save_cpk_to_mc_overrides(path, overrides: dict) -> bool:
    """Atomically + verifiably save the routing overrides file."""
    return _save_json_verified(path, overrides)


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
        "builds": {},
    }


def repair_custom_palettes(text):
    """Best-effort repair of a TRUNCATED custom_palettes.json (the workspace
    filesystem can silently short-write). Walks the JSON tracking bracket depth
    (ignoring string contents), truncates at the last position where the prefix
    can be validly closed, and appends the missing ``]``/``}``. Returns the
    parsed dict on success or ``None`` if nothing salvageable.

    Salvages everything up to the last complete element; only a single
    partially-written entry at the very end is dropped.
    """
    def _stack(prefix):
        stk = []; in_str = False; esc = False
        for ch in prefix:
            if in_str:
                if esc: esc = False
                elif ch == "\\": esc = True
                elif ch == '"': in_str = False
            elif ch == '"': in_str = True
            elif ch in "{[": stk.append(ch)
            elif ch in "}]":
                if stk: stk.pop()
        return stk, in_str
    # candidate cut points: every } or ] that is not inside a string
    cuts = []; in_str = False; esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': in_str = False
        elif ch == '"': in_str = True
        elif ch in "}]": cuts.append(i)
    for pos in reversed(cuts[-400:]):
        prefix = text[:pos + 1]
        stk, ins = _stack(prefix)
        if ins:
            continue
        cand = prefix + "".join("]" if c == "[" else "}" for c in reversed(stk))
        try:
            data = _json.loads(cand)
            if isinstance(data, dict):
                return data
        except Exception:
            continue
    return None


def load_custom_palettes(path) -> dict:
    """Load custom_palettes.json from ``path``. On a parse error (e.g. a
    truncated write) this preserves the corrupt file as ``<path>.corrupt``,
    attempts an automatic structural repair, and prints a loud warning -- it
    NEVER silently discards saved overrides. Returns an empty structure only
    when the file is missing or unsalvageable."""
    path = str(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except FileNotFoundError:
        return empty_custom_palettes()
    except Exception:
        return empty_custom_palettes()
    try:
        data = _json.loads(text)
    except Exception as e:
        import sys as _sys
        try:
            import shutil
            shutil.copy2(path, path + ".corrupt")
            bak = path + ".corrupt"
        except Exception:
            bak = "(backup failed)"
        repaired = repair_custom_palettes(text)
        if repaired is not None:
            print(f"[mc_overrides] WARNING: {path} was corrupt ({e}); "
                  f"AUTO-REPAIRED in memory (corrupt copy saved to {bak}). "
                  f"Re-save to persist the repair.", file=_sys.stderr)
            data = repaired
        else:
            print(f"[mc_overrides] ERROR: {path} failed to parse ({e}) and could "
                  f"not be repaired; corrupt copy at {bak}. Loaded EMPTY -- saved "
                  f"overrides are preserved in the .corrupt file.", file=_sys.stderr)
            return empty_custom_palettes()
    if not isinstance(data, dict):
        return empty_custom_palettes()
    data.setdefault("format_version", 1)
    data.setdefault("entries", {})
    data.setdefault("builds", {})
    return data


def save_custom_palettes(path, data: dict) -> bool:
    """Atomically + verifiably save custom_palettes.json (truncation-guarded;
    keeps a ``.bak`` of the last good file). See :func:`_save_json_verified`."""
    return _save_json_verified(path, data)


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


# ---------------------------------------------------------------------------
# Tileset BUILDS — self-contained per-(chapter, cpk, variant) recipes that
# bind a hand-built palette + cell_map + force_android edits to a specific
# Android mc variant. Stored in the same custom_palettes.json under "builds".
#
# Resolution is CHAPTER-AGNOSTIC: a physical cpk can appear in several
# chapters, so when several chapters carry a build for the same
# (cpk_entry, variant) we take the one from the HIGHEST-numbered chapter
# (treated as the most up-to-date). See [[feedback-workflow]].
#
# Build record shape:
#   {"palette": [[r,g,b], ...] | null,    # inline; null = native palette 0
#    "cell_map": {"c,r": {mobile_col, mobile_row, flip_h}, ...},
#    "force_android_cells": ["c,r", ...],
#    "fill_from_android": bool,
#    "note": str}
# ---------------------------------------------------------------------------

def _chapter_sort_key(chapter) -> int:
    """Rank a chapter label so the 'highest-numbered' wins. Numbered
    chapters sort by their embedded integer (Chapter10 > Chapter5);
    non-numbered labels (Prologue, ChapterOnline, Postgame, ...) sort
    below all numbered ones (key -1) since the user's rule is about
    numbered chapters being newest."""
    if chapter is None:
        return -1
    digits = "".join(ch for ch in str(chapter) if ch.isdigit())
    if digits:
        try:
            return int(digits)
        except ValueError:
            return -1
    return -1


def _builds_root(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    return data.get("builds") or {}


def set_tileset_build(data: dict, chapter, cpk_entry, variant,
                      palette=None, cell_map=None, force_android_cells=None,
                      fill_from_android=False, note="") -> None:
    """Store/overwrite a build for (chapter, cpk_entry, variant). Chapter
    is normalised to dense form on write. ``palette`` is an inline list of
    (r,g,b) (or None to use the cpk's native palette 0)."""
    builds = data.setdefault("builds", {})
    chap = builds.setdefault(str(chapter).replace(" ", ""), {})
    cpk = chap.setdefault(str(cpk_entry), {})
    rec = {
        "fill_from_android": bool(fill_from_android),
        "note": note or "",
    }
    if palette is not None:
        rec["palette"] = [[int(c[0]), int(c[1]), int(c[2])] for c in palette]
    if cell_map:
        rec["cell_map"] = {str(k): dict(v) for k, v in cell_map.items()}
    if force_android_cells:
        rec["force_android_cells"] = [str(x) for x in force_android_cells]
    cpk[str(variant)] = rec


def get_tileset_build(data: dict, chapter, cpk_entry, variant):
    """Return the build dict stored for the EXACT (chapter, cpk_entry,
    variant), trying literal and dense chapter forms. None if absent."""
    builds = _builds_root(data)
    vk = str(variant)
    ek = str(cpk_entry)
    for k in (chapter, str(chapter).replace(" ", "")):
        chap = builds.get(k)
        if chap and ek in chap and vk in chap[ek]:
            return chap[ek][vk]
    return None


def resolve_tileset_build(data: dict, cpk_entry, variant):
    """Chapter-agnostic lookup: scan every chapter's builds for
    (cpk_entry, variant) and return ``(chapter, build)`` from the
    highest-numbered chapter, or ``(None, None)`` if none exist."""
    builds = _builds_root(data)
    ek = str(cpk_entry)
    vk = str(variant)
    best = None  # (sort_key, chapter, build)
    for chap, chap_entries in builds.items():
        if not isinstance(chap_entries, dict):
            continue
        rec = (chap_entries.get(ek) or {}).get(vk)
        if not isinstance(rec, dict):
            continue
        sk = _chapter_sort_key(chap)
        if best is None or sk > best[0]:
            best = (sk, chap, rec)
    if best is None:
        return (None, None)
    return (best[1], best[2])


def list_tileset_builds(data: dict):
    """Yield (chapter, cpk_entry_str, variant_str, build) for every stored
    build — handy for export pipelines that emit all bound variants."""
    for chap, chap_entries in _builds_root(data).items():
        if not isinstance(chap_entries, dict):
            continue
        for ek, by_var in chap_entries.items():
            if not isinstance(by_var, dict):
                continue
            for vk, rec in by_var.items():
                if isinstance(rec, dict):
                    yield (chap, ek, vk, rec)


def bound_variants_for_cpk(data: dict, cpk_entry):
    """Return the set of int variants that have a build for this cpk_entry
    in ANY chapter (used to emit missing variants in mass-convert)."""
    out = set()
    ek = str(cpk_entry)
    for chap, chap_entries in _builds_root(data).items():
        if not isinstance(chap_entries, dict):
            continue
        by_var = chap_entries.get(ek)
        if isinstance(by_var, dict):
            for vk in by_var:
                try:
                    out.add(int(vk))
                except (TypeError, ValueError):
                    pass
    return out


def delete_tileset_build(data: dict, chapter, cpk_entry, variant) -> bool:
    """Remove a build for the exact (chapter, cpk_entry, variant). Returns
    True if something was removed."""
    builds = _builds_root(data)
    ek = str(cpk_entry)
    vk = str(variant)
    for k in (chapter, str(chapter).replace(" ", "")):
        chap = builds.get(k)
        if chap and ek in chap and vk in chap[ek]:
            del chap[ek][vk]
            return True
    return False


# ---------------------------------------------------------------------------
# Override management (powers the toolkit's "Manage overrides" viewer/editor)
# ---------------------------------------------------------------------------


def delete_cpk_to_mc_override(overrides: dict, chapter, cpk_entry,
                              palette=None) -> bool:
    """Remove a routing override for (chapter, cpk_entry). With ``palette`` set,
    only drops that ``by_palette`` entry (and the whole record if it becomes
    empty). Returns True if something was removed."""
    entries = (overrides or {}).get("entries") or {}
    ek = str(cpk_entry)
    for k in (chapter, str(chapter).replace(" ", "")):
        chap = entries.get(k)
        if not chap or ek not in chap:
            continue
        if palette is None:
            del chap[ek]
            return True
        bp = chap[ek].get("by_palette") or {}
        if str(palette) in bp:
            del bp[str(palette)]
            if not bp and "mc_id" not in chap[ek] and "variant" not in chap[ek]:
                del chap[ek]
            return True
    return False


def enumerate_overrides(routing=None, custom=None):
    """Flatten every stored override into display rows for a management UI.

    Each row is ``{kind, chapter, cpk, variant, detail, key}`` where ``key`` is a
    tuple consumable by :func:`delete_override_row`.  ``kind`` is one of
    ``'routing'`` (overall cpk->mc), ``'routing-pal'`` (per-Mobile-palette
    routing), ``'palette'`` (a hand-built custom Mobile palette), ``'build'``
    (a tileset build = palette + cell_map + fill bound to a variant)."""
    rows = []
    for chap, cpks in ((routing or {}).get("entries") or {}).items():
        for cpk, rec in (cpks or {}).items():
            if not isinstance(rec, dict):
                continue
            if "mc_id" in rec:
                rows.append({"kind": "routing", "chapter": chap, "cpk": cpk,
                             "variant": None,
                             "detail": f"-> mc{rec.get('mc_id')}_{rec.get('variant')}",
                             "key": ("routing", chap, cpk, None)})
            for pal, pr in (rec.get("by_palette") or {}).items():
                rows.append({"kind": "routing-pal", "chapter": chap, "cpk": cpk,
                             "variant": None,
                             "detail": f"pal {pal} -> mc{pr.get('mc_id')}_{pr.get('variant')}",
                             "key": ("routing-pal", chap, cpk, pal)})
    for chap, cpks in ((custom or {}).get("entries") or {}).items():
        for cpk, rec in (cpks or {}).items():
            for i, pal in enumerate((rec or {}).get("palettes") or []):
                nc = pal.get("nc", len(pal.get("colors") or []))
                note = (" " + pal.get("note", "")) if pal.get("note") else ""
                rows.append({"kind": "palette", "chapter": chap, "cpk": cpk,
                             "variant": i,
                             "detail": f"custom palette #{i} ({nc} colors){note}",
                             "key": ("palette", chap, cpk, i)})
    for chap, cpks in ((custom or {}).get("builds") or {}).items():
        for cpk, byvar in (cpks or {}).items():
            for var, b in (byvar or {}).items():
                pal = (b or {}).get("palette")
                pn = len(pal) if isinstance(pal, list) else pal
                rows.append({"kind": "build", "chapter": chap, "cpk": cpk,
                             "variant": var,
                             "detail": (f"build v{var} (palette {pn}, "
                                        f"fill={(b or {}).get('fill_from_android')}, "
                                        f"cells={len((b or {}).get('cell_map') or {})})"),
                             "key": ("build", chap, cpk, var)})

    def _sk(r):
        cpk = r["cpk"]
        return (r["kind"], str(r["chapter"]),
                int(cpk) if str(cpk).isdigit() else 0,
                r["variant"] if r["variant"] is not None else -1)
    rows.sort(key=_sk)
    return rows


def delete_override_row(routing, custom, key) -> bool:
    """Delete one row produced by :func:`enumerate_overrides`. ``key`` is
    ``(kind, chapter, cpk, sub)``. Mutates ``routing``/``custom`` in place;
    returns True if something was removed."""
    kind, chap, cpk, sub = key
    if kind == "routing":
        return delete_cpk_to_mc_override(routing, chap, cpk)
    if kind == "routing-pal":
        return delete_cpk_to_mc_override(routing, chap, cpk, palette=sub)
    if kind == "palette":
        return delete_custom_palette(custom, chap, cpk, int(sub))
    if kind == "build":
        return delete_tileset_build(custom, chap, cpk, sub)
    return False
