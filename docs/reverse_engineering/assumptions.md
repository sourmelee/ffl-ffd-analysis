# Working Assumptions

*Audit 2026-06-10. Things the codebase treats as true without proof, or chooses deliberately. If one of these breaks, the listed dependents break with it.*

## Format assumptions

1. **Tile size from sheet width** (≥512 px ⇒ 32 else 16) — heuristic in renderer/compositor/baker. Holds on all observed sheets. Dependents: every map render, FFM tile math.
2. **High byte of tile words is only 0/1** — observed-data claim, not engine-proved for all 1,679 maps. Dependent: slot dispatch.
3. **`msg{N}` bank = map group `g{N}`** — convention extracted from engine reading; FFSmith hardcodes `bankOf()` accordingly; the `msgBank` script variable could override it (stored, ignored).
4. **boot_data namedesc records are BE-on-both inside bodies** — verified for items/jobs/monsters/chara_set; *assumed* for magic/passive/command bodies (their fields are mostly unread anyway).
5. **`proper_obb/` ≡ in-OBB bytes** — the toolkit treats Colmines92-extracted folders as equivalent to decoding the OBB. Verified historically; new OBB versions would need re-checking (`tools/boot_data_analyze.py` exists for that).
6. **Layer 0 is the collision layer** — pass grid built from layer-0 tiles only; verified visually on town maps, not proved for all maps.
7. **Common-event pack byte-identical across all 15 groups** — verified once at 0.7.25 bake; baked as a single file on that basis.

## Engine-behavior assumptions (FFSmith)

8. **60 Hz frame-locked logic** matches the original's feel — unverified (no golden trace).
9. **Walk speed 2 px/tick @32 px tiles**, anim `speed×8` ticks/frame, damage floor HP/16, ATB threshold 256, EXP-to-all-survivors, rate 100% — all flagged approximations (Engine ffsmith_status.md has the full list).
10. **Appear-condition re-evaluation on flag writes** (dirty-flag rescan) reproduces `UpdateEventAppear` semantics.
11. **Auto-event loop guards** (≤4/event, ≤32/visit) — invented safety rails; the original presumably relies on script discipline + flags.

## Process assumptions

12. **Manual annotation beats heuristics** — sidecar JSONs with `user_confirmed` outrank any parser output; seeding tools must never overwrite confirmed entries (`seed_mc_overrides_from_engine.py` priority rules).
13. **Toolkit output = ground truth for the engine** — engine loaders are validated against Python bytes/pixels, not against the original game (original-game validation is a separate, mostly undone axis — see testing strategy).
14. **Ghidra structure is trustworthy, Ghidra types are not** — trust control flow, verify arithmetic behaviorally (roadmap Part 6).
15. **Pixel art: integer nearest-neighbor only** — hard rule.
