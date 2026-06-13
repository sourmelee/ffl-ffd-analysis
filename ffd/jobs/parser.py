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
indices) plus the HP%/MP%/stat% growth multipliers are decoded by
`decode_job_body`; the rest is exposed as a `tail` blob for ComparisonTab.
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
# Growth multipliers -- HIGH confidence (2026-06-13). Traced from
# GameClass::SetJobStatus (libjniproxy.so_new.c @152572): the engine computes
#   maxHP = base_hp[level] * jobStruct[0x1d] / 100   (and likewise MP / stats),
# where jobStruct[0x1d] = body[9] and [0x1e] = body[10] (LoadJobData @150402
# stores body[9]->struct+0x1d, body[10]->struct+0x1e, body[11..15]->+0x1f..+0x23).
# Validated by archetype: Monk 142% HP, Black Mage 143% MP / 71 INT, Summoner
# 67% HP / 150% MP, Warrior 138% HP / 33% MP -- exactly the expected FF curves.

def decode_job_body(body: bytes) -> dict:
    if len(body) < _JOB_BODY_SIZE:
        return {}
    return {
        "sprite_ow":   body[1],
        "sprite_btl":  body[2],
        "palette_ow":  body[3],
        "palette_btl": body[4],
        # growth multipliers (percent of the shared level-table base) — HIGH
        "hp_pct":      body[9],
        "mp_pct":      body[10],
        "str_pct":     body[11],
        "spd_pct":     body[12],
        "vit_pct":     body[13],
        "int_pct":     body[14],
        "mnd_pct":     body[15],
        # u32 BE @5 is the learn/EXP block per the legacy decode (kept for diffing)
        "stat_a":      be_u32(body, 5),
        # equip/move flags live near the end per the legacy decode
        "equip_flags": body[124],
        "move_type":   body[125],
        # bag of unmapped bytes for ComparisonTab to highlight diffs in
        "tail":        bytes(body[16:124]),
    }
