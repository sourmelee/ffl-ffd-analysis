"""``ic`` image format parser + renderer (FFD_REVERSE_ENGINEERING.md §2).

The ic header is::

    "ic"   (2B magic)
    width  (BE u16)
    height (BE u16)
    nc     (u8 — palette colour count)
    palette: nc × BGR triplets (3 bytes each)
    flag   (u8) — 0xFF means "sequential, no tile table"
    [tile_table]  (1 or 2 bytes per cell, depending on image size)
    tile_data     (8×8 tiles; 4bpp if nc≤16 else 8bpp)

Tile data is treated as an addressable slice of the source buffer
(``tile_data_start + tile_num * tile_bytes``) so callers can render
without first decoding every tile.
"""

from __future__ import annotations

from typing import Optional

from PIL import Image


class ICImage:
    """Decoded ic-format image. Holds palette + a reference to the source
    buffer so we can index tile data directly by tile_num."""

    __slots__ = ("width", "height", "nc", "palette", "flag", "tile_table",
                 "tile_pixels", "header_end", "data_end",
                 "source", "tile_data_start", "tile_bytes")

    def __init__(self, width, height, nc, palette, flag, tile_table,
                 tile_pixels, header_end, data_end,
                 source=None, tile_data_start=0, tile_bytes=0):
        self.width  = width
        self.height = height
        self.nc     = nc
        self.palette = palette          # list of (r,g,b)
        self.flag   = flag
        self.tile_table = tile_table    # list[(idx, hflip, vflip)]
        self.tile_pixels = tile_pixels  # legacy: list[bytearray(64)] (may be empty)
        self.header_end = header_end
        self.data_end   = data_end
        self.source = source            # bytes — the buffer containing tile data
        self.tile_data_start = tile_data_start  # offset in source where tile bytes begin
        self.tile_bytes = tile_bytes    # 32 (4bpp) or 64 (8bpp)


def _decode_palette_bgr(raw: bytes, nc: int):
    """ic embedded palette is stored as B-G-R triplets."""
    pal = []
    for i in range(nc):
        b = raw[i*3 + 0]
        g = raw[i*3 + 1]
        r = raw[i*3 + 2]
        pal.append((r, g, b))
    return pal


def _decode_palette_rgb(raw: bytes, nc: int):
    """Container palette overrides are stored as R-G-B triplets."""
    pal = []
    for i in range(nc):
        r = raw[i*3 + 0]
        g = raw[i*3 + 1]
        b = raw[i*3 + 2]
        pal.append((r, g, b))
    return pal


def parse_ic(buf: bytes, off: int = 0) -> Optional[ICImage]:
    """
    Parse an ic image starting at `buf[off:]`. Returns ICImage or None.

    IMPORTANT: Tile data is treated as an *addressable* slice of the source
    buffer. Each tile of `tile_bytes` bytes is found at
    `tile_data_start + tile_num * tile_bytes`. We don't pre-build a fixed-
    size tile pool — the ic format permits tile_num to reference any tile
    in the contiguous data region following the table.
    """
    if off + 7 > len(buf) or buf[off:off+2] != b"ic":
        return None

    w  = (buf[off+2] << 8) | buf[off+3]
    h  = (buf[off+4] << 8) | buf[off+5]
    nc = buf[off+6]
    if not (8 <= w <= 1024 and 8 <= h <= 1024 and 1 <= nc <= 256):
        return None
    if w % 8 != 0 or h % 8 != 0:
        return None

    pal_off = off + 7
    pal = _decode_palette_bgr(buf[pal_off:pal_off + nc*3], nc)
    p   = pal_off + nc*3
    if p >= len(buf):
        return None

    flag = buf[p]
    p += 1

    n_tiles_w = w // 8
    n_tiles_h = h // 8
    n_cells   = n_tiles_w * n_tiles_h
    is_large  = (w * h) >= 4096

    # ---- Tile table ------------------------------------------------------
    tile_table = []
    if flag == 0xFF:
        # Sequential — no table; tile_data starts immediately
        for i in range(n_cells):
            tile_table.append((i, False, False))
        # tile_data_start = p (already past flag)
    else:
        # Has table; flag byte is the first byte of the table
        # so back up by 1 to include it.
        p -= 1
        if is_large:
            for i in range(n_cells):
                if p + 2 > len(buf):
                    return None
                v = (buf[p] << 8) | buf[p+1]
                p += 2
                idx   = v & 0x3FFF
                hflip = bool(v & 0x8000)
                vflip = bool(v & 0x4000)
                tile_table.append((idx, hflip, vflip))
        else:
            for i in range(n_cells):
                if p >= len(buf):
                    return None
                v = buf[p]
                p += 1
                idx   = v & 0x3F
                hflip = bool(v & 0x80)
                vflip = bool(v & 0x40)
                tile_table.append((idx, hflip, vflip))

    # ---- Tile data ------------------------------------------------------
    bpp = 4 if nc <= 16 else 8
    tile_size = 32 if bpp == 4 else 64

    return ICImage(
        width=w, height=h, nc=nc, palette=pal, flag=flag,
        tile_table=tile_table,
        # Pixels pool is now an empty list; render_ic indexes directly
        # into source bytes via _ic_source / _ic_data_start. Older callers
        # that look at tile_pixels will see [] and the renderer falls back.
        tile_pixels=[],
        header_end=pal_off + nc*3, data_end=p,
        source=buf, tile_data_start=p, tile_bytes=tile_size,
    )


def render_ic(ic: ICImage, palette=None) -> Image.Image:
    """
    Render an ICImage to a Pillow RGBA image. Index 0 is transparent.
    Tiles are addressed directly into ic.source: each tile of ic.tile_bytes
    bytes lives at ic.tile_data_start + tile_num * ic.tile_bytes.
    """
    pal = palette if palette is not None else ic.palette
    w, h = ic.width, ic.height

    src   = ic.source
    base  = ic.tile_data_start
    tb    = ic.tile_bytes          # 32 (4bpp) or 64 (8bpp)
    bpb   = 4 if tb == 32 else 8   # bytes per row of 8 pixels
    n_tw  = w // 8

    # Decode to a flat pixel-index array first (matches reference exactly)
    pixels = bytearray(w * h)
    if src is None or tb == 0:
        # Legacy fallback: use tile_pixels pool if available
        for cell_idx, (tile_idx, hflip, vflip) in enumerate(ic.tile_table):
            cx = (cell_idx % n_tw) * 8
            cy = (cell_idx // n_tw) * 8
            if tile_idx >= len(ic.tile_pixels):
                continue
            tp = ic.tile_pixels[tile_idx]
            for ty in range(8):
                sy = (7 - ty) if vflip else ty
                for tx in range(8):
                    sx = (7 - tx) if hflip else tx
                    ci = tp[sy*8 + sx]
                    pixels[(cy + ty) * w + (cx + tx)] = ci
    else:
        for ti, (tnum, hflip, vflip) in enumerate(ic.tile_table):
            tc = ti % n_tw
            tr = ti // n_tw
            tbase = base + tb * tnum
            for row in range(8):
                src_row = (7 - row) if vflip else row
                roff = tbase + src_row * bpb
                dy = tr * 8 + row
                dxb = tc * 8
                if dy >= h:
                    continue
                if tb == 32:  # 4bpp
                    for bi in range(bpb):
                        if roff + bi >= len(src):
                            break
                        b = src[roff + bi]
                        hi = (b >> 4) & 0xF
                        lo = b & 0xF
                        if hflip:
                            hi, lo = lo, hi
                            px0 = dxb + (6 - bi * 2)
                        else:
                            px0 = dxb + bi * 2
                        if 0 <= px0 < w:
                            pixels[dy * w + px0] = hi
                        if 0 <= px0 + 1 < w:
                            pixels[dy * w + px0 + 1] = lo
                else:  # 8bpp
                    for px_i in range(8):
                        if roff + px_i >= len(src):
                            break
                        dx = dxb + ((7 - px_i) if hflip else px_i)
                        if 0 <= dx < w:
                            pixels[dy * w + dx] = src[roff + px_i]

    # Convert palette indices to RGBA via a 256-entry lookup table. Index 0
    # and any index >= len(pal) are fully transparent (matching the original
    # per-pixel skip logic); every other index maps to (r, g, b, 255). Building
    # the whole RGBA buffer at once and handing it to Image.frombytes avoids
    # the per-pixel PixelAccess writes that dominated this path (~3x faster in
    # pure Python; ~10x+ when NumPy is available).
    n_pal = len(pal)
    m = min(n_pal, 256)
    try:
        import numpy as _np
        lut = _np.zeros((256, 4), dtype=_np.uint8)
        if m > 1:
            lut[1:m, :3] = _np.array(pal[:m], dtype=_np.uint8)[1:m]
            lut[1:m, 3] = 255
        idx = _np.frombuffer(bytes(pixels), dtype=_np.uint8)
        rgba = lut[idx].tobytes()
    except Exception:
        lut = [b"\x00\x00\x00\x00"] * 256
        for ci in range(1, m):
            r, g, b = pal[ci]
            lut[ci] = bytes((r, g, b, 255))
        rgba = b"".join([lut[c] for c in pixels])
    return Image.frombytes("RGBA", (w, h), rgba)


def find_ic_offsets(data: bytes):
    """Scan a cpk-style file for plausible ic image starts."""
    out = []
    pos = 0
    n = len(data)
    while pos < n - 7:
        pos = data.find(b"ic", pos)
        if pos < 0 or pos >= n - 7:
            break
        w  = (data[pos+2] << 8) | data[pos+3]
        h  = (data[pos+4] << 8) | data[pos+5]
        nc = data[pos+6]
        if 8 <= w <= 1024 and 8 <= h <= 1024 and 1 <= nc <= 256 \
           and w % 8 == 0 and h % 8 == 0:
            out.append(pos)
            pos += 7 + nc*3
        else:
            pos += 1
    return out
