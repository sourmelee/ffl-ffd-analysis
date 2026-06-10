# Toolkit Refactoring Candidates

*Audit 2026-06-10. Ranked by leverage; none are urgent — parsers are healthy.*

1. **Baked-format round-trip module** (`ffd/android_export/bundle_read.py`): Python readers for FTEX/FFM4/FITM/…/FSTR mirroring `Engine/src/data/bundle.cpp`, + a `verify_bundle(out_dir)` that re-parses everything just baked. Kills debt #2, enables tests, and gives editors a read path for free.
2. **Split `_bake_menu_data`** into per-table functions with explicit failure (items, chars, levels, monsters, spells), each returning provenance metadata into `manifest.json`.
3. **Extract converter-tab logic**: move the non-Tk parts of `sprites/converter_tab.py` (cell mapping, build resolution, palette workflows) into `sprites/` modules like the existing `mobile_tile_to_android.py` — the pattern already exists, the tab just outgrew it.
4. **Sidecar store class**: one `SidecarStore` owning load/save/backup/versioning for the four data/ JSONs (today: four sets of load/save/empty functions in `mc_overrides.py`, only one with backups).
5. **Monster decode unification**: fold `parse_enemies_mobile`'s alias layer into `decode_monster_body` returning explicit `None` for unmapped fields; update MonsterTab/CrossRef to render unknowns honestly (pairs with contradictions #5).
6. **Retire or fence `parse_android_map_chunk`'s heuristics** where `parse_android_map_engine` covers the need; document the residual cases the heuristic still wins.
7. **`attic/` sweep**: ffd_toolkit_BACKUP.py, deprecated exports, root sidecar copies (with Jack's sign-off).
8. **Schema-first table definitions** (longer-term, shared with engine/editor): JSON schema for items/chars/monsters/spells → generate the Python writer and C++ reader structs. This is the editor-foundation bottleneck named in `Engine/docs/future/editor_foundation.md`.
