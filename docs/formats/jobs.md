# Format: Jobs, Characters & Abilities

*Audit 2026-06-10; job growth multipliers + magic body decoded 2026-06-13. Parsers: `ffd/jobs/parser.py`, `ffd/characters/parser.py`, `ffd/abilities/parser.py`.*

## Jobs — HIGH (structure), MEDIUM (body fields)

boot_data Mobile **§5** (BE pointer @TOC byte 20 — a legacy comment said "section 20", that was the *byte offset*; behavior was always right), Android **§6** (LE @0x18). Record = name + desc + **126-byte body**, body BE on both. Counts: Mobile Ch1 = 31, Android = 33; Mobile is chapter-scoped with duplicate-name placeholder slots until jobs are introduced. `decode_job_body` decodes sprite_ow/sprite_btl, palette_ow/palette_btl, the growth multipliers below, and exposes the rest as a `tail` blob for diffing.

**Growth multipliers — HIGH (decoded 2026-06-13).** From `GameClass::SetJobStatus` (libjniproxy.so_new.c @152572): the engine scales the shared level-table base by per-job percents — `maxHP = base_hp[level] * jobBody[9] / 100`, `maxMP` via body[10], and STR/SPD/VIT/INT/MND via body[11..15] (`LoadJobData` @150402 maps body[9]→struct+0x1d, body[10]→+0x1e, body[11..15]→+0x1f..+0x23, which SetJobStatus multiplies). Validated by archetype: Monk 142 % HP, Black Mage 143 % MP / 71 INT, Summoner 67 % HP / 150 % MP, Warrior 138 % HP / 33 % MP. Baked to `data/jobs.bin` (FJOB); FFSmith applies the HP/MP percents in `memberMaxHp`/`memberMaxMp` and the level-up deltas.

## `chara_set.dat` — HIGH

Same record layout both platforms (records BE on both): u16-BE count; per character: name(pstr SJIS), 2×u8, 10 skip, 5×u16-BE, u8, **6×u16-BE equipment**, 6×u8. Header differs: Mobile 12 B (3×u32-BE: records_start, sect2, filesize), Android 16 B (4×u32-LE: version=2, records_start, sect2, filesize). Mobile chapter-scoped (Ch1 = 20 recs) vs Android full roster (21). Byte-identical for the core cast; genuine rename at id 12 (グラム → 黒騎士) and Mobile placeholder 予備1 where Android has Eduardo. Decoded per-character stats job/level/STR/SPD/VIT/INT/MND (0.7.9; engine-verified via `ReadStartData`/`MEMBER_STATUS`) + CHPK field-sprite id (0.7.19). `CHARA_TABLE` (constants.py) supplies romaji names.

## Abilities (Android-only parsers) — HIGH structure

Shared namedesc decoder, differing only in TOC offset + body size: magic toc 0x08 **body 54** (same layout family as items), passive toc 0x0c body 24, command toc 0x10 body 25. Counts: 512 / 113 / 50.

**Magic body — HIGH (decoded 2026-06-13)** via `decode_magic_body`. Traced from `GameClass::LoadMagicData` (@150182, magic struct = 0x58 B) and confirmed in the consumers: `school` = body[0] (1 white / 2 black), `cost_type` = body[6], **`mp_cost` = body[7]** (`GetMagicUseLostValue` @90534 returns it as the cost), **`effect_cat` = body[16]** (1 HP-damage / 2 HP-heal / 5–8 status — `SetMagicStatus` @95336), **`formula` = body[18]** (`CalcMagicDmg` switch @93146: 1/2 magic-stat, 3/4/5 stat-derived, 6 fixed, 7 random, 8 weapon), **`power` = body[19]** (iVar21 in `CalcMagicDmg`), `factor` = body[20], **`element` = body[31]** (`CalcElementPoint`). Validated across the table against canonical FF values (Fire/Fira/Firaga 5/10/32 MP, pow 14/40/90; Cure→Curaga heal tiers; correct elements & summon affinities). The baked `spells.bin` now carries **251 real damage/heal spells** (FSPL record gained an `element` byte); status spells (effect_cat 5–8) are skipped pending an engine status system. Passive/command body semantics remain largely unmapped. Mobile equivalents exist in the Mobile TOC (magic at §1 per the comparison-stub note — Unverified).

## Multi-language names

All of the above splice display names from `system_message.msd` (§5 chars, §6 command, §7 items, §8 jobs, §9 magic, §10 passive, §13 monsters) — see text.md.
