"""Dialogue/text parsers (FFD_REVERSE_ENGINEERING.md §18).

``message.dat`` (mobile) is a multi-section length-prefixed Shift-JIS
container; ``.msd`` (Android) reuses the same shape but stores UTF-8
strings. :func:`parse_msd` probes for the multi-section header first
and falls back to a flat string scan for files like ``bem.msd``.
"""

from __future__ import annotations

from ..binary import le_u32


MESSAGE_SECTION_LABELS = [
    "Common UI/menus",       # 0
    "Common shared",         # 1
    "Ch1 Light",             # 2
    "Ch2 Light",             # 3
    "Ch3 Light",             # 4
    "Ch4 Light",             # 5
    "Ch5 Light",             # 6
    "Ch1 Dark",              # 7
    "Ch2 Dark",              # 8
    "Ch3 Dark",              # 9
    "Ch4 Dark",              # 10
    "Ch5 Dark",              # 11
    "Ch6 (both)",            # 12
    "Ch7 Final",             # 13
    "Cutscenes / boss",      # 14
    "Challenge Dungeon",     # 15
]


def parse_message(data: bytes):
    """Parse message.dat into list-of-list-of-strings (per section)."""
    if len(data) < 8:
        return []
    n_sections = le_u32(data, 0)
    if not (1 <= n_sections <= 64):
        return []
    offs = []
    for i in range(n_sections):
        if 4 + 4*(i+1) > len(data):
            return []
        offs.append(le_u32(data, 4 + 4*i))
    offs.append(len(data))

    sections = []
    for s in range(n_sections):
        start = offs[s]
        end   = offs[s+1] if offs[s+1] >= start else len(data)
        strs = []
        p = start
        while p < end:
            L = data[p]
            if L == 0:
                p += 1
                continue
            if p + 1 + L > end:
                break
            try:
                strs.append(bytes(data[p+1:p+1+L]).decode("shift-jis",
                                                         errors="replace"))
            except Exception:
                strs.append(f"<decode-error len={L}>")
            p += 1 + L
        sections.append(strs)
    return sections


def parse_msd(data: bytes, encoding: str = "utf-8") -> list:
    """
    Parse a single .msd dialogue/text file from the Android .obb.

    The .msd files (msg0.msd … msg15.msd, bem.msd, etc.) are English
    counterparts to the Japanese .dat text files.  Format is assumed to
    be the same length-prefixed string scheme used elsewhere, but with
    UTF-8 (or Latin-1 fallback) encoding.

    Two layouts are tried:
      1. Multi-section: LE u32 n_sections, then n_sections × LE u32 offsets
         (same as message.dat — used when msg0.msd etc. are separate files
         each representing one chapter)
      2. Flat string list: scan for printable length-prefixed strings
         (fallback; used for bem.msd / ability-name style files)

    Returns a list of sections (each section = list of strings).
    For flat files, returns [[s0, s1, ...]].
    """
    if not data:
        return []

    # Probe: does it start with a sane section count?
    if len(data) >= 8:
        n = le_u32(data, 0)
        if 1 <= n <= 64:
            # Try multi-section parse
            result = parse_message(data)
            if result:
                # Re-decode as UTF-8
                out = []
                offs = [le_u32(data, 4 + 4*i) for i in range(n)]
                offs.append(len(data))
                for s in range(n):
                    start, end = offs[s], offs[s+1]
                    strs = _msd_read_strings(data, start, end, encoding)
                    out.append(strs)
                return out

    # Fallback: flat string scan
    strs = _msd_read_strings(data, 0, len(data), encoding)
    return [strs] if strs else []


def _msd_read_strings(data: bytes, start: int, end: int,
                      encoding: str = "utf-8") -> list:
    """Read length-prefixed strings from a byte range, trying multiple encodings."""
    strs = []
    p = start
    end = min(end, len(data))
    while p < end:
        L = data[p]
        if L == 0:
            p += 1
            continue
        if p + 1 + L > end:
            break
        chunk = bytes(data[p+1:p+1+L])
        s = None
        for enc in (encoding, "utf-8", "shift-jis", "latin-1"):
            try:
                s = chunk.decode(enc)
                break
            except Exception:
                continue
        if s is not None:
            strs.append(s)
        p += 1 + L
    return strs
