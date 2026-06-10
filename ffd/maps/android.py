"""Android map chunk parser — ports ``FieldClass::LoadMapInfo`` from
``libjniproxy.so``.

The Android engine uses a streaming reader (SetRomRead + RomReadByte /
UByte / ShortBig / IntBig) that consumes the map chunk byte-by-byte
after a 4-byte size-prefix wrapper. The mc_id is NOT at a fixed offset
— it comes after a variable-length per-layer descriptor + tile/attribute
payload section.

Verified 2026-05-13: 73% strict (mc_id+variant) match against 168
manually annotated maps from ``mc_overrides.json``. Of the remaining
27%, ~15 cases are "engine says slot 0 = -1" (no tileset, override
defaulted to 0) and most others are low-confidence override-defaults
that the engine disagrees with.
"""

from __future__ import annotations

import struct

from ..binary import be_u32


class _RomReader:
    """Mirrors GameClass::SetRomRead + RomRead* primitives from libjniproxy.so."""
    __slots__ = ("buf", "pos")
    def __init__(self, buf, pos=0):
        self.buf = buf
        self.pos = pos
    def u8(self):
        v = self.buf[self.pos]; self.pos += 1; return v
    def i8(self):
        v = self.buf[self.pos]; self.pos += 1
        return v if v < 0x80 else v - 0x100
    def i16be(self):
        v = struct.unpack_from(">h", self.buf, self.pos)[0]
        self.pos += 2; return v
    def i32be(self):
        v = struct.unpack_from(">i", self.buf, self.pos)[0]
        self.pos += 4; return v


def parse_android_map_engine(chunk: bytes):
    """
    Replicate FieldClass::LoadMapInfo from libjniproxy.so.

    The caller (line 98975 in the Ghidra export) does:
        LoadMapInfo(this, chunk + 4, 0)
    — i.e. the first 4 bytes of the chunk are a size-prefix wrapper that the
    engine skips. Then a streaming parse:
        u8 (discard); bool; i16BE; i16BE width; i16BE height; i16BE;
        i32BE color; 7× u8; u8 n_layers;
        per layer (7 byte header):
            bool has_tile_data; bool flag_b; bool flag_a; u8; u8; bool; bool;
        per layer (data section, only if has_tile_data):
            W*H*2 bytes of tile data;
            if flag_a: W*H bytes attribute_a;
            if flag_b: W*H bytes attribute_b;
        u8; i16BE; i16BE; u8;
        i8 mc_id_slot0; u8 variant_slot0;     ← THE ANSWER
        i8 mc_id_slot1; u8 variant_slot1;
        ...
    Returns dict or None if the chunk is malformed.
    """
    if len(chunk) < 30:
        return None
    try:
        r = _RomReader(chunk, 4)               # skip 4-byte size prefix
        r.u8()                                 # offset 4: u8 discarded
        r.u8()                                 # offset 5: bool
        r.i16be()                              # offset 6..7: i16BE (this[0x5b4])
        w = r.i16be()                          # offset 8..9: width
        h = r.i16be()                          # offset 10..11: height
        r.i16be()                              # offset 12..13: i16BE
        color = r.i32be() & 0xFFFFFFFF         # offset 14..17: i32BE color
        # offset 18..24: 7 u8 fields. From FieldClass::LoadMapInfo (libjniproxy
        # @118828-118848) these are, in order:
        #   field_bgm(0xdc5c) battle_bgm(0xaec) battle_bg(0xad8)
        #   battle_bg_water(0xae0) 0xadc 0xae4 encount_ratio(0xad4)
        misc7 = [r.u8() for _ in range(7)]
        field_bgm = misc7[0]                   # 0xdc5c -> active 0xdc58 (GetFieldBgm)
        battle_bgm = misc7[1]                  # 0xaec  -> active 0xae8  (GetBattleBgm)
        battle_bg = misc7[2]                   # 0xad8
        battle_bg_water = misc7[3]             # 0xae0
        encount_ratio = misc7[6]               # 0xad4  -> active 0xad0
        n_layers = r.u8()                      # offset 25: n_layers

        # Per-layer 7-byte header section
        layer_flags = []
        for _ in range(n_layers):
            htd = r.u8()                       # has_tile_data (pbVar1[0])
            fb  = r.u8()                       # flag_b (pbVar1[2])
            fa  = r.u8()                       # flag_a (pbVar1[1])
            r.u8(); r.u8(); r.u8(); r.u8()     # 4 more bytes (numeric + 2 bools)
            layer_flags.append((htd, fa, fb))

        # Per-layer data section (only if has_tile_data)
        for (htd, fa, fb) in layer_flags:
            if htd:
                r.pos += w * h * 2
                if fa: r.pos += w * h
                if fb: r.pos += w * h

        # Default spawn (FieldClass+0xdc48..0xdc54, libjniproxy @118922): used
        # by InitPlayer when SetMapChange is called with layer == -1 (e.g. the
        # New Game FieldMapStart) — u8 layer, BE i16 x, BE i16 y, u8 dir.
        spawn_layer = r.u8()
        spawn_x = r.i16be()
        spawn_y = r.i16be()
        spawn_dir = r.u8()
        mc0 = r.i8(); v0 = r.u8()
        mc1 = r.i8(); v1 = r.u8()

        # Overhead-layer threshold (FieldClass+0xdc2c): layers with index > this are
        # drawn ABOVE characters (overhead).  It sits 10 bytes after slot1's variant:
        # has_far(u8) + 2 far params + has_BG(u8) + 2 BG params + 2 i16BE BG shorts;
        # LoadFar/LoadBGLayerAnime consume nothing from the stream.  Default 0.
        overhead_threshold = 0
        try:
            r.u8()                       # has_far
            r.u8(); r.u8()               # far params (always read)
            r.u8()                       # has_BG
            r.u8(); r.u8()               # BG params
            r.i16be(); r.i16be()         # BG shorts
            overhead_threshold = r.u8()  # 0xdc2c
        except (IndexError, struct.error):
            overhead_threshold = 0

        return {
            "w": w, "h": h, "n_layers": n_layers, "color": color,
            "layer_flags": layer_flags,
            "mc_id_slot0": mc0, "variant_slot0": v0,
            "mc_id_slot1": mc1, "variant_slot1": v1,
            "overhead_threshold": overhead_threshold,
            "spawn_layer": spawn_layer, "spawn_x": spawn_x,
            "spawn_y": spawn_y, "spawn_dir": spawn_dir,
            "field_bgm": field_bgm, "battle_bgm": battle_bgm,
            "battle_bg": battle_bg, "battle_bg_water": battle_bg_water,
            "encount_ratio": encount_ratio,
        }
    except (IndexError, struct.error):
        return None


def parse_android_map_chunk(chunk: bytes, force_layers=None):
    """
    Parse one Android map chunk.

    Header layout (verified by hex inspection):
        [0..3]  BE u32  end-of-tile-data offset (44179 for map1)
        [4..7]  BE u32  scenario id (0x02000000 for overworld)
        [9]     map width  (tiles)
        [11]    map height (tiles)
        [22..53] table descriptor (32 bytes of structured fields)
        [54..end_field]  TILE DATA (1 layer, 2 bytes/cell, LE u16)
        [end_field..]    event scripts / NPC data

    Tile word (LE u16):
        bits 0-7  = tile_num (0-255)
        bits 8-15 = high_byte (currently mostly 0; could route to alt tileset)

    `force_layers` (1 or 2) only used as advisory if multi-layer detected.
    """
    if len(chunk) < 56:
        return None

    HEAD_SIZE = 54   # confirmed: tile data starts at offset 54

    end = be_u32(chunk, 0)
    w   = chunk[9]
    h   = chunk[11]
    n   = w * h
    if n <= 0 or w > 512 or h > 512:
        return None

    # Sanity: there must be enough room from HEAD_SIZE to end for n cells × 2 bytes
    avail_in_data_region = max(0, end - HEAD_SIZE)
    if avail_in_data_region < n * 2:
        # Map's tile region is too small — reject (or fallback)
        return None

    # Layer count detection.
    # Earlier heuristic used `avail >= n*4` which over-counted layers on
    # 1-layer maps that happen to have a trailing event-script region inside
    # `end`. That made the renderer composite garbage tiles on top.
    # New rule: 2-layer requires (a) the byte region is big enough AND (b)
    # the second-layer bytes look like real tile words — i.e. their high
    # byte is mostly 0x00 or 0x01 (the variant flag). If the high bytes are
    # mixed (which happens in event-script data), treat it as 1 layer.
    def _looks_like_tile_data(base_off):
        sample = min(n, 256)
        if base_off + sample * 2 > len(chunk):
            return False
        good = 0
        for i in range(sample):
            if chunk[base_off + i*2 + 1] in (0, 1):
                good += 1
        # ≥90% of high bytes must be 0/1 to count as real tile data
        return good * 10 >= sample * 9

    # Layer offsets via the ENGINE parser. The engine reads per-layer flags
    # (htd, flag_a, flag_b) and each layer's data section is:
    #   tile_data (W*H*2) + (attr_a if flag_a: W*H) + (attr_b if flag_b: W*H)
    # The OLD code assumed layers are packed contiguously as tile_data-only,
    # which caused layer 1 to be read from the middle of layer 0's attr_b
    # region for maps with flag_a/flag_b set — producing garbage tiles.
    engine = parse_android_map_engine(chunk)
    if engine is not None and engine["w"] == w and engine["h"] == h:
        layer_tile_data_offsets = []   # one (start, n_cells) per layer with htd
        # Re-walk: skip 4 prefix bytes + 22 fixed-header bytes + 7 bytes per layer-header
        rp = 4 + 22 + 7 * engine["n_layers"]
        for (htd, fa, fb) in engine["layer_flags"]:
            if htd:
                layer_tile_data_offsets.append((rp, w * h))
                rp += w * h * 2
                if fa: rp += w * h
                if fb: rp += w * h
            else:
                layer_tile_data_offsets.append(None)
        n_layers = sum(1 for o in layer_tile_data_offsets if o is not None)
    else:
        # Engine parse failed — fall back to the legacy heuristic
        layer_tile_data_offsets = None
        if force_layers == 1:
            n_layers = 1
        elif force_layers == 2:
            n_layers = 2 if avail_in_data_region >= n * 4 else 1
        else:
            if (avail_in_data_region >= n * 4
                    and _looks_like_tile_data(HEAD_SIZE + n * 2)):
                n_layers = 2
            else:
                n_layers = 1

    tile_start = HEAD_SIZE
    layers = []
    if layer_tile_data_offsets is not None:
        # Engine-driven: each layer has a precise start offset
        for idx, info in enumerate(layer_tile_data_offsets):
            if info is None:
                continue
            base, ncell = info
            if base + ncell * 2 > len(chunk):
                break
            cells = []
            for i in range(ncell):
                lb = chunk[base + i*2]
                hb = chunk[base + i*2 + 1]
                # high_byte is the slot selector (0 or 1). Keep the parser's
                # (mc_type, variant, tile_num) tuple shape for compatibility,
                # but encode the slot in `variant` so the renderer can dispatch
                # on it. (mc_type is 0 — the actual mc_id comes from the slot
                # lookup in _render_android_map.)
                cells.append((0, hb, lb))
            layers.append(cells)
    else:
        for L in range(n_layers):
            cells = []
            base = tile_start + L * n * 2
            if base + n*2 > len(chunk):
                break
            for i in range(n):
                lb = chunk[base + i*2]
                hb = chunk[base + i*2 + 1]
                cells.append((0, hb, lb))
            layers.append(cells)

    if not layers:
        return None

    return {"w": w, "h": h, "n_layers": len(layers), "layers": layers,
            "tile_start": tile_start, "end_field": end}
