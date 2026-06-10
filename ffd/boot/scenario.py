"""boot_data scenario table (section 1) — chapter/start-point records.

Decoded 2026-06-10 from ``GameClass::LoadScenarioData`` (libjniproxy.so_new.c
:151000).  Section 1 of the Android ``boot_data.dat`` holds one record per
story *bank* (16 — the same N that selects ``msg{N}.msd`` and clusters with
map groups).  ``GameClass::TitleScene`` New Game starts the game at scenario
record [GameClass+0x19fe0] (bank 0): ``FieldClass::FieldMapStart(map)`` with
``map = rec.map`` (GameClass+0x1a0ac) and the player at ``rec.x/rec.y``
(+0x1a08c/+0x1a090).  (``e3_param.dat`` is the E3 trade-show demo start —
``g_IsE3Mode`` — NOT the retail New Game path.)

Record layout (cursor walk, all multi-byte values big-endian)::

    4 x pstr (u8 len + bytes)      chapter titles (ja Shift-JIS + alts)
    u16 x 3                        -> +0x1a0f0 / +0x1a0f8 / +0x1a100
    u8  flags                      -> +0x1a108 (bit7 -> 0x1a0e8, bit3 -> 0x1a0ec)
    u8, u8                         -> +0x1a050 / +0x1a058
    u32 x 2                        -> +0x1a118 / +0x1a120
    u8                             -> +0x1a128
    tail[0x2e]:                    (skipped for non-active banks)
      u16, u16, u8                 -> +0x1a0b0, +0x1a110, BeforeStory (+0x1a114)
      then 0x29 bytes; map = BE u16 @ +0xc, x = u8 @ +0xe, y = u8 @ +0xf
"""

from __future__ import annotations

import struct


def parse_scenario_android(boot: bytes) -> list[dict]:
    """Parse boot_data section 1 into scenario records (Android LE TOC)."""
    if len(boot) < 12:
        return []
    start = struct.unpack_from("<I", boot, 4)[0]
    end = struct.unpack_from("<I", boot, 8)[0]
    if not (0 < start < end <= len(boot)):
        return []
    pos = start
    count = struct.unpack_from(">H", boot, pos)[0]
    pos += 2
    recs = []
    for idx in range(count):
        titles = []
        for _ in range(4):
            if pos >= end:
                return recs
            ln = boot[pos]
            titles.append(boot[pos + 1:pos + 1 + ln])
            pos += ln + 1
        if pos + 18 + 0x2e > end + 1:
            return recs
        u16a, u16b, u16c = struct.unpack_from(">3H", boot, pos); pos += 6
        flags = boot[pos]; pos += 1
        b1, b2 = boot[pos], boot[pos + 1]; pos += 2
        u32a, u32b = struct.unpack_from(">2I", boot, pos); pos += 8
        b3 = boot[pos]; pos += 1
        tail = boot[pos:pos + 0x2e]; pos += 0x2e
        head = struct.unpack_from(">HHB", tail, 0)
        t = tail[5:]
        try:
            title = titles[0].decode("shift_jis")
        except (UnicodeDecodeError, LookupError):
            title = titles[0].hex()
        recs.append({
            "index": idx,
            "title": title,
            "u16s": (u16a, u16b, u16c),
            "flags": flags,
            "bytes": (b1, b2, b3),
            "u32s": (u32a, u32b),
            "pre": head,                      # (+0x1a0b0, +0x1a110, BeforeStory)
            "before_story": head[2],
            "map": (t[12] << 8) | t[13],      # GameClass+0x1a0ac (start map id)
            "x": t[14],                       # +0x1a08c
            "y": t[15],                       # +0x1a090
            "tail": tail,
        })
    return recs
