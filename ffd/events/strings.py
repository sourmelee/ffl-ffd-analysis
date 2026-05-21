"""Shift-JIS string extractor used by the event-script tabs."""

from __future__ import annotations


def extract_sjis_strings(blob: bytes, min_len: int = 2):
    """
    Heuristic: scan for length-prefixed Shift-JIS strings.
    Returns list of (offset, string).
    """
    out = []
    pos = 0
    while pos < len(blob):
        n = blob[pos]
        if 0 < n <= 64 and pos + 1 + n <= len(blob):
            chunk = blob[pos+1:pos+1+n]
            try:
                s = chunk.decode("shift-jis")
            except Exception:
                pos += 1
                continue
            # Heuristic: must contain at least one Japanese char or printable ASCII
            ok = False
            for ch in s:
                cp = ord(ch)
                if cp >= 0x3000:  # CJK / kana / punctuation
                    ok = True; break
                if 0x20 <= cp < 0x7F and ch.isalpha():
                    ok = True; break
            if ok and len(s) >= min_len:
                out.append((pos, s))
                pos += 1 + n
                continue
        pos += 1
    return out
