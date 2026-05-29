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
- Event-script disassembler (`opcodes 0..0xab`, big-endian operands)
  with Mobile and Android container loaders and a SJIS string scanner.

### GUI

- Tk-based notebook of tabs: Files, Extract, Map, Map Annotation,
  Event Script, Text, Character, Animation, Tileset, Background,
  Battle Effect, Monster, Music, Ability, Item, Job, Cross-Ref,
  Comparison.
- Per-tab data refresh via `FFData` listeners.
- Status bar with archive / SP-slot summary.

### Project save / load

- `File > Save Project` writes a lightweight `.ffdproj` JSON snapshot
  of every loaded SP slot and archive path.
- `File > Save Project Bundle (embed files)` additionally embeds every
  referenced file (and zips folder-style sources) as base64 inside the
  `.ffdproj`, producing a self-contained workspace.
- Each entry stores both `path_rel` (relative to the `.ffdproj` file)
  and `path_abs`; the loader prefers relative, falls back to absolute,
  then to bundled bytes.
- `File > Load Project` restores everything in one click; missing slots
  surface as warnings rather than blocking the load.
- `File > Recent Projects` submenu, automatically updated on save/load,
  with a `Clear list` option.
- Auto-load: the toolkit reopens the last project on startup. State
  lives in `Python/.ffd_toolkit_config.json` (gitignored).
- Bundles materialize embedded bytes into a per-process temp dir which
  is cleaned up on the next load and on shutdown (both `Quit` menu and
  window-close handlers).
- `.ffdproj` files record both a wire-format version (`version: 1`,
  bumped only on schema changes) and an informational `toolkit_version`
  (the release that wrote the file).

### Comparison framework

- Phase-1 Mobile-vs-Android divergence mapper (`ffd.comparison`)
  exposed via both a `Comparison` tab and the headless
  `python ffd_toolkit.py --compare` CLI.
- Wired asset kinds: items. Stubs in place for the remaining 8 kinds.

### CLI

- `python ffd_toolkit.py` — launch GUI.
- `python ffd_toolkit.py --version` / `-V` — print version and exit.
- `python ffd_toolkit.py --compare ...` — headless asset comparison.

[Unreleased]: https://github.com/sourmelee/ffl-ffd-analysis/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/sourmelee/ffl-ffd-analysis/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/sourmelee/ffl-ffd-analysis/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/sourmelee/ffl-ffd-analysis/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/sourmelee/ffl-ffd-analysis/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/sourmelee/ffl-ffd-analysis/releases/tag/v0.1.0
