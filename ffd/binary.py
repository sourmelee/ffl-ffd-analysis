"""Low-level binary readers shared across every parser in the toolkit.

The mobile (Final Fantasy Legends) engine is mostly big-endian; the
Android (Final Fantasy Dimensions) port mostly switched to little-endian
inside ``boot_data.dat``. Both helpers live here side-by-side so callers
can pick the right one explicitly at the call site.
"""

from __future__ import annotations

import struct


def be_u8(d, o):  return d[o] & 0xFF
def be_s8(d, o):  return struct.unpack(">b", bytes([d[o]]))[0]
def be_u16(d, o): return struct.unpack(">H", bytes(d[o:o+2]))[0]
def be_u32(d, o): return struct.unpack(">I", bytes(d[o:o+4]))[0]
def le_u16(d, o): return struct.unpack("<H", bytes(d[o:o+2]))[0]
def le_u32(d, o): return struct.unpack("<I", bytes(d[o:o+4]))[0]


def read_pstr_sjis(data, pos):
    """Read length-prefixed Shift-JIS string. Returns (str, new_pos)."""
    if pos >= len(data):
        return "", pos
    n = data[pos] & 0xFF
    end = pos + 1 + n
    if end > len(data):
        end = len(data)
    s = bytes(data[pos+1:end]).decode("shift-jis", errors="replace")
    return s, end


def safe_decode_ascii(data: bytes) -> str:
    return data.decode("ascii", errors="replace").rstrip("\x00")
