"""AssetKind registry -- one entry per comparable asset type.

Each AssetKind plugs in:
    load_mobile(ffdata, source_key=None)  -> list of records
    load_android(ffdata, source_key=None) -> list of records
    list_sources_mobile(ffdata)           -> [(key, label), ...] or None
    list_sources_android(ffdata)          -> [(key, label), ...] or None
    record_label(record)                  -> short string for the dropdown
    decode(record, side)                  -> normalised dict to diff
    render(m_rec, a_rec)                  -> optional (Pillow_img, Pillow_img)

`source_key` lets the GUI/CLI pick a non-default source (e.g. per-chapter
chara_set.dat on Mobile). The selected source is forwarded to the loader.

Multi-language names (English / French / etc.) are pulled from Android
`system_message.msd` via ffd.text.system_message.SystemMessageLookup and
spliced into the decoded dicts as `en_name`, `en_desc`, etc.
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
from ..constants import CHARA_TABLE
from ..text.system_message import SystemMessageLookup
from .diff import diff_dicts, diff_bytes


# ---------------------------------------------------------------------------
# AssetKind dataclass + dispatch helper
# ---------------------------------------------------------------------------

LoaderFn      = Callable[..., List[Any]]
SourceListFn  = Callable[[Any], List[Tuple[str, str]]]
LabelFn       = Callable[[Any], str]
DecodeFn      = Callable[[Any, str], dict]
RenderFn      = Callable[[Any, Any], Tuple[Any, Any]]


@dataclass
class AssetKind:
    name: str
    load_mobile: Optional[LoaderFn] = None
    load_android: Optional[LoaderFn] = None
    list_sources_mobile:  Optional[SourceListFn] = None
    list_sources_android: Optional[SourceListFn] = None
    record_label: Optional[LabelFn] = None
    decode: Optional[DecodeFn] = None
    render: Optional[RenderFn] = None
    notes: str = ""


def _call_loader(loader, ffdata, source_key):
    if loader is None:
        return []
    try:
        return loader(ffdata, source_key=source_key) or []
    except TypeError:
        return loader(ffdata) or []


# ---------------------------------------------------------------------------
# Multi-language name lookup cache (per FFData identity)
# ---------------------------------------------------------------------------
#
# Parsing system_message.msd is non-trivial (~750KB of UTF-8) so cache
# the SystemMessageLookup against the underlying bytes object. The cache
# entry invalidates when FFData reloads its OBB (different bytes -> new
# key in the WeakValueDictionary).
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


def _splice_names(out: dict, ffdata, asset_type: str, record_id: int,
                  langs=("en", "fr"), include_desc=True) -> None:
    """Add `en_name`, `en_desc`, `fr_name`, etc. into `out` if available."""
    if ffdata is None or record_id is None:
        return
    sm = _system_message(ffdata)
    if not sm.has(asset_type):
        return
    for lang in langs:
        nm = sm.name(asset_type, record_id, lang)
        if nm:
            out[lang + "_name"] = nm
        if include_desc:
            ds = sm.desc(asset_type, record_id, lang)
            if ds:
                out[lang + "_desc"] = ds


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------

def _items_label(rec):
    if rec is None:
        return "(deleted)"
    return "%s -- %s" % (rec.get("id", "?"), rec.get("name", "?"))


def _items_decode(rec, side, ffdata=None):
    if rec is None:
        return {}
    out = {"id": rec.get("id"), "name": rec.get("name"),
           "desc": rec.get("desc"), "body": rec.get("body", b"")}
    body = rec.get("body", b"")
    if body:
        out.update(decode_item_body(body))
    _splice_names(out, ffdata, "Item", rec.get("id"))
    return out


def _items_load_mobile(ffdata, source_key=None):
    bd = ffdata.boot_data_mobile() if ffdata else None
    return parse_items_mobile(bd) if bd else []


def _items_load_android(ffdata, source_key=None):
    bd = ffdata.boot_data_android() if ffdata else None
    return parse_items_android(bd) if bd else []


_ITEMS = AssetKind(
    name="Item",
    load_mobile=_items_load_mobile,
    load_android=_items_load_android,
    record_label=_items_label,
    decode=_items_decode,
    notes=(
        "640 records each. Body=54, BE on BOTH platforms (multi-byte fields "
        "inside the record body don't endian-flip -- only the outer TOC "
        "pointer does). body[45..46] differ on 100% of items (per-record "
        "watermark/sort-key the remaster systematically renumbered). "
        "EN/FR names spliced from system_message.msd sec 7."
    ),
)


# ---------------------------------------------------------------------------
# Character
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
    if ffdata.apk_files:
        for k in ffdata.apk_files:
            if k.endswith("chara_set.dat"):
                return [("apk", "Android APK")]
    return []


def _load_chara_mobile(ffdata, source_key=None):
    if ffdata is None: return []
    chosen = None
    for slot, blob in ffdata.find_in_sp_any_chapter("chara_set.dat"):
        if source_key is None or slot == source_key:
            chosen = (slot, blob)
            if source_key is not None: break
    if chosen is None: return []
    _, blob = chosen
    chars = parse_chara_set_mobile(blob)
    items = None
    try:
        bd = ffdata.boot_data_mobile()
        if bd is not None: items = parse_items_mobile(bd)
    except Exception:
        items = None
    for c in chars:
        if c is not None:
            c["equipment_resolved"] = _resolve_equipment(c.get("equipment", []), items)
    return chars


def _load_chara_android(ffdata, source_key=None):
    if ffdata is None: return []
    blob = None
    if source_key in (None, "obb") and ffdata.obb_files:
        blob = ffdata.obb_files.get("chara_set.dat")
    if blob is None and ffdata.apk_files:
        for k, v in ffdata.apk_files.items():
            if k.endswith("chara_set.dat"):
                blob = v; break
    if blob is None: return []
    chars = parse_chara_set_android(blob)
    items = None
    try:
        bd = ffdata.boot_data_android()
        if bd is not None: items = parse_items_android(bd)
    except Exception:
        items = None
    for c in chars:
        if c is not None:
            c["equipment_resolved"] = _resolve_equipment(c.get("equipment", []), items)
    return chars


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
    notes=(
        "chara_set.dat. Mobile = 12-byte BE header per chapter, .sp-local; "
        "Android = 16-byte LE header in OBB. Records section is BE on both. "
        "Equipment ids resolved to item names. EN/FR names from "
        "system_message.msd sec 5."
    ),
)


# ---------------------------------------------------------------------------
# Monster
# ---------------------------------------------------------------------------

def _list_sources_monster_mobile(ffdata):
    """Each Mobile .sp ships its own boot_data with chapter-scoped §8."""
    if ffdata is None: return []
    out = []
    for slot, files in ffdata.sp_slots.items():
        if files and "boot_data.dat" in files:
            out.append((slot, slot))
    return out


def _list_sources_monster_android(ffdata):
    if ffdata is None: return []
    if ffdata.boot_data_android() is not None:
        return [("obb", "Android OBB")]
    return []


def _load_monsters_mobile(ffdata, source_key=None):
    if ffdata is None: return []
    blob = None
    if source_key is not None:
        files = ffdata.sp_slots.get(source_key)
        if files and "boot_data.dat" in files:
            blob = files["boot_data.dat"]
    if blob is None:
        # Default: use any slot with boot_data.dat
        for slot, files in ffdata.sp_slots.items():
            if files and "boot_data.dat" in files:
                blob = files["boot_data.dat"]; break
    if blob is None: return []
    return parse_monsters_mobile(blob)


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
    if body:
        out.update(decode_monster_body(body))
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
    notes=(
        "boot_data section 8 (Mobile, BE TOC) / section 9 (Android, LE TOC). "
        "Body=64, BE on BOTH platforms (no endian flip inside record body). "
        "No desc field (unlike Item/Magic/Job). Mobile .sp ships chapter-"
        "scoped tables; pick per-chapter via source picker. EN/FR names "
        "from system_message.msd sec 13."
    ),
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

def _todo_loader(name):
    def _f(ffdata, source_key=None):
        raise NotImplementedError(
            "%s comparison not implemented yet -- see "
            "ffd/comparison/registry.py" % name)
    return _f


_STUB_KINDS = [
    AssetKind(name="Job",       load_mobile=_todo_loader("Job"),
              load_android=_todo_loader("Job"),
              notes="Mobile section 20 BE / Android section 6 LE, body=126."),
    AssetKind(name="Magic",     load_mobile=_todo_loader("Magic"),
              load_android=_todo_loader("Magic"),
              notes="Android section 2 LE body=54; Mobile equivalent at section 1 (verify)."),
    AssetKind(name="Sprite",    load_mobile=_todo_loader("Sprite"),
              load_android=_todo_loader("Sprite"),
              notes="chpk/cpk on Mobile vs cpk/ICP on Android; ic format shared."),
    AssetKind(name="Animation", load_mobile=_todo_loader("Animation"),
              load_android=_todo_loader("Animation"),
              notes="Mobile chpk hardcoded layout vs Android field_anm.dat 63 generic anims."),
    AssetKind(name="Map",       load_mobile=_todo_loader("Map"),
              load_android=_todo_loader("Map"),
              notes="Mobile mpk chunk BE vs Android mpkh+mpk streaming chunk LE."),
    AssetKind(name="Text",      load_mobile=_todo_loader("Text"),
              load_android=_todo_loader("Text"),
              notes="Mobile message.dat SJIS vs Android .msd UTF-8."),
]


ASSET_KINDS = {k.name: k for k in ([_ITEMS, _CHARACTER, _MONSTER] + _STUB_KINDS)}


def list_asset_kinds():
    return list(ASSET_KINDS.keys())


# ---------------------------------------------------------------------------
# compare_records
# ---------------------------------------------------------------------------

def _safe_decode(decode_fn, rec, side, ffdata):
    """Call decoder, gracefully handling both 2-arg and 3-arg signatures."""
    if decode_fn is None:
        return rec or {}
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
