"""Multi-language name lookup from Android `system_message.msd`.

Decoded 2026-05-22 by inspection of Android/proper_obb/system_message.msd
(753565 bytes). The file shares the standard `.msd` header (16 LE u32
section offsets, last = filesize) but each section holds localized
record tables instead of free message strings.

Section layout (per record):

    u16-BE   count (record count)
    record * count:
        for each of `slots_per_record` slots:
            u16-BE   string length (UTF-8 bytes, excludes terminator)
            N bytes  UTF-8 payload
            1 byte   NULL terminator

Records align back-to-back; no padding.

Six languages per name slot, in this order:
    0  Japanese
    1  English
    2  French
    3  Chinese-simplified
    4  Chinese-traditional
    5  Korean

For asset types that have a description field (items, magic, jobs,
passive abilities), each record uses TWO slots per language (name + desc
interleaved): JP_name, JP_desc, EN_name, EN_desc, ... -- 12 slots total.

Section -> asset mapping confirmed by record-count match against the
Android boot_data namedesc tables and chara_set.dat:

    sec 5   Characters       21 recs ×  6 slots  (name only)
    sec 6   Command abilities 50 recs × 12 slots  (name + desc)
    sec 7   Items            640 recs × 12 slots  (name + desc)
    sec 8   Jobs              33 recs × 12 slots
    sec 9   Magic            512 recs × 12 slots
    sec 10  Passive abilities 113 recs × 12 slots
    sec 13  Monsters         645 recs ×  6 slots  (name only)

Other sections are scenario / UI text (handled by the generic msd
parser in ffd/text/parser.py).
"""

from __future__ import annotations

import struct
from typing import List


LANGUAGES = ["ja", "en", "fr", "zh_cn", "zh_tw", "ko"]

# Section ID -> (asset_name, slots_per_record, has_desc)
SYSTEM_MESSAGE_SECTIONS = {
    5:  ("Character",          6, False),
    6:  ("CommandAbility",    12, True),
    7:  ("Item",              12, True),
    8:  ("Job",               12, True),
    9:  ("Magic",             12, True),
    10: ("PassiveAbility",    12, True),
    13: ("Monster",            6, False),
}


def _read_toc(data: bytes):
    """Read up to 16 LE u32 offsets; stop at filesize terminator."""
    n = len(data)
    offs = []
    i = 0
    while i + 4 <= n:
        v = struct.unpack_from("<I", data, i)[0]
        if v > n: break
        offs.append(v); i += 4
        if v == n: break
        if len(offs) > 32: break
    return offs


def parse_system_message_section(data: bytes, sec_id: int):
    """Parse a single section's per-record language bundles.

    Returns a list of records, each a list of strings (one per slot, in
    the order LANGUAGES * (1 or 2) depending on has_desc). None if the
    section ID isn't a name table.
    """
    if sec_id not in SYSTEM_MESSAGE_SECTIONS:
        return None
    _name, n_slots, _has_desc = SYSTEM_MESSAGE_SECTIONS[sec_id]
    toc = _read_toc(data)
    if sec_id + 1 >= len(toc):
        return []
    start, end = toc[sec_id], toc[sec_id + 1]
    if start >= end or end > len(data):
        return []
    if start + 2 > end:
        return []
    count = struct.unpack_from(">H", data, start)[0]
    p = start + 2
    out: List[List[str]] = []
    for _ in range(count):
        rec: List[str] = []
        for _ in range(n_slots):
            if p + 2 > end:
                rec.append(""); continue
            L = struct.unpack_from(">H", data, p)[0]; p += 2
            if p + L > end:
                rec.append(""); break
            s = data[p:p+L].decode("utf-8", errors="replace") if L > 0 else ""
            p += L
            if p < end:
                p += 1   # skip NULL terminator
            rec.append(s)
        out.append(rec)
    return out


def parse_system_message_msd(data: bytes):
    """Parse every named section in `system_message.msd`.

    Returns a dict of `{asset_name: [records...]}` where each record is
    either:
      * for name-only sections: a dict with one key per language --
        `{ja: '...', en: '...', fr: '...', ...}`
      * for name+desc sections: same plus `_desc` keys (`ja_desc`, ...).
    """
    out = {}
    for sec_id, (asset, n_slots, has_desc) in SYSTEM_MESSAGE_SECTIONS.items():
        recs = parse_system_message_section(data, sec_id)
        if recs is None: continue
        decoded = []
        for r in recs:
            d = {}
            if has_desc:
                # interleaved name+desc per language
                for lang_idx, lang in enumerate(LANGUAGES):
                    name_slot = lang_idx * 2
                    desc_slot = lang_idx * 2 + 1
                    d[lang] = r[name_slot] if name_slot < len(r) else ""
                    d[lang + "_desc"] = r[desc_slot] if desc_slot < len(r) else ""
            else:
                for lang_idx, lang in enumerate(LANGUAGES):
                    d[lang] = r[lang_idx] if lang_idx < len(r) else ""
            decoded.append(d)
        out[asset] = decoded
    return out


class SystemMessageLookup:
    """Convenience wrapper. Build once from `system_message.msd` bytes,
    then resolve `lookup(asset_type, record_id, lang='en')`.

    Returns "" when the asset type isn't in the table or the record id
    is out of range. Resilience over correctness -- this is a side
    enrichment for the comparison view, never a hard dependency.
    """

    def __init__(self, data: bytes):
        try:
            self._table = parse_system_message_msd(data) if data else {}
        except Exception:
            self._table = {}

    @classmethod
    def from_ffdata(cls, ffdata) -> "SystemMessageLookup":
        blob = None
        if ffdata is not None and ffdata.obb_files:
            blob = ffdata.obb_files.get("system_message.msd")
        # Fallback: scan APK
        if blob is None and ffdata is not None and ffdata.apk_files:
            for k, v in ffdata.apk_files.items():
                if k.endswith("system_message.msd"):
                    blob = v; break
        return cls(blob or b"")

    def name(self, asset_type: str, record_id: int, lang: str = "en") -> str:
        recs = self._table.get(asset_type, [])
        if not (0 <= record_id < len(recs)):
            return ""
        return recs[record_id].get(lang, "") or ""

    def desc(self, asset_type: str, record_id: int, lang: str = "en") -> str:
        recs = self._table.get(asset_type, [])
        if not (0 <= record_id < len(recs)):
            return ""
        return recs[record_id].get(lang + "_desc", "") or ""

    def has(self, asset_type: str) -> bool:
        return asset_type in self._table and len(self._table[asset_type]) > 0
