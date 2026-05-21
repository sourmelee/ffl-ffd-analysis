"""Android ``.obb`` decoder (relocated from the top-level
``ffd_obb_extractor.py``).

The OBB shipped with Final Fantasy Dimensions is *not* a real ZIP — it is
a XOR-obfuscated custom container that wraps PNG-/OGG-/MSD-bearing
payloads. This module decodes it in memory so callers (notably
:func:`ffd.containers.archive.load_zip_container`) get the same flat
``{filename: bytes}`` dict whether the source is an extracted folder or
the raw ``.obb``.

The legacy public surface (``is_ffd_obb_path``, ``load_obb_as_dict``,
plus the low-level ``decode_icp`` / ``convert_for_proper_mode`` helpers)
is preserved verbatim.
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final Fantasy Dimensions Android .obb extractor.

Two modes:
  raw    - extract every file payload verbatim (what the OBB stores: most are
           .dat blobs even when the underlying content is a PNG or OGG).
           This is the original behaviour of this script.
  proper - same extraction, but post-process the payloads:
             * Plain PNG payloads (start with \x89PNG) are renamed .dat -> .png.
             * 'INP' + 1-byte variant prefix: strip 4 bytes, write as .png.
             * Plain OGG payloads (start with 'OggS') are renamed .dat -> .ogg.
             * 'mtxs....' (16-byte) prefix: strip 16 bytes, write as .ogg.
             * Message-data files (bem, dbgmes, msg0..msg15, sysmes,
               system_message) are renamed .msd (bytes unchanged).
             * 'ICP' + 1-byte variant prefix: a custom Square Enix tile/pixel
               container that wraps a paletted image inside a PNG-shaped
               byte stream. We decode it with a port of Colmines92's
               ICP2PNG / DefilterRawImage / UnpackRawImage logic and emit a
               palettised PNG (PLTE+tRNS+IDAT). Requires Pillow; if Pillow
               isn't available the file falls back to .dat.

           Output is intended to match Colmines92's FFDimensionsTool output
           (Android/proper_obb/) image-for-image. Note: produced PNG/OGG
           bytes are pixel/audio-equivalent but not always a byte-for-byte
           match to Colmines (different PNG filter selection, different
           zlib compression level, etc.).

Usage:
    python ffd_obb_extractor.py <path_to_obb> [--mode raw|proper] [--out DIR]
"""

import argparse
import io
import os
import struct
import sys
import zlib

# Files that proper_obb stores with a .msd extension. Bytes are unchanged from
# the .dat payload - this is purely a rename based on the in-OBB filename.
MSD_BASENAMES = {
    "bem", "dbgmes", "sysmes", "system_message",
    *(f"msg{i}" for i in range(16)),  # msg0 .. msg15
}

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
OGG_MAGIC = b"OggS"

# ---------------------------------------------------------------------------
# Custom Square Enix container magics (decoded from libjniproxy.so on 2026-05-13).
#
# INP and ICP share the same 4th-byte semantic: that byte's LSB is the texture
# INTERPOLATION FILTER flag used at GL upload time:
#   flag = 0 → GL_LINEAR  (smooth/blurry sampling)
#   flag = 1 → GL_NEAREST (pixelated/sharp sampling)
# Confirmed in MtxTexture::LoadTextureFromICPBuffer (line 57712 of
# Decomp/Functions/libjniproxy_c.c): both INP and ICP branches store
# `pcVar9[3] & 1` to MtxTexture+0x64, which is consulted by LoadMapChipImage
# to decide between GL_LINEAR (0x2601) and GL_NEAREST (0x2600).
#
# mtxs is the audio container — 16-byte header preceding an OggS or RIFF
# stream. Confirmed in MtxSoundDataReader::Open (line 53708) via the magic
# check `if (local_50 == 0x7378746d)` ("mtxs" LE u32). Layout:
#   bytes  0..3   "mtxs"
#   bytes  4..7   u32 LE - discarded by engine
#   bytes  8..11  u32 LE - stored at MtxSoundDataReader+0x20 (metadata field A)
#   bytes 12..15  u32 LE - stored at MtxSoundDataReader+0x24 (metadata field B)
#   bytes 16+    payload (OggS or RIFF)
# The 16-byte size matches what the toolkit was already stripping; we now
# know the 12 bytes after the magic carry sound metadata, not just padding.
# ---------------------------------------------------------------------------
INP_MAGIC = b"INP"                # 3-byte tag; 4th byte = (0=GL_LINEAR, 1=GL_NEAREST)
ICP_MAGIC = b"ICP"                # 3-byte tag; 4th byte = same filter flag as INP
MTXS_MAGIC = b"mtxs"
MTXS_PREFIX_LEN = 16

# Magenta marker used by FFD as "missing texture" placeholder. Colmines's tool
# detects ICP images that decode to solid magenta and emits a fully-transparent
# placeholder PNG instead. We do the same so the output matches.
PLACEHOLDER_RGBA = (255, 0, 255, 255)


def sanitize_filepath(filepath, fallback_index):
    cleaned = "".join(c for c in filepath if ord(c) >= 32)
    cleaned = cleaned.replace("\\", "/")
    for bad_char in '<>:"|?*':
        cleaned = cleaned.replace(bad_char, "_")
    cleaned = cleaned.strip()
    if not cleaned:
        return f"unknown_file_{fallback_index}.dat"
    return cleaned


# ---------------------------------------------------------------------------
# ICP decoder (port of Colmines92's ICP2PNG IL)
# ---------------------------------------------------------------------------

def _png_chunk(name, data):
    crc = zlib.crc32(name + data)
    return struct.pack(">I", len(data)) + name + data + struct.pack(">I", crc)


def _write_paletted_png(width, height, indices, palette_rgba):
    """Build a paletted PNG (PLTE+tRNS+IDAT)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0)  # color type 3 = paletted
    plte = b"".join(bytes([c[0], c[1], c[2]]) for c in palette_rgba)
    trns = bytes([c[3] for c in palette_rgba])
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # PNG filter type 0 (None)
        raw += indices[y * width:(y + 1) * width]
    idat = zlib.compress(bytes(raw))
    return (sig
            + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"PLTE", plte)
            + _png_chunk(b"tRNS", trns)
            + _png_chunk(b"IDAT", idat)
            + _png_chunk(b"IEND", b""))


def _write_transparent_rgba_png(width, height):
    """Build a fully-transparent RGBA PNG (matches Colmines's placeholder output)."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # color type 6 = RGBA
    raw = bytearray()
    for _ in range(height):
        raw.append(0)
        raw += b"\x00" * (width * 4)
    idat = zlib.compress(bytes(raw))
    return sig + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


def decode_icp(payload):
    """
    Decode an ICP\\x?? payload into a paletted PNG.

    Returns the encoded PNG bytes, or None if decoding fails (Pillow missing,
    embedded PNG malformed, etc.). Fallback handling is the caller's problem.

    Algorithm (ported from Colmines92's FFDimensionsTool ICP2PNG):
      1. Header: 4 magic bytes 'ICP<flag>' + 4 bytes (unknown1, unknown2 - LE u16)
         + 4 bytes (Width, Height - LE u16). Embedded PNG begins at offset 12.
      2. Decompress the embedded PNG's IDAT (zlib).
      3. DefilterRawImage(decompressed, width*4) - per scanline, skip the filter
         byte and pull (R, G, B) for each pixel (drop alpha). Output is a flat
         BGR-style stream (no reversal).
      4. UnpackRawImage - seek to byte 3 in defilter output, read 3-byte triplets
         and reverse each (so RGB ordering is restored), then RemoveAt(0).
      5. First 1024 bytes of the unpacked stream are 256 palette entries
         (R, G, B, A in stream order).
      6. Bytes [1024 .. 1024 + width*height) are the pixel indices.
      7. Truncate palette to (max_idx + 1) entries and emit a paletted PNG.

    Special case: if the decoded image is solid magenta (255, 0, 255), Colmines
    emits a fully-transparent RGBA placeholder. We do the same.
    """
    try:
        from PIL import Image, ImageFile
        ImageFile.LOAD_TRUNCATED_IMAGES = True
    except ImportError:
        return None

    if len(payload) < 12 or payload[:3] != ICP_MAGIC:
        return None

    width = struct.unpack_from("<H", payload, 8)[0]
    height = struct.unpack_from("<H", payload, 10)[0]
    if width <= 0 or height <= 0 or width > 4096 or height > 4096:
        return None

    embedded = payload[12:]

    # --- Decompress IDAT via Pillow (also handles unfiltering for PNG types 1..4) ---
    try:
        emb = Image.open(io.BytesIO(embedded)).convert("RGBA")
    except Exception:
        return None
    rgba = emb.tobytes()  # already-unfiltered RGBA pixel bytes in scan order

    # --- DefilterRawImage equivalent: pull (R,G,B) per pixel, drop alpha ---
    df = bytearray(len(rgba) // 4 * 3)
    for i in range(len(rgba) // 4):
        df[i*3]     = rgba[i*4]
        df[i*3 + 1] = rgba[i*4 + 1]
        df[i*3 + 2] = rgba[i*4 + 2]

    # --- UnpackRawImage: seek 3, then read 3-byte triplets reversed, RemoveAt(0) ---
    L = len(df)
    if L < 7:
        return None
    n_iters = (L - 6) // 3 + 1
    if n_iters < 1:
        return None
    out = bytearray(n_iters * 3)
    for k in range(n_iters):
        base = 3 + k * 3
        out[k*3]     = df[base + 2]
        out[k*3 + 1] = df[base + 1]
        out[k*3 + 2] = df[base]
    unpacked = bytes(out[1:])  # RemoveAt(0)

    if len(unpacked) < 4:
        return None

    # --- Parse palette (256 entries, 4 bytes each = R,G,B,A in stream order) ---
    n_pal = min(256, len(unpacked) // 4)
    palette = [
        (unpacked[i*4], unpacked[i*4 + 1], unpacked[i*4 + 2], unpacked[i*4 + 3])
        for i in range(n_pal)
    ]

    indices = unpacked[1024:1024 + width * height]
    if len(indices) < width * height:
        return None

    max_idx = max(indices)
    if max_idx >= len(palette):
        return None
    used_palette = palette[:max_idx + 1]

    # Placeholder detection: solid magenta = "missing texture" - emit transparent.
    if max_idx == 0 and used_palette[0] == PLACEHOLDER_RGBA:
        return _write_transparent_rgba_png(width, height)

    return _write_paletted_png(width, height, indices, used_palette)


# ---------------------------------------------------------------------------
# Per-payload routing for proper mode
# ---------------------------------------------------------------------------

def is_icp_payload(payload):
    return len(payload) > 4 and payload[:3] == ICP_MAGIC


def convert_for_proper_mode(filename, payload):
    """
    Decide the final filename and bytes for proper mode.
    Returns (out_filename, out_bytes, decoded_kind) where decoded_kind is one
    of {'png', 'ogg', 'msd', 'icp_decoded', 'icp_failed', 'passthrough'}.
    """
    base, ext = os.path.splitext(filename)

    # ICP first - handle whether ext is .dat OR already .png (e.g. r_chocobo.png).
    if is_icp_payload(payload):
        decoded = decode_icp(payload)
        if decoded is not None:
            return base + ".png", decoded, "icp_decoded"
        # fall back to whatever ext we have (likely .dat) on decode failure
        return filename, payload, "icp_failed"

    # Files that already have a non-.dat extension pass through unchanged.
    if ext.lower() != ".dat":
        return filename, payload, "passthrough"

    if payload.startswith(PNG_MAGIC):
        return base + ".png", payload, "png"

    if (len(payload) > 4 and payload[:3] == INP_MAGIC
            and payload[4:4 + len(PNG_MAGIC)] == PNG_MAGIC):
        return base + ".png", payload[4:], "png"

    if payload.startswith(OGG_MAGIC):
        return base + ".ogg", payload, "ogg"

    if (payload.startswith(MTXS_MAGIC)
            and len(payload) >= MTXS_PREFIX_LEN
            and payload[MTXS_PREFIX_LEN:MTXS_PREFIX_LEN + 4] == OGG_MAGIC):
        return base + ".ogg", payload[MTXS_PREFIX_LEN:], "ogg"

    base_only = os.path.basename(base)
    if base_only in MSD_BASENAMES:
        return base + ".msd", payload, "msd"

    return filename, payload, "passthrough"


# ---------------------------------------------------------------------------
# OBB parsing core (shared by extract() and load_obb_as_dict())
# ---------------------------------------------------------------------------

def is_ffd_obb_path(path) -> bool:
    """
    Cheap detection: returns True if the file at `path` looks like a Final
    Fantasy Dimensions Android .obb (vs an APK, JAR, plain ZIP, etc.).

    The OBB has its first 4 bytes in plaintext, then global-XOR 0x14 from
    byte 4 onwards. After XOR, bytes 8..12 hold the chunk count (little-
    endian u32). For a real FFD OBB this is in the low hundreds.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(12)
    except Exception:
        return False
    if len(head) < 12:
        return False
    # Decrypt bytes 4..12 with XOR 0x14 to read the chunk count.
    decrypted = bytes(b ^ 0x14 for b in head[4:12])
    num_chunks = struct.unpack("<I", decrypted[4:8])[0]
    # Real FFD OBBs have ~80 chunks. Allow a generous range.
    return 1 <= num_chunks <= 4096


def _iter_obb_entries(data: bytearray, mode: str):
    """
    Yield (out_filename, out_bytes, kind) for every file in the OBB payload.
    `data` must be the post-XOR-decrypted byte buffer.

    `mode` is "raw" (verbatim payloads) or "proper" (post-processed via
    convert_for_proper_mode). Counts are not tracked here — the caller can
    aggregate from the yielded `kind` strings if it wants.
    """
    num_chunks = struct.unpack("<I", data[8:12])[0]
    chunk_offsets = []
    for i in range(num_chunks + 1):
        ptr = 12 + (i * 4)
        chunk_offsets.append(struct.unpack("<I", data[ptr:ptr + 4])[0])

    fat_start = chunk_offsets[0]
    info_size = struct.unpack("<I", data[fat_start + 8: fat_start + 12])[0]
    num_files = struct.unpack("<I", data[fat_start + 16: fat_start + 20])[0]
    str_block_abs = fat_start + info_size
    records_start = fat_start + 20

    for i in range(num_files):
        entry_ptr = records_start + (i * 24)
        if entry_ptr + 24 > len(data):
            break
        name_offset, c_size, u_size, chunk_id, d_offset, d_high = struct.unpack(
            "<IIIIII", data[entry_ptr:entry_ptr + 24]
        )
        str_start = str_block_abs + name_offset + 1
        if str_start >= len(data):
            continue
        str_end = str_start
        while str_end < len(data) and data[str_end] != 0:
            str_end += 1
        raw_name_str = bytes(data[str_start:str_end]).decode("utf-8", "ignore")
        filename = sanitize_filepath(raw_name_str, i)

        if chunk_id >= len(chunk_offsets):
            continue
        abs_offset = chunk_offsets[chunk_id] + d_offset
        if abs_offset + c_size > len(data):
            continue
        file_data = bytes(data[abs_offset: abs_offset + c_size])

        if mode == "proper":
            yield convert_for_proper_mode(filename, file_data)
        else:
            yield (filename, file_data, "raw")


def _decrypted_obb_bytes(obb_path) -> bytearray:
    """Read an .obb file and apply the global XOR 0x14 from byte 4 onwards."""
    with open(obb_path, "rb") as f:
        data = bytearray(f.read())
    for i in range(4, len(data)):
        data[i] ^= 0x14
    return data


def load_obb_as_dict(obb_path, mode: str = "proper"):
    """
    Decode an FFD .obb file in memory and return an OrderedDict[str, bytes]
    keyed by the same filenames Colmines's tool would write to proper_obb/.

    Used by ffd_toolkit.py so loading an .obb file directly works without
    pre-extraction. Pillow is needed for ICP decoding; missing Pillow means
    ICP files fall through as .dat (everything else still works).
    """
    from collections import OrderedDict
    data = _decrypted_obb_bytes(obb_path)
    out = OrderedDict()
    for out_filename, out_bytes, _kind in _iter_obb_entries(data, mode):
        out[out_filename] = out_bytes
    return out


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract(obb_path, out_dir, mode):
    print(f"[*] Loading archive: {obb_path}...")
    print("[*] Decrypting OBB (Global XOR 0x14)...")
    data = _decrypted_obb_bytes(obb_path)

    num_chunks = struct.unpack("<I", data[8:12])[0]
    print(f"[+] FAT synchronized! Found {num_chunks} Data Chunks.")
    print(f"[+] Extracting in '{mode}' mode...\n")

    os.makedirs(out_dir, exist_ok=True)
    success = 0
    counts = {"png": 0, "ogg": 0, "msd": 0, "icp_decoded": 0, "icp_failed": 0}

    for out_filename, out_bytes, kind in _iter_obb_entries(data, mode):
        if kind in counts:
            counts[kind] += 1
        out_path = os.path.join(out_dir, out_filename)
        parent = os.path.dirname(out_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        try:
            with open(out_path, "wb") as f_out:
                f_out.write(out_bytes)
            success += 1
        except Exception:
            pass
        if success > 0 and success % 500 == 0:
            print(f"    ... extracted {success} files")

    print(f"\n[SUCCESS] Extracted {success} files to '{out_dir}'.")
    if mode == "proper":
        print(f"          PNG (passthrough/INP): {counts['png']}")
        print(f"          OGG (passthrough/mtxs): {counts['ogg']}")
        print(f"          MSD (renamed):         {counts['msd']}")
        print(f"          ICP decoded -> PNG:    {counts['icp_decoded']}")
        if counts["icp_failed"]:
            print(f"          ICP decode FAILED:     {counts['icp_failed']} (left as .dat)")


def main():
    parser = argparse.ArgumentParser(
        description="Extract files from a Final Fantasy Dimensions main.obb."
    )
    parser.add_argument("obb_path", help="Path to main.obb")
    parser.add_argument(
        "--mode", choices=("raw", "proper"), default="raw",
        help="raw = verbatim payloads (.dat); proper = decode into .png/.ogg/.msd",
    )
    parser.add_argument(
        "--out", default=None,
        help="Output directory (default: obb_extracted_perfect for raw, obb_extracted_proper for proper)",
    )
    args = parser.parse_args()
    out_dir = args.out or (
        "obb_extracted_proper" if args.mode == "proper" else "obb_extracted_perfect"
    )
    extract(args.obb_path, out_dir, args.mode)


if __name__ == "__main__":
    main()
