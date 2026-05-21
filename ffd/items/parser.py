"""Item parsers — mobile (BE section 4) and Android (LE section 5)."""

from __future__ import annotations

from ..binary import be_u16, be_u32, read_pstr_sjis
from ..boot.sections import boot_section_be, _parse_android_namedesc_section


def parse_items_mobile(boot: bytes):
    """Parse mobile item records from section 4 (BE)."""
    sec = boot_section_be(boot, 4)
    if len(sec) < 2:
        return []
    n = be_u16(sec, 0)
    pos = 2
    out = []
    safety = 0
    while pos < len(sec) and safety < 4096:
        safety += 1
        try:
            name, pos = read_pstr_sjis(sec, pos)
            desc, pos = read_pstr_sjis(sec, pos)
            if pos + 50 > len(sec):
                break
            item_type   = sec[pos]; pos += 1
            equip_type  = sec[pos]; pos += 1
            price       = be_u32(sec, pos); pos += 4
            atk         = sec[pos]; pos += 1
            df          = sec[pos]; pos += 1
            mag         = sec[pos]; pos += 1
            weight      = be_u16(sec, pos); pos += 2
            flags       = be_u16(sec, pos); pos += 2
            element     = sec[pos]; pos += 1
            status      = sec[pos]; pos += 1
            # 11 stat fields (rough mix); we skip heuristically using 19 bytes
            pos += 19
            hp_bonus    = sec[pos]; pos += 1
            mp_bonus    = sec[pos]; pos += 1
            speed       = sec[pos]; pos += 1
            use_effect  = be_u16(sec, pos); pos += 2
            battle_flg  = be_u16(sec, pos); pos += 2
            pos += 8                                  # 4 pairs of equip fields
            job_mask    = sec[pos]; pos += 1
            ic_r = sec[pos]; pos += 1
            ic_g = sec[pos]; pos += 1
            ic_b = sec[pos]; pos += 1
            sort_key = be_u16(sec, pos); pos += 2
            out.append({
                "id": len(out), "name": name, "desc": desc,
                "item_type": item_type, "equip_type": equip_type,
                "price": price, "attack": atk, "defense": df, "magic": mag,
                "weight": weight, "flags": flags,
                "element": element, "status": status,
                "hp_bonus": hp_bonus, "mp_bonus": mp_bonus, "speed": speed,
                "use_effect": use_effect, "battle_flags": battle_flg,
                "job_mask": job_mask,
                "icon_color": (ic_r, ic_g, ic_b),
                "sort_key": sort_key,
            })
        except Exception:
            break
        if n > 0 and len(out) >= n:
            break
    return out


def parse_items_android(boot: bytes):
    """Items / equipment. body=54."""
    return _parse_android_namedesc_section(boot, 0x14, 54)
