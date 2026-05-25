"""Monster / enemy parsers -- mobile (BE TOC) + Android (LE TOC).

Both builds use the same record shape inside boot_data: u16-BE count,
then `name(pstr SJIS) + body[64]` per record (no desc, unlike items/jobs).
Multi-byte fields *inside* the body are BE on both platforms.

Mobile section: §8 (TOC byte offset 32, BE pointer). The README and
prior code claimed §12; that's actually the tileset preload pack table.
Empirically located 2026-05-22 by searching for the pascal-Goblin byte
signature across every Mobile data file -- only hit was in boot_data §8.

Android section: §9 (TOC byte offset 0x24, LE pointer). Confirmed
2026-05-13 from libjniproxy.so GameClass::LoadMonsterData.

Verified parsing 2026-05-22: Goblin (id=1) has byte-identical name and
62/64 byte-identical body across Chapter 1 Mobile and Android.

Mobile chapter scoping: each .sp ships its own §8 with 0xff sentinels
for monsters not yet introduced. Chapter 1 / Online have 93 active
records; later chapters add more.

Also includes the mobile `bem.dat` reader (a flat list of pascal SJIS
strings used for ability/monster name lookups).

Attribution: Mobile-side section identification builds on GuyPerfect's
``class_20.java`` research; Android decoding from libjniproxy.so.
"""

from __future__ import annotations

from ..binary import be_s8, be_u16, be_u32, le_u32, read_pstr_sjis


# Per-record body size on both platforms.
_MONSTER_BODY_SIZE = 64

# TOC byte offsets per platform.
_MOBILE_MONSTER_TOC  = 32      # §8 in mobile boot_data (8 * 4 bytes)
_ANDROID_MONSTER_TOC = 0x24    # §9 in android boot_data (9 * 4 bytes)


def _parse_monsters_namedesc(boot: bytes, toc_offset: int, endian: str):
    """Walk a `[u16-BE count] + (pascal_name + body[64])` table.

    Same as items namedesc, minus the desc pstr. Returns
    `[{id, name, body: bytes} | None]`. Returns [] if the section
    pointer looks bad. Endian only controls the TOC pointer read.
    """
    if endian == "be":
        rd = be_u32
    elif endian == "le":
        rd = le_u32
    else:
        raise ValueError("endian must be 'be' or 'le', got %r" % endian)
    if len(boot) < toc_offset + 8:
        return []
    sec_start = rd(boot, toc_offset)
    sec_end   = rd(boot, toc_offset + 4)
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
    for i in range(count):
        if p >= len(sec):
            break
        if sec[p] == 0xff:
            out.append(None); p += 1; continue
        L = sec[p]
        if L > 80 or p + 1 + L + _MONSTER_BODY_SIZE > len(sec):
            break
        try:
            name = bytes(sec[p+1:p+1+L]).decode("shift_jis", errors="replace")
        except Exception:
            name = ""
        p += 1 + L
        body = bytes(sec[p:p+_MONSTER_BODY_SIZE])
        p += _MONSTER_BODY_SIZE
        # Suppress all-zero placeholder records (some Android slots
        # decode as length-0 + 64 zero bytes). Caller can still inspect
        # the underlying body if needed.
        if not name and all(b == 0 for b in body):
            out.append(None); continue
        out.append({"id": i, "name": name, "body": body})
    return out


def parse_monsters_mobile(boot: bytes):
    """Mobile §8 monster table (BE TOC pointer)."""
    return _parse_monsters_namedesc(boot, _MOBILE_MONSTER_TOC, endian="be")


def parse_monsters_android(boot: bytes):
    """Android §9 monster table (LE TOC pointer).

    Returns dicts with `id, name, body` (raw 64 bytes). Use
    `decode_monster_body(body)` to extract per-field stats. For
    callers that need the legacy flat-field shape, see
    `parse_enemies_mobile` which decorates each record with
    decoded fields.
    """
    return _parse_monsters_namedesc(boot, _ANDROID_MONSTER_TOC, endian="le")


# ---------------------------------------------------------------------------
# Body field decode (shared between platforms -- BE on both)
# ---------------------------------------------------------------------------
#
# Layout traced from libjniproxy.so GameClass::LoadMonsterData. Offsets
# in the +33..+63 tail are tentative (the engine reads them but mapping
# to in-game stats is in progress). Keep them visible as `tail`
# bytes; the ComparisonTab raw-byte view is the right place to spot
# changes in that region.

def decode_monster_body(body: bytes) -> dict:
    """Decode a 64-byte monster body. BE on both platforms."""
    if len(body) < _MONSTER_BODY_SIZE:
        return {}
    return {
        "sprite_id":  body[0],
        "field9":     body[1],
        "max_hp":     be_u32(body, 2),
        "stat_b":     be_u32(body, 6),
        "stat_c":     be_u32(body, 10),
        "field14":    body[14],
        "skills":     bytes(body[15:33]),
        # tentative tail fields (see module docstring)
        "tail_u16_33": be_u16(body, 33),
        "tail_u8_35":  body[35],
        "tail_u16_36": be_u16(body, 36),
        "tail_u32_38": be_u32(body, 38),
        "tail_u32_42": be_u32(body, 42),
        "tail_u8_46":  body[46],
        "tail_u8_47":  body[47],
        "tail_u16_48": be_u16(body, 48),
        "tail_u8_50":  body[50],
        "tail_u16_51": be_u16(body, 51),
        "tail_u8_53":  body[53],
        "tail_u16_54": be_u16(body, 54),
        "tail_u16_56": be_u16(body, 56),
        "tail_u8_58":  body[58],
        "tail_u8_59":  body[59],
        "tail_u16_60": be_u16(body, 60),
        "tail_u16_62": be_u16(body, 62),
    }


# ---------------------------------------------------------------------------
# Back-compat: parse_enemies_mobile flattens body decode into each record.
# Existing callers (CrossRefTab, MonsterTab) expect this shape.
# ---------------------------------------------------------------------------

def parse_enemies_mobile(boot: bytes):
    """Mobile monster records with the body decoded inline.

    Drop-in replacement for the broken pre-2026-05-22 parser, which
    read the wrong section and assumed a name+desc layout. Returns
    `[{id, name, body, sprite_id, max_hp, ...}]`.
    """
    recs = parse_monsters_mobile(boot)
    flat = []
    for r in recs:
        if r is None:
            continue
        d = dict(r)
        d.update(decode_monster_body(r["body"]))
        # Legacy aliases used by existing tabs.
        d["desc"] = ""
        d["level"] = d.get("field14", 0)
        d["max_mp"] = 0
        d["attack"] = 0
        d["defense"] = 0
        d["magic"] = 0
        d["magic_def"] = 0
        d["elem_weak"] = 0
        d["elem_half"] = 0
        d["elem_null"] = 0
        d["status_flg"] = 0
        d["status_imm"] = 0
        d["evade"] = 0
        d["ai_type"] = 0
        d["gil"] = 0
        d["exp"] = 0
        d["size"] = 0
        flat.append(d)
    return flat


def parse_enemy_names_android(boot: bytes):
    """DEPRECATED: prefer parse_monsters_android. Returns just names."""
    monsters = parse_monsters_android(boot)
    return [m["name"] if m else "" for m in monsters]


# ---------------------------------------------------------------------------
# bem.dat reader -- mobile ability/monster name table
# ---------------------------------------------------------------------------

def parse_bem(data: bytes):
    """Flat list of length-prefixed Shift-JIS strings.

    Some bem.dat files have a short binary header before the strings;
    we scan forward for a position where >=3 consecutive valid strings
    parse, then walk from there.
    """
    out = []
    if not data:
        return out

    def looks_like_sjis_string(blob, pos):
        if pos >= len(blob):
            return False
        L = blob[pos]
        if L < 2 or L > 32: return False
        if pos + 1 + L > len(blob): return False
        chunk = blob[pos+1:pos+1+L]
        try: s = chunk.decode("shift_jis")
        except Exception: return False
        for ch in s:
            cp = ord(ch)
            if cp >= 0x3000 or (0x20 <= cp < 0x7F and ch.isprintable()):
                return True
        return False

    start = 0
    found = False
    for cand in range(min(256, len(data))):
        ok = 0; cp = cand
        for _ in range(3):
            if not looks_like_sjis_string(data, cp): break
            cp += 1 + data[cp]; ok += 1
        if ok >= 3:
            start = cand; found = True; break
    if not found:
        start = 0
    p = start; safety = 0
    while p < len(data) and safety < 8192:
        safety += 1
        L = data[p]
        if L == 0 or L > 64 or p + 1 + L > len(data): break
        try:
            s = bytes(data[p+1:p+1+L]).decode("shift_jis")
        except Exception:
            break
        out.append(s); p += 1 + L
    return out
