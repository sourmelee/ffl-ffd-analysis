"""Enemy / monster parsers — mobile (BE) and Android (LE).

Also includes the mobile ``bem.dat`` reader, which is a flat list of
length-prefixed Shift-JIS strings used for ability/monster name lookups.
"""

from __future__ import annotations

from ..binary import (
    be_s8, be_u16, be_u32, le_u32,
    read_pstr_sjis,
)


def parse_enemies_mobile(boot: bytes):
    """
    Parse mobile enemy records. The spec lists both section 12 (primary)
    and section 16 (continued). We try section 12 first; if that yields
    fewer than 10 plausible records we fall back to 16.
    """
    from ..boot.sections import boot_section_be

    def _try(sec_byte_off):
        sec = boot_section_be(boot, sec_byte_off)
        if len(sec) < 4:
            return []
        # First two bytes = count (BE u16) — but be tolerant
        n = be_u16(sec, 0)
        pos = 2
        out = []
        safety = 0
        while pos < len(sec) and len(out) < 1024 and safety < 4096:
            safety += 1
            try:
                start_pos = pos
                name, pos = read_pstr_sjis(sec, pos)
                desc, pos = read_pstr_sjis(sec, pos)
                # Sanity: name must look like a name
                if not name or len(name) > 30:
                    break
                if pos + 30 > len(sec):
                    break
                sprite_id  = be_s8(sec, pos); pos += 1
                max_hp     = be_u32(sec, pos); pos += 4
                level      = sec[pos]; pos += 1
                max_mp     = sec[pos]; pos += 1
                attack     = be_u16(sec, pos); pos += 2
                defense    = be_u16(sec, pos); pos += 2
                magic      = sec[pos]; pos += 1
                mdef       = sec[pos]; pos += 1
                elem_weak  = be_u16(sec, pos); pos += 2
                elem_half  = be_u16(sec, pos); pos += 2
                elem_null  = be_u16(sec, pos); pos += 2
                status_flg = be_u16(sec, pos); pos += 2
                pos += 4
                status_imm = be_u16(sec, pos); pos += 2
                evade      = sec[pos]; pos += 1
                ai_type    = sec[pos]; pos += 1
                gil = (sec[pos] << 16) | (sec[pos+1] << 8) | sec[pos+2]
                pos += 3
                pos += 20
                if pos + 3 > len(sec):
                    break
                exp = be_u16(sec, pos); pos += 2
                size = sec[pos]; pos += 1
                out.append({
                    "id": len(out), "name": name, "desc": desc,
                    "sprite_id": sprite_id, "max_hp": max_hp, "level": level,
                    "max_mp": max_mp, "attack": attack, "defense": defense,
                    "magic": magic, "magic_def": mdef,
                    "elem_weak": elem_weak, "elem_half": elem_half,
                    "elem_null": elem_null,
                    "status_flg": status_flg, "status_imm": status_imm,
                    "evade": evade, "ai_type": ai_type, "gil": gil,
                    "exp": exp, "size": size,
                })
            except Exception:
                break
            if n > 0 and len(out) >= n:
                break
        return out

    # Try the documented order: 12 first, then 16
    for sec_off in (12, 16):
        result = _try(sec_off)
        if len(result) >= 10:
            return result
    # If neither hit the threshold, return whichever was longer
    r12 = _try(12); r16 = _try(16)
    return r12 if len(r12) >= len(r16) else r16


def parse_monsters_android(boot: bytes):
    """
    Android monster table.

    Decoded 2026-05-13 from libjniproxy.so `GameClass::LoadMonsterData` (line
    134726 of Decomp/Functions/libjniproxy_c.c). The loader reads from boot
    section 9 (TOC offset 0x24) which starts with a BE u16 monster count.

    Per record (after the u16 count):
        if buf[pos] == 0xff: skip 1 byte (deleted/empty slot)
        else:
            pascal name (1 length byte + length bytes)
            64 bytes of body (parsed below)

    Body layout (offsets from name_end):
        +0   u8   sprite_id
        +1   u8   field9 (sprite variant? group?)
        +2   u32 BE  primary stat (max_hp)
        +6   u32 BE  secondary stat (max_mp? or attack)
        +10  u32 BE  another stat
        +14  u8   field14
        +15  18 bytes of u8s (skill / element table)
        +33  u16 BE (struct+0x2c)
        +35  u8     (struct+0x2e)
        +36  u16 BE (struct+0x30)
        +38  u32 BE (struct+0x34)
        +42  u32 BE (struct+0x38)
        +46  u8     (struct+0x3c)
        +47  u8     (struct+0x3d)
        +48  u16 BE + u8     (struct+0x40, 0x3e)
        +51  u16 BE + u8     (struct+0x42, 0x3f)
        +54  u16 BE          (struct+0x44)
        +56  u16 BE          (struct+0x46)
        +58  u8, u8          (struct+0x48, 0x49)
        +60  u16 BE          (struct+0x4a)
        +62  u16 BE          (struct+0x4c)
        +64  END of body

    The first record always has name "DBG:7.19_11:30" (a debug build stamp).
    Real monsters start at index 1. The declared count (645 in shipping data)
    is larger than the real-monster count (~146); remaining slots are zero
    placeholders that decode as length-0 / blank.
    """
    if len(boot) < 0x28 + 4:
        return []
    sec_start = le_u32(boot, 0x24)
    sec_end   = le_u32(boot, 0x28)
    if not (0 < sec_start < sec_end <= len(boot)):
        return []
    sec = boot[sec_start:sec_end]
    if len(sec) < 4:
        return []
    count = be_u16(sec, 0)
    if not (0 < count < 4096):
        return []

    out = []
    p = 2
    BODY = 64
    for i in range(count):
        if p >= len(sec):
            break
        if sec[p] == 0xff:
            out.append(None)  # deleted slot
            p += 1
            continue
        L = sec[p]
        if p + 1 + L + BODY > len(sec):
            break
        try:
            name = bytes(sec[p+1:p+1+L]).decode("shift_jis", errors="replace")
        except Exception:
            name = ""
        p += 1 + L
        body = sec[p:p+BODY]
        p += BODY
        # Reject obvious garbage: real records have sprite_id < 100 and HP
        # values in a plausible range. The all-zero placeholder records pass
        # through with name="" and we record them as None for downstream.
        if not name and all(b == 0 for b in body):
            out.append(None)
            continue
        out.append({
            "name":      name,
            "sprite_id": body[0],
            "field9":    body[1],
            "max_hp":    be_u32(body, 2),
            "stat_b":    be_u32(body, 6),
            "stat_c":    be_u32(body, 10),
            "field14":   body[14],
            "skills":    bytes(body[15:33]),
            "exp_or_gil": be_u16(body, 56),    # tentative
            "level":     body[58],              # tentative
            "_body":     bytes(body),           # raw for inspection
        })
    return out


def parse_enemy_names_android(boot: bytes):
    """
    DEPRECATED — kept for backwards compatibility with callers that only
    needed names. Now prefer `parse_monsters_android(boot)` which returns
    full records.

    Now delegates to `parse_monsters_android` and extracts just the names.
    Returns a list of name strings, with empty strings preserved for empty
    slots so caller indexing matches the engine's monster IDs.
    """
    monsters = parse_monsters_android(boot)
    return [m["name"] if m else "" for m in monsters]


def parse_bem(data: bytes):
    """
    Flat list of length-prefixed Shift-JIS strings.
    Some bem.dat files have a short binary header before the strings start;
    we scan forward to find the first position from which N consecutive
    valid string reads succeed, then walk from there.
    """
    out = []
    if not data:
        return out

    def looks_like_sjis_string(blob: bytes, pos: int) -> bool:
        """Quick test: is there a plausible SJIS string at this position?"""
        if pos >= len(blob):
            return False
        L = blob[pos]
        if L < 2 or L > 32:        # plausible name length range
            return False
        if pos + 1 + L > len(blob):
            return False
        chunk = blob[pos+1:pos+1+L]
        try:
            s = chunk.decode("shift-jis")
        except Exception:
            return False
        # must contain at least one CJK/kana/printable char
        for ch in s:
            cp = ord(ch)
            if cp >= 0x3000 or (0x20 <= cp < 0x7F and ch.isprintable()):
                return True
        return False

    # Find a starting position where >=3 consecutive valid strings parse.
    start = 0
    found = False
    for cand in range(min(256, len(data))):
        ok = 0
        cp = cand
        for _ in range(3):
            if not looks_like_sjis_string(data, cp):
                break
            cp += 1 + data[cp]
            ok += 1
        if ok >= 3:
            start = cand
            found = True
            break
    if not found:
        # Fall back to old behavior from offset 0
        start = 0

    p = start
    safety = 0
    while p < len(data) and safety < 8192:
        safety += 1
        L = data[p]
        if L == 0 or L > 64 or p + 1 + L > len(data):
            break
        try:
            s = bytes(data[p+1:p+1+L]).decode("shift-jis")
        except Exception:
            break
        out.append(s)
        p += 1 + L
    return out
