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

| 2026-06-11 | **Cutscene direction decoded + implemented**: 0x68 command bytes (68-entry table from the real .so), 0x69/0x32 script suspension, 0x1b camera re-target, 0x20/0x21/0x55 position/visibility, 0x2a fades; call-stack suspension; **exact-tile story sequencing** (stacked boot-7 dispatchers) | SetCharaCommand/MoveCharaEvent/CheckRangeEvent/ScriptIf reads + DAT_00418d40 extraction; intro plays headless w/ full direction (`--cuttest` PASS) | events.md, Engine field.{h,cpp} |
| 2026-06-13 | **Magic body decoded** — mp_cost b[7], effect_cat b[16] (1 dmg/2 heal/5–8 status), formula b[18], power b[19], element b[31], school b[0]; replaces the hardcoded 11-spell `CAST` list (251 real spells baked) | `LoadMagicData`@150182, `GetMagicUseLostValue`@90534, `CalcMagicDmg`@93078; full-table canonical-FF-value match (Fire/Fira/Firaga 5/10/32 MP) | jobs.md, `abilities/parser.py`, FSPL |
| 2026-06-13 | **Item equip stat = body[32]** (weapon ATK / armor DEF by item_type), **price = BE body[1..4]** (old `price@2` off by a byte) — replaces the bake's desc-regex | `LoadItemData`@149955; 206/209 wpn + 164/167 armor desc match; Potion 30 / Elixir 50000 G | items.md, `items/parser.py` |
| 2026-06-13 | **Job HP%/MP%/stat% growth = body[9]/[10]/[11..15]** (percent of shared level-table base) — replaces the 100% default | `SetJobStatus`@152572 + `LoadJobData`@150402; archetype validation (Monk 142% HP, BlkMage 143% MP) | jobs.md, `jobs/parser.py`, FJOB |

| 2026-06-14 | **FF5 PC item record format decoded** (from `FUN_0046b380` in `FFV_Game.exe.unpacked.exe.c`): `[u8 name_len][name_sjis][u8 0x00][u8[91] stat_stream]`; stat = category@0, price(BE)@1..4, use_cat@5, misc@6..17, 18×s16 abilities@18..53, FF5-only zero@54..90. FFD→FF5: `stat = ffd_body[0:54] + b'\x00'*37`. In-memory: GameClass+0x1d6f4, 300 slots × 0xD0. All 10 sub-loader `this+offset` pairs decoded (see `ffd_port/docs/ffv_pc_addresses.md`). | `FFV_Game.exe.unpacked.exe.c` lines 75142-77400; cross-checked via item shim in `ffd_port/src/hooks/engine_hooks.c` | `ffd_port/docs/rebake_plan.md`, `ffd_port/tools/bake_boot_data.py` |
| 2026-06-14 | **FF5-PC decompile sanctioned as a 2nd ground-truth** for shared engine systems (alongside `libjniproxy.so`). Source `Decomp/FFV_FFD_compare/FFV_Game.exe.unpacked.exe.c`, ImageBase 0x400000 -> **decomp addr = RVA + 0x400000**; same-engine premise proven by the `ffd_port` re-bake (FF5's unmodified loaders parse re-baked FFD items/jobs/magic). FF5 `SetMemberStatus` (`FUN_00468490`) is the named parallel to FFD `SetJobStatus`; use FF5-PC only to disambiguate murky Android code -- **`libjniproxy` stays primary**. | `ffv_pc_addresses.md`; FUN_00468490 (decomp 72670) vs SetJobStatus libjniproxy 152572 | `Engine/docs/architecture/ffsmith_status.md`, this log |
| 2026-06-14 | **N2 job-stat derivation fully decoded** -- FFD derives all five attributes from a **single per-level base-stat byte** (§8 level row, byte **+6**) scaled by each job's stat-% (`body[11..15]`): `attr = max(1, base6[level] * jobPct / 100) + equip + ability`. **No separate per-character base attribute** -- the chara_set stat bytes are display/initial only. HP/MP use the same row's BE-u16 `+2`/`+4` x `body[9]`/`[10]`%. FF5 `SetMemberStatus` uses a *flat* bonus model (`HP = baseHP + baseHP*(VIT+jobVitBonus)/32`), confirming byte layout while proving FFD != FF5 model. base6 grows 20->32 over L0-15; HP/MP match canonical Sol L3=70/23, Aigis L10=199/51; engine harness reproduces Sol L3 -> HP60 MP19 STR10 SPD10 VIT9 INT6 MND6. | `SetJobStatus` libjniproxy 152644-152705 (primary); `SetMemberStatus` decomp 72718-72783; boot §8 dump | jobs.md, `ffsmith_bake.py` FLVL, FFSmith `host.cpp` |
| 2026-06-14 | **FFD party model = dual Light/Dark, 5 each** -- `GameClass::GetPartyMemberID(i)` = `this[i*4 + side*0x20 + 0x21428]`: a **side selector** at `+0x21424` (0=Light, 1=Dark) indexing two charaID arrays (8 slots/side, 5 active) at `+0x21428`. Entered-roster bitmask (24 chars, IDs 0-23) at `+0x2172c` via `AddEntryPartyMember`. Per-character MEMBER_STATUS at `+0x1a180` stride 0x4c4; per-party struct stride 0x840 (member-slot @+0x1b8). | `GetPartyMemberID` libjniproxy 153556; `AddEntryPartyMember` 120483; `InitEntryPartyMember` 120467 | FFSmith `host.cpp` (`parties_[2]`/`partySide_`/`switchSide`, FSAV v6) |
| 2026-06-14 | **chara_set equipment was mis-offset** -- the 5x BE-u16 block at body offset 12 (was mislabelled `f181`) is the real **equipment** (R.Hand/L.Hand/Head/Body/Accessory); the 6/7x BE-u16 block at offset 23 is the **ability** list. Fixes weapons showing in head/off-hand slots. | `GameClass::ReadStartData` libjniproxy 151839-151899; Aigis=Iron Sword/Bronze Shield/Helm/Armor, Gawain=Galatine/Knight's set | `characters/parser.py`, `ffsmith_bake.py` FCHR |

- snd.dat is **not** gzip-wrapped (the old scanner found nothing because there was nothing).
- Door warps are **not** map-header encoded (first assumption) — they're script-var idiom via common event 0x104.
- The per-chip "overhead priority bit" does **not** exist — z-order is the layer-threshold sort.
- `system_message.msd` §4 is **not** field dialogue (coincidentally coherent decoy).
- Monster "level" (`field14`) is **not** a difficulty proxy (Werewolf atk 205 at "level 1") — resolved 2026-06-10: that "atk" was `stat_b` = weapon-attack body[15]; level body[0] IS the level, and high-watk low-level monsters are simply hard-hitting.
- Old `stat_c` was **not** the monster's DEF (real DEF = body[18]).
- `e3_param.dat` is **not** the retail start party path.
- Script warps do **not** auto walk-in a step — beats land exactly on dispatcher tiles (tried, reverted 2026-06-11); m200's off-by-one spawn expects a real player step.
- A consumable's **heal amount is not a literal body field** (Potion's "100" appears nowhere in its 54-byte body; 2026-06-13). body[5] `use_category` classifies the effect (1 HP/2 MP/3 full/5 revive) but the magnitude is resolved through a separate effect table from the use-item path — still unmapped.
- Item `attack`/`defense` are **not** at body[6]/[7] (the old `_ITEM_FIELDS` guess); the real equip stat is the single body[32], read as ATK or DEF by item_type.
