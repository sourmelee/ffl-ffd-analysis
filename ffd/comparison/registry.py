"""AssetKind registry -- one entry per comparable asset type.

Each AssetKind plugs in:
    load_mobile(ffdata, source_key=None)  -> list of records
    load_android(ffdata, source_key=None) -> list of records
    list_sources_mobile(ffdata)           -> [(key, label), ...] or None
    list_sources_android(ffdata)          -> [(key, label), ...] or None
    record_label(record)                  -> short string for the dropdown
    decode(record, side, ffdata=...)      -> normalised dict to diff

Per-side source picker: when `list_sources_*` is non-None, the GUI shows
a combobox; the chosen `source_key` is forwarded to the loader.

`supports_all_sources_mobile = True` adds an "(All chapters)" entry at
the top of the Mobile source picker. The loader receives
`source_key = ALL_SOURCES_KEY` and is expected to merge across every
loaded chapter (typically: latest-non-null record per id). Useful for
chapter-scoped tables (Character, Monster, Job) so you don't have to
flip the picker just to see late-game records.

Multi-language names from `system_message.msd` (sec 5/7/8/9/10/13)
are spliced into the decoded dicts via `_splice_names`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple

from ..items.parser import (
    parse_items_mobile, parse_items_android, decode_item_body,
)
from ..characters.parser import (
    parse_chara_set_mobile, parse_chara_set_android,
)
from ..monsters.parser import (
    parse_monsters_mobile, parse_monsters_android, decode_monster_body,
)
from ..jobs.parser import (
    parse_jobs_mobile, parse_jobs_android, decode_job_body,
)
from ..constants import CHARA_TABLE
from ..text.system_message import SystemMessageLookup
from .diff import diff_dicts, diff_bytes


# Special source key that asks the loader to merge across every loaded
# chapter (Mobile only -- Android has one canonical source per kind).
# The string is intentionally unlikely to clash with a real slot label.
ALL_SOURCES_KEY = "__all__"
ALL_SOURCES_LABEL = "(All chapters)"


# ---------------------------------------------------------------------------
# AssetKind dataclass + dispatch helpers
# ---------------------------------------------------------------------------

LoaderFn      = Callable[..., List[Any]]
SourceListFn  = Callable[[Any], List[Tuple[str, str]]]
LabelFn       = Callable[[Any], str]
DecodeFn      = Callable[[Any, str], dict]


@dataclass
class AssetKind:
    name: str
    load_mobile: Optional[LoaderFn] = None
    load_android: Optional[LoaderFn] = None
    list_sources_mobile:  Optional[SourceListFn] = None
    list_sources_android: Optional[SourceListFn] = None
    record_label: Optional[LabelFn] = None
    decode: Optional[DecodeFn] = None
    notes: str = ""
    # When True, the Mobile source picker prepends "(All chapters)" and
    # passes ALL_SOURCES_KEY to load_mobile. The loader must handle it.
    supports_all_sources_mobile: bool = False


def _call_loader(loader, ffdata, source_key):
    if loader is None:
        return []
    try:
        return loader(ffdata, source_key=source_key) or []
    except TypeError:
        return loader(ffdata) or []


def _augmented_sources(base_list, kind, side):
    """Prepend (All chapters) to the source list when supported."""
    if base_list is None: return None
    if side == "mobile" and kind.supports_all_sources_mobile:
        return [(ALL_SOURCES_KEY, ALL_SOURCES_LABEL)] + list(base_list)
    return list(base_list)


def list_sources(kind: AssetKind, ffdata, side: str):
    """Public helper used by the tab and CLI to enumerate sources."""
    if side == "mobile":
        base = kind.list_sources_mobile(ffdata) if kind.list_sources_mobile else None
    else:
        base = kind.list_sources_android(ffdata) if kind.list_sources_android else None
    if base is None: return []
    return _augmented_sources(base, kind, side)


# ---------------------------------------------------------------------------
# system_message.msd cache + name splice
# ---------------------------------------------------------------------------
import weakref
_sm_cache: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def _system_message(ffdata) -> SystemMessageLookup:
    if ffdata is None:
        return SystemMessageLookup(b"")
    try:
        cached = _sm_cache.get(ffdata)
    except TypeError:
        cached = None
    if cached is not None:
        return cached
    sm = SystemMessageLookup.from_ffdata(ffdata)
    try:
        _sm_cache[ffdata] = sm
    except TypeError:
        pass
    return sm


def _splice_names(out, ffdata, asset_type, record_id,
                  langs=("en", "fr"), include_desc=True):
    if ffdata is None or record_id is None: return
    sm = _system_message(ffdata)
    if not sm.has(asset_type): return
    for lang in langs:
        nm = sm.name(asset_type, record_id, lang)
        if nm: out[lang + "_name"] = nm
        if include_desc:
            ds = sm.desc(asset_type, record_id, lang)
            if ds: out[lang + "_desc"] = ds


# ---------------------------------------------------------------------------
# Merge helper for ALL_SOURCES_KEY loaders
# ---------------------------------------------------------------------------

def _merge_records_across_sources(per_source_records, *, prefer_later=True):
    """Merge per-source record lists into a single id-indexed list.

    Each input is the list returned by load_mobile(ffdata, source_key=K).
    Records are aligned by list index (the id). For each index, pick the
    most-developed record across sources: prefer entries that aren't
    None and whose name doesn't look like a placeholder.

    `prefer_later=True` (default) gives the later source the win when
    multiple have valid records -- chapters tend to be loaded in
    chronological order, and later chapters have the populated table.
    """
    if not per_source_records: return []
    max_len = max(len(lst) for lst in per_source_records)
    merged = [None] * max_len
    # Iterate sources; either first-wins or last-wins per id depending
    # on prefer_later. We do "last-non-placeholder wins" so an empty
    # later record doesn't overwrite a populated earlier one.
    order = list(range(len(per_source_records)))
    if prefer_later:
        order.reverse()
    for src_idx in order:
        recs = per_source_records[src_idx]
        for i, r in enumerate(recs):
            if r is None or i >= max_len:
                continue
            cur = merged[i]
            if cur is None:
                merged[i] = r
                continue
            # Keep whichever record is "more populated". Heuristic:
            # prefer one whose name isn't a placeholder.
            cur_p = _looks_placeholder(cur.get("name", ""))
            new_p = _looks_placeholder(r.get("name", ""))
            if cur_p and not new_p:
                merged[i] = r
            # if both placeholder or both real, keep current (later
            # source wins when iterating in reverse so we keep first-seen)
    return merged


_PLACEHOLDER_PATTERNS = ("ダミー", "予備", "？？？", "?????")


def _looks_placeholder(name: str) -> bool:
    if not name:
        return True
    return any(p in name for p in _PLACEHOLDER_PATTERNS)


# ---------------------------------------------------------------------------
# Item -- single source per side
# ---------------------------------------------------------------------------

def _items_load_mobile(ffdata, source_key=None):
    bd = ffdata.boot_data_mobile() if ffdata else None
    return parse_items_mobile(bd) if bd else []


def _items_load_android(ffdata, source_key=None):
    bd = ffdata.boot_data_android() if ffdata else None
    return parse_items_android(bd) if bd else []


def _items_label(rec):
    if rec is None: return "(deleted)"
    return "%s -- %s" % (rec.get("id", "?"), rec.get("name", "?"))


def _items_decode(rec, side, ffdata=None):
    if rec is None: return {}
    out = {"id": rec.get("id"), "name": rec.get("name"),
           "desc": rec.get("desc"), "body": rec.get("body", b"")}
    body = rec.get("body", b"")
    if body: out.update(decode_item_body(body))
    _splice_names(out, ffdata, "Item", rec.get("id"))
    return out


_ITEMS = AssetKind(
    name="Item",
    load_mobile=_items_load_mobile,
    load_android=_items_load_android,
    record_label=_items_label,
    decode=_items_decode,
    notes=("640 records each. Body=54 BE on BOTH platforms. body[45..46] differ "
           "on 100% of items (per-record watermark/sort-key). EN/FR from "
           "system_message.msd sec 7."),
)


# ---------------------------------------------------------------------------
# Character -- per-chapter Mobile, +All chapters
# ---------------------------------------------------------------------------

_ID_TO_ROMAJI = {row[0]: row[2] for row in CHARA_TABLE}


def _resolve_equipment(equipment, items):
    out = []
    for eid in equipment:
        if eid == 0 or items is None:
            out.append({"id": eid, "name": "" if eid == 0 else "?"})
            continue
        if 0 <= eid < len(items) and items[eid] is not None:
            out.append({"id": eid, "name": items[eid].get("name", "?")})
        else:
            out.append({"id": eid, "name": "?"})
    return out


def _list_sources_chara_mobile(ffdata):
    if ffdata is None: return []
    return [(slot, slot) for slot, _ in ffdata.find_in_sp_any_chapter("chara_set.dat")]


def _list_sources_chara_android(ffdata):
    if ffdata is None or not ffdata.obb_files: return []
    if "chara_set.dat" in ffdata.obb_files:
        return [("obb", "Android OBB")]
    return []


def _resolve_chara_equipment(chars, items):
    for c in chars:
        if c is not None:
            c["equipment_resolved"] = _resolve_equipment(c.get("equipment", []), items)
    return chars


def _load_chara_mobile(ffdata, source_key=None):
    if ffdata is None: return []
    items = None
    try:
        bd = ffdata.boot_data_mobile()
        if bd is not None: items = parse_items_mobile(bd)
    except Exception:
        items = None
    if source_key == ALL_SOURCES_KEY:
        per_source = []
        for slot, blob in ffdata.find_in_sp_any_chapter("chara_set.dat"):
            per_source.append(_resolve_chara_equipment(
                parse_chara_set_mobile(blob), items))
        return _merge_records_across_sources(per_source)
    chosen = None
    for slot, blob in ffdata.find_in_sp_any_chapter("chara_set.dat"):
        if source_key is None or slot == source_key:
            chosen = (slot, blob)
            if source_key is not None: break
    if chosen is None: return []
    _, blob = chosen
    return _resolve_chara_equipment(parse_chara_set_mobile(blob), items)


def _load_chara_android(ffdata, source_key=None):
    if ffdata is None: return []
    blob = None
    if source_key in (None, "obb", ALL_SOURCES_KEY) and ffdata.obb_files:
        blob = ffdata.obb_files.get("chara_set.dat")
    if blob is None: return []
    chars = parse_chara_set_android(blob)
    items = None
    try:
        bd = ffdata.boot_data_android()
        if bd is not None: items = parse_items_android(bd)
    except Exception:
        items = None
    return _resolve_chara_equipment(chars, items)


def _character_label(rec):
    if rec is None: return "(deleted)"
    romaji = _ID_TO_ROMAJI.get(rec.get("id"), "")
    suffix = "  (%s)" % romaji if romaji else ""
    return "%2d -- %s%s" % (rec.get("id", -1), rec.get("name", "?"), suffix)


def _character_decode(rec, side, ffdata=None):
    if rec is None: return {}
    eq = rec.get("equipment_resolved") or [
        {"id": e, "name": "?"} for e in rec.get("equipment", [])
    ]
    eq_str = ", ".join("%d:%s" % (e["id"], e["name"]) if e["name"] else str(e["id"])
                       for e in eq)
    out = {
        "id":         rec.get("id"),
        "name":       rec.get("name"),
        "romaji":     _ID_TO_ROMAJI.get(rec.get("id"), ""),
        "chpk_entry": rec.get("f186"),
        "palette":    rec.get("f190"),
        "f173":       rec.get("f173"),
        "f174":       rec.get("f174"),
        "f182":       rec.get("f182"),
        "f187":       rec.get("f187"),
        "f188":       rec.get("f188"),
        "f189":       rec.get("f189"),
        "f191":       rec.get("f191"),
        "equipment":  eq_str,
    }
    _splice_names(out, ffdata, "Character", rec.get("id"), include_desc=False)
    return out


_CHARACTER = AssetKind(
    name="Character",
    load_mobile=_load_chara_mobile,
    load_android=_load_chara_android,
    list_sources_mobile=_list_sources_chara_mobile,
    list_sources_android=_list_sources_chara_android,
    record_label=_character_label,
    decode=_character_decode,
    supports_all_sources_mobile=True,
    notes=("chara_set.dat. Mobile = chapter-scoped 12B BE header; Android = 16B "
           "LE header (OBB). Equipment ids resolved to item names. EN/FR from "
           "system_message.msd sec 5."),
)


# ---------------------------------------------------------------------------
# Monster -- per-chapter Mobile, +All chapters
# ---------------------------------------------------------------------------

def _list_sources_monster_mobile(ffdata):
    if ffdata is None: return []
    return [(slot, slot) for slot, files in ffdata.sp_slots.items()
            if files and "boot_data.dat" in files]


def _list_sources_monster_android(ffdata):
    if ffdata is None or ffdata.boot_data_android() is None: return []
    return [("obb", "Android OBB")]


def _load_monsters_mobile(ffdata, source_key=None):
    if ffdata is None: return []
    if source_key == ALL_SOURCES_KEY:
        per_source = []
        for slot, files in ffdata.sp_slots.items():
            if files and "boot_data.dat" in files:
                per_source.append(parse_monsters_mobile(files["boot_data.dat"]))
        return _merge_records_across_sources(per_source)
    blob = None
    if source_key is not None:
        files = ffdata.sp_slots.get(source_key)
        if files and "boot_data.dat" in files:
            blob = files["boot_data.dat"]
    if blob is None:
        for slot, files in ffdata.sp_slots.items():
            if files and "boot_data.dat" in files:
                blob = files["boot_data.dat"]; break
    return parse_monsters_mobile(blob) if blob else []


def _load_monsters_android(ffdata, source_key=None):
    if ffdata is None: return []
    bd = ffdata.boot_data_android()
    return parse_monsters_android(bd) if bd else []


def _monster_label(rec):
    if rec is None: return "(deleted)"
    return "%3d -- %s" % (rec.get("id", -1), rec.get("name", "?"))


def _monster_decode(rec, side, ffdata=None):
    if rec is None: return {}
    out = {"id": rec.get("id"), "name": rec.get("name"),
           "body": rec.get("body", b"")}
    body = rec.get("body", b"")
    if body: out.update(decode_monster_body(body))
    _splice_names(out, ffdata, "Monster", rec.get("id"), include_desc=False)
    return out


_MONSTER = AssetKind(
    name="Monster",
    load_mobile=_load_monsters_mobile,
    load_android=_load_monsters_android,
    list_sources_mobile=_list_sources_monster_mobile,
    list_sources_android=_list_sources_monster_android,
    record_label=_monster_label,
    decode=_monster_decode,
    supports_all_sources_mobile=True,
    notes=("boot_data sec 8 (Mobile, BE) / sec 9 (Android, LE). Body=64 BE "
           "on both. No desc. Mobile chapter-scoped. EN/FR from "
           "system_message.msd sec 13."),
)


# ---------------------------------------------------------------------------
# Job -- per-chapter Mobile, +All chapters
# ---------------------------------------------------------------------------

def _list_sources_job_mobile(ffdata):
    if ffdata is None: return []
    return [(slot, slot) for slot, files in ffdata.sp_slots.items()
            if files and "boot_data.dat" in files]


def _list_sources_job_android(ffdata):
    if ffdata is None or ffdata.boot_data_android() is None: return []
    return [("obb", "Android OBB")]


def _load_jobs_mobile(ffdata, source_key=None):
    if ffdata is None: return []
    if source_key == ALL_SOURCES_KEY:
        per_source = []
        for slot, files in ffdata.sp_slots.items():
            if files and "boot_data.dat" in files:
                per_source.append(parse_jobs_mobile(files["boot_data.dat"]))
        return _merge_records_across_sources(per_source)
    blob = None
    if source_key is not None:
        files = ffdata.sp_slots.get(source_key)
        if files and "boot_data.dat" in files:
            blob = files["boot_data.dat"]
    if blob is None:
        for slot, files in ffdata.sp_slots.items():
            if files and "boot_data.dat" in files:
                blob = files["boot_data.dat"]; break
    return parse_jobs_mobile(blob) if blob else []


def _load_jobs_android(ffdata, source_key=None):
    if ffdata is None: return []
    bd = ffdata.boot_data_android()
    return parse_jobs_android(bd) if bd else []


def _job_label(rec):
    if rec is None: return "(deleted)"
    return "%2d -- %s" % (rec.get("id", -1), rec.get("name", "?"))


def _job_decode(rec, side, ffdata=None):
    if rec is None: return {}
    out = {"id": rec.get("id"), "name": rec.get("name"),
           "desc": rec.get("desc"), "body": rec.get("body", b"")}
    body = rec.get("body", b"")
    if body: out.update(decode_job_body(body))
    _splice_names(out, ffdata, "Job", rec.get("id"))
    return out


_JOB = AssetKind(
    name="Job",
    load_mobile=_load_jobs_mobile,
    load_android=_load_jobs_android,
    list_sources_mobile=_list_sources_job_mobile,
    list_sources_android=_list_sources_job_android,
    record_label=_job_label,
    decode=_job_decode,
    supports_all_sources_mobile=True,
    notes=("boot_data sec 5 (Mobile, BE) / sec 6 (Android, LE). Body=126 BE "
           "on both. Mobile 31 / Android 33; ids 19, 25, 30 diverge "
           "(placeholders / Mobile chapter-scoping). EN/FR from "
           "system_message.msd sec 8."),
)


# ---------------------------------------------------------------------------
# Stubs for remaining types
# ---------------------------------------------------------------------------

def _todo_loader(name):
    def _f(ffdata, source_key=None):
        raise NotImplementedError(
            "%s comparison not implemented yet -- see "
            "ffd/comparison/registry.py" % name)
    return _f


_STUB_KINDS = [
    AssetKind(name="Magic",     load_mobile=_todo_loader("Magic"),
              load_android=_todo_loader("Magic"),
              notes="Android sec 2 LE body=54; Mobile equivalent at sec 1."),
    AssetKind(name="Sprite",    load_mobile=_todo_loader("Sprite"),
              load_android=_todo_loader("Sprite"),
              notes="chpk/cpk on Mobile vs cpk/ICP on Android; ic shared."),
    AssetKind(name="Animation", load_mobile=_todo_loader("Animation"),
              load_android=_todo_loader("Animation"),
              notes="Mobile chpk hardcoded vs Android field_anm.dat 63 generic."),
    AssetKind(name="Map",       load_mobile=_todo_loader("Map"),
              load_android=_todo_loader("Map"),
              notes="Mobile mpk chunk BE vs Android mpkh+mpk streaming chunk LE."),
    AssetKind(name="Text",      load_mobile=_todo_loader("Text"),
              load_android=_todo_loader("Text"),
              notes="Mobile message.dat SJIS vs Android .msd UTF-8."),
]


ASSET_KINDS = {k.name: k for k in (
    [_ITEMS, _CHARACTER, _MONSTER, _JOB] + _STUB_KINDS)}


def list_asset_kinds():
    return list(ASSET_KINDS.keys())


# ---------------------------------------------------------------------------
# compare_records
# ---------------------------------------------------------------------------

def _safe_decode(decode_fn, rec, side, ffdata):
    if decode_fn is None: return rec or {}
    try:
        return decode_fn(rec, side, ffdata=ffdata)
    except TypeError:
        return decode_fn(rec, side)


def compare_records(kind_name, m_idx, a_idx, ffdata,
                    *, hide_identical=True, mode="semantic",
                    m_source=None, a_source=None):
    kind = ASSET_KINDS.get(kind_name)
    if kind is None:
        raise KeyError("unknown asset kind: %r" % kind_name)
    m_recs = _call_loader(kind.load_mobile,  ffdata, m_source)
    a_recs = _call_loader(kind.load_android, ffdata, a_source)
    m_rec = m_recs[m_idx] if 0 <= m_idx < len(m_recs) else None
    a_rec = a_recs[a_idx] if 0 <= a_idx < len(a_recs) else None
    m_dict = _safe_decode(kind.decode, m_rec, "mobile", ffdata)
    a_dict = _safe_decode(kind.decode, a_rec, "android", ffdata)
    if mode == "semantic":
        rows = diff_dicts(m_dict, a_dict, hide_identical=hide_identical)
    elif mode == "raw":
        mb = (m_rec or {}).get("body", b"") if isinstance(m_rec, dict) else b""
        ab = (a_rec or {}).get("body", b"") if isinstance(a_rec, dict) else b""
        rows = diff_bytes(mb, ab, hide_identical=hide_identical, prefix="body")
    else:
        raise ValueError("mode must be 'semantic' or 'raw', got %r" % mode)
    n_diff = sum(1 for r in rows if not r.same)
    summary = "%d field(s) differ%s" % (
        n_diff, " (identical fields hidden)" if hide_identical else "")
    return {
        "m_record": m_rec, "a_record": a_rec,
        "m_dict":   m_dict, "a_dict":   a_dict,
        "m_total":  len(m_recs), "a_total":  len(a_recs),
        "rows":     rows, "summary": summary,
        "kind":     kind,
        "m_source": m_source, "a_source": a_source,
    }
