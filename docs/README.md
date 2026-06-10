# Toolkit docs index

*Living documentation from the 2026-06-10 repository audit. Engine counterpart: `../../Engine/docs/`.*

- **Start here:** `architecture/toolkit_status.md` — capability report (extraction/parsing coverage, confidence).
- `architecture/asset_pipeline.md` — **authoritative baked-bundle format spec** (FFM4, FTEX, all data/*.bin, FSAV/SST).
- `architecture/repository_relationships.md` — inputs, sidecars, outputs, doc map.
- `formats/` — per-format specs with confidence ratings: maps, tilesets, sprites, animations, events, text, audio, saves, battles, ai, jobs, items, effects.
- `reverse_engineering/` — discoveries log (incl. negative results), unresolved_questions, assumptions, confidence_matrix, contradictions.
- `development/` — roadmap, technical_debt, refactoring_candidates, testing_strategy.

Maintenance: keep these in sync with code changes (same spirit as the CHANGELOG rules in `../../CLAUDE.md`); every claim should carry a confidence label and, where possible, a source citation (file/function/decompilation line).
