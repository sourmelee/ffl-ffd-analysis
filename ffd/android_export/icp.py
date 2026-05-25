"""PNG -> ICP-wrapped .dat encoder (symmetric inverse of
``ffd.containers.obb.decode_icp``).

The Square Enix ICP container wraps a paletted image inside a PNG-shaped
byte stream with a 12-byte header::

    bytes  0..2   "ICP"
    byte    3     filter flag (0 = GL_LINEAR, 1 = GL_NEAREST)
    bytes  4..5   unknown1 (LE u16) -- engine-side metadata, ignored by us
    bytes  6..7   unknown2 (LE u16) -- engine-side metadata, ignored by us
    bytes  8..9   width  (LE u16)
    bytes 10..11  height (LE u16)
    bytes 12..    embedded PNG with paletted pixel data smuggled inside RGB
                  channels.

The decoder's inner pipeline is (see ``decode_icp``)::

    embedded_PNG --PIL-> RGBA bytes
    -- defilter --> df[i*3..i*3+3] = (R, G, B) for each pixel i  (drop A)
    -- unpack   --> out[k*3 + j] = df[3 + k*3 + (2 - j)]         (reverse triplets, skip 3)
                   unpacked = out[1:]                            (RemoveAt(0))
    palette  = unpacked[0:1024]   # 256 RGBA entries
    indices  = unpacked[1024:1024 + W*H]

To encode we reverse each step. See :func:`encode_icp_dat` below.
"""

from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path
from typing import Optional, Iterable, Tuple, List

from PIL import Image


class ICPEncodeError(Exception):
    """Raised when a PNG can't be encoded into ICP form (palette too large,
    dimensions out of range, etc.)."""


# Reuse the magic/constants from the existing decoder for parity.
_ICP_MAGIC = b"ICP"
_DEFAULT_FILTER_FLAG = 1   # GL_NEAREST -- right default for pixel art


# ---------------------------------------------------------------------------
# Palette extraction
# ---------------------------------------------------------------------------

def _png_to_palette_and_indices(img: Image.Image) -> Tuple[List[Tuple[int, int, int, int]], bytes, int, int]:
    """
    Turn a Pillow image into (palette_rgba_256, indices_bytes, width, height).

    Always returns exactly 256 palette entries (padded with (0,0,0,0)) and
    width*height index bytes. Used colors are placed at the front of the
    palette so unused entries don't waste a slot.

    Strategy:
      * Mode 'P': honor the existing palette + transparency chunk. This is
        the loss-free fast path -- the file is already paletted.
      * Other modes: convert to RGBA, then quantize. Fully-transparent pixels
        all map to index 0 (alpha-aware), the remaining unique colors are
        bucketed into <=255 slots via Pillow's median-cut quantizer.
    """
    W, H = img.size

    if img.mode == "P":
        pal_rgb = img.getpalette() or []
        # Pad palette out to 256 RGB triplets.
        pal_rgb = list(pal_rgb) + [0] * max(0, 256 * 3 - len(pal_rgb))
        trns = img.info.get("transparency")
        pal_rgba: List[Tuple[int, int, int, int]] = []
        for i in range(256):
            r = pal_rgb[i * 3]
            g = pal_rgb[i * 3 + 1]
            b = pal_rgb[i * 3 + 2]
            if isinstance(trns, (bytes, bytearray)):
                a = trns[i] if i < len(trns) else 255
            elif isinstance(trns, int):
                a = 0 if trns == i else 255
            else:
                a = 255
            pal_rgba.append((r, g, b, a))
        indices = img.tobytes()
        if len(indices) != W * H:
            raise ICPEncodeError(
                f"paletted PNG produced {len(indices)} index bytes, "
                f"expected {W*H}")
        return pal_rgba, indices, W, H

    # Generic path: RGBA -> alpha-aware quantization.
    rgba = img.convert("RGBA")
    px = rgba.load()

    # First pass: gather unique (r,g,b,a) tuples. We DO NOT collapse
    # (R,G,B,0) -> (0,0,0,0) because round-trip-faithfulness matters when
    # an image is later re-decoded (GIF chroma-key transparency keeps the
    # RGB channel intact and we'd otherwise lose it).
    seen: dict = {}
    flat: List[Tuple[int, int, int, int]] = []
    indices_list = bytearray(W * H)
    next_idx = 0
    for y in range(H):
        for x in range(W):
            key = px[x, y]
            if key not in seen:
                seen[key] = next_idx
                flat.append(key)
                next_idx += 1
                if next_idx > 256:
                    break
        if next_idx > 256:
            break

    if next_idx <= 256:
        # Exact: image already has <=256 colors. Build palette directly.
        pal_rgba = list(flat) + [(0, 0, 0, 0)] * (256 - len(flat))
        i = 0
        for y in range(H):
            for x in range(W):
                indices_list[i] = seen[px[x, y]]
                i += 1
        return pal_rgba, bytes(indices_list), W, H

    # >256 colors: need to quantize. Reserve index 0 for fully-transparent.
    # Mask transparent pixels with a sentinel RGB, quantize the rest to 255
    # opaque colors, then re-thread index 0 in for transparent pixels.
    rgb_only = Image.new("RGB", (W, H), (0, 0, 0))
    rgb_px = rgb_only.load()
    transparent_mask = bytearray(W * H)
    for y in range(H):
        for x in range(W):
            r, g, b, a = px[x, y]
            if a == 0:
                transparent_mask[y * W + x] = 1
                rgb_px[x, y] = (0, 0, 0)
            else:
                rgb_px[x, y] = (r, g, b)

    # `colors=255` reserves room for our explicit transparent slot at index 0.
    quantized = rgb_only.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    q_palette = quantized.getpalette() or [0] * (255 * 3)
    q_idx = quantized.tobytes()  # values in 0..254

    pal_rgba = [(0, 0, 0, 0)]  # index 0 = fully transparent
    for i in range(255):
        r = q_palette[i * 3]
        g = q_palette[i * 3 + 1]
        b = q_palette[i * 3 + 2]
        pal_rgba.append((r, g, b, 255))
    # pad to 256 (already exactly 256 here -- 1 transparent + 255 opaque)
    while len(pal_rgba) < 256:
        pal_rgba.append((0, 0, 0, 0))

    for i in range(W * H):
        if transparent_mask[i]:
            indices_list[i] = 0
        else:
            indices_list[i] = q_idx[i] + 1  # shift up to skip the transparent slot

    return pal_rgba, bytes(indices_list), W, H


# ---------------------------------------------------------------------------
# Inner pipeline: pack a flat "unpacked" stream back into an embedded PNG.
# ---------------------------------------------------------------------------

def _build_defiltered_stream(unpacked: bytes) -> bytes:
    """
    Inverse of decode's UnpackRawImage+RemoveAt(0) step.

    Given the target ``unpacked`` stream (palette + indices), construct the
    ``df`` byte buffer such that the decoder's pipeline recovers it
    verbatim.

    Decoder pipeline (per byte index k, j in 0..2)::

        out[3k + j]    = df[3 + 3k + (2 - j)]
        unpacked[m]    = out[m + 1]      # RemoveAt(0)

    We choose ``out[0]`` = 0 (decoder discards it), then assign df bytes by
    inverting the index map.
    """
    # Build "out": first byte is the discarded one, then unpacked verbatim,
    # padded to a multiple of 3 so all triplet writes are clean.
    out = bytearray(b"\x00") + bytearray(unpacked)
    while len(out) % 3 != 0:
        out.append(0)
    n_iters = len(out) // 3

    # df must cover indices [3, 3*n_iters + 2]. Bytes 0..2 are unread by
    # the decoder (it seeks to 3 immediately), so they can be anything.
    df = bytearray(3 * n_iters + 3)
    for k in range(n_iters):
        base = 3 + k * 3
        df[base + 2] = out[k * 3]
        df[base + 1] = out[k * 3 + 1]
        df[base + 0] = out[k * 3 + 2]
    return bytes(df)


def _pack_df_as_embedded_png(df: bytes, target_width: int) -> bytes:
    """
    Wrap a defiltered (R,G,B,...) stream as a PNG that Pillow can load.

    We pad df to fit a (target_width, ceil(N / target_width)) RGBA canvas,
    treat consecutive triplets as (R,G,B), and append alpha=0xFF. The
    decoder converts the embedded PNG to RGBA and drops alpha, so any
    alpha value is fine.
    """
    if target_width <= 0:
        raise ICPEncodeError("target_width must be positive")
    bytes_per_row = target_width * 3
    rows_needed = (len(df) + bytes_per_row - 1) // bytes_per_row
    emb_w = target_width
    emb_h = max(1, rows_needed)
    total_pixels = emb_w * emb_h
    pad_to = total_pixels * 3
    df_padded = bytes(df) + b"\x00" * (pad_to - len(df))

    rgba = bytearray(total_pixels * 4)
    for i in range(total_pixels):
        rgba[i * 4]     = df_padded[i * 3]
        rgba[i * 4 + 1] = df_padded[i * 3 + 1]
        rgba[i * 4 + 2] = df_padded[i * 3 + 2]
        rgba[i * 4 + 3] = 0xFF

    emb = Image.frombytes("RGBA", (emb_w, emb_h), bytes(rgba))
    bio = io.BytesIO()
    # No optimize=True: we don't need byte-identity with Square Enix's
    # PNG bytes, and skipping the optimization pass is faster.
    emb.save(bio, format="PNG", compress_level=6)
    return bio.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encode_icp_dat(
    png_input,
    *,
    original_raw: Optional[bytes] = None,
    filter_flag: int = _DEFAULT_FILTER_FLAG,
    unknown1: Optional[int] = None,
    unknown2: Optional[int] = None,
) -> bytes:
    """
    Encode a PNG into an ICP-wrapped .dat payload.

    Parameters
    ----------
    png_input
        Either a path-like to a PNG file, ``bytes`` of a PNG, or a
        ``PIL.Image.Image``.
    original_raw
        Optional bytes of the *original* raw .dat (i.e. an existing
        ``raw_obb/mon0_0.dat``). When provided AND it parses as ICP, the
        filter flag and the two "unknown" header fields are copied from
        it so round-trip stays byte-faithful at the engine-relevant
        positions. Explicit kwargs override this.
    filter_flag
        ICP byte 3 -- 0 = GL_LINEAR (smooth), 1 = GL_NEAREST (pixel art).
        Default 1.
    unknown1, unknown2
        ICP bytes 4..5 / 6..7 (LE u16) -- engine metadata. Default uses
        (width, height) when no original is supplied.
    """
    # ---- Step 1: normalize input to a Pillow Image -----------------------
    if isinstance(png_input, Image.Image):
        img = png_input
    elif isinstance(png_input, (bytes, bytearray)):
        img = Image.open(io.BytesIO(bytes(png_input)))
    else:
        img = Image.open(Path(png_input))

    palette_rgba, indices, W, H = _png_to_palette_and_indices(img)
    if W <= 0 or H <= 0:
        raise ICPEncodeError(f"invalid dimensions {W}x{H}")
    if W > 4096 or H > 4096:
        raise ICPEncodeError(f"dimensions {W}x{H} exceed engine cap 4096")

    # ---- Step 2: build the unpacked byte stream --------------------------
    # 256 palette entries x 4 bytes each (RGBA in stream order) = 1024 bytes.
    pal_bytes = bytearray(1024)
    for i, (r, g, b, a) in enumerate(palette_rgba[:256]):
        pal_bytes[i * 4] = r
        pal_bytes[i * 4 + 1] = g
        pal_bytes[i * 4 + 2] = b
        pal_bytes[i * 4 + 3] = a
    unpacked = bytes(pal_bytes) + indices  # palette + W*H indices

    # ---- Step 3: invert UnpackRawImage to get the "df" stream ------------
    df = _build_defiltered_stream(unpacked)

    # ---- Step 4: pack df into an embedded PNG ----------------------------
    # Using `W` as the embedded PNG's width matches what real ICP files do
    # in practice and keeps the embedded image vaguely image-shaped, which
    # makes inspection nicer.
    embedded_png = _pack_df_as_embedded_png(df, target_width=W)

    # ---- Step 5: pick header bytes ---------------------------------------
    use_flag = filter_flag
    use_unk1 = W if unknown1 is None else unknown1
    use_unk2 = H if unknown2 is None else unknown2
    if original_raw and len(original_raw) >= 12 and original_raw[:3] == _ICP_MAGIC:
        if unknown1 is None:
            use_unk1 = struct.unpack_from("<H", original_raw, 4)[0]
        if unknown2 is None:
            use_unk2 = struct.unpack_from("<H", original_raw, 6)[0]
        # If the caller didn't override filter_flag from the default, take
        # the original's. (Caller can still force a value by passing
        # filter_flag= explicitly.)
        if filter_flag == _DEFAULT_FILTER_FLAG:
            use_flag = original_raw[3]

    header = (
        _ICP_MAGIC
        + bytes([use_flag & 0xFF])
        + struct.pack("<HHHH", use_unk1 & 0xFFFF, use_unk2 & 0xFFFF, W, H)
    )
    return header + embedded_png


def encode_icp_directory(
    png_dir,
    out_dir,
    *,
    ref_raw_dir=None,
    pattern: str = "*.png",
    filter_flag: int = _DEFAULT_FILTER_FLAG,
    log=None,
) -> int:
    """
    Walk every PNG matching ``pattern`` under ``png_dir`` and write a parallel
    .dat tree under ``out_dir``. When ``ref_raw_dir`` is given, the
    encoder looks up an originals-side .dat with the same basename to copy
    header metadata (filter flag, unknown1, unknown2) from.

    Returns the number of files written. ``log`` is an optional
    ``print``-compatible callable for progress.
    """
    png_dir = Path(png_dir)
    out_dir = Path(out_dir)
    ref_raw_dir = Path(ref_raw_dir) if ref_raw_dir else None
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for png_path in sorted(png_dir.rglob(pattern)):
        if not png_path.is_file():
            continue
        rel = png_path.relative_to(png_dir)
        dat_name = rel.with_suffix(".dat")
        dat_path = out_dir / dat_name
        dat_path.parent.mkdir(parents=True, exist_ok=True)

        original_raw: Optional[bytes] = None
        if ref_raw_dir is not None:
            candidate = ref_raw_dir / dat_name.name
            if candidate.exists():
                try:
                    original_raw = candidate.read_bytes()
                except OSError:
                    original_raw = None

        try:
            dat_bytes = encode_icp_dat(
                png_path,
                original_raw=original_raw,
                filter_flag=filter_flag,
            )
        except Exception as exc:
            if log:
                log(f"  FAIL  {rel}: {type(exc).__name__}: {exc}")
            continue

        dat_path.write_bytes(dat_bytes)
        written += 1
        if log and written % 50 == 0:
            log(f"  wrote {written} .dat files…")
    if log:
        log(f"  total: {written} .dat files -> {out_dir}")
    return written
