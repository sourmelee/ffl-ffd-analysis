# Repository Relationships (Toolkit view)

*Audit 2026-06-10. Engine-side counterpart: `Engine/docs/architecture/repository_relationships.md`.*

This repo (`Python/`, github `sourmelee/ffl-ffd-analysis`, repo root = this folder) is the **decoding side** of a two-repo project; `../Engine` (FFSmith, separate git) is the **runtime side**. The contract: every on-disk game format is decoded once, here; FFSmith consumes only baked bundles (`--bake-ffsmith`). Correctness flows toolkit → engine (byte/pixel-match gates); decoded knowledge flows engine-RE → toolkit (new header fields become new bake fields: FFM2 events → FFM3 appear → FFM4 spawn/rect/id).

## Inputs (unversioned, machine-local)

- `../Android/proper_obb/` — Colmines92-tool extraction of `main.obb`; the preferred bake/parse source. `../Android/main.obb` — decodable directly (`ffd/containers/obb.py`).
- `../Mobile/Scratchpads/*.sp` — 6 dumped chapters (Chapter1/3/4/5, GladiatorHall, Online); 8 more are lost media.
- `../Mobile/Decompiled_Java_Classes/` — GuyPerfect's research base (class_16, class_20…).
- `../Decomp/FFV_FFD_compare/libjniproxy.so_new.c` — Android native ground truth (~254K lines); `libff5lib.so.c` — FFV Rosetta Stone; `../Decomp/Functions/` — pre-cut extracts. Docstrings cite line numbers in these files.

## Versioned sidecars (in this repo, `data/`)

`mc_overrides.json` (per-map tileset annotations: engine-derived + user_confirmed), `cpk_to_mc.json` (SAD-matcher output), `cpk_to_mc_overrides.json` (manual cpk→mc picks), `custom_palettes.json` (hand-built Mobile palettes + tileset builds). These encode *human verification labor* — treat as data assets, never regenerate over `user_confirmed` entries.

Note: stale copies/backups of some sidecars exist at the **workspace root** (`../mc_overrides.json`, `../cpk_to_mc.json`, `cpk_to_mc - Copy.json`, `*_backup.json`, `.bak-*`) from before the sidecars moved into `Python/data/`. The toolkit only reads `Python/data/` (`FFData._data_dir`). The root copies are unreferenced — candidates for archival/deletion (see contradictions #8).

## Outputs

- FFSmith bundles (gitignored, user-baked) — spec in `asset_pipeline.md`.
- `.ffdproj` project files (`ffd/project/serialize.py`) — GUI session state, light or bundled.
- Android-format exports of Mobile assets (`ffd/android_export/exporter.py`) and ICP re-encodes (modding path back into the OBB via `dict_to_obb`).

## Documentation map

- This `docs/` tree — toolkit status, format specs, RE knowledge (new, 2026-06-10 audit).
- `README.md` / `CHANGELOG.md` — user-facing; maintenance rules in `../CLAUDE.md` (changelog entry per `Python/` change; PATCH bumps free, ask before 0.8.0+).
- `../PROJECT_KNOWLEDGE_EXPORT.md` (2026-05-29) — the previous knowledge snapshot; partially superseded by this tree.
- `../HANDOFF_NEXT_CHAT.md` — session-handoff brief (some counts stale; see contradictions).
- Claude memory `ffd_*.md` notes — institutional knowledge index mirrored into these docs.
