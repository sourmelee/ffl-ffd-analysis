"""AssetKind registry -- one entry per comparable asset type.

Each AssetKind plugs in:
    load_mobile(ffdata, source_key=None)  -> list of records
    load_android(ffdata, source_key=None) -> list of records
    list_sources_mobile(ffdata)           -> [(key, label), ...] or None
    list_sources_android(ffdata)          -> [(key, label), ...] or None
    record_label(record)                  -> short string for the dropdown
    decode(record, side)                  -> normalised dict to diff
    render(m_rec, a_rec)                  -> optional (Pillow_img, Pillow_img)

When `list_sources_*` is non-None, the GUI shows a per-side source
combobox; the selected `source_key` is forwarded to the loader. Items
have a single implicit source (whichever boot_data is currently
loaded), so they leave it None. Characters have one chara_set.dat per
chapter on the Mobile side, so they enumerate every loaded SP slot.
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
from ..constants import CHARA_TABLE
from .diff import diff_dicts, diff_bytes


# ---------------------------------------------------------------------------
# AssetKind dataclass
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
    """Loaders can be written with or without the `source_key` kwarg
    (back-compat with the stub loaders). Try with kwarg first."""
    if loader is None:
        return []
    try:
        return loader(ffdata, source_key=source_key) or []
    except TypeError:
        return loader(ffdata) or []


# ---------------------------------------------------------------------------
# Item -- the seed asset (single implicit source per side).
# ---------------------------------------------------------------------------

def _items_label(rec):
    if rec is None:
        return "(deleted)"
    return "%s -- %s" % (rec.get("id", "?"), rec.get("name", "?"))


def _items_decode(rec, side):
    if rec is None:
        return {}
    out = {"id": rec.get("id"), "name": rec.get("name"),
           "desc": rec.get("desc"), "body": rec.get("body", b"")}
    body = rec.get("body", b"")
    if body:
        out.update(decode_item_body(body,
                                    "be" if side == "mobile" else "le"))
    return out


_ITEMS = AssetKind(
    name="Item",
    load_mobile=lambda ffdata, source_key=None: parse_items_mobile(
        ffdata.boot_data_mobile()),
    load_android=lambda ffdata, source_key=None: parse_items_android(
        ffdata.boot_data_android()),
    record_label=_items_label,
    decode=_items_decode,
    notes=(
        "640 records each. name/desc encoded as Shift-JIS pascal on both "
        "platforms (NOT UTF-8 on Android -- only .msd messages are UTF-8). "
        "Body=54 bytes; legacy per-field offsets are a best guess that the "
        "diff is here to invalidate."
    ),
)


# ---------------------------------------------------------------------------
# Character -- per-chapter source on Mobile (chara_set.dat ships in every
# .sp scratchpad and varies by chapter; Android has one canonical copy in
# the OBB). Equipment IDs are resolved to item names via parse_items_*.
# ---------------------------------------------------------------------------

# Build a single id -> romaji map up front. Some CHARA_TABLE entries have
# trailing fields we don't need here; we only want id + romaji name.
_ID_TO_ROMAJI = {row[0]: row[2] for row in CHARA_TABLE}


def _romaji_for(rec_id):
    return _ID_TO_ROMAJI.get(rec_id, "")


def _resolve_equipment(equipment, items):
    """Replace each numeric equip id with its item name (if known)."""
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
    """Every loaded SP slot that contains chara_set.dat."""
    if ffdata is None:
        return []
    out = []
    for slot, blob in ffdata.find_in_sp_any_chapter("chara_set.dat"):
        out.append((slot, slot))
    return out


def _list_sources_chara_android(ffdata):
    if ffdata is None or not ffdata.obb_files:
        return []
    if "chara_set.dat" in ffdata.obb_files:
        return [("obb", "Android OBB")]
    # Some apks ship chara_set.dat directly; surface that too.
    if ffdata.apk_files:
        for k in ffdata.apk_files:
            if k.endswith("chara_set.dat"):
                return [("apk", "Android APK")]
    return []


def _load_chara_mobile(ffdata, source_key=None):
    if ffdata is None:
        return []
    chosen = None
    for slot, blob in ffdata.find_in_sp_any_chapter("chara_set.dat"):
        if source_key is None or slot == source_key:
            chosen = (slot, blob)
            if source_key is not None:
                break
    if chosen is None:
        return []
    _, blob = chosen
    chars = parse_chara_set_mobile(blob)
    # Resolve equipment names against any loaded mobile boot_data. If no
    # boot_data is loaded the equipment field stays as raw ids -- still
    # useful, just less readable.
    items = None
    try:
        bd = ffdata.boot_data_mobile()
        if bd is not None:
            items = parse_items_mobile(bd)
    except Exception:
        items = None
    for c in chars:
        if c is not None:
            c["equipment_resolved"] = _resolve_equipment(c.get("equipment", []),
                                                        items)
    return chars


def _load_chara_android(ffdata, source_key=None):
    if ffdata is None:
        return []
    blob = None
    if source_key in (None, "obb") and ffdata.obb_files:
        blob = ffdata.obb_files.get("chara_set.dat")
    if blob is None and ffdata.apk_files:
        for k, v in ffdata.apk_files.items():
            if k.endswith("chara_set.dat"):
                blob = v; break
    if blob is None:
        return []
    chars = parse_chara_set_android(blob)
    items = None
    try:
        bd = ffdata.boot_data_android()
        if bd is not None:
            items = parse_items_android(bd)
    except Exception:
        items = None
    for c in chars:
        if c is not None:
            c["equipment_resolved"] = _resolve_equipment(c.get("equipment", []),
                                                        items)
    return chars


def _character_label(rec):
    if rec is None:
        return "(deleted)"
    romaji = _romaji_for(rec.get("id"))
    suffix = "  (%s)" % romaji if romaji else ""
    return "%2d -- %s%s" % (rec.get("id", -1), rec.get("name", "?"), suffix)


def _character_decode(rec, side):
    """Flatten the character record for diffing.

    Equipment is shown as a compact "id:name" list so the diff highlights
    rename-style changes (same id, different item name across builds)
    distinctly from id changes.
    """
    if rec is None:
        return {}
    eq = rec.get("equipment_resolved") or [
        {"id": e, "name": "?"} for e in rec.get("equipment", [])
    ]
    eq_str = ", ".join("%d:%s" % (e["id"], e["name"]) if e["name"] else str(e["id"])
                       for e in eq)
    out = {
        "id":         rec.get("id"),
        "name":       rec.get("name"),
        "romaji":     _romaji_for(rec.get("id")),
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
        "chara_set.dat. Mobile = 12-byte BE header per chapter (record set "
        "varies by chapter, .sp-local); Android = 16-byte LE header in OBB. "
        "Records section is BE on both. Equipment ids resolved to item "
        "names via parse_items_*."
    ),
)


# ---------------------------------------------------------------------------
# Stubs for the remaining types -- filled in by future sessions.
# ---------------------------------------------------------------------------

def _todo_loader(name):
    def _f(ffdata, source_key=None):
        raise NotImplementedError(
            "%s comparison not implemented yet -- see "
            "ffd/comparison/registry.py" % name)
    return _f


_STUB_KINDS = [
    AssetKind(name="Monster",   load_mobile=_todo_loader("Monster"),
              load_android=_todo_loader("Monster"),
              notes="Mobile section 12 BE / Android section 9 LE, body=64, no desc."),
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


ASSET_KINDS = {k.name: k for k in ([_ITEMS, _CHARACTER] + _STUB_KINDS)}


def list_asset_kinds():
    return list(ASSET_KINDS.keys())


# ---------------------------------------------------------------------------
# compare_records
# ---------------------------------------------------------------------------

def compare_records(kind_name, m_idx, a_idx, ffdata,
                    *, hide_identical=True, mode="semantic",
                    m_source=None, a_source=None):
    """Run a comparison and return a result dict.

    `m_source` / `a_source` select which source the loaders use when the
    kind exposes multiple (e.g. Character per-chapter on Mobile). None
    means "default": loader picks the first available source.
    """
    kind = ASSET_KINDS.get(kind_name)
    if kind is None:
        raise KeyError("unknown asset kind: %r" % kind_name)
    m_recs = _call_loader(kind.load_mobile,  ffdata, m_source)
    a_recs = _call_loader(kind.load_android, ffdata, a_source)
    m_rec = m_recs[m_idx] if 0 <= m_idx < len(m_recs) else None
    a_rec = a_recs[a_idx] if 0 <= a_idx < len(a_recs) else None
    decode = kind.decode or (lambda r, side: r or {})
    m_dict = decode(m_rec, "mobile")
    a_dict = decode(a_rec, "android")
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
