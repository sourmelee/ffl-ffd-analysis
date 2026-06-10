# Toolkit Testing Strategy

*Audit 2026-06-10. Current state: no automated tests (README acknowledges this). QA = eyeball-verification by Jack + cross-platform byte comparisons done ad hoc in sessions.*

## What implicitly tests the toolkit today

- FFSmith's byte-identical render gate (any compositor/parser drift breaks the engine diff).
- `dict_to_obb` byte-identical repack (a standing self-check for the OBB decoder).
- ComparisonTab cross-platform record diffs (catches parser regressions when a human looks).
- `seed_mc_overrides_from_engine.py` dry-run mode (engine-parser sanity over 1,679 maps).

## Recommended build-out (ordered)

1. **Parser fixtures** (README's own suggestion): commit a handful of *small, non-copyrighted* known chunks — synthetic or truncated-with-permission samples are the clean-room-safe route; where that's impossible, fixture = (hash of input slice taken from the user's local OBB path, expected parsed dict). A `pytest` run that skips cleanly when local game files are absent and verifies fully when present matches the project's no-assets rule.
2. **Bake round-trip** (after refactoring candidate #1): bake a 2-map bundle from local data → re-parse with the Python readers → assert tables/records/pixel hashes. This single test guards the entire engine contract.
3. **Endian/TOC invariants**: boot_data TOC walk, namedesc record-count assertions per section (counts are stable facts: 640 items, 33 jobs, 645 monsters, 512 magic, 113 passive, 50 command, 21 chars).
4. **Sidecar JSON schema checks**: load each data/*.json, validate shape, ensure no `user_confirmed` entry would be overwritten by the seeders' dry-run.
5. **GUI smoke**: headless `import ffd` + construct each parser on empty bytes (must not raise unhandled); full Tk smoke stays manual (Jack/Windows — tkinter can't run in the sandbox).

## Environment notes (from hard experience — see memory `feedback_file_tool_quirks`)

Shell-side file reads can be stale after editor writes (verify with `wc -l`/import); clear `__pycache__` and `touch` sources before re-importing; run long bakes in bounded chunks (`--limit`, `--only-chapters`, `--resume` already exist for this reason).
