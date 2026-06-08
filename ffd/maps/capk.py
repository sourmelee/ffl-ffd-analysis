"""capk.dat -- chip-attribute (collision) parser.

Decoded from FieldClass::LoadChipAttribute + CheckMovePass in libjniproxy.so.

Layout:
  * little-endian u32 TOC; the per-tileset section for ``mc_id`` is at
    ``TOC[mc_id + 1]`` (TOC[0] overlaps the header; final entry == file size).
  * each section: u16-BE ``count``, then ``count`` x 7-byte chip records.
  * chip record = u32-BE ``A`` + u24-BE ``B``. ``A & 0x0F`` is the 4-direction
    passability mask (bit d set => the player may move in direction d). A nibble
    of 0 therefore means "blocked on all sides" = a wall / solid object.
"""

from __future__ import annotations


def parse_capk(data: bytes):
    """Return ``{mc_id: [pass_nibble per tile_num]}`` for every tileset section."""
    def leu32(o): return int.from_bytes(data[o:o + 4], "little")
    def beu16(o): return (data[o] << 8) | data[o + 1]
    def beu32(o): return int.from_bytes(data[o:o + 4], "big")

    n = len(data)
    out = {}
    mc = 0
    while mc < 4096:
        toc_pos = (mc + 1) * 4
        if toc_pos + 4 > n:
            break
        sec = leu32(toc_pos)
        if sec <= 0 or sec + 2 > n or sec >= n:
            break
        count = beu16(sec)
        off = sec + 2
        nibs = []
        for _ in range(count):
            if off + 7 > n:
                break
            nibs.append(beu32(off) & 0x0F)
            off += 7
        out[mc] = nibs
        mc += 1
    return out


def pass_nibble(capk, mc_id, tile_num):
    """4-dir pass nibble for a chip; unknown tiles default to passable (0x0F)."""
    if mc_id is None or mc_id < 0:
        return 0x0F
    nibs = capk.get(mc_id)
    if not nibs or tile_num >= len(nibs):
        return 0x0F
    return nibs[tile_num]


def parse_capk_anim(data: bytes):
    """Return {mc_id: [(inner_idx, type, frames, speed), ...]} for animated chips.

    From FieldClass::LoadChipAttribute + GetUpdateChipIDOfPosition: in the 7-byte
    chip record's u32-BE word A, bit 8 = animated, bits 9-10 = type (0 loop,
    1 ping-pong), bits 11-14 = frame count, bits 15-17 = speed index. Animated
    chip cycles consecutive inner ids base..base+frames-1. Verified 2026-06-08:
    1136 animated chips, all 3-frame, speed 1-2 (water/torch pattern).
    """
    def leu32(o): return int.from_bytes(data[o:o + 4], "little")
    def beu16(o): return (data[o] << 8) | data[o + 1]
    def beu32(o): return int.from_bytes(data[o:o + 4], "big")
    n = len(data)
    out = {}
    mc = 0
    while mc < 4096:
        toc_pos = (mc + 1) * 4
        if toc_pos + 4 > n:
            break
        sec = leu32(toc_pos)
        if sec <= 0 or sec + 2 > n or sec >= n:
            break
        count = beu16(sec)
        off = sec + 2
        anim = []
        for idx in range(count):
            if off + 7 > n:
                break
            A = beu32(off)
            off += 7
            if (A >> 8) & 1:
                anim.append((idx, (A >> 9) & 3, (A >> 11) & 0xF, (A >> 15) & 7))
        if anim:
            out[mc] = anim
        mc += 1
    return out
