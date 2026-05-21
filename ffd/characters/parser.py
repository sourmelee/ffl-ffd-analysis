"""``chara_set.dat`` parser (FFD_REVERSE_ENGINEERING.md §10).

Returns a list of dicts, one per playable character record, containing
sprite (chpk entry) + palette indices plus an embedded equipment list.
"""

from __future__ import annotations

from ..binary import be_u16, be_u32, read_pstr_sjis


def parse_chara_set(data: bytes):
    """Parse chara_set.dat. Returns list of dicts."""
    if len(data) < 6:
        return []
    start = be_u32(data, 0)
    if start >= len(data):
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
