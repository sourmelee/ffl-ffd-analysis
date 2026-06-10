# Toolkit Roadmap (post-audit, 2026-06-10)

*Toolkit work is demand-driven by FFSmith milestones (Engine/docs/development/roadmap.md) plus its own format-completeness goals. Versioning: PATCH freely, ask before 0.8.0+.*

## Engine-driven (near-term)

1. **ScriptEncount decode → bake** formation linkage (pairs with engine N1). Likely new: Android formation table parser + `data/encounters.bin`.
2. **Body decodes for battle fidelity** (engine N2): magic body 54 B, monster body field map (replace stat_b/stat_c guesses), job tail (per-job HP%/MP%), item use-effects. Each lands as parser fields + comparison-tab columns + re-bake.
3. **Wrap flags** — locate in the map header, bake into FFM (engine N6 prerequisite).
4. **Encounter tables** + floor-attr values 1/8/12/15 (engine N3).

## Toolkit-own

5. **Wire the 5 comparison stubs** (Magic, Sprite, Animation, Map, Text) — the framework + per-side source pickers already exist.
6. **Generalize non-48 character grids** (Sol 32×48, 16×16 NPCs) through the sprite_grid override path; Animation-tab eyeball pass on Windows (open per HANDOFF).
7. **Test scaffolding** — see testing_strategy.md; start with parser fixtures (README already names this as highest-value).
8. **MonsterTab/CrossRef honesty fix** — stop displaying fabricated zeros (contradictions #5); wire exp/gil which are already decoded.
9. **Docstring refresh sweep** — ffsmith_bake header, mc_overrides, README tab count/§12 (contradictions #1–#3, #7).
10. **MFi trac decode → MIDI** (deferred; nice-to-have for preservation).
11. **Mobile collision source** hunt (capk equivalent) — enables Mobile map collision rendering.

## Hygiene

12. Move `ffd_toolkit_BACKUP.py` to `attic/`; clean root-level sidecar litter with Jack (contradictions #8, #11).
13. Promote `[Unreleased]` CHANGELOG entries with the next release per the maintenance rules in `../CLAUDE.md`.
