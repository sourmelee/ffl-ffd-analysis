# Format: Enemy AI

*Audit 2026-06-10.*

## Status: NOT DECODED

No enemy-AI format, table, or routine has been reverse-engineered in either repo. Recording the little that is known so future work starts honestly:

- **Where it must live (Inferred, MEDIUM):** `BattleClass` (636 methods) in `libjniproxy.so_new.c` — turn scheduling and action selection are in there; the Mobile twin is `class_16` (14k lines, "stat/battle tables & math" per the roadmap's correspondence table).
- **Monster body bytes:** ~50 of the 64 body bytes are unmapped (battles.md); an `ai_type`/action-list pointer plausibly hides there (**hypothesis, LOW** — the legacy `parse_enemies_mobile` exposes an `ai_type` field that is hardcoded 0, i.e. fake).
- **FFSmith's enemy behavior** is a placeholder: every enemy attacks a random living member every turn (`Host::doEnemyAttack`), fixed SPD 7. No spells, no patterns, no targeting logic.

## Recommended attack plan (when this becomes a milestone)

1. Enumerate `BattleClass` method surface from the `.h` (the roadmap's grep recipe), find the enemy-turn entry (`SetBtlEnemyParam` neighbors).
2. Cross-read `class_16`'s enemy action selection — Java keeps structure.
3. Diff against `libff5lib.so` (FFV's enemy AI is community-documented; the shared Mtx engine may mean shared dispatch shape).
4. Map whatever table indices appear back onto the unmapped monster-body bytes.
