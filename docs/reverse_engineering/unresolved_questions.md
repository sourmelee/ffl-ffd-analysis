# Unresolved Questions

*Audit 2026-06-10. The honest list. Grouped by blast radius. (E) = blocks engine milestones, (T) = toolkit/format completeness, (M) = modding.*

## High value

1. (E) **`0x50 ScriptEncount` semantics** — formation id source, battle params, post-battle script resume. Blocks closing the retail intro into playable m150.
2. (E) **`SetJobStatus` stat derivation** — how base stats + job + level + equipment produce BTLACT A/W/D. Blocks damage exact-match.
3. (E) **Original RNG + turn scheduler** — Mobile = `java.util.Random`; Android's own PRNG unidentified. Blocks any trace-level battle/encounter match.
4. (T/E) **Random-encounter mechanics** — how `encount_ratio` + (suspected) floor-attr value 15 + step logic select formations; Android formation table location.
5. (T) **Android map mc_id 27% tail** — which side is right where engine parse and overrides disagree; meaning of bucket bytes chunk[18]/chunk[5].
6. (T/M) **Monster body full field map** (~50/64 bytes), incl. attack/defense/elements/AI hooks; job body 126-byte tail (per-job HP%/MP%); magic body 54-byte semantics; item use-effect encoding.

## Medium

7. (E) **Per-map wrap flags** — where in the chunk header; needed for world-map edge wrap (CheckMovePass modulo path is decoded, its trigger flags' storage isn't).
8. (E) **Boot conditions 2/3** exact trigger types; common parallels 0x102/0x105/0x106 behavior; page register (`+0xe474`) full semantics; script timer ticking model; `0x32` wait timing.
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
