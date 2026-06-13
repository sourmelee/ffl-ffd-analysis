# Toolkit Contradiction & Drift Report

*Audit 2026-06-10. Problem → evidence → resolution. Engine-side report: `Engine/docs/development/contradiction_report.md`.*

## 1. `ffsmith_bake.py` module docstring documents FFM1; the code writes FFM4
**Evidence:** docstring lines 8–12 ("FFM1, format below") vs `FFMAP_MAGIC = b"FFM4"` (line 43) and the FFM4 spawn/rect/appear writers.
**Resolution:** Replace the docstring's format block with a pointer to `docs/architecture/asset_pipeline.md` (now authoritative).

## 2. README says "18 tabs"; `FFDApp.TAB_ORDER` has 20
**Evidence:** README "The notebook displays 18 tabs"; `gui_core/app.py:48` lists 20 (the README's tab list omits **Android Export** and **Comparison**, both of which have full implementations and their own CLI).
**Resolution:** Update the README count and add the two missing tab descriptions.

## 3. README Monsters-tab text still teaches the §12 story
**Evidence:** README: "Mobile uses big-endian boot_data section 12 (with section 16 as fallback)". `monsters/parser.py` docstring: §8 is correct; §12 is the tileset preload table; the §12 claim is explicitly called out as the old error. The tab itself calls `parse_enemies_mobile`, which now wraps the corrected §8 parser — so only the README prose is wrong.
**Resolution:** Fix the README sentence.

## 4. HANDOFF_NEXT_CHAT.md stale counts
**Evidence:** "8 unwired AssetKinds in the comparison framework" — registry has 4 wired + **5** stubs (Character/Monster/Job were wired after the note was drafted). Also lists "custom Mobile palettes" as open — shipped (custom_palettes.json, v4 of the converter, per memory + README).
**Resolution:** Refresh HANDOFF when next edited; meanwhile `docs/architecture/toolkit_status.md` is the accurate count.

## 5. `parse_enemies_mobile` legacy aliases fabricate zeros
**Evidence:** `monsters/parser.py:158` fills attack/defense/magic/gil/exp/… with 0 "legacy aliases used by existing tabs". MonsterTab and CrossRef display these as if real.
**Resolution:** Either render "?" for unmapped fields or decode the real offsets (exp/gil ARE known — body[6]/[10] — yet the alias sets them to 0 while `decode_monster_body` is available; wire them).

## 6. Baked stats provenance is weaker than it looks
**Evidence (original):** FITM atk/def regex-scraped from English descriptions; FMON atk/def/level from partially-mapped `stat_b`/`stat_c`/`field14`; FSPL was a hardcoded 11-spell list (`CAST`). All inside `_bake_menu_data`, all commented, none visible from the bundle itself.
**Resolution:** **Largely resolved 2026-06-13** — FITM atk/def now decoded from body[32] (`LoadItemData`); FSPL now the real 251-spell table decoded from the magic body (`LoadMagicData`/`CalcMagicDmg`); FJOB adds real per-job HP%/MP%. Monster stats were decoded earlier (FMN2). Remaining weak spot: consumable use-effect *magnitudes* still come from description text. Longer-term: surface provenance in manifest.json.

## 7. `docs`-vs-code drift inside `mc_overrides.py`
**Evidence:** module docstring: "Until that header field is decoded, we let the user annotate…" — the header field **was** decoded (engine parser, 73%); the override system's role shifted from "stopgap" to "correction layer", and the file also grew custom-palettes + tileset-builds storage its docstring doesn't mention.
**Resolution:** Refresh docstring; content reality is captured in formats/tilesets.md.

## 8. Workspace-root sidecar litter
**Evidence:** `../mc_overrides.json` (+ `.bak`), `../cpk_to_mc.json`, `../cpk_to_mc - Copy.json`, `../cpk_to_mc_v2_backup.json` at the workspace root; the code reads only `Python/data/` (`FFData._data_dir`). Root copies differ in size from the live ones (e.g. root mc_overrides 399 KB vs data/ version).
**Resolution:** Confirm the root copies are pre-migration artifacts, archive or delete. **Do this with Jack** — they may be intentional backups. Also `scratch_tileset_*` smoke dirs at root are session leftovers.

## 9. "Unit-tested headlessly" (0.7.22) vs no tests in repo
**Evidence:** CHANGELOG claims sprite_grid helpers are unit-tested; no test files exist anywhere (`find -name 'test*'` empty). README's limitations section honestly says "No automated tests yet."
**Resolution:** The tests were session-time verifications. Either commit them or rephrase future changelog entries ("verified headlessly" not "unit-tested").

## 10. Commit-message version typo
**Evidence:** commit `065bfc4` "Version 0.2.23 - FFSmith audio support" — should be 0.7.23. Harmless; recorded so future archaeology isn't confused.

## 11. Dead/duplicate code candidates
- `ffd_toolkit_BACKUP.py` (9,715 lines) — the pre-split mega-module, kept at repo root; confusing for newcomers, shadows nothing but doubles grep hits. Move under `attic/` or delete (it's in git history).
- `parse_enemy_names_android` marked DEPRECATED but still exported.
- `ffd_obb_extractor.py` — intentional back-compat alias (keep, it's documented).
- `events/strings.py` `extract_sjis_strings` — utility, only ad-hoc usage.
**Resolution:** sweep during the next MINOR release.
