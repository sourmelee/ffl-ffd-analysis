"""``chara_set.dat`` parser -- Mobile (BE header) + Android (LE header).

Both builds share the same records layout: u16-BE count, then per-character
records of `[name(pstr SJIS)][2 u8][10 skip][5 u16-BE][u8 f182]
[6 u16-BE equipment][6 u8 (f186..f191)]`. The records section is BE on
both platforms (same convention as boot_data namedesc tables).

The header differs:

* Mobile (12 bytes):  3 u32-BE values -- `[start_of_records, sect2, filesize]`.
                      Records begin at `be_u32(data, 0)`.
* Android (16 bytes): 4 u32-LE values -- `[version=2, start_of_records,
                      sect2, filesize]`. Records begin at `le_u32(data, 4)`.

Verified 2026-05-22 by direct comparison of Mobile/Chapter1/_raw/chara_set.dat
(1635 bytes, 20 records) against Android/proper_obb/chara_set.dat (1603 bytes,
21 records). Sol/Aigis/Dusk/Sarah/Nacht/Alba/Diana/Glaive/Elgo are byte-
identical across both builds; later records show small numeric tweaks plus a
genuine rename at id=12 (Mobile "グラム" -> Android "黒騎士" / Black Knight)
and a Mobile-side placeholder at id=19 ("予備1") where Android has Eduardo.

CHARA_TABLE in ffd/constants.py provides the romaji name lookup keyed by id.
"""

from __future__ import annotations

import struct

from ..binary import be_u16, be_u32, read_pstr_sjis


def _parse_chara_set_records(data: bytes, start: int):
    """Walk the records section starting at `start` (count u16-BE followed
    by `count` records). Used by both the Mobile and Android wrappers."""
    if start + 2 > len(data):
        return []
    p = start
    n_chars = be_u16(data, p); p += 2
    out = []
    for i in range(n_chars):
        try:
            name, p = read_pstr_sjis(data, p)
            if p + 50 > len(data):
                break
            f173 = data[p]; p += 1
            f174 = data[p]; p += 1
            p += 10                                     # skip
            f181 = []
            for _ in range(5):
                if p + 2 > len(data): break
                f181.append(be_u16(data, p)); p += 2
            f182 = data[p]; p += 1
            equip = []
            for _ in range(6):
                if p + 2 > len(data): break
                equip.append(be_u16(data, p)); p += 2
            if p + 6 > len(data):
                break
            f186 = data[p]; p += 1   # CHPK ENTRY
            f187 = data[p]; p += 1
            f188 = data[p]; p += 1
            f189 = data[p]; p += 1
            f190 = data[p]; p += 1   # PALETTE INDEX
            f191 = data[p]; p += 1
            out.append({
                "id": i, "name": name,
                "f173": f173, "f174": f174,
                "f182": f182,
                "f186": f186, "f187": f187, "f188": f188,
                "f189": f189, "f190": f190, "f191": f191,
                "equipment": equip,
            })
        except Exception:
            break
    return out


def parse_chara_set_mobile(data: bytes):
    """Mobile chara_set.dat: 12-byte BE header, records at be_u32(data,0)."""
    if len(data) < 6:
        return []
    start = be_u32(data, 0)
    if start >= len(data):
        return []
    return _parse_chara_set_records(data, start)


def parse_chara_set_android(data: bytes):
    """Android chara_set.dat: 16-byte LE header, records at le_u32(data,4).

    The first u32-LE (offset 0) is a format version that is consistently 2
    in shipped Android dumps. Returns [] if the header doesn't look LE.
    """
    if len(data) < 16:
        return []
    # Sanity: header[0] should be a small version int; header[1] (start)
    # must be in-range. If neither check passes, refuse rather than
    # accidentally parsing a Mobile blob.
    version = struct.unpack_from("<I", data, 0)[0]
    start   = struct.unpack_from("<I", data, 4)[0]
    if version > 16 or start >= len(data) or start < 16:
        return []
    return _parse_chara_set_records(data, start)


def parse_chara_set(data: bytes):
    """Back-compat alias -- defaults to the Mobile header reader.

    Every pre-2026-05-22 caller (CrossRefTab, CharacterTab, scripts that
    imported the name from ffd_toolkit) passes Mobile-shaped data. New
    code that needs to handle both should call the explicit variants.
    """
    return parse_chara_set_mobile(data)
