"""``field_anm.dat`` parser — Android field-character animation data.

Verified against engine code in ``libjniproxy.so``:

* ``MtxAnmCtrl::SetAnimeData`` controls the per-entry animation table
* ``MtxAnmData::Draw`` consumes the keyframe + part records

Each entry exposes a flat frame table plus a decoded list of
sub-animations (static frames, walk cycles, etc.) with playback
metadata so callers can preview without re-walking the raw structures.
"""

from __future__ import annotations

import struct


def parse_field_anm(data: bytes):
    """
    Parse Android field_anm.dat — both the flat frame table AND the per-entry
    animation sequences decoded from sub[2..5].

    File layout:
      [0..3]  LE u32  n_entries (63 in FFD)
      [4..]   n_entries × LE u32  absolute offsets to entry records

    Per-entry layout (verified against engine — see MtxAnmCtrl::SetAnimeData
    and MtxAnmData::Draw in libjniproxy.so):
      +0  : 6 × LE u32   sub-section offsets (relative to entry start)
              sub[0] (24..) — 12-byte header  (u32, u16 sVar6, u16 sVar7, …)
              sub[1] (36..) — flat FRAME table (10 bytes per record):
                  LE u16  tex_id (always 0 — engine binds character sheet)
                  LE u16  src_y
                  LE u16  src_x
                  LE u16  w
                  LE u16  h
              sub[2]        — ANIMATION table (16 bytes per record):
                  LE i32  n_keyframes
                  LE i32  sub4_offset (= keyframe table base, in 8-byte units)
                  LE i32  loop_count
                  LE i32  sub3_offset (= loop info table)
              sub[3]        — loop info (6 bytes per record):
                  LE i16  loop_start
                  LE i16  loop_end (or duration)
                  LE i16  loop_step
              sub[4]        — KEYFRAME table (8 bytes per record):
                  LE i16  duration (field ticks)
                  LE i32  part_index  (into sub[5])
                  LE i16  ?
              sub[5]        — PART table (20 bytes per record):
                  LE i16  sprite_idx (into sub[1] frame table) — -1 = no draw
                  LE i16  part_x
                  LE i16  part_y
                  LE i16  …
                  LE i16  rotation (degrees ×1, scaled)
                  LE u32  color (RGBA-ish)
                  LE i16  flip / flags
                  … (20 bytes total)

    Returns: list of dicts, one per entry, each with:
      'index'     : entry index
      'offset'    : absolute file offset
      'n_frames'  : frame count (= len(frames), from sub[0]+4 u16)
      'frames'    : list of dicts {tex_id, x, y, w, h} from sub[1]
      'sub_anims' : list of decoded animations (see below)
      'subs'      : list of 6 sub-offsets (relative to entry start)
      'raw'       : entry bytes

    Each sub_anim is a dict:
      'index'        : index inside this entry's sub[2] table
      'n_keyframes'  : number of keyframes
      'loop_count'   : loop count from sub[2]
      'keyframes'    : list of dicts {duration, sprite_idx, part_x, part_y,
                                      frame: {tex_id,x,y,w,h} or None}
      'frame_indices': list of sprite indices (into 'frames'), in playback order
      'kind'         : 'static' if n_keyframes==1, 'cycle' if >1
      'label'        : human-readable label (e.g. "Static frame#3 (col 1, y=1)",
                                                   "Walk cycle (col 0)")
    """
    if len(data) < 8:
        return []

    n_entries = struct.unpack("<I", data[0:4])[0]
    if n_entries < 1 or n_entries > 1024:
        return []

    offsets = []
    for i in range(n_entries):
        o = 4 + i * 4
        if o + 4 > len(data):
            break
        offsets.append(struct.unpack("<I", data[o:o+4])[0])

    def le_i16(d, o):
        return struct.unpack("<h", bytes(d[o:o+2]))[0]
    def le_i32(d, o):
        return struct.unpack("<i", bytes(d[o:o+4]))[0]
    def le_u16(d, o):
        return struct.unpack("<H", bytes(d[o:o+2]))[0]

    entries = []
    for i, base in enumerate(offsets):
        # Entry size = distance to next entry (or end of file)
        end_of_entry = (offsets[i + 1] if i + 1 < len(offsets)
                        else len(data))
        if base + 36 > len(data):
            entries.append({
                "index": i, "offset": base, "n_frames": 0,
                "frames": [], "sub_anims": [], "subs": [], "raw": b""})
            continue

        # 6 sub-section offsets
        subs = []
        for s in range(6):
            so = base + s * 4
            if so + 4 > len(data):
                subs.append(0)
            else:
                subs.append(struct.unpack("<I", data[so:so+4])[0])

        # Sub-section absolute spans
        def sub_abs(s):
            return base + subs[s] if 0 <= s < 6 else None

        def sub_len(s):
            start = subs[s]
            stop = subs[s + 1] if s + 1 < 6 else (end_of_entry - base)
            return max(0, stop - start)

        # n_frames at entry+28 (single byte in old code; verified vs sub[1]
        # length = n_frames * 10).
        n_frames_byte = data[base + 28] if base + 28 < len(data) else 0
        n_frames_from_sub1 = sub_len(1) // 10
        n_frames = max(n_frames_byte, n_frames_from_sub1)

        # Decode sub[1] frame table
        frames = []
        sub1 = sub_abs(1)
        for f in range(n_frames):
            fo = sub1 + f * 10
            if fo + 10 > len(data):
                break
            tex = le_u16(data, fo)
            src_y = le_u16(data, fo + 2)
            src_x = le_u16(data, fo + 4)
            w = le_u16(data, fo + 6)
            h = le_u16(data, fo + 8)
            frames.append({"tex_id": tex, "x": src_x, "y": src_y,
                           "w": w, "h": h})

        # --- Decode sub_anims ----------------------------------------------
        sub2 = sub_abs(2); sub4 = sub_abs(4); sub5 = sub_abs(5)
        n_anims = sub_len(2) // 16
        n_kf_total = sub_len(4) // 8
        n_parts = sub_len(5) // 20

        def part(p_idx):
            """Return (sprite_idx, x, y) from sub[5] part record."""
            if p_idx < 0 or p_idx >= n_parts:
                return (-1, 0, 0)
            po = sub5 + p_idx * 20
            if po + 20 > len(data):
                return (-1, 0, 0)
            sp = le_i16(data, po)
            x = le_i16(data, po + 2)
            y = le_i16(data, po + 4)
            return (sp, x, y)

        def keyframe(k_idx):
            """Return (duration, part_idx) from sub[4] keyframe record."""
            if k_idx < 0 or k_idx >= n_kf_total:
                return (0, -1)
            ko = sub4 + k_idx * 8
            if ko + 8 > len(data):
                return (0, -1)
            dur = le_i16(data, ko)
            p_off = le_i32(data, ko + 4)
            return (dur, p_off)

        sub_anims = []
        for a in range(n_anims):
            ao = sub2 + a * 16
            if ao + 16 > len(data):
                break
            nkf = le_i32(data, ao)
            kf_off = le_i32(data, ao + 4)
            loop_cnt = le_i32(data, ao + 8)
            lp_off = le_i32(data, ao + 12)
            if nkf < 0 or nkf > 64:
                nkf = max(0, min(nkf, 64))
            keyframes = []
            frame_indices = []
            for k in range(nkf):
                dur, p_idx = keyframe(kf_off + k)
                sp_idx, px, py = part(p_idx)
                frame_rect = (frames[sp_idx]
                              if 0 <= sp_idx < len(frames) else None)
                keyframes.append({
                    "duration": dur, "part_idx": p_idx,
                    "sprite_idx": sp_idx, "part_x": px, "part_y": py,
                    "frame": frame_rect,
                })
                if 0 <= sp_idx < len(frames):
                    frame_indices.append(sp_idx)

            # Heuristic label.  Each "column" in the frame table (frames with
            # the same src_x) tends to be one facing direction.  Multi-keyframe
            # anims that pull all their frames from one column = directional
            # walk cycle.
            if nkf == 0:
                kind = "empty"; label = f"anm {a:2d}  (empty)"
            elif nkf == 1:
                kind = "static"
                if keyframes[0]["frame"]:
                    fr = keyframes[0]["frame"]
                    label = (f"anm {a:2d}  static · frame#{keyframes[0]['sprite_idx']} "
                             f"at ({fr['x']},{fr['y']})")
                else:
                    label = f"anm {a:2d}  static · frame#?"
            else:
                kind = "cycle"
                cols = set()
                for kf in keyframes:
                    if kf["frame"] is not None:
                        cols.add(kf["frame"]["x"])
                if len(cols) == 1:
                    col_x = next(iter(cols))
                    label = (f"anm {a:2d}  {nkf}-frame cycle · "
                             f"col x={col_x} · frames "
                             f"[{','.join('#'+str(i) for i in frame_indices)}]")
                else:
                    label = (f"anm {a:2d}  {nkf}-frame cycle · "
                             f"frames [{','.join('#'+str(i) for i in frame_indices)}]")
            sub_anims.append({
                "index": a, "n_keyframes": nkf, "loop_count": loop_cnt,
                "keyframes": keyframes, "frame_indices": frame_indices,
                "kind": kind, "label": label,
            })

        entries.append({
            "index": i, "offset": base, "n_frames": len(frames),
            "frames": frames, "sub_anims": sub_anims,
            "subs": subs, "raw": data[base:end_of_entry],
        })

    return entries
