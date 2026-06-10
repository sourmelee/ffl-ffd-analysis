# Format: Battle Data

*Audit 2026-06-10. Parsers: `ffd/monsters/parser.py`, `ffd/formats/form_bin.py`, boot §8 growth (baked via `ffsmith_bake._bake_menu_data`). Struct map: `Engine/docs/BTLACT_MAP.md` (keep that file — it's the canonical BTLACT spec).*

## Monster records — HIGH

boot_data: Mobile **§8** (BE pointer; chapter-scoped, 0xff sentinels, 93 active in Ch1/Online), Android **§9** (LE pointer; 645 records). Record = pstr name + **64-byte body** (no desc); body multi-byte fields **BE on both** platforms. Goblin 62/64 bytes identical cross-platform.
Decoded body fields: max_hp; **EXP = BE u32 @ body[6]**; **gil = BE u32 @ body[10]**; AP = body[14]; sprite_id (verified Goblin 10 exp / 3 gil — an earlier "13367" exp was a wrong offset, Incorrect→fixed). Remaining ~50 bytes: attack/defense/magic/elements/status presumed present, **not field-mapped** (the `decode_monster_body` legacy aliases attack/defense/etc. to 0 — do not trust those zeros as data).
History: README/older code claimed Mobile monsters in §12 — §12 is the tileset preload pack table; §8 located empirically by Goblin byte-signature search (2026-05-22).

## Level/growth (boot §8 tail) — HIGH

EXP threshold[i] = BE u32 @ `s8[0x10 + 9i]` (45/97/173/261…, 98 thresholds); per-level maxHP = BE u16 @ `s8[L*9+2]`, maxMP @ +4 (143 rows). Verified Sol L3→HP70, Aigis L10→HP199. **Hypothesis:** single global curve; per-job HP%/MP% multipliers exist in the original (`SetJobStatus`) but are undecoded.

## BTLACT / damage formula — HIGH (struct map), MEDIUM (full pipeline)

`BattleClass::SetMemberStatus` (c:83626) / `SetBtlPlayerParam` (c:88079) / `SetBtlEquipParam` (c:83685) populate the BTLACT actor struct; `CalcPhysicAttackDmg` (c:91987) core:
`damage = MAX(0, W·64·H/32 + Rand(max(0x80, W·64/20)) − D·64) × modifiers × MAX(0x40,(3A+L)·4) >> 12`.
Decoded fields and offsets: see BTLACT_MAP.md. **Not decoded:** SetJobStatus derivation of A/W/D values, crit/element/race/status/hit-count/back-attack modifiers' exact math, `CalcMagicDmg` details.

## Formations (`form.bin`, Mobile) — HIGH structure

BE u16 offset table → per-formation: inner_id, enemy count, per-enemy (x,y,z,enemy_type), drops. **Android formation source not located** — `0x50 ScriptEncount` presumably references formation ids; pinning that linkage is the next battle decode target. `encount_ratio` (map header u8) is baked but its consumption logic (random-encounter stepping) is undecoded.

## Items-as-equipment (battle-relevant)

`item_type` (body off 0) is the real category; `equip_type` (off 1) is always 0 (verified across 640 names). **Caveat:** the baked FITM atk/def are regex-extracted from the English *descriptions* ("ATK 7"), not read from body bytes (`_bake_menu_data`); likewise baked monster atk/def/level come from the partially-mapped `stat_b`/`stat_c`/`field14` body fields. Both work in practice but are MEDIUM until the body offsets are pinned. Item *combat effects* (use-effects, casts) undecoded.

## AI

Nothing decoded — see `ai.md`.
