# Format: Battle Data

*Audit 2026-06-10. Parsers: `ffd/monsters/parser.py`, `ffd/formats/form_bin.py`, boot §8 growth (baked via `ffsmith_bake._bake_menu_data`). Struct map: `Engine/docs/BTLACT_MAP.md` (keep that file — it's the canonical BTLACT spec).*

## Monster records — HIGH

boot_data: Mobile **§8** (BE pointer; chapter-scoped, 0xff sentinels, 93 active in Ch1/Online), Android **§9** (LE pointer; 645 records). Record = pstr name + **64-byte body** (no desc); body multi-byte fields **BE on both** platforms. Goblin 62/64 bytes identical cross-platform.
Decoded body fields (extended 2026-06-10 via `LoadMonsterData` c:151254 + `SetBtlEnemyParam` c:88427): **level = body[0]**; **HP = BE u32 @ body[2]** (enemy MP = HP/8); **EXP = BE u32 @ body[6]**; **gil = BE u32 @ body[10]**; AP = body[14]; **weapon-attack = body[15]**; body[16/17] → BTLACT 0x50/0x54 (unnamed/hit-count-class); **DEF = body[18]**; **MDEF = body[19]**; **evade = body[20]**; **magic-evade = body[21]**; body[22/23] → damage-taken multipliers (0x148/0x150); **attack-stat range = body[24..25]** (base + Rand(max−min+1)); body[26] → VIT/INT-class (0x44/0x48); body[27] flags (bit0 → BTLACT 0xb4|=0x2000 path, bits 1-2 → 0xa4); body[28] → 0x80/0x84; body[29..32] → element groups (0x70..0x7c); body[33..] → BE16/byte run mapped to rec 0x2c..0x46 (semantics open). The enemy's attack STAT (BTLACT+0x3c/0x40) is its **LEVEL**. Old `stat_b` was accidentally body[15] (right value); `stat_c` was NOT the real DEF — both replaced in the FMN2 bake.
History: README/older code claimed Mobile monsters in §12 — §12 is the tileset preload pack table; §8 located empirically by Goblin byte-signature search (2026-05-22).

## Level/growth (boot §8 tail) — HIGH

EXP threshold[i] = BE u32 @ `s8[0x10 + 9i]` (45/97/173/261…, 98 thresholds); per-level maxHP = BE u16 @ `s8[L*9+2]`, maxMP @ +4 (143 rows). Verified Sol L3→HP70, Aigis L10→HP199. **Hypothesis:** single global curve; per-job HP%/MP% multipliers exist in the original (`SetJobStatus`) but are undecoded.

## BTLACT / damage formula — HIGH (struct map), MEDIUM (full pipeline)

`BattleClass::SetMemberStatus` (c:83626) / `SetBtlPlayerParam` (c:88079) / `SetBtlEquipParam` (c:83685) populate the BTLACT actor struct; `CalcPhysicAttackDmg` (c:91987) core:
`damage = MAX(0, W·64·H/32 + Rand(max(0x80, W·64/20)) − D·64) × modifiers × MAX(0x40,(3A+L)·4) >> 12`.
Decoded fields and offsets: see BTLACT_MAP.md. **Not decoded:** SetJobStatus derivation of A/W/D values, crit/element/race/status/hit-count/back-attack modifiers' exact math, `CalcMagicDmg` details.

## Formations — DECODED (Android, 2026-06-10, HIGH)

Android `form.bin` (79 KB, in the OBB — `BufferControl::Set(+0x4df58, "form.bin")` c:149554; reader `BattleClass::LoadFormation` c:103535): u32-LE per-story-bank TOC at [4+bank·4] ([0] = bank count 16); per bank a BE u16 record-offset table by formation id (0 = none); record = no_escape u8 + battle-script i16BE (id into **`bsc.dat`** — battles have their own script VM, `StartBattleScript`/`BattleScriptExec` — undecoded) + u8 n × **(enemy_id i16, x i16, y i16, flags u8)** (≤8 kept; → `SetBtlEnemyParam(actor, id, x, y)`) + u8 m party-entry overrides (slot, value, i16). Verified: 1,887 formations, 5,259 enemy refs all < 645; bank-0 fid 1 = Goblin×2, fid 150 = the no-escape prologue boss (enemy 48 "???", bsc 1000). Parser `parse_form_bin_android`; baked as `data/encounters.bin` (FENC).

**Random encounters:** per-map areas (set id = formation id, rate, rect) decoded from the LoadMapInfo tail (maps.md) and baked (FFM5). The per-step **roll formula is still open** — `GetMapData` (c:134195) exposes ratio/areas/rate-sums but the consuming roll wasn't located this pass.

**Mobile `form.bin`** (legacy heuristic parser): field naming `(x,y,z,enemy_type)` is now **suspect** given the Android record is `(enemy_id, x, y, flags)` — re-verify before trusting (parser docstring flags this).

**Battle results to scripts:** `GetReference` target 8 = `GetReferenceBattle` (c:135841); type 3 → 1 won (result-flag bit9 clear) / 2 escaped (bit10). Types 0–2 read bytes off the battle-info struct (+0x44c90) — unmapped.

## Items-as-equipment (battle-relevant)

`item_type` (body off 0) is the real category; `equip_type` (off 1) is always 0 (verified across 640 names). **Caveat:** the baked FITM atk/def are regex-extracted from the English *descriptions* ("ATK 7"), not read from body bytes (`_bake_menu_data`) — MEDIUM until the item body offsets are pinned. (Monster stats were upgraded to the decoded body fields in 0.7.26/FMN2.) Item *combat effects* (use-effects, casts) undecoded.

## AI

Nothing decoded — see `ai.md`.
