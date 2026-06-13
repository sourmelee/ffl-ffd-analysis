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

# Verified offsets (HIGH) traced from GameClass::LoadItemData / consumers in
# libjniproxy.so_new.c (2026-06-13, item-struct deserializer @149955):
#   body[0]       item_type   (struct-0x28)  category discriminator
#   body[1..4]    price        BE u32 (struct-0x24); body[1] is the always-0 high
#                              byte the old parser mislabelled `equip_type`.
#   body[5]       use_category (struct-0x20)  consumables: 1=HP 2=MP 3=full 5=revive
#   body[32]      primary_stat (struct+0)     weapon ATK *or* armor DEF, keyed by
#                              item_type. Verified against the "ATK n"/"DEF n"
#                              descriptions: 206/209 weapons + 164/167 armor match
#                              exactly (the few mismatches are stale desc text —
#                              the body field is the value the game actually uses).
#   body[33]      accuracy     (struct+2)     weapon hit-rate.
# The remaining MEDIUM fields below are exploratory (kept for ComparisonTab); they
# are NOT used by the FFSmith bake.
_ITEM_FIELDS = [
    # (field_name, offset, size_bytes, kind)
    ("item_type",     0,  1, "u8"),    # HIGH
    ("price",         1,  4, "u32"),   # HIGH  (BE body[1..4])
    ("use_category",  5,  1, "u8"),    # HIGH  (consumable effect class)
    ("primary_stat", 32,  1, "u8"),    # HIGH  (weapon ATK / armor DEF)
    ("accuracy",     33,  1, "u8"),    # HIGH  (weapon hit-rate)
    # --- exploratory / MEDIUM (not bake-critical) ---
    ("weight",        9,  2, "u16"),
    ("flags",        11,  2, "u16"),
    ("element",      13,  1, "u8"),
    ("status",       14,  1, "u8"),
    ("hp_bonus",     34,  1, "u8"),
    ("mp_bonus",     35,  1, "u8"),
    ("use_effect",   37,  2, "u16"),
    ("battle_flags", 39,  2, "u16"),
    ("job_mask",     49,  1, "u8"),
]

# item_type → equip category
_WEAPON_TYPES = range(1, 16)      # 1..15 weapon classes
_ARMOR_TYPES  = range(16, 24)     # 16 shield, 17..19 head, 20..22 body, 23 accessory


def _read_int(body, off, size):
    raw = body[off:off + size]
    if len(raw) < size:
        return 0
    return int.from_bytes(raw, "big", signed=False)


def decode_item_body(body, endian=None):
    """Decode the 54-byte item body to a flat field dict.

    The `endian` kwarg is retained for back-compat with callers that pass
    'be' or 'le', but is IGNORED -- multi-byte fields inside the item
    body are big-endian on both platforms. (Verified 2026-05-22 by
    checking item bodies across all 640 records; re-confirmed 2026-06-13
    against the engine's own little-/big-endian reads in LoadItemData.)

    `attack`/`defense` are the same on-disk field (``primary_stat`` = body[32]),
    surfaced under the item's equip category so callers (ComparisonTab, the
    FFSmith bake) can read whichever they expect.
    """
    out = {}
    for name, off, size, kind in _ITEM_FIELDS:
        if kind == "u8":
            out[name] = body[off] if off < len(body) else 0
        else:
            out[name] = _read_int(body, off, size)
    t = out.get("item_type", 0)
    ps = out.get("primary_stat", 0)
    out["attack"]  = ps if t in _WEAPON_TYPES else 0
    out["defense"] = ps if t in _ARMOR_TYPES  else 0
    return out
