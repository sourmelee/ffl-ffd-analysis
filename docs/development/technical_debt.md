# Toolkit Technical Debt

*Audit 2026-06-10. Ranked.*

1. **Zero automated tests** for ~24K LOC of parsers whose correctness the engine depends on. The eyeball-verify culture works because Jack verifies, but every refactor risks silent corruption that only shows up as a weird render later. (testing_strategy.md)
2. **Dual-maintained bundle formats**: every baked format exists twice (writer in `ffsmith_bake.py`, reader in `Engine/src/data/bundle.cpp`) with no shared schema or round-trip test. A one-byte drift = corrupted bundles with no error. Highest-leverage fix: a Python reader for every baked format + a bake→parse round-trip check (the FSAV verification already proved this pattern).
3. **`_bake_menu_data` is a 125-line try/except monolith** that silently `print`s and skips on any error ("menu data skipped") — a failed table bake produces a *valid-looking* bundle missing items/chars/levels. Should fail loudly per-table.
4. **GUI tabs of very different quality/size**: `sprites/converter_tab.py` is 3,807 lines (larger than some whole domains) with logic interleaved into Tk code; `maps/tab.py` 1,340; `files_io/extract_tab.py` 1,229. Parser/GUI separation is clean elsewhere — these three accreted.
5. **Heuristic data in baked output without provenance** (desc-regex atk/def, stat_b/c, hardcoded spell list) — see contradictions #6.
6. **`ffd_toolkit_BACKUP.py`** (9.7K lines) at root.
7. **Sidecar JSON growth**: `custom_palettes.json` now holds palettes *and* builds; `mc_overrides.json` is 400 KB. Format versioning inside these files is informal (`empty_*` constructors define shape). A bad write loses annotation labor — backups exist for mc_overrides (timestamped) but not the others.
8. **Environment fragility knowledge lives in memory/HANDOFF, not code**: the Edit-tool truncation / stale-`__pycache__` gotchas could be partially mitigated by a `make verify` style script (compile-check + import + version print).
9. **`parse_android_map_chunk` (heuristic) vs `parse_android_map_engine` (engine port)** both exist and both get used (baker uses both: chunk for layers, engine for header). Their disagreement surface is undocumented; the heuristic one's `_looks_like_tile_data` probing deserves a correctness note or retirement where the engine parse suffices.
10. **CLI surface is scattered**: `--bake-ffsmith` (in ffd_toolkit main), `--android-export`/`--android-encode` (`android_export/cli.py`), `--compare` (`comparison/cli.py`), plus three standalone `tools/` scripts. Fine today; document-or-unify when the next CLI lands.
