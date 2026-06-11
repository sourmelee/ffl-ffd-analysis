# Confidence Matrix

*Audit 2026-06-10. One row per format/subsystem. Confidence: HIGH (engine-cited and/or byte-verified), MEDIUM (works, partially verified or approximated), LOW (guess/placeholder), — (not attempted). "Verified how" is the strongest single piece of evidence.*

| Area | Decode | Toolkit impl | Engine impl | Verified how |
|---|---|---|---|---|
| .sp container | HIGH | HIGH | n/a | full directory extraction (GuyPerfect lineage) |
| OBB container | HIGH | HIGH | n/a | **byte-identical repack** |
| ICP images | MEDIUM (unk fields) | HIGH | n/a | 2137/2137 pixel-perfect + symmetric encoder |
| ic images / sprite containers | HIGH | HIGH | n/a | renders match originals (eyeball) |
| Mobile map chunks | HIGH | HIGH | — | renders + event-region reconstruction |
| Android map chunk structure | HIGH | HIGH | HIGH (baked) | LoadMapInfo port; byte-identical engine render |
| Android mc_id selection | MEDIUM | MEDIUM | n/a | 73% strict vs 168 annotations + override system |
| capk pass/anim/floor bits | HIGH | HIGH | HIGH | collision overlays; 22,307 water cells; mc63 hazards |
| capk word B / floor values 1/8/12/15 | — | — | — | open |
| Z-order layer threshold | HIGH | HIGH | HIGH | per-map splits verified (m500/cave/m2601) |
| boot_data TOC + section maps | HIGH | HIGH | n/a | loader dispatch + empirical sections |
| Items / Jobs / Monsters / Chara records | HIGH (structure) | HIGH | HIGH (baked) | cross-platform byte identity |
| Monster body combat fields | HIGH (2026-06-10) | HIGH (FMN2) | HIGH | LoadMonsterData/SetBtlEnemyParam map; Goblin verified |
| Item/job/magic **body fields** | MEDIUM/partial | partial | heuristic consumers | offsets pinned only where listed in formats/ |
| §8 EXP thresholds + growth | HIGH | HIGH | HIGH | Sol/Aigis curves |
| §1 scenario/start | HIGH | HIGH | HIGH | New Game boots real m0 |
| Event packs + opcode table | HIGH | HIGH | n/a | disassembly vs MoveScript switch |
| Script exec model (registry, 0x3d/3f/40/3c/41/57/66/6b) | HIGH | HIGH (disasm) | HIGH | `--vmtest` + retail intro chain plays |
| Flag/var banks + appear blocks | HIGH | HIGH (baked) | HIGH | m501 doors, Barbara gate |
| Boot/trigger conditions | HIGH (0/1/4–8), LOW (2/3) | HIGH | HIGH | CheckRangeEvent + walk traces |
| ScriptEncount 0x50 + formations | HIGH (2026-06-10) | HIGH (FENC) | HIGH (pause→battle→resume) | `--enctest` PASS on real bank-0 data |
| Random-encounter areas | HIGH | HIGH (FFM5) | MEDIUM (approx roll, `--encounters`) | 8,154 areas parse; roll formula open |
| NPC-move / fades / waits | catalogued only | catalogued | log-skip | open |
| message.dat / msd / system_message / msg banks | HIGH | HIGH | HIGH (baked EN) | record-count cross-checks; on-screen text |
| field_anm | HIGH | HIGH | HIGH (geo baked) | MtxAnmCtrl cite + in-engine sprites |
| btlanm_sp | MEDIUM | MEDIUM | — | structure parses; playback unverified |
| Mobile chpk animation layout | MEDIUM (engine-hardcoded) | MEDIUM | n/a | user-adjusted grid |
| snd.dat MFi | HIGH (container), — (trac) | HIGH | n/a | valid .mld exports |
| Android OGG/bgm_loop/map BGM | HIGH | HIGH | HIGH | audible per-map BGM |
| form.bin formations | HIGH | HIGH | — | offset-table walk |
| BTLACT struct map | HIGH | n/a | partial consumer | SetMemberStatus/Calc reads |
| Damage formula core | HIGH | n/a | HIGH (core) MEDIUM (modifiers absent) | formula reproduces scaling |
| ATB / enemy AI / encounters | — | — | LOW placeholders | invented |
| Original save.bin | — | — | n/a | open |
| FSAV/SST (engine-own) | n/a | n/a | HIGH | round-trips + independent parser |
| cpk→mc mapping | empirical | HIGH (tooling) | n/a | SAD + human overrides |
| Mobile→Android converters | n/a (tooling) | HIGH | n/a | eyeball-verified output |
