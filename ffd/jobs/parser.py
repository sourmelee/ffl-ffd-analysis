"""Job class parsers — mobile (BE section 20) and Android (LE section 6)."""

from __future__ import annotations

from ..binary import be_u16, be_u32, read_pstr_sjis
from ..boot.sections import boot_section_be, _parse_android_namedesc_section


def parse_jobs_mobile(boot: bytes):
    """Parse mobile job class records from section 20 (BE)."""
    sec = boot_section_be(boot, 20)
    if len(sec) < 2:
        return []
    n = be_u16(sec, 0)
    pos = 2
    out = []
    safety = 0
    while pos < len(sec) and safety < 256:
        safety += 1
        try:
            name, pos = read_pstr_sjis(sec, pos)
            desc, pos = read_pstr_sjis(sec, pos)
            if pos + 25 > len(sec):
                break
            job_id      = sec[pos]; pos += 1
            sprite_ow   = sec[pos]; pos += 1
            sprite_btl  = sec[pos]; pos += 1
            palette_ow  = sec[pos]; pos += 1
            palette_btl = sec[pos]; pos += 1
            base_hp     = be_u32(sec, pos); pos += 4
            pos += 7                                  # field_248
            base_mp     = sec[pos]; pos += 1
            base_atk    = sec[pos]; pos += 1
            pos += 6                                  # field_250
            # ability list: 20 × (r2 + r1 + r2) = 20 × 5 = 100 bytes
            abilities = []
            for _ in range(20):
                if pos + 5 > len(sec):
                    break
                a1 = be_u16(sec, pos); pos += 2
                a2 = sec[pos];         pos += 1
                a3 = be_u16(sec, pos); pos += 2
                abilities.append((a1, a2, a3))
            equip_flags = sec[pos]; pos += 1
            move_type   = sec[pos]; pos += 1
            out.append({
                "id": job_id, "name": name, "desc": desc,
                "sprite_ow": sprite_ow, "sprite_btl": sprite_btl,
                "palette_ow": palette_ow, "palette_btl": palette_btl,
                "base_hp": base_hp, "base_mp": base_mp, "base_atk": base_atk,
                "abilities": abilities,
                "equip_flags": equip_flags, "move_type": move_type,
            })
        except Exception:
            break
        if n > 0 and len(out) >= n:
            break
    return out


def parse_jobs_android(boot: bytes):
    """Jobs / classes. body=126 — much larger than other sections."""
    return _parse_android_namedesc_section(boot, 0x18, 126)
