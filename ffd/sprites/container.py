"""Sprite-container ``.dat`` parsers (FFD_REVERSE_ENGINEERING.md §3).

Walks the TOC, optionally decodes the per-entry sub-offset table, and
yields ic images (with palette variants) for the caller.
"""

from __future__ import annotations

from ..binary import be_u32
from ..images.ic import ICImage, parse_ic, _decode_palette_rgb


def parse_sprite_container(data: bytes):
    """
    Parse a sprite-container .dat (chpk, ene, bg, feimg, img_etc, cpk).
    Yields (entry_index, variant_index, ICImage_or_None, raw_bytes_subset).
    """
    if len(data) < 4:
        return
    first_off = be_u32(data, 0)
    if first_off == 0 or first_off > len(data) or first_off % 4 != 0:
        return
    n_entries = first_off // 4

    # Read all offsets (None for empty/invalid entries — don't break the loop!)
    entry_offs = []
    for i in range(n_entries):
        if 4 * i + 4 > len(data):
            break
        eo = be_u32(data, 4 * i)
        if eo == 0 or eo > len(data):
            entry_offs.append(None)
        else:
            entry_offs.append(eo)

    # End-of-entry = next non-None offset; precompute in one reverse pass (O(n)).
    _eof = len(data)
    next_off = [_eof] * len(entry_offs)
    _nxt = _eof
    for j in range(len(entry_offs) - 1, -1, -1):
        next_off[j] = _nxt
        if entry_offs[j] is not None:
            _nxt = entry_offs[j]

    for i, eo in enumerate(entry_offs):
        if eo is None:
            continue
        e_end = next_off[i]
        entry_blob = data[eo:e_end]
        if len(entry_blob) < 4:
            continue

        first_sub = be_u32(entry_blob, 0)
        decoded = False

        # Direct entry: ic image immediately after a single 8-byte prefix
        if (first_sub == 8 and len(entry_blob) >= 10
                and entry_blob[8:10] == b"ic"):
            ic = parse_ic(entry_blob, 8)
            if ic:
                yield (i, 0, ic, entry_blob[8:ic.data_end])
                decoded = True
            if decoded:
                continue

        # Container entry: sub-offset table, sub[0] = ic, sub[1..] = palettes
        if first_sub % 4 == 0 and first_sub <= len(entry_blob):
            n_subs = first_sub // 4
            sub_offs = []
            ok = True
            for s in range(n_subs):
                if 4*s + 4 > len(entry_blob):
                    ok = False; break
                so = be_u32(entry_blob, 4*s)
                if so == 0 or so > len(entry_blob):
                    ok = False; break
                sub_offs.append(so)
            if ok and sub_offs:
                ic = parse_ic(entry_blob, sub_offs[0])
                if ic is not None:
                    yield (i, 0, ic,
                           entry_blob[sub_offs[0]:ic.data_end])
                    decoded = True
                    # Palette variants
                    for v_idx in range(1, len(sub_offs)):
                        pstart = sub_offs[v_idx]
                        pend   = (sub_offs[v_idx+1]
                                  if v_idx + 1 < len(sub_offs)
                                  else len(entry_blob))
                        pal_raw = entry_blob[pstart:pend]
                        if len(pal_raw) >= ic.nc * 3:
                            new_pal = _decode_palette_rgb(pal_raw, ic.nc)
                            ic2 = ICImage(
                                width=ic.width, height=ic.height, nc=ic.nc,
                                palette=new_pal, flag=ic.flag,
                                tile_table=ic.tile_table,
                                tile_pixels=ic.tile_pixels,
                                header_end=ic.header_end,
                                data_end=ic.data_end,
                                source=ic.source,
                                tile_data_start=ic.tile_data_start,
                                tile_bytes=ic.tile_bytes,
                            )
                            yield (i, v_idx, ic2, pal_raw)
                    continue

        # Fallback: scan for an "ic" magic anywhere in the first 32 bytes.
        # Catches entries with an unusual prefix that neither layout above
        # recognises (the cause of "ene.dat returned 0 sprites" for some
        # chapter scratchpads — the entries WERE there, but the parser bailed
        # because first_sub wasn't 8 and the bytes didn't form a sub-offset
        # table).
        scan_limit = min(32, len(entry_blob) - 2)
        for j in range(scan_limit):
            if entry_blob[j:j+2] == b"ic":
                ic = parse_ic(entry_blob, j)
                if ic is not None:
                    yield (i, 0, ic, entry_blob[j:ic.data_end])
                    decoded = True
                    break


def iter_dat_entries(data: bytes):
    """
    Yield (entry_index, entry_blob) for every entry in a sprite-container
    .dat file. Same TOC walk as `parse_sprite_container` but yields RAW
    entry bytes regardless of whether they decode as 'ic'. Use this to do
    custom analyses (e.g. GIF magic search, header reverse engineering).
    """
    if len(data) < 4:
        return
    first_off = be_u32(data, 0)
    if first_off == 0 or first_off > len(data) or first_off % 4 != 0:
        return
    n_entries = first_off // 4
    entry_offs = []
    for i in range(n_entries):
        if 4 * i + 4 > len(data):
            break
        eo = be_u32(data, 4 * i)
        if eo == 0 or eo > len(data):
            entry_offs.append(None)
        else:
            entry_offs.append(eo)

    # Precompute next non-None offset in one reverse pass (O(n)).
    _eof = len(data)
    next_off = [_eof] * len(entry_offs)
    _nxt = _eof
    for j in range(len(entry_offs) - 1, -1, -1):
        next_off[j] = _nxt
        if entry_offs[j] is not None:
            _nxt = entry_offs[j]

    for i, eo in enumerate(entry_offs):
        if eo is None:
            continue
        e_end = next_off[i]
        yield i, data[eo:e_end]


def extract_hidden_gifs(data: bytes):
    """
    Scan a sprite-container .dat for entries containing hidden GIF data.

    GIFs are wrapped in custom engine headers (variable-size — anchor points,
    hitboxes, animation framing data, etc. that the engine cares about). The
    actual GIF payload starts at the first occurrence of `GIF89a` or
    `GIF87a` within the entry blob.

    Designed to be run AFTER `parse_sprite_container`: entries that decode
    cleanly as 'ic' typically won't trigger here, while entries the standard
    parser silently dropped often DO contain valid animated GIFs.

    Yields (entry_index, header_size, gif_bytes). header_size is the byte
    offset of the GIF magic within the entry — useful for reverse-engineering
    the proprietary header schema in a follow-up pass.
    """
    GIF_MAGICS = (b"GIF89a", b"GIF87a")
    for entry_idx, entry_blob in iter_dat_entries(data):
        idx = -1
        for magic in GIF_MAGICS:
            j = entry_blob.find(magic)
            if j != -1:
                idx = j
                break
        if idx == -1:
            continue
        gif_bytes = entry_blob[idx:]
        # Sanity: a GIF needs at minimum the 6-byte magic + 7-byte Logical
        # Screen Descriptor.
        if len(gif_bytes) < 13:
            continue
        yield entry_idx, idx, gif_bytes


def parse_bip(data: bytes):
    """
    Parse bip.dat (3-group container).
    Yields (group_index, entry_index, variant_index, ICImage).
    """
    if len(data) < 16:
        return
    g_offs = [be_u32(data, 0), be_u32(data, 4), be_u32(data, 8)]
    g_offs_sentinel = be_u32(data, 12)
    bounds = g_offs + [g_offs_sentinel if g_offs_sentinel > g_offs[-1]
                       else len(data)]
    for gi in range(3):
        gstart = g_offs[gi]
        gend   = bounds[gi+1] if bounds[gi+1] > gstart else len(data)
        if gstart >= len(data) or gstart >= gend:
            continue
        sub = data[gstart:gend]
        for (e_idx, v_idx, ic, _raw) in parse_sprite_container(sub):
            yield (gi, e_idx, v_idx, ic)
