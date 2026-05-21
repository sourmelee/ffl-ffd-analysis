"""``boot_data.dat`` section-table walker and shared section helpers.

The boot_data file starts with a packed array of u32 section offsets,
where ``section[i] = buf[u32(i*4) : u32((i+1)*4)]``. The last u32 in
the array equals filesize (end terminator). We walk u32 entries until
we hit it.

Mobile boot_data is big-endian; the Android port re-encoded it as
little-endian. :func:`detect_boot_endian` picks the right reader.
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
    # tie-break: if high bytes are zero, it's LE
    return "le" if boot[3] == 0 and boot[7] == 0 else "be"


def parse_boot_toc(boot: bytes, endian: str | None = None):
    """
    Parse the section TOC of a boot_data.dat.
    Returns (sections, endian) where sections is a list of (start, end) byte ranges.
    """
    if endian is None:
        endian = detect_boot_endian(boot)
    rd = le_u32 if endian == "le" else be_u32
    n = len(boot)
    offs: list[int] = []
    i = 0
    prev = -1
    while i + 4 <= n:
        v = rd(boot, i)
        if v < prev or v > n:
            break
        offs.append(v)
        i += 4
        if v == n:                       # file-size terminator
            break
        prev = v
    sections = [(offs[k], offs[k+1]) for k in range(len(offs) - 1)]
    return sections, endian


# Android section labels (decoded 2026-05-13 by cross-referencing Mobile
# class_20.java loaders + verifying byte patterns in proper_obb/boot_data.dat).
# Section count and ordering DIFFERS from Mobile — these labels are Android-specific.
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

# Mobile labels — accessed by method_940(boot, i) in class_20.java
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


def boot_section_label(idx: int, endian: str) -> str:
    table = ANDROID_BOOT_SECTION_LABELS if endian == "le" else MOBILE_BOOT_SECTION_LABELS
    return table.get(idx, "(unknown)")


# Section→loader map decoded from libjniproxy.so's GameClass::LoadBootData.
# Each tuple is (toc_offset_in_boot_data, body_size, label).
ANDROID_BOOT_LOADERS = {
    "magic":    (0x08, 54, "Magic / spells (~512)"),
    "passive":  (0x0c, 24, "Passive abilities (~113)"),
    "command":  (0x10, 25, "Command abilities (~50)"),
    "items":    (0x14, 54, "Items (~640)"),
    "jobs":     (0x18, 126, "Jobs (~33)"),
}


def _parse_android_namedesc_section(boot: bytes, toc_offset: int,
                                    body_size: int):
    """
    Generic Android boot_data section parser for "pascal_name + pascal_desc +
    body_size fixed bytes" records (the pattern used by all Load*Data calls).

    Returns a list of dicts (or None for 0xff-sentinel slots), one entry per
    declared record. Each dict has:
        name, desc (Shift-JIS decoded), body (bytes object).

    `toc_offset` is the byte offset in boot_data where the section's start
    pointer (LE u32) lives. e.g. items = 0x14, magic = 0x08, jobs = 0x18.
    """
    if len(boot) < toc_offset + 8:
        return []
    sec_start = le_u32(boot, toc_offset)
    sec_end   = le_u32(boot, toc_offset + 4)
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
        out.append({"name": name, "desc": desc, "body": body})
    return out
