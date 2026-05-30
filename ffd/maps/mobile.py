"""Mobile (FOMA) map chunk + mpk index parsing.

The mobile build packs maps into ``mpk*.dat`` pack files; an optional
mpk index (when present in boot_data) gives per-map (id, offset, size).
Without the index we fall back to a forwards-walking heuristic.
"""

from __future__ import annotations

import struct



def parse_mobile_map_chunk(chunk: bytes):
    """
    Parse one mobile map chunk. Header layout (from working reference):
        [5]      ts0 cpk entry_id   (255 = none)
        [6]      ts1 cpk entry_id   (255 = none)
        [7]      ts0 palette index
        [8]      ts1 palette index
        [9]      map width  (tiles)
        [10]     map height (tiles)
        [30..34] BE u32  layer flags  (bit 0 = layer 0, bit 1 = layer 1)
        [34]     name length
        [35..]   name bytes (Shift-JIS)
        [tiles]  tile data
    Tile encoding:
      Both layers active: 3 bytes/tile, 24-bit BE value;
        layer0_id = value & 0xFFF; layer1_id = (value >> 12) & 0xFFF
      Single layer w/ 2 tilesets: 2 bytes/tile (BE u16); high byte = sel,
        low byte = tile_num.
      Single layer w/ 1 tileset: 1 byte/tile = tile_num for the only ts.
    Each id splits as: ts_sel = (id >> 8) & 0xF, tile_num = id & 0xFF.
    """
    if len(chunk) < 36:
        return None
    ts0_id = chunk[5]
    ts1_id = chunk[6]
    pal0   = chunk[7]
    pal1   = chunk[8]
    w = chunk[9]
    h = chunk[10]
    if w == 0 or h == 0 or w > 200 or h > 200:
        return None
    field_356 = struct.unpack(">I", chunk[30:34])[0]
    layer0 = bool(field_356 & 1)
    layer1 = bool(field_356 & 2)
    name_len = chunk[34]
    name_end = 35 + name_len
    if name_len > 64 or name_end > len(chunk):
        return None
    try:
        name = bytes(chunk[35:name_end]).decode("shift-jis", errors="replace")
    except Exception:
        name = "<bad-name>"
    tile_start = name_end
    n_ts = (1 if ts0_id != 255 else 0) + (1 if ts1_id != 255 else 0)
    if layer0 and layer1:
        bpt = 3
    elif n_ts == 2:
        bpt = 2
    else:
        bpt = 1
    n = w * h
    tile_end = tile_start + n * bpt
    if tile_end > len(chunk):
        # truncated — render whatever we have
        tile_end = len(chunk)
    return {
        "name": name, "w": w, "h": h,
        "tile_start": tile_start, "tile_end": tile_end,
        "bpt": bpt,
        "tile_data": bytes(chunk[tile_start:tile_end]),
        "ts0_id": ts0_id, "ts1_id": ts1_id,
        "pal0": pal0, "pal1": pal1,
        "layer0": layer0, "layer1": layer1,
        "n_ts": n_ts,
    }


def scan_mobile_mpk_chunks(data: bytes, mpk_index_for_pack=None):
    """
    Scan a mobile mpk*.dat for chunk boundaries.

    If `mpk_index_for_pack` is provided, it should be a list of
    (map_id, offset, size) tuples for THIS pack file. We use it directly
    for chunk boundaries — this is the accurate path.

    Otherwise we fall back to a heuristic: try to parse the chunk header
    starting at offset 0, and use `name_end + w*h*bpt` to find the next
    chunk start.

    Yields dicts with:
      'offset'       : chunk start in pack
      'chunk_size'   : full size including event-script region
      'tile_end'     : tile-data end offset within the chunk
      'parsed'       : output of parse_mobile_map_chunk
      'script_bytes' : raw bytes of the event-script region (may be empty)
      'map_id'       : map id (only if mpk_index_for_pack is provided)
    """
    if mpk_index_for_pack is not None:
        for entry in mpk_index_for_pack:
            if isinstance(entry, dict):
                map_id = entry.get("map_id", 0)
                off    = entry.get("offset", 0)
                size   = entry.get("size", 0)
            else:
                map_id, off, size = entry[0], entry[1], entry[2]
            if off + size > len(data) or size <= 0:
                continue
            chunk = bytes(data[off:off + size])
            parsed = parse_mobile_map_chunk(chunk)
            if parsed is None:
                continue
            tile_end = parsed["tile_end"]
            script = chunk[tile_end:] if tile_end < len(chunk) else b""
            yield {
                "offset": off, "chunk_size": size,
                "tile_end": tile_end, "parsed": parsed,
                "script_bytes": script,
                # Full chunk bytes — required by parse_mobile_event_region,
                # which calls _mobile_true_event_offset on the entire chunk.
                "chunk": chunk,
                "map_id": map_id,
            }
        return

    # Heuristic fallback — walk forwards using parsed chunk sizes.
    # A memoryview makes the per-offset slice O(1): the previous
    # ``data[pos:pos + 0x40000]`` copied up to 256 KB on *every* byte we
    # stepped over. ``len``/indexing/``struct``/``bytes()`` all behave
    # identically on a memoryview slice, and parse_mobile_map_chunk already
    # materialises its output to ``bytes``, so results are unchanged.
    mv = memoryview(data)
    pos = 0
    n = len(data)
    while pos < n - 36:
        # Try to parse a chunk starting here
        # The chunk extends at least to tile_end; we don't know its full
        # size without an index, so we use tile_end as a lower bound and
        # advance there, accepting that any event-script region may bleed
        # into the next chunk.
        parsed = parse_mobile_map_chunk(mv[pos:pos + 0x40000])
        if parsed and parsed["w"] >= 4 and parsed["h"] >= 4:
            tile_end = parsed["tile_end"]
            yield {
                "offset": pos, "chunk_size": tile_end,
                "tile_end": tile_end, "parsed": parsed,
                "script_bytes": b"",
            }
            pos += tile_end
            continue
        pos += 1


def parse_mobile_mpk(data: bytes, mpk_index_for_pack=None):
    """
    Mobile mpk*.dat: variable-width pack index then map chunks.
    Delegates to scan_mobile_mpk_chunks. If `mpk_index_for_pack` (a list of
    (map_id, offset, size)) is provided, uses it directly; otherwise scans.

    Yields (offset, parsed_chunk_dict).
    """
    for entry in scan_mobile_mpk_chunks(data, mpk_index_for_pack):
        yield entry["offset"], entry["parsed"]


def parse_mpkh_index(data: bytes):
    """
    Android mpkh*.dat index. Returns list-of-list:
    packs[pack_idx] = [(map_id, offset_in_packfile, size), ...]

    Format (confirmed from pack file sizes):
      [0..3]  4 bytes header
      [4]     cnt_b  - bytes for entry count per pack
      [5]     id_b   - bytes for map ID
      [6]     sz_b   - bytes for chunk size  (INDIVIDUAL size, NOT cumulative)
      [7]     n_packs
      For each pack: count × (id + size) entries

    Offsets are computed as running sums of preceding sizes within the pack.
    """
    if len(data) < 8:
        return []
    cnt_b   = data[4]
    id_b    = data[5]
    sz_b    = data[6]
    n_packs = data[7]
    p = 8

    def rN(width):
        nonlocal p
        v = 0
        for k in range(width):
            v = (v << 8) | data[p+k]
        p += width
        return v

    packs = []
    for _pi in range(n_packs):
        if p >= len(data):
            break
        n_entries = rN(cnt_b)
        entries = []
        running_off = 0
        for _ in range(n_entries):
            if p + id_b + sz_b > len(data):
                break
            mid  = rN(id_b)
            size = rN(sz_b)
            entries.append((mid, running_off, size))
            running_off += size
        packs.append(entries)
    return packs
