"""Audio parsers (FFD_REVERSE_ENGINEERING.md §13 + §17)."""

from __future__ import annotations

import zlib

from ..monsters.parser import parse_bem


def parse_snd(data: bytes):
    """
    snd.dat = container of gzip-wrapped MFi/MLD melodies.
    Returns list of (name_index, raw_mld_bytes).
    """
    out = []
    # Walk through the file looking for gzip magic 1f 8b
    p = 16  # skip header
    n = len(data)
    idx = 0
    while True:
        p = data.find(b"\x1f\x8b", p)
        if p < 0 or p >= n - 2:
            break
        # try decompressing one stream
        try:
            d = zlib.decompressobj(31)
            inflated = d.decompress(data[p:]) + d.flush()
            consumed = len(data) - p - len(d.unused_data)
            if inflated[:4] == b"melo" or inflated[:4] == b"MTHd":
                out.append((idx, inflated))
                idx += 1
            p += consumed
            continue
        except Exception:
            pass
        p += 1
    return out


def parse_resbin(data: bytes):
    """res.bin = 7 gzip blocks. Returns list of decompressed bytes."""
    blocks = []
    p = 4   # skip the BE u32 total size
    n = len(data)
    while True:
        p = data.find(b"\x1f\x8b", p)
        if p < 0 or p >= n - 2:
            break
        try:
            d = zlib.decompressobj(31)
            infl = d.decompress(data[p:]) + d.flush()
            consumed = len(data) - p - len(d.unused_data)
            blocks.append(infl)
            p += consumed
            continue
        except Exception:
            pass
        p += 1
    return blocks


def parse_audio_names_resbin(blocks):
    """Block 2 of res.bin = list of audio (BGM/SFX) names."""
    if len(blocks) < 3:
        return []
    return parse_bem(blocks[2])
