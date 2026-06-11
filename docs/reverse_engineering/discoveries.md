# Reverse-Engineering Discoveries Log

*Audit 2026-06-10. Chronological register of the load-bearing discoveries, each with evidence and where it now lives. Detailed specs: `../formats/`. Predecessor doc: `../../../PROJECT_KNOWLEDGE_EXPORT.md` (2026-05-29 snapshot).*

| When | Discovery | Evidence | Lives in |
|---|---|---|---|
| pre-project | `.sp` scratchpad container (header 64 B, dir @0x41A4) | GuyPerfect's extraction breakthrough + Java research | `containers/sp.py` |
| pre-project | Mobile sprite/ic layout | PowerPanda's manual YYCHR work | `images/ic.py`, `sprites/container.py` |
| pre-project | OBB extraction reference | Colmines92's FFDimensionsTool | `containers/obb.py` (byte-for-byte target) |
| 2026-05 | OBB outer format: global XOR-0x14, chunk_offsets, FAT records | round-trip: `dict_to_obb` repacks byte-identically | obb.py |
| 2026-05 | INP/mtxs/ICP payload magics; msd rename allowlist | 2137/2137 ICP pixel-perfect | obb.py / icp.py |
| 2026-05-13 | boot_data 16-section LE TOC + full Android section map (§1..§15) | loader dispatch table in libjniproxy | `boot/sections.py` |
| 2026-05-13 | **Android mc_id selector**: streaming LoadMapInfo parse, mc not at fixed offset | 73% strict match vs 168 manual annotations | `maps/android.py` |
| 2026-05-?? | **Tile-word high byte = variant/slot only** (old `(hb<<1)\|variant` wrong) | observed values only 0/1; renders correct | `maps/mc_overrides.py` |
| 2026-05-22 | Items §4/§5 namedesc, body 54; legacy Mobile item parser was reading §1 | Potion byte-identical cross-platform | `items/parser.py` |
| 2026-05-22 | **Monsters in Mobile §8, not §12** (§12 = tileset preload packs) | Goblin pascal-signature search; 62/64 body match | `monsters/parser.py` |
| 2026-05-22 | chara_set BE/12B vs LE/16B headers; chapter scoping; equipment list | byte comparison Ch1 vs Android | `characters/parser.py` |
| 2026-05-22 | system_message.msd 6-language master table + section→asset map | record-count cross-check | `text/system_message.py` |
| 2026-05-22 | Jobs §5/§6 body 126 BE-on-both; "section 20" was a byte offset | comparison framework | `jobs/parser.py` |
| 2026-05-2x | snd.dat = uncompressed 3-bank BE MFi container (not gzip stream) | bank walk produces valid `melo` blobs | `music/parser.py` |
| 2026-05-2x | Mobile→Android sprite pagination (fixes doubled-sprite artifact); chpk entry = fldchr idx | visual verification | `sprites/mobile_to_android.py` |
| 2026-06-01→ | Event-script format both platforms: length-prefixed packets, BE operands, 96 opcodes | MoveScript switch + class_16.method_785 | `events/` |
| 2026-06 | capk.dat chip attributes: pass nibble, anim bits 8–17, floor `(A>>18)&0x3f` bit 0x10 | 22,307 rippling water cells; mc63 hazard floors on-screen | `maps/capk.py` |
| 2026-06-08 | **Z-order = per-layer sort key with threshold** `Field+0xdc2c` (not a per-chip bit) | SortIndexOfChara read; layer composites; 1432/220/3 distribution | maps.md / FFM reserved u32 |
| 2026-06-08 | Monster EXP@body[6], gil@body[10] BE u32; §8 EXP thresholds + HP/MP growth rows | Goblin 10/3 verified; Sol/Aigis HP curves | battles.md |
| 2026-06-08 | item_type @body[0] is the real equip category; equip_type @1 always 0 | 640-name verification | items.md |
| 2026-06-09 | Map-header 7×u8 = field_bgm/battle_bgm/battle_bg/…/encount_ratio | LoadMapInfo @118828-118848 | maps.md |
| 2026-06-10 | **Script-execution model**: registry advance; `0x3d` if-NOT-goto; flag/var banks; appear blocks | `--vmtest` + m501 door pair on real data | events.md / Engine scripting.md |
| 2026-06-10 | boot §1 = scenario/start table; `e3_param.dat` is the E3 demo, not retail New Game | LoadScenarioData c:151000 | `boot/scenario.py` |
| 2026-06-10 | **`0x66` = CallEvent**; common pool = map 10000 (26 routines); `0x41` = map/layer/x/y/dir | retail intro chain plays end-to-end headlessly | events.md |
| 2026-06-10 | Boot triggers: 6/7/8 rect semantics; boot 7 fires on load; map-default spawn @+0xdc48 (scenario x/y vestigial) | CheckRangeEvent c:113368; m0 prologue auto-runs | events.md / maps.md |
| 2026-06-10 | **`0x50 ScriptEncount` + Android formations**: form.bin per-bank TOC, (enemy_id,x,y,flags) records, no_escape + bsc.dat battle-script id; result to scripts via GetReference target 8 | ScriptEncount c:120371, LoadFormation c:103535, GetReferenceBattle c:135841; 1,887 formations parse, all enemy ids < 645; FFSmith `--enctest` PASS | `formats/battles.md`, `form_bin.py`, FENC |
| 2026-06-10 | **Per-map random-encounter areas** in the LoadMapInfo tail: 3 bools + n×(set_id u16BE, rate, rect) | LoadEncountData c:119075; 901/1,679 maps, 8,154 areas; overworld = full-map sets {1,2,3} @5 | maps.md, FFM5 |
| 2026-06-10 | **Monster body combat map**: level=b[0], HP=BE32@b[2] (MP=HP/8), wATK=b[15], DEF=b[18], MDEF=b[19], EVA=b[20], MEVA=b[21], atk-range=b[24..25]; enemy A=LEVEL | LoadMonsterData c:151254 + SetBtlEnemyParam c:88427; Goblin lvl1/hp21/watk10 | battles.md, FMN2 |

## Negative results (worth not re-discovering)

- snd.dat is **not** gzip-wrapped (the old scanner found nothing because there was nothing).
- Door warps are **not** map-header encoded (first assumption) — they're script-var idiom via common event 0x104.
- The per-chip "overhead priority bit" does **not** exist — z-order is the layer-threshold sort.
- `system_message.msd` §4 is **not** field dialogue (coincidentally coherent decoy).
- Monster "level" (`field14`) is **not** a difficulty proxy (Werewolf atk 205 at "level 1") — resolved 2026-06-10: that "atk" was `stat_b` = weapon-attack body[15]; level body[0] IS the level, and high-watk low-level monsters are simply hard-hitting.
- Old `stat_c` was **not** the monster's DEF (real DEF = body[18]).
- `e3_param.dat` is **not** the retail start party path.
