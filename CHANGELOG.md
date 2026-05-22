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

[Unreleased]: https://github.com/sourmelee/ffl-ffd-analysis/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sourmelee/ffl-ffd-analysis/releases/tag/v0.1.0
