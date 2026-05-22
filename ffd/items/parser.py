"""Item parsers — mobile (BE section 4) and Android (LE section 5).

Both platforms store items in the shared namedesc record layout: a u16
count, then `name(pstr) + desc(pstr) + body[54]` per record (with 0xff
sentinel for deleted slots).

Layout match verified 2026-05-22: Potion (id 420) has byte-identical
name + desc on both platforms, with 51 out of 54 body bytes identical
(see ffd/comparison/registry.py::register_items for the field-level
delta surfaced by ComparisonTab).

History: the prior Mobile parser called ``boot_section_be(boot, 4)``,
which the helper reads as a byte-offset — that's TOC entry 1 (magic),
not §4 (items). It also assumed a 50-byte body; the real size is 54.
Together this produced garbage starting at record 1. Fixed 2026-05-22.

Mobile attribution: section identification builds on GuyPerfect's
``class_20.java`` research; see ``project_collaborators.md`` /
``ffd_boot_data_format.md`` in MEMORY for the credit graph.
"""

from __future__ import annotations

from ..boot.sections import _parse_namedesc_section


_MOBILE_ITEMS_TOC_OFFSET  = 0x10
_ANDROID_ITEMS_TOC_OFFSET = 0x14
_ITEM_BODY_SIZE = 54


def parse_items_mobile(boot: bytes):
    """Parse mobile item records from section 4 (BE TOC).

    Returns a list of {id, name, desc, body: bytes} dicts, with None
    in deleted-slot positions. Body bytes are not field-decoded here.
    """
    return _parse_namedesc_section(
        boot, _MOBILE_ITEMS_TOC_OFFSET, _ITEM_BODY_SIZE, endian="be"
    )


def parse_items_android(boot: bytes):
    """Parse Android item records from section 5 (LE TOC). Body=54 bytes."""
    return _parse_namedesc_section(
        boot, _ANDROID_ITEMS_TOC_OFFSET, _ITEM_BODY_SIZE, endian="le"
    )


# ---------------------------------------------------------------------------
# Body field decode (shared)
# ---------------------------------------------------------------------------

_ITEM_FIELDS = [
    # (field_name, offset, size_bytes, kind)
    ("item_type",     0,  1, "u8"),
    ("equip_type",    1,  1, "u8"),
    ("price",         2,  4, "u32"),
    ("attack",        6,  1, "u8"),
    ("defense",       7,  1, "u8"),
    ("magic",         8,  1, "u8"),
    ("weight",        9,  2, "u16"),
    ("flags",        11,  2, "u16"),
    ("element",      13,  1, "u8"),
    ("status",       14,  1, "u8"),
    ("hp_bonus",     34,  1, "u8"),
    ("mp_bonus",     35,  1, "u8"),
    ("speed",        36,  1, "u8"),
    ("use_effect",   37,  2, "u16"),
    ("battle_flags", 39,  2, "u16"),
    ("job_mask",     49,  1, "u8"),
    ("icon_r",       50,  1, "u8"),
    ("icon_g",       51,  1, "u8"),
    ("icon_b",       52,  1, "u8"),
    ("sort_key_lo",  53,  1, "u8"),
]


def _read_int(body, off, size, endian):
    raw = body[off:off + size]
    if len(raw) < size:
        return 0
    return int.from_bytes(raw, "big" if endian == "be" else "little",
                          signed=False)


def decode_item_body(body, endian):
    """Decode the 54-byte item body to a flat field dict.

    `endian` controls how multi-byte fields are read ('be' for Mobile,
    'le' for Android). u8 fields are platform-invariant.
    """
    out = {}
    for name, off, size, kind in _ITEM_FIELDS:
        if kind == "u8":
            out[name] = body[off] if off < len(body) else 0
        else:
            out[name] = _read_int(body, off, size, endian)
    return out
