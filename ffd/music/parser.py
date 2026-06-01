"""Audio parsers -- Mobile/Android ``snd.dat`` melodies + the Android
``res.bin`` audio-name table.

snd.dat container  (Mobile *and* Android -- identical layout)
-------------------------------------------------------------
Decoded from the DoJa engine: ``class_1.method_27`` walks the file using
the big-endian readers ``class_20.method_1036`` (u16) / ``method_1037``
(u32).  All integers are big-endian::

    +0   u32  bank0 offset       (the file has 3 sound "banks")
    +4   u32  bank1 offset
    +8   u32  bank2 offset
    @bank:
        u16  count N
        u32  rel[0..N]           (N+1 offsets; sound i spans
                                  rel[i]..rel[i+1], relative to @bank)
        ...melody blobs...

Each non-empty blob is a self-contained melody.  In FF Legends every blob
is MFi ("Melody Format for i-mode", extension ``.mld``), ASCII magic
``melo``.  Zero-length slots are placeholders the engine still addresses
by index, so we preserve each blob's *original* slot index as its sound
id rather than compacting.

Engine bank usage (``class_1``): bank 0 and bank 1 both feed the BGM
channel (``method_39``/``method_40``); bank 2 feeds the two SFX channels
(``method_37``/``method_38``).  Hence the heuristic role labels below.

The legacy parser assumed snd.dat was a stream of *gzip-wrapped* melodies
and scanned for ``1f 8b`` -- but the real container is uncompressed, so it
found nothing.  This version parses the actual bank/offset tables.

MFi (.mld) internal layout -- notes for a future MFi->MIDI converter
--------------------------------------------------------------------
    "melo"                4 bytes magic
    u32  body_len         bytes after this field (whole file = 8 + body_len)
    u16  hdr_len          length of the info-chunk section
    <info chunks>         each [4-char tag][u16 len][data]:
                          vers, note, exst, sorc, supt, date, titl, ...
    <track chunks>        "trac" [u32 len][event stream]  (one per track)

These blobs are MFi v5 (``vers 0500`` / ``supt MFi5PlugIn_DoCoMo``).  The
per-``trac`` event stream is variable-length and not yet decoded, so the
melody->MIDI conversion is deferred; raw ``.mld`` export is byte-exact.
"""

from __future__ import annotations

from collections import namedtuple

from ..binary import be_u16, be_u32
from ..monsters.parser import parse_bem

# Heuristic role per bank index, from the decompiled engine (class_1):
# banks 0/1 play on the BGM channel, bank 2 on the SFX channels.
BANK_ROLES = ("bgm", "bgm2", "sfx")

# One extracted melody.  ``index`` is the blob's *original* slot index
# within its bank (empty slots counted) so it matches the engine sound id.
SndEntry = namedtuple("SndEntry", "bank bank_role index fmt ext data")


def _detect_fmt(blob: bytes):
    """Return (format_label, file_extension) from a melody's magic bytes."""
    head = blob[:4]
    if head == b"melo":
        return "MFi", ".mld"      # DoCoMo Melody Format for i-mode
    if head == b"MThd":
        return "SMF", ".mid"      # Standard MIDI File
    if head == b"MMMD":
        return "SMAF", ".mmf"     # Yamaha SMAF (.mmf)
    return "unknown", ".bin"


def parse_snd(data: bytes):
    """Parse a Mobile/Android ``snd.dat`` container.

    Returns a list of :class:`SndEntry` for every non-empty sound, in
    (bank, slot) order.  Empty placeholder slots are skipped, but the
    surviving entries keep their true slot index (the engine sound id).
    """
    out = []
    if not data or len(data) < 12:
        return out
    for bank in range(3):
        try:
            base = be_u32(data, bank * 4)
        except Exception:
            continue
        # Bank offset must point at a valid count word inside the file.
        if base <= 0 or base + 2 > len(data):
            continue
        n = be_u16(data, base)
        table = base + 2
        if n < 0 or table + (n + 1) * 4 > len(data):
            continue
        role = BANK_ROLES[bank] if bank < len(BANK_ROLES) else "bank%d" % bank
        try:
            prev = be_u32(data, table)
        except Exception:
            continue
        for i in range(n):
            try:
                nxt = be_u32(data, table + (i + 1) * 4)
            except Exception:
                break
            start, end = base + prev, base + nxt
            prev = nxt
            if end <= start or end > len(data) or start < table:
                continue                       # empty slot / out of range
            blob = data[start:end]
            fmt, ext = _detect_fmt(blob)
            out.append(SndEntry(bank, role, i, fmt, ext, blob))
    return out


def parse_resbin(data: bytes):
    """res.bin = 7 gzip blocks. Returns list of decompressed bytes."""
    import zlib
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
