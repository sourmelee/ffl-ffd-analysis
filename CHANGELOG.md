# Changelog

All notable changes to the FFD/FFL Toolkit are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **MAJOR** — breaking changes to parsers, the `.ffdproj` schema, or the
  public `from ffd_toolkit import ...` surface.
- **MINOR** — backward-compatible new capability (new tab, new parser,
  new menu entry, new CLI flag).
- **PATCH** — bug fixes and small internal cleanups.

The canonical version string lives in [`ffd/__init__.py`](ffd/__init__.py)
(`__version__`); every consumer imports from there. Bump it in the same
commit as the changelog entry.

## [Unreleased]

## [0.3.0] - 2026-05-31

### Added

- **Independent cpk/mc selection (`SpriteConverterTab`, Tilesets mode)**:
  a new **Link auto-match** checkbox (default on) in the tileset action
  bar. While ticked, picking a Mobile cpk auto-selects the matching
  Android mc (and vice-versa) via `cpk_to_mc` as before; unticking it
  guards both `_auto_match_android_tileset` and `_auto_match_mobile_tileset`
  so cpk and mc can be chosen completely independently.
- **Mobile→Android colour picking in the custom-palette editor**: the
  dialog gains a **Pick: Mobile→Android** mode. Click a colour in the
  Mobile pane to select the palette index that produced it, then click the
  Android pane to assign the replacement RGB. Supplements (does not
  replace) the existing swatch grid, **Pick from Android**, colour
  chooser, and reset-to-native controls.
- **Tileset *builds* — manual edits now reach Maps + exports**: a new
  **Save tileset build** button (and an automatic bind on custom-palette
  save) records the current palette (native or custom), `cell_map`
  remaps, force-Android cells, and the fill-from-Android flag as a
  *build* bound to `(cpk_entry, variant)` in `data/custom_palettes.json`
  (under a new `builds` key). Builds are resolved **chapter-agnostically**:
  when several chapters carry a build for the same `(cpk, variant)` the
  highest-numbered chapter wins (treated as most up-to-date). New
  `ffd.maps.mc_overrides` helpers: `set_tileset_build`, `get_tileset_build`,
  `resolve_tileset_build`, `list_tileset_builds`, `bound_variants_for_cpk`,
  `delete_tileset_build`. New shared producer
  `ffd.sprites.mobile_tile_to_android.produce_build_tile` renders a cpk
  through a resolved build (palette + cells), normalising to a uniform
  512×512 (32px-tile) sheet.
- **Maps "Android, mobile tilesets" view honours builds**: all four
  resolver tiers in `_collect_android_with_mobile_tilesets` now route
  through `produce_build_tile`, so manual palette/cell edits appear in the
  live preview — on top of the routing overrides (`cpk_to_mc_overrides.json`)
  that already fed it via `cpk_to_mc_inverse()`. Sheets are normalised to
  512px so the renderer never mixes 16px/32px tiles across a map's two
  slots (verified byte-identical to a plain 2× nearest-neighbour upscale,
  so tile addressing is unchanged).
- **Extracted Mobile-tileset maps + mass-convert honour builds**:
  `ExtractTab._make_mobile_ts_cache_for_extract` (used by *Extract maps,
  mobile tilesets*) routes through the same build-aware producer, and the
  *Mass convert tilesets* sub-tab applies a build for `(cpk, variant)`
  when emitting each variant and additionally emits any user-built
  variant the OBB never shipped (e.g. a hand-authored `mc{id}_3`).

- **Custom Mobile palettes for missing Android variants
  (`SpriteConverterTab`, Tilesets mode)**: a new **Build custom
  palette...** button in the tileset action bar opens a modal where the
  user hand-crafts a Mobile `cpk` palette for Android `mc` variants the
  Mobile build never shipped a palette for (e.g. Chapter 5 cpk7 has 2
  Mobile palettes but the matching `mc` has 4 variants; the RGBA-only
  `mc34_0`/`mc60_0` sheets also break the `swap` path). The editor shows
  one swatch per palette colour; the user clicks **Pick from Android**
  then clicks the Android pane to sample that pixel's RGB into the active
  index (the index stays put until **Next** is pressed), or opens a Tk
  colour chooser for arbitrary colours, or resets to the native palette.
  The Mobile pane re-renders live as colours are assigned. Saved palettes
  persist in `data/custom_palettes.json` keyed per `(chapter, cpk_entry)`
  and **extend the Mobile-palette dropdown** as extra indices
  (`n_native`, `n_native+1`, ...). Selecting a custom index renders the
  cpk through that palette and runs the normal 2x nearest-neighbour
  upscale + `fill_from_android` flow, so the missing variant is authored
  from Mobile pixels (stays integer nearest-neighbour per the pixel-art
  rule; verified 0 non-palette pixels introduced).
- **New sidecar `data/custom_palettes.json`** with helpers in
  `ffd.maps.mc_overrides`: `empty_custom_palettes`,
  `load_custom_palettes`, `save_custom_palettes`, `list_custom_palettes`,
  `get_custom_palette`, `add_custom_palette`, `delete_custom_palette`
  (+ `CUSTOM_PALETTES_FILENAME`). New `FFData` accessors:
  `custom_palettes_path`, `custom_palettes`, `save_custom_palettes`.
- **`ffd.tilesets.parser`**: `cpk_native_palette(cpk_data, off, sz,
  pal_idx)` returns `(nc, [(r,g,b), ...])` for a cpk palette;
  `render_cpk_with_palette(cpk_data, off, sz, palette_rgb)` renders a cpk
  entry through an explicit RGB palette. New `MobileTilesetResolver`
  methods `get_palette(eid, pal_idx)` and `get_with_palette(eid,
  palette_rgb)`.


## [0.2.1] - 2026-05-31

### Changed

- **Manual overrides now propagate to the Maps tab**:
  `FFData.cpk_to_mc_inverse()` overlays `cpk_to_mc_overrides.json`
  entries on the SAD-derived reverse table with `best_sad = 0` so
  they sort first. Both top-level overrides and `by_palette[N]`
  entries contribute reverse candidates. Saving an override via the
  Sprite Converter's "Save override" button also invalidates
  `_cpk_to_mc_inv_cache` so the next Maps render picks it up
  immediately (no restart needed). Effect: a `Chapter 5 cpk1 → mc1_0`
  override now correctly renders Android maps that reference mc1 with
  the Chapter 5 cpk1 tileset in the "Android with Mobile tilesets"
  Maps view, matching the Sprite Converter's auto-match.

## [0.2.0] - 2026-05-30

### Added

- **Mobile palette picker in `SpriteConverterTab` (Tilesets mode)**:
  the action bar exposes a *Mobile palette* combobox populated from
  `count_cpk_palettes(sp_files, entry_id)` for the selected `cpk`
  entry (Chapter 1 cpks have 2–4 palettes each). Switching palettes
  re-renders the Mobile image via `MobileTilesetResolver.get(eid,
  pal_idx)` and live-updates the preview.
- **Per-cell tileset remap (click-click + drag-and-drop)**: click a
  Mobile cell, then click an Android cell, to write
  `cell_map["dst_col,dst_row"] = {mobile_col, mobile_row, flip_h}`.
  Drag from Mobile pane to Android pane has the same effect. Cyan
  outlines on remapped Android cells with the Mobile source label.
- **Per-Android-cell source override**: right-click an Android cell
  → context menu with "Use Mobile (default — clears overrides)",
  "Use Android original (force_android)", and "Clear remap". New
  `android_target.force_android_cells` list (`"col,row"` strings)
  pastes the Android original tile after `cell_map` and before
  `fill_from_android`. force-Android wins over cell_map. Magenta
  outline + "A" label on force-Android cells.
- **Resizable four-pane layout for `SpriteConverterTab`**: the body
  is now a `ttk.PanedWindow(orient="horizontal")` so all four panes
  (Mobile | Android | Preview | Inspector) have draggable sashes
  with equal initial weight.
- **`cpk_to_mc_overrides.json` manual override layer**: takes
  absolute precedence over `cpk_to_mc.json`. Stored at project root.
  Structure `{entries: {ChapterDense: {cpk: {mc_id, variant,
  by_palette?: {N: {mc_id, variant}}}}}}` — supports overall and
  palette-specific overrides. New helpers in
  `ffd.maps.mc_overrides`: `empty_cpk_to_mc_overrides`,
  `load_cpk_to_mc_overrides`, `save_cpk_to_mc_overrides`,
  `set_cpk_to_mc_override`, `lookup_cpk_to_mc_override`. New
  `FFData` accessors: `cpk_to_mc_overrides_path`,
  `cpk_to_mc_overrides`, `save_cpk_to_mc_overrides`. Tileset action
  bar gets a **Save override** button that prompts palette-specific
  vs overall save scope via `askyesnocancel`.
- **Palette-aware SAD matcher** (`Python/tools/regenerate_cpk_to_mc.py`):
  for every (chapter, cpk_entry, palette_idx) computes alpha+luminance
  SAD against every (mc_id, variant) in the OBB, masked to Mobile-
  opaque pixels. Output adds `best_palette` (winning Mobile palette)
  and `by_palette: {N: {mc_id, variant, best_sad, second_*, gap}}`
  per cpk_entry. Loads `mc*.png` from `Android/proper_obb/` (~0.6s)
  instead of re-decrypting the OBB (~41s). Supports `--resume`
  (skips chapters already in the output file), `--only-chapters
  X,Y` for chunked runs, and per-chapter incremental saves so a
  partial run survives a timeout. Requires NumPy.

### Changed

- **OBB XOR de-obfuscation is now a single bulk pass**
  (`ffd.containers.obb`): the 0x14 XOR over the ~209 MB OBB
  payload no longer loops byte-by-byte in Python. New
  `_xor14_inplace` helper does an in-place NumPy XOR on a
  `frombuffer` view when NumPy is importable, falling back to
  `bytes.translate` with a precomputed 256-entry table otherwise —
  both single C-level passes. Shared by decode
  (`_decrypted_obb_bytes` / `load_obb_as_dict`), encode
  (`dict_to_obb` / `folder_to_obb`), and the `is_ffd_obb_path`
  magic sniff. ~4× faster decode on the dependency-free path,
  ~40× with NumPy; output is byte-identical (golden SHA-256
  verified on both paths, plus an encode round-trip).
- **`render_ic` palette→RGBA conversion vectorised**
  (`ffd.images.ic`): the per-pixel `PixelAccess` write loop is
  replaced by a 256-entry RGBA lookup table handed straight to
  `Image.frombytes`. Uses NumPy when present, with a pure-Python
  `bytes`-join fallback. Index 0 and out-of-palette indices stay
  transparent, so every rendered thumbnail / map / sprite is
  byte-identical to the previous renderer (verified on both
  paths). ~3× faster in pure Python, 10×+ with NumPy — speeds
  up effectively every image the toolkit draws. (The now-unused
  `Image.new` scratch allocation it replaced is also gone.)
- **Magic-byte container scans use `bytes.find`** instead of a
  byte-by-byte Python loop. gzip-member discovery in `parse_snd` and
  `parse_resbin` (`ffd.music.parser`, `1f 8b`) and the `ic` image scan
  in `find_ic_offsets` (`ffd.images.ic`) now let the C runtime locate
  each magic. Output is byte-identical — verified function-by-function
  against the prior implementation over every real
  `snd*.dat`/`res.bin`/`cpk*.dat` — at ~8–10× for the audio scans and
  100×+ for the `ic` scan on dense cpks.
- **Sprite-container entry boundaries computed in one O(n) reverse
  pass** (`ffd.sprites.container`): `parse_sprite_container` and
  `iter_dat_entries` replaced a per-entry forward rescan for the next
  populated offset (O(n²)) with a single precomputed `next_off` table.
  Byte-identical output, verified on 2,775 `.dat` files plus a 200,000-
  case equivalence fuzz of the boundary logic.
- **Mobile map heuristic fallback avoids a 256 KB copy per byte**
  (`ffd.maps.mobile`): with no mpk index available,
  `scan_mobile_mpk_chunks` walks every offset; it now slices a
  `memoryview` (O(1)) rather than copying up to 256 KB of
  `data[pos:pos+0x40000]` on each step. ~6.7× faster across the 24 real
  Mobile `mpk*.dat` files (673 chunks, byte-identical output).
- **Unused-import sweep across `ffd/`**: autoflake removed unused
  imports from 31 modules (~1,300 fewer lines); the wildcard
  re-export shims in the package `__init__.py` files were left
  untouched. Import-only change with no behavioural difference —
  trims module import time and the pyflakes baseline.
- **`cpk_to_mc.json` regenerated with the v3 palette-aware matcher**.
  40 of ~125 cpks now have a different `mc_id` vs v2. Backup of the
  pre-regen file saved as `cpk_to_mc_v2_backup.json`. Each record
  gains two new fields: `best_palette` and `by_palette`. Top-level
  `mc_id`/`variant`/`best_sad`/`second_*`/`gap` fields stay for
  back-compat with legacy callers.
- **`lookup_mc_for_cpk` signature**: now accepts `palette=int` and
  `overrides=dict` kwargs. New source-tag values:
  `"override_palette"`, `"override_chapter"`. Chapter-step lookup
  also tries the space-stripped form of the chapter label so the
  GUI's `SP_SLOTS` labels (e.g. `"Chapter 5"`) match the JSON's
  dense keys (`"Chapter5"`).
- **Sidecar JSONs moved to `Python/data/`**: `cpk_to_mc.json`,
  `cpk_to_mc_overrides.json`, and `mc_overrides.json` now live
  inside the toolkit folder so they ship with the code in git.
  `FFData` resolves their paths via `_data_dir()` (computed from
  `__file__`) instead of searching project-root / next-to-archive /
  cwd. Old fallback locations are no longer checked. The folder is
  auto-created so first-time saves on a fresh checkout succeed.
  `tools/seed_mc_overrides_from_engine.py` and
  `tools/regenerate_cpk_to_mc.py` default outputs likewise point at
  `Python/data/`.

### Fixed

- **Slot-label normalisation bug in `lookup_mc_for_cpk`**: the
  per-chapter step previously always missed for `SP_SLOTS` labels
  (because they contain spaces but the JSON keys don't), causing
  the auto-match status bar to show `[aggregate]` instead of
  `[chapter]`. Verified end-to-end: `'Chapter 5'` now finds
  `'Chapter5'` entries.

## [0.1.4] - 2026-05-29

### Added

- **Tileset converter** (`ffd.sprites.mobile_tile_to_android`,
  `SpriteConverterTab` — new "Tilesets" sub-tab): converts Mobile cpk
  tile sheets to Android-format mc PNG sheets via 2× nearest-neighbor
  upscale with optional `fill_from_android` back-fill and two palette
  strategies (`verbatim` / `swap`). `tileset_default.json` mapping
  sidecar ships with the package.
- **Mass tileset conversion** (`AndroidExportTab` — new "Mass Convert
  Tilesets" sub-tab): batch-converts all Mobile cpk tilesheets in a
  loaded project to mc-format PNGs, writing output under a user-chosen
  directory with proper `mc{id}_{variant}.png` naming.

## [0.1.3] - 2026-05-28

### Added

- **Battle-animation parser** (`ffd.animation.parser.parse_btl_anm`):
  decodes `btlanm_sp.dat` — the Android battle-animation container.
  Handles the nested sub-container structure where entry 0 is a
  party-member template and `fldchr30`–`fldchr49` are individual
  character sheets.
- **`character_battle.json` mapping spec**: covers the full
  battle-animation to field-character sprite layout translation.

### Changed

- `SpriteConverterTab` overhauled: now supports `extra_frames` (Android
  positions outside the standard 5-row `field_anm` grid — KO/death
  sprites, unused-grid fillers, composite parts), multi-cell Mobile
  extracts via `mobile_cells_w`/`mobile_cells_h`, and `flip_h` per
  entry.
- `ffd.sprites.mobile_to_android`: fixed doubled-sprite artifact caused
  by dropping an unrepaginated 2×-upscaled Mobile sheet (160×288) into
  the Android slot (256×512); converter now re-paginates cells to match
  the 6 col × 5 row Android layout before compositing.
- `TextTab`: SJIS string scanner (`extract_sjis_strings`) integrated
  directly into the tab for single-click event-script string dumps.

### Fixed

- Several `ConverterTab` layout bugs corrected in follow-up commits
  (036f91f, 5139095).

## [0.1.2] - 2026-05-27

### Added

- **Sprite converter** (`ffd.sprites.mobile_to_android`,
  `ffd.sprites.converter_tab.SpriteConverterTab`): new "Sprite
  Converter" tab — interactive side-by-side viewer for mapping Mobile
  chpk cells onto Android fldchr sheets. Loads a JSON mapping spec
  (`frame_map` + `extra_frames`), renders both sheets at configurable
  zoom with overlay annotations, and writes the converted PNG.
- **Mapping specs** (`ffd/sprites/mappings/`): `sol.json` ships as the
  first hand-annotated character mapping (Sol party-member sheet).
- **Experimental OBB packer** (`ffd.containers.obb.dict_to_obb`,
  `folder_to_obb`): round-trips a `{filename: bytes}` dict back to a
  valid XOR-0x14 OBB archive. Byte-identical to the original for
  content-identical inputs. GUI "Encode" sub-tab added to
  `AndroidExportTab`.

## [0.1.1] - 2026-05-25

### Added

- **Android Export tab** (`ffd.android_export`): new GUI tab with two
  sub-tabs — "Extract" (batch-render Mobile chapter assets to
  Android-layout output folders: monsters, characters, tilesets) and
  "Encode" (pack a folder or dict back into an OBB). All images are
  2× nearest-neighbor upscaled.
- **ICP encoder** (`ffd.android_export.icp`): encodes PIL Images to the
  Android ICP payload format (palette + pixel data), mirroring the
  existing `decode_icp` decoder.
- **Export CLI** (`ffd.android_export.cli`): headless driver wired into
  `ffd_toolkit.py main()` — allows batch export without launching the
  GUI.
- **Comparison tab wired for all-sources + Jobs**: the `Comparison` tab
  now merges data across all loaded SP slots (`ALL_SOURCES_KEY`) and
  has a working Jobs comparison in addition to Items; remaining 6 kinds
  promoted from placeholder stubs to partial implementations.

## [0.1.0] - 2026-05-22

First tagged release. The toolkit was already functional for several
months of reverse-engineering work; 0.1.0 is the line we drew once the
project went up on GitHub.

### Parsers and formats

- `.sp` DoCoMo scratchpad container (Mobile / feature-phone build).
- `.obb` XOR-obfuscated FFD container (Android build), plus `.apk` /
  `.jar` ZIP archives and `.jam` manifest sidecars.
- IC image format (with BGR and RGB palette variants) and sprite
  containers; hidden-GIF extraction helper for Mobile assets.
- Mobile map parser (MPK chunks, MPKH index) and Android engine map
  parser (`_RomReader`, streaming chunk reader).
- `mc_overrides.json` and `cpk_to_mc.json` sidecar formats for the
  Android tileset-id remapping work.
- `boot_data.dat` 16-section TOC (BE for Mobile, LE for Android) with
  per-section loaders for the namedesc tables (items, monsters,
  abilities, jobs).
- Tileset parsers for both platforms (`MobileTilesetResolver`,
  `parse_android_tileset_lookup`).
- Monster / item / job / ability tables for both platforms, including
  Android magic, passive, and command-ability tables and the Mobile
  `bem.dat` enemy index.
- Character set (`chara_set.dat`) — Mobile big-endian/12-byte header
  chapter-scoped, Android little-endian/16-byte header full-roster.
- Message tables (`message.dat`, `.msd`), `snd.dat` audio, `resbin`
  audio-name table, field animations (`field_anm`), and `form.bin`.
- Event-script d