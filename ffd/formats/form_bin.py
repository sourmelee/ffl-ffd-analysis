"""``form.bin`` enemy formation parser (FFD_REVERSE_ENGINEERING.md §15)."""

from __future__ import annotations

import struct


def parse_form_bin(data: bytes):
    """
    Parse form.bin into structured formations.

    Format (per FFD_REVERSE_ENGINEERING.md §15):
      [0..1]   BE u16 count (or offset table[0]/2 — heuristic)
      Offset table: BE u16 entries indexed by formation_id
      Each formation:
        BE u16   inner_id
        u8       n_enemies
        For each enemy: x(BE u16), y(BE u16), z(BE u16), enemy_type(u8)
        u8       n_drops
        For each drop: slot(u8), type(u8), value(BE u16)

    Returns: list of formation dicts, indexed by formation_id.
    """
    formations = []
    if len(data) < 2:
        return formations

    # Determine how many formations exist by scanning the offset table
    # (each entry is BE u16). The first entry's value points just past
    # the offset table itself.
    first = struct.unpack(">H", data[0:2])[0]
    if first < 2 or first > len(data):
        # Fallback: try the count-as-u16 interpretation
        n = first
    else:
        n = first // 2  # offset table covers n entries

    if n > 4096 or n < 1:
        return formations

    for fid in range(n):
        o = fid * 2
        if o + 2 > len(data):
            break
        ptr = struct.unpack(">H", data[o:o+2])[0]
        if ptr + 3 > len(data):
            formations.append({"id": fid, "valid": False,
                               "inner_id": 0, "enemies": [], "drops": []})
            continue
        try:
            inner = struct.unpack(">H", data[ptr:ptr+2])[0]
            n_e = data[ptr + 2]
            p = ptr + 3
            enemies = []
            for _ in range(n_e):
                if p + 7 > len(data):
                    break
                ex = struct.unpack(">H", data[p:p+2])[0]
                ey = struct.unpack(">H", data[p+2:p+4])[0]
                ez = struct.unpack(">H", data[p+4:p+6])[0]
                et = data[p + 6]
                enemies.append({"type": et, "x": ex, "y": ey, "z": ez})
                p += 7
            drops = []
            if p < len(data):
                n_d = data[p]; p += 1
                for _ in range(n_d):
                    if p + 4 > len(data):
                        break
                    slot = data[p]; dtype = data[p+1]
                    val = struct.unpack(">H", data[p+2:p+4])[0]
                    drops.append({"slot": slot, "type": dtype, "value": val})
                    p += 4
            formations.append({
                "id": fid, "valid": True,
                "inner_id": inner, "enemies": enemies, "drops": drops,
            })
        except Exception:
            formations.append({"id": fid, "valid": False,
                               "inner_id": 0, "enemies": [], "drops": []})

    return formations
