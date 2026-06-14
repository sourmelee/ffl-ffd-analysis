"""Faithful reproduction of FFD's battle stat derivation (``GameClass::SetJobStatus``).

This is the Toolkit-side reference for the engine's N2 derivation, decoded from
``libjniproxy.so_new.c`` lines 152644-152705 (primary) and disambiguated against
FF5-PC ``SetMemberStatus`` ``FUN_00468490`` (decomp 72718-72783) — see
``Python/docs/formats/jobs.md`` and the discoveries log.

The model (FFD, %-growth — *not* FF5's flat bonuses):

* Each level row of boot_data **§8** holds ``base_hp`` (BE-u16 @+2), ``base_mp``
  (BE-u16 @+4) and a **single base-stat byte** (@+6).
* ``max_hp = base_hp[L] * job.hp_pct / 100`` (likewise MP via ``job.mp_pct``).
* All five attributes derive from the **same** base-stat byte, scaled by each
  job's own percent: ``STR = base_stat[L] * job.str_pct / 100``, and so on for
  SPD/VIT/INT/MND (``job.{spd,vit,int,mnd}_pct``). There is no separate
  per-character base attribute in the derivation.
* Equipment and learned-ability bonuses are then added (out of scope here — the
  Toolkit bakes no equip-stat table yet; callers pass ``equip=`` if known).

All results are floored at 1 to mirror the engine's ``MATH_MAX(1, …)``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobPercents:
    """Per-job growth percents (FJOB / ``decode_job_body``)."""

    hp: int = 100
    mp: int = 100
    str: int = 100
    spd: int = 100
    vit: int = 100
    int: int = 100
    mnd: int = 100


@dataclass(frozen=True)
class DerivedStats:
    max_hp: int
    max_mp: int
    str: int
    spd: int
    vit: int
    int: int
    mnd: int


def _scale(base: int, pct: int) -> int:
    # Engine: MATH_MAX(1, base * pct / 100), integer (truncating) division.
    return max(1, (base * pct) // 100)


def derive_stats(
    base_hp: int,
    base_mp: int,
    base_stat: int,
    job: JobPercents,
    equip_str: int = 0,
    equip_spd: int = 0,
    equip_vit: int = 0,
    equip_int: int = 0,
    equip_mnd: int = 0,
) -> DerivedStats:
    """Derive a member's battle stats from the level-row bases and job percents.

    ``base_hp``/``base_mp``/``base_stat`` come from the §8 level row for the
    member's *current* level (BE-u16, BE-u16, u8 at row +2/+4/+6).
    """
    return DerivedStats(
        max_hp=_scale(base_hp, job.hp),
        max_mp=_scale(base_mp, job.mp),
        str=_scale(base_stat, job.str) + equip_str,
        spd=_scale(base_stat, job.spd) + equip_spd,
        vit=_scale(base_stat, job.vit) + equip_vit,
        int=_scale(base_stat, job.int) + equip_int,
        mnd=_scale(base_stat, job.mnd) + equip_mnd,
    )


def level_row_bases(boot: bytes, level: int) -> tuple[int, int, int]:
    """Return ``(base_hp, base_mp, base_stat)`` for ``level`` from boot §8.

    Level is the row index directly (the engine clamps to 99); row stride 9.
    """
    import struct

    t = [struct.unpack_from("<I", boot, i * 4)[0] for i in range(17)]
    s8 = boot[t[8] : t[9]]
    L = max(0, min(level, len(s8) // 9 - 1))
    e = s8[L * 9 : L * 9 + 9]
    return ((e[2] << 8) | e[3], (e[4] << 8) | e[5], e[6])


def job_percents(boot: bytes, job_id: int) -> JobPercents:
    """Pull a job's growth percents from the Android §6 job table."""
    from .parser import parse_jobs_android, decode_job_body

    for j in parse_jobs_android(boot):
        if j["id"] == job_id:
            d = decode_job_body(j.get("body", b""))
            return JobPercents(
                hp=d["hp_pct"], mp=d["mp_pct"], str=d["str_pct"], spd=d["spd_pct"],
                vit=d["vit_pct"], int=d["int_pct"], mnd=d["mnd_pct"],
            )
    return JobPercents()
