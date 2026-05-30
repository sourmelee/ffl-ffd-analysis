"""Job class parsers -- mobile (BE §5) and Android (LE §6).

Both platforms share the same record layout: u16-BE count, then
`name(pstr SJIS) + desc(pstr SJIS) + body[126]`. The Android port flips
only the outer TOC pointer; multi-byte fields inside the body remain BE
on both, matching Items and Monsters.

Mobile uses §5 (TOC byte offset 20). The docstring comment in the
legacy parser said "section 20" -- that was misleading, the actual
section index is 5 and the byte offset is 20 (= 5 * 4). Behaviour was
correct; only the comment was wrong.

Android uses §6 (TOC byte offset 0x18) per ANDROID_BOOT_LOADERS.

Counts: Mobile Chapter 1 has 31 records; Android has 33. Mobile is
chapter-scoped (like chara_set / monsters) -- early chapters fill
later id slots with duplicate names ("メモリスト" appears at both
id=13 and id=25 in Chapter 1) until the real job is introduced.

Body decode is BE-on-both. The high-confidence prefix (sprite/palette
indices) is decoded by `decode_job_body`; the rest is exposed as
`tail_uN_OFF` fields for ComparisonTab to surface during phase-2
delta-spec work.
"""

from __future__ import annotations

from ..binary import be_u32
from ..boot.sections import _parse_namedesc_section


_MOBILE_JOBS_TOC_OFFSET  = 20      # §5 in mobile boot_data
_ANDROID_JOBS_TOC_OFFSET = 0x18    # §6 in android boot_data
_JOB_BODY_SIZE = 126


def parse_jobs_mobile(boot: bytes):
    """Mobile §5 job table (BE TOC).

    Returns `[{id, name, desc, body: bytes}]` matching the items/monsters
    parsers. Use `decode_job_body(body)` for the per-field decode.
    """
    return _parse_namedesc_section(
        boot, _MOBILE_JOBS_TOC_OFFSET, _JOB_BODY_SIZE, endian="be"
    )


def parse_jobs_android(boot: bytes):
    """Android §6 job table (LE TOC). Body=126 bytes."""
    return _parse_namedesc_section(
        boot, _ANDROID_JOBS_TOC_OFFSET, _JOB_BODY_SIZE, endian="le"
    )


# ---------------------------------------------------------------------------
# Body decode (BE on both platforms)
# ---------------------------------------------------------------------------
#
# High-confidence fields traced from the legacy parser and verified by
# eyeball against Warrior id=2:
#   body[0]      job_id   (often matches the dropdown id; sometimes shifted)
#   body[1]      sprite_ow
#   body[2]      sprite_btl
#   body[3]      palette_ow
#   body[4]      palette_btl  (or palette_btl2)
#
# Tail bytes [5..125] hold stats + ability lists + flags. The legacy
# parser tried to break this into individual fields (base_hp, base_mp,
# abilities, etc.) using heuristic skips -- and got it wrong (Warrior's
# decoded base_hp came out as 8372223). Until the layout is verified
# from libjniproxy.so / class_*.java, we expose the tail bytes as a
# single `tail` blob in the decode dict, with a few tentative named
# fields you can promote once you've eyeballed deltas in ComparisonTab.

def decode_job_body(body: bytes) -> dict:
    if len(body) < _JOB_BODY_SIZE:
        return {}
    return {
        "sprite_ow":   body[1],
        "sprite_btl":  body[2],
        "palette_ow":  body[3],
        "palette_btl": body[4],
        # tentative stat block
        "stat_a":      be_u32(body, 5),
        "stat_b":      be_u32(body, 9),
        # equip/move flags live near the end per the legacy decode
        "equip_flags": body[124],
        "move_type":   body[125],
        # bag of unmapped bytes for ComparisonTab to highlight diffs in
        "tail":        bytes(body[13:124]),
    }
