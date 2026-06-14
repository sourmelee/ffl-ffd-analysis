"""``boot_data.dat`` section-table walker and shared section helpers.

The boot_data file starts with a packed array of u32 section offsets,
where ``section[i] = buf[u32(i*4) : u32((i+1)*4)]``. The last u32 in
the array equals filesize (end terminator). We walk u32 entries until
we hit it.

Mobile boot_data is big-endian; the Android port re-encoded it as
little-endian. :func:`detect_boot_endian` picks the right reader.

Most record sections (items, magic, jobs, etc.) share a common shape:

    u16 count
    record × count, where each record is either:
        0xff sentinel byte (deleted slot)   OR
        pascal_name + pascal_desc + body[body_size]

This is shared between Mobile (BE count) and Android (BE count too --
verified 2026-05-22 against Mobile section 4 boot_data which produces
the same 640-record items table as Android section 5, with name/desc
byte-for-byte identical). :func:`_parse_namedesc_section` decodes
either side; :func:`_parse_android_namedesc_section` is kept as a
back-compat wrapper for callers that hard-coded the Android LE path.
"""

from __future__ import annotations

from ..binary import be_u16, be_u32, le_u32


def boot_section_be(boot: bytes, byte_offset: int) -> bytes:
    """Mobile boot_data: BE pointer at byte_offset, returns slice from there."""
    if byte_offset + 4 > len(boot):
        return b""
    ptr = be_u32(boot, byte_offset)
    if ptr >= len(boot):
        return b""
    return boot[ptr:]


def boot_section_le(boot: bytes, byte_offset: int) -> bytes:
    """Android boot_data: LE pointer."""
    if byte_offset + 4 > len(boot):
        return b""
    ptr = le_u32(boot, byte_offset)
    if ptr >= len(boot):
        return b""
    return boot[ptr:]


def detect_boot_endian(boot: bytes) -> str:
    """Return 'le' or 'be' based on which interpretation yields sensible offsets."""
    if len(boot) < 8:
        return "le"
    le0 = le_u32(boot, 0)
    be0 = be_u32(boot, 0)
    n = len(boot)
    if 0 < le0 <= n and (be0 == 0 or be0 > n):
        return "le"
    if 0 < be0 <= n and (le0 == 0 or le0 > n):
        return "be"
    return "le" if boot[3] == 0 and boot[7] == 0 else "be"


def parse_boot_toc(boot: bytes, endian=None):
    """Parse the section TOC of a boot_data.dat.

    Returns (sections, endian) where sections is a list of (start, end)
    byte ranges.
    """
    if endian is None:
        endian = detect_boot_endian(boot)
    rd = le_u32 if endian == "le" else be_u32
    n = len(boot)
    offs = []
    i = 0
    prev = -1
    while i + 4 <= n:
        v = rd(boot, i)
        if v < prev or v > n:
            break
        offs.append(v)
        i += 4
        if v == n:
            break
        prev = v
    sections = [(offs[k], offs[k+1]) for k in range(len(offs) - 1)]
    return sections, endian


ANDROID_BOOT_SECTION_LABELS = {
    0:  "(unused — overlaps TOC tail)",
    1:  "16 records, Shift-JIS pascal (elements / small enum table)",
    2:  "LoadMagicData — magic / spell records (~512)",
    3:  "LoadPassiveAbility — passive abilities (~113)",
    4:  "LoadCommandAbility — command abilities (~50)",
    5:  "LoadItemData — items (~640, starts with '-' / 'none' / 'ダガー')",
    6:  "LoadJobData — jobs (~33, starts with 'デバッガー')",
    7:  "scenario / constants buffer (start)",
    8:  "LoadFusionData / constants (cont.)",
    9:  "LoadMonsterData — bestiary (645 declared, ~146 real)",
    10: "(u16-BE count + (u16,u16) pairs — possible mc_id lookup)",
    11: "int[][] config tables (input/control config Shift-JIS)",
    12: "preload mc-id pack table (12 packs × 16 bytes)",
    13: "palette / colour-ramp candidate",
    14: "tiny fixed table (20 bytes)",
    15: "asset / scene name pascal-string manifest",
}

MOBILE_BOOT_SECTION_LABELS = {
    0:  "method_951 — string-pair table (mob/spell names)",
    1:  "method_938 — class_6[] records",
    2:  "method_945 — class_3[] records",
    3:  "method_943 — class_14[] records",
    4:  "main loader — class_9[] (640 entries)",
    5:  "method_941 — class_8[] records",
    6:  "method_947 — class_11[] records",
    7:  "field_994 constants (start)",
    8:  "field_994 constants (end)",
    9:  "method_1117 pack table",
    10: "raw → field_1042",
    11: "method_1134 int[][] tables",
    12: "method_1143 preload mc-id pack table",
    13: "raw → field_1075",
    14: "(singleton int at offset 56)",
    15: "raw → field_1041",
    16: "raw → field_1044",
    17: "raw → field_1045",
    18: "raw → field_1046",
    19: "raw → field_1043",
    20: "raw → field_1047",
}


def boot_section_label(idx, endian):
    table = ANDROID_BOOT_SECTION_LABELS if endian == "le" else MOBILE_BOOT_SECTION_LABELS
    return table.get(idx, "(unknown)")


# Section→loader map decoded from libjniproxy.so's GameClass::LoadBootData.
# Each tuple is (toc_offset_in_boot_data, body_size, label).
# FF5-PC cross-check (2026-06-14, sanctioned 2nd ground-truth): FF5's
# LoadMagicData/LoadItemData/LoadJobData read their sections from the SAME TOC
# byte offsets 0x08 / 0x14 / 0x18 used below (FFV_Game.exe.unpacked.exe.c
# FUN_0046c0a0 / FUN_0046b380 / FUN_0046c830) -- only FF5's section *indices*
# (1/4/5) and record *formats* differ from FFD's (2/5/6). Same-engine TOC
# alignment; the byte offsets here are correct.
ANDROID_BOOT_LOADERS = {
    "magic":    (0x08, 54, "Magic / spells (~512)"),
    "passive":  (0x0c, 24, "Passive abilities (~113)"),
    "command":  (0x10, 25, "Command abilities (~50)"),
    "items":    (0x14, 54, "Items (~640)"),
    "jobs":     (0x18, 126, "Jobs (~33)"),
}

# Mobile equivalent — discovered 2026-05-22 by side-by-side comparison
# with Android. Mobile boot_data has more sections (21 vs 16), so indices
# differ, but per-record body sizes match.
MOBILE_BOOT_LOADERS = {
    "items": (0x10, 54, "Items (640)"),                # section 4 in mobile TOC
}


def _parse_namedesc_section(boot, toc_offset, body_size, endian):
    """Shared namedesc decoder for both Mobile (BE) and Android (LE).

    Section layout (verified 2026-05-22 against Mobile section 4 +
    Android section 5 items, 640 records each, body=54, name/desc
    byte-identical):

        u16-BE count                  ; count is BE on both platforms
        record × count:
            0xff sentinel             ; deleted slot
            OR
            u8 name_len, name bytes (SJIS)
            u8 desc_len, desc bytes (SJIS)
            body[body_size]

    `endian` selects the TOC pointer reader (the outer u32 pointers in
    boot_data.dat flip endian between platforms). Returns a list of
    dicts (or None for sentinel slots) with id, name, desc, body.
    """
    if endian == "be":
        rd = be_u32
    elif endian == "le":
        rd = le_u32
    else:
        raise ValueError("endian must be 'be' or 'le', got %r" % (endian,))

    if len(boot) < toc_offset + 8:
        return []
    sec_start = rd(boot, toc_offset)
    sec_end   = rd(boot, toc_offset + 4)
    if not (0 < sec_start < sec_end <= len(boot)):
        return []
    sec = boot[sec_start:sec_end]
    if len(sec) < 4:
        return []
    count = be_u16(sec, 0)
    if not (0 < count < 4096):
        return []

    out = []
    p = 2
    for i in range(count):
        if p >= len(sec):
            break
        if sec[p] == 0xff:
            out.append(None)
            p += 1
            continue
        L = sec[p]
        if L > 80 or p + 1 + L > len(sec):
            break
        try:
            name = bytes(sec[p+1:p+1+L]).decode("shift_jis", errors="replace")
        except Exception:
            name = ""
        p += 1 + L
        if p >= len(sec):
            break
        Ld = sec[p]
        if Ld > 80 or p + 1 + Ld > len(sec):
            break
        try:
            desc = bytes(sec[p+1:p+1+Ld]).decode("shift_jis", errors="replace")
        except Exception:
            desc = ""
        p += 1 + Ld
        if p + body_size > len(sec):
            break
        body = bytes(sec[p:p+body_size])
        p += body_size
        out.append({"id": i, "name": name, "desc": desc, "body": body})
    return out


def _parse_android_namedesc_section(boot, toc_offset, body_size):
    """Back-compat wrapper: Android-side namedesc decoder.

    Older callers (magic, passive, command, jobs, monsters) pass just
    `(toc_offset, body_size)` and expect the Android LE TOC pointer
    convention. Forward to the unified decoder. Note: the return shape
    now includes an `id` field that older callers didn't get -- this is
    purely additive.
    """
    return _parse_namedesc_section(boot, toc_offset, body_size, endian="le")
