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



# Canonical FFD field-character walk layout — confirmed against fldchr1 (the
# "Masked Man" sheet) by visual inspection (see Engine/README, M3b).
#   48x48 cells, origin (1,1), pitch 50.
#   ROWS = facing : Down=y1, Up=y51, Left=y101   (Right = Left flipped)
#   COLS = frame  : idle=x1, walkA=x51, walkB=x101
# IMPORTANT: field_anm's decoded sub_anims (anm5/6/7 ...) do NOT correspond to
# the cardinal walk cycles, so they must not be used for a field-walk preview.
def field_walk_entries(cell=48, pitch=50, origin=1):
    """Return playable AnimationTab entries for the real cardinal field walk
    cycles + idles. Each frame is {tex_id,x,y,w,h,duration,flip_h}."""
    def F(cx, cy, flip=False):
        return {"tex_id": 0, "x": cx, "y": cy, "w": cell, "h": cell,
                "duration": 6, "flip_h": flip}
    def cx(c):
        return origin + c * pitch
    rows = [("Down", origin), ("Up", origin + pitch), ("Left", origin + 2 * pitch)]
    out = []
    for name, ry in rows:
        out.append({"label": f"Walk {name}", "kind": "field_walk",
                    "frames": [F(cx(0), ry), F(cx(1), ry), F(cx(0), ry), F(cx(2), ry)]})
    ry = origin + 2 * pitch  # Right = Left row, flipped
    out.append({"label": "Walk Right", "kind": "field_walk",
                "frames": [F(cx(0), ry, True), F(cx(1), ry, True),
                           F(cx(0), ry, True), F(cx(2), ry, True)]})
    for name, ry, fl in (("Down", origin, False), ("Up", origin + pitch, False),
                         ("Left", origin + 2 * pitch, False), ("Right", origin + 2 * pitch, True)):
        out.append({"label": f"Idle {name}", "kind": "field_walk",
                    "frames": [F(cx(0), ry, fl)]})
    return out


def parse_btl_anm(data: bytes):
    """Parse Android ``btlanm_sp.dat`` -- battle sprite animation table.

    Verified against engine code in ``libjniproxy_c.c``:

    * ``BattleClass::SetAnmData(MtxAnmCtrl &, int entry_idx, int sub_idx)``
      at line 77816 does ``MtxAnmCtrl::SetAnimeData(entry_ptr, entry[sub_idx+1])``
      -- the same ``SetAnimeData`` function used for ``field_anm.dat``.

    Layout (verified 2026-05-27 against btlanm_sp.dat):

    * File header: same as field_anm:
        [0..3]  LE u32  n_entries (8 in FFD)
        [4..]   n_entries x LE u32 offsets to entry records.

    * Per entry (NEW container vs field_anm's hardcoded 6-sub layout):
        +0      LE u32  n_anims (variable per entry; 10 for the
                        party-member template, up to 150 for effects)
        +4..    n_anims x LE u32 offsets to SUB-BLOCKS (relative to
                                  entry start).

    * Per sub-block: ONE field_anm-style entry, embedded inline.
      6 sub-section offsets + [12B header, 10B frames, 16B anims,
                                6B loop, 8B keyframes, 20B parts].

    Each sub-block is functionally equivalent to a single
    ``field_anm.dat`` entry. The total picture is therefore: each
    "battle entry" is a *bundle* of mini-field-anm entries (probably
    idle / attack / hit / cast / KO / etc. per character template).

    Identified entries (FFD):
    * Entry 0 (9656B, 10 sub-blocks) -- universal party-member battle
      template (48x48 cells at pitch 50 -- SAME grid as field). Used
      with sheets fldchr30-49.
    * Entry 1 (1172B, 1 sub-block, 17 frames) -- simpler 1-anim template.
    * Entry 2 (1140B, 9 sub-blocks) -- UI/icons (mixed cell sizes).
    * Entry 3 (1044B, 5 sub-blocks) -- special effects.
    * Entry 4 (30308B, 150 sub-blocks) -- effects/spell template,
      varied cell sizes from 16x16 up to 480x48.
    * Entries 5-7 -- menu/banners/UI elements.

    Returns: list of "battle sub-block entries" -- flat, one per
    sub-block across all file entries. Each dict has the same shape
    as a ``parse_field_anm`` entry PLUS identifying fields:
        'btl_entry'   : file entry index (0..n_entries-1)
        'btl_sub'     : sub-block index within file entry (0..n_anims-1)
        'index'       : flat global index (for compat with field_anm
                        callers that key by 'index')
        'offset'      : absolute file offset of sub-block
        'n_frames'    : frame count
        'frames'      : list of {tex_id,x,y,w,h}
        'sub_anims'   : decoded animation list (same shape as field_anm)
        'subs'        : 6 sub-section offsets (relative to sub-block)
        'raw'         : sub-block bytes
    """
    if len(data) < 8:
        return []

    n_entries = struct.unpack("<I", data[0:4])[0]
    if n_entries < 1 or n_entries > 1024:
        return []

    file_entry_offs = []
    for i in range(n_entries):
        o = 4 + i * 4
        if o + 4 > len(data):
            break
        file_entry_offs.append(struct.unpack("<I", data[o:o+4])[0])

    def le_i16(d, o):
        return struct.unpack("<h", bytes(d[o:o+2]))[0]
    def le_i32(d, o):
        return struct.unpack("<i", bytes(d[o:o+4]))[0]
    def le_u16(d, o):
        return struct.unpack("<H", bytes(d[o:o+2]))[0]

    flat = []
    global_idx = 0
    for ei, e_base in enumerate(file_entry_offs):
        e_end = (file_entry_offs[ei + 1] if ei + 1 < len(file_entry_offs)
                 else len(data))
        if e_base + 4 > len(data):
            continue
        n_anims = struct.unpack("<I", data[e_base:e_base+4])[0]
        if n_anims < 0 or n_anims > 4096:
            continue

        sub_offs = []
        for s in range(n_anims):
            so_pos = e_base + 4 + s * 4
            if so_pos + 4 > len(data):
                break
            sub_offs.append(struct.unpack("<I", data[so_pos:so_pos+4])[0])
        sub_ends = sub_offs[1:] + [e_end - e_base]

        for si, sb_rel in enumerate(sub_offs):
            sb_abs = e_base + sb_rel
            sb_size = sub_ends[si] - sb_rel
            if sb_size <= 0 or sb_abs + 24 > len(data):
                flat.append({"btl_entry": ei, "btl_sub": si,
                             "index": global_idx, "offset": sb_abs,
                             "n_frames": 0, "frames": [], "sub_anims": [],
                             "subs": [], "raw": b""})
                global_idx += 1
                continue

            # 6 sub-section offsets relative to sub-block start
            sub_subs = []
            for ss in range(6):
                pos = sb_abs + ss * 4
                if pos + 4 > len(data):
                    sub_subs.append(0)
                else:
                    sub_subs.append(struct.unpack("<I", data[pos:pos+4])[0])

            def sub_abs(s, _base=sb_abs, _subs=sub_subs):
                return _base + _subs[s] if 0 <= s < 6 else None

            def sub_len(s, _subs=sub_subs, _size=sb_size):
                start = _subs[s]
                stop = _subs[s + 1] if s + 1 < 6 else _size
                return max(0, stop - start)

            # Header at sub[0] -- 12 bytes; u16 at +4 is n_frames
            n_frames_byte = data[sb_abs + sub_subs[0] + 4]
            n_frames_hdr = le_u16(data, sb_abs + sub_subs[0] + 4)
            n_frames_from_sub1 = sub_len(1) // 10
            n_frames = max(n_frames_hdr, n_frames_from_sub1)

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

            # Decode sub_anims using the same logic as field_anm
            sub2 = sub_abs(2); sub4 = sub_abs(4); sub5 = sub_abs(5)
            n_anims_sub = sub_len(2) // 16
            n_kf_total = sub_len(4) // 8
            n_parts = sub_len(5) // 20

            def part(p_idx, _sub5=sub5, _np=n_parts):
                if p_idx < 0 or p_idx >= _np:
                    return (-1, 0, 0)
                po = _sub5 + p_idx * 20
                if po + 20 > len(data):
                    return (-1, 0, 0)
                return (le_i16(data, po),
                        le_i16(data, po + 2),
                        le_i16(data, po + 4))

            def keyframe(k_idx, _sub4=sub4, _nkf=n_kf_total):
                if k_idx < 0 or k_idx >= _nkf:
                    return (0, -1)
                ko = _sub4 + k_idx * 8
                if ko + 8 > len(data):
                    return (0, -1)
                return (le_i16(data, ko), le_i32(data, ko + 4))

            sub_anims = []
            for a in range(n_anims_sub):
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
                    fr = frames[sp_idx] if 0 <= sp_idx < len(frames) else None
                    keyframes.append({"duration": dur, "part_idx": p_idx,
                                      "sprite_idx": sp_idx, "part_x": px,
                                      "part_y": py, "frame": fr})
                    if 0 <= sp_idx < len(frames):
                        frame_indices.append(sp_idx)
                if nkf == 0:
                    kind = "empty"; label = f"sub_anm {a:2d} (empty)"
                elif nkf == 1:
                    kind = "static"
                    label = f"sub_anm {a:2d} static · frame#{frame_indices[0] if frame_indices else '?'}"
                else:
                    kind = "cycle"
                    label = f"sub_anm {a:2d} {nkf}-frame cycle · frames {frame_indices}"
                sub_anims.append({
                    "index": a, "n_keyframes": nkf, "loop_count": loop_cnt,
                    "keyframes": keyframes, "frame_indices": frame_indices,
                    "kind": kind, "label": label,
                })

            flat.append({
                "btl_entry": ei, "btl_sub": si,
                "index": global_idx, "offset": sb_abs,
                "n_frames": len(frames), "frames": frames,
                "sub_anims": sub_anims, "subs": sub_subs,
                "raw": data[sb_abs:sb_abs + sb_size],
            })
            global_idx += 1
    return flat

