"""``form.bin`` enemy formation parsers.

* :func:`parse_form_bin` — the legacy Mobile heuristic parser
  (FFD_REVERSE_ENGINEERING.md §15). NOTE: its field naming
  ``(x, y, z, enemy_type)`` predates the Android engine decode and is
  suspect — the Android record is ``(enemy_id i16, x i16, y i16,
  flags u8)``; the Mobile layout likely matches and should be
  re-verified (see Python/docs/formats/battles.md).
* :func:`parse_form_bin_android` — engine-accurate Android parser,
  decoded 2026-06-10 from ``BattleClass::LoadFormation``
  (libjniproxy.so_new.c:103535):

      file TOC:   u32-LE section offset per story bank at [4 + bank*4]
                  (banks 0..15; [0] = header word)
      section:    BE u16 record-offset table indexed by formation id
                  (offset relative to section start; 0 = no record)
      record:     u8   no_escape      (engine: clears BattleClass[0x6e35])
                  i16BE battle_script (id into bsc.dat; <=0 = none)
                  u8   n_enemies      (engine keeps at most 8)
                    n × { i16BE enemy_id, i16BE x, i16BE y, u8 flags }
                      -> BattleClass::SetBtlEnemyParam(actor, enemy_id, x, y)
                         (x,y land in BTLACT+0x63c/0x640)
                  u8   n_entries      (party-entry overrides)
                    n × { u8 member_slot, u8 value, i16BE param }
"""

from __future__ import annotations

import struct


def parse_form_bin_android(data: bytes, max_banks: int = 16):
    """Engine-accurate Android form.bin parse.

    Returns ``{bank: {formation_id: record_dict}}`` with record_dict =
    ``{no_escape, battle_script, enemies: [{enemy_id, x, y, flags}],
    entries: [{slot, value, param}]}``. Ids with a zero table offset are
    omitted (the engine treats them as "no formation").
    """
    out = {}
    if len(data) < 4 + 4 * max_banks:
        return out
    sec_offs = [struct.unpack_from("<I", data, 4 + b * 4)[0]
                for b in range(max_banks)]
    for bank, sec in enumerate(sec_offs):
        if sec == 0 or sec >= len(data):
            continue
        # The BE u16 offset table runs from the section start to the first
        # (lowest nonzero) record offset.
        first_rec = None
        n_ids = 0
        probe = sec
        while probe + 2 <= len(data):
            if first_rec is not None and probe - sec >= first_rec:
                break
            v = struct.unpack_from(">H", data, probe)[0]
            if v:
                if first_rec is None or v < first_rec:
                    first_rec = v
            probe += 2
            n_ids += 1
            if n_ids > 4096:
                break
        bank_out = {}
        for fid in range(n_ids):
            off = struct.unpack_from(">H", data, sec + fid * 2)[0]
            if off == 0:
                continue
            p = sec + off
            if p + 4 > len(data):
                continue
            no_escape = data[p]
            bsc = struct.unpack_from(">h", data, p + 1)[0]
            n_e = data[p + 3]
            p += 4
            enemies = []
            for _ in range(n_e):
                if p + 7 > len(data):
                    break
                eid, ex, ey = struct.unpack_from(">hhh", data, p)
                enemies.append({"enemy_id": eid, "x": ex, "y": ey,
                                "flags": data[p + 6]})
                p += 7
            entries = []
            if p < len(data):
                n_m = data[p]
                p += 1
                for _ in range(n_m):
                    if p + 4 > len(data):
                        break
                    entries.append({
                        "slot": data[p], "value": data[p + 1],
                        "param": struct.unpack_from(">h", data, p + 2)[0]})
                    p += 4
            bank_out[fid] = {"no_escape": no_escape,
                             "battle_script": bsc,
                             "enemies": enemies, "entries": entries}
        if bank_out:
            out[bank] = bank_out
    return out


def parse_form_bin(data: bytes):
    """
    Parse Mobile form.bin into structured formations (legacy heuristic).

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
