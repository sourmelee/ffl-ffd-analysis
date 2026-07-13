# Unresolved Questions

*Audit 2026-06-10. The honest list. Grouped by blast radius. (E) = blocks engine milestones, (T) = toolkit/format completeness, (M) = modding.*

## High value

1. ~~(E) `0x50 ScriptEncount` semantics~~ **RESOLVED 2026-06-10** (see discoveries log / formats/battles.md). Residue: `bsc.dat` battle-script VM, the battle-condition flag table values (DAT_00418f94), and per-formation loss handling.
2. (E) **`SetJobStatus` stat derivation** — how base stats + job + level + equipment produce BTLACT A/W/D. Blocks damage exact-match.
3. (E) **Original RNG + turn scheduler** — Mobile = `java.util.Random`; Android's own PRNG unidentified. Blocks any trace-level battle/encounter match.
4. (T/E) **Random-encounter roll** — areas/formations/ratio are now decoded+baked (FFM5/FENC); still open: the per-step roll formula combining rate × encount_ratio (× floor-attr 15?), and where it runs. FFSmith `--encounters` ships an approximation.
5. (T) **Android map mc_id 27% tail** — which side is right where engine parse and overrides disagree; meaning of bucket bytes chunk[18]/chunk[5].
6. (T/M) **Remaining body maps** — monster body is now ~70% mapped (battles.md; open: b[16/17/22/23/26/28], element groups b[29..32], the 0x2c..0x46 tail incl. suspected AI/drops). **Resolved 2026-06-13:** magic body (mp/power/type/element/formula — jobs.md) and the job growth multipliers (HP%/MP%/stat% = body[9]/[10]/[11..15]). Still open: the rest of the job 126-byte tail (ability-learn lists, equip/element flags) and **item use-effect *magnitude*** — body[5] classifies the effect (HP/MP/full/revive) but the heal amount is resolved via a separate effect table, not a literal body field.

## Medium

7. (E) **Per-map wrap flags** — where in the chunk header; needed for world-map edge wrap (CheckMovePass modulo path is decoded, its trigger flags' storage isn't).
8. (E) **Boot conditions 2/3** exact trigger types; common parallels 0x102/0x105/0x106 behavior; page register (`+0xe474`) full semantics; script timer ticking model; `0x32` exact tick rate (frames assumed). ~~NPC *autonomous* wander (`MoveCharaAuto` + the chara `pattern` field)~~ **RESOLVED 2026-07-11** — decoded + implemented (`formats/events.md` "NPC auto-wander"; FFSmith 0.3.0 `Field::tickWander`, toolkit 0.9.0 FFM6). Still open within it: the face-command duration and the exact CheckMovePass chara-flag gates (`+0x48` bits 0xc40).
9. (E) **Choice-line text source** (option value = msg id works empirically — confirm).
10. (E) **Original save format** (`save.bin`, 15 KB/slot) — entirely undecoded (saves.md).
11. (T) **Map layer attribute planes** (flag_a/flag_b payloads) — skipped, never decoded.
12. (T) **capk word B** (u24 per chip) and floor-attr values 1/8/12/15.
13. (T) **ICP unknown header fields + variant-prefix tail**; what writes/reads unk1/unk2 engine-side.
14. (T) **MFi v5 `trac` event stream** — blocks MFi→MIDI.
15. (E) **Timing model** — is the original frame-locked at a fixed Hz? Movement speed/anim speed never trace-verified.
16. (T) **Mobile collision source** — where Mobile stores chip passability (capk equivalent).

## Low / curiosity

17. Why the Android OBB ships unused Mobile-format assets (`Mobile_Assets_In_Android_Version_unused`).
18. `battle_bg_water` and the two unnamed map-header u8s' runtime use.
19. Android `snd1_*` bank contents/role.
20. Message control codes inventory (color/pause escapes).
21. The 8 undumped Mobile chapters — external (lost media), not an RE question per se, but caps Mobile coverage.

## Standing method note

Every answer should land as: decompilation citation → toolkit parser/bake → engine consumption → self-test — in that order (the symbiosis loop). Questions resolved only in chat/memory rot; resolve them into this tree.
