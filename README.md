# FFL / FFD Toolkit

[![version](https://img.shields.io/badge/version-0.7.25-blue.svg)](CHANGELOG.md)

Reverse-engineering toolkit for **Final Fantasy Legends** (DoCoMo FOMA feature-phone, 2010 — Japan-only mobile release) and its 2013 Android remaster **Final Fantasy Dimensions**. The two builds share roughly 80% of their asset format DNA — the Android port re-encoded the mobile data files almost field-for-field, mostly flipping big-endian to little-endian and stuffing the obfuscated payloads inside an XOR-wrapped OBB. This codebase parses both.

The toolkit is a single Tk GUI plus a parser library, structured so that every viewer tab uses the same parsers a headless script would. Run the GUI, click around, and inspect map chunks, sprite atlases, event scripts, tile palettes, monster stats, etc. — or import `ffd.*` from your own scripts to do batch analysis without launching Tk.

---

## Getting started

**Requirements**: Python 3.7+, [Pillow](https://pillow.readthedocs.io/). Tk and `PIL.ImageTk` are needed for the GUI but optional for headless parser use.

```bash
pip install pillow
python ffd_toolkit.py
```

The GUI opens to the **Files** tab. Use the *File* menu (or the buttons inside the Files tab) to load:

- One or more **`.sp` scratchpads** — DoCoMo FOMA mobile chapters (Prologue + Chapters 1-10 + Finale Part 1/2 + Postgame, 14 slots total).
- The Android **`.obb`** archive, the **`.apk`**, and/or a `.jar` + `.jam` pair for the mobile build.
- Folders can also be loaded as if they were `.obb`/`.apk`/`.jar` contents (useful for the pre-extracted `proper_obb/` directory).

Once anything is loaded, every other tab pulls from the central `FFData` store; selecting an entry renders it lazily.

---

## Project layout

```
Python/
├── ffd_toolkit.py            # Launcher + back-compat re-export shim
├── ffd_obb_extractor.py      # Back-compat alias for ffd.containers.obb
├── ffd/                      # The package — split by domain
│   ├── binary.py             # BE/LE int readers + Shift-JIS pstr decoder
│   ├── constants.py          # SP_SLOTS, KNOWN_DAT_FILES, CHARA_TABLE, …
│   ├── gui_stub.py           # Lazy Tk/PIL.ImageTk import guard
│   ├── data/                 # Central FFData model (archive holder + listeners)
│   ├── containers/           # .sp, .obb, .apk/.jar, .jam loaders
│   ├── images/               # ic-format image parser/renderer
│   ├── sprites/              # Sprite-container .dat parsers
│   ├── maps/                 # Map chunk parsers + mc_overrides annotation system
│   ├── boot/                 # boot_data.dat section TOC + endian detect
│   ├── tilesets/             # Mobile mpk/cpk indexes + Android tileset lookup
│   ├── monsters/             # Enemy parsers + bem.dat name table
│   ├── items/                # Item parsers (mobile + Android)
│   ├── jobs/                 # Job class parsers (mobile + Android)
│   ├── abilities/            # Magic / passive / command ability parsers (Android)
│   ├── characters/           # chara_set.dat parser
│   ├── text/                 # message.dat / .msd parsers
│   ├── music/                # snd.dat (MFi/MLD) + res.bin audio-name parsers
│   ├── animation/            # field_anm.dat parser
│   ├── formats/              # form.bin (enemy formations)
│   ├── events/               # Event-script opcodes + per-platform extractors
│   ├── cross_ref/            # Cross-reference tab (enemy ↔ sprite ↔ formation)
│   ├── files_io/             # Files + Extract tabs
│   └── gui_core/             # FFDApp window, TabBase, shared widgets
├── tools/
│   ├── boot_data_analyze.py
│   ├── seed_mc_overrides_from_engine.py
│   └── regenerate_cpk_to_mc.py
└── data/                     # Sidecar JSONs (cpk_to_mc, mc_overrides,
                              # cpk_to_mc_overrides). Tracked in git.
```

The legacy mega-module pattern is preserved: `from ffd_toolkit import parse_ic` (and every other name the old `ffd_toolkit.py` exported) still works, courtesy of explicit re-exports in `ffd_toolkit.py`.

---

## GUI tabs

The notebook displays 18 tabs in this order, every one defined by a `TabBase` subclass with a `LABEL` constant.

**Files** — load `.sp` scratchpads into chapter slots and pick the Android container (`.obb` / `.apk` / `.jar` / `.jam`). Empty slots are flagged across every other viewer.

**Extract** — bulk export. Each row in `EXTRACT_OPTIONS` is a checkbox: sprite sheets per chapter (mobile chpk and Android cpk/mpk), map renders, raw `.dat`s, text dumps (items / magic / jobs / monsters in CSV/TSV), formation tables, collision data, etc. The Android boot-data-derived text dumps (items §5, magic §2, passive §3, command §4, jobs §6, bestiary §9) are TSV.

**Maps** — three sources: pure mobile (`.sp` `mpk*.dat`), pure Android (`.obb` `mpkh+mpk`), or Android-tile-IDs-against-mobile-tilesets (a useful diff view). Renderer is shared with ExtractTab; lazy on selection. Includes an "Obb inventory…" dialog and a "Chunk hex…" inspector.

**Map Annotations** — walks every Android map and lets you manually assign its primary `mc_id` + variant. Persisted to `Python/data/mc_overrides.json` (ships with the toolkit so annotations track in git). The tree is keyed by `(chunk[18], chunk[5])` buckets so similar maps cluster together. See **The `mc_overrides` annotation workflow** below.

**Event Scripts** — disassembles per-map event scripts on both platforms using the opcode table in `ffd/events/opcodes.py`. Each opcode has a mnemonic, an operand-format string, and a description; platform-specific opcodes are tagged `[Mobile]` or `[Android]` in the description.

**Text** — viewer for `message.dat` (Mobile, multi-section length-prefixed Shift-JIS) and `.msd` (Android UTF-8). Sections are labelled: Common UI, Common Shared, Ch1-7 Light/Dark, Cutscenes, Challenge Dungeon, etc.

**Characters** — renders `chara_set.dat`: each playable character's sprite indices (chpk entry + palette), equipment list, and the `CHARA_TABLE` mapping to canonical names.

**Animation** — sprite animation playback.
- *Android*: `field_anm.dat` has 63 generic field animations (idle, walk N/S/E/W, sit, talk, …). Every frame stores `tex_id=0` because the engine binds whichever `fldchr*_*.png` sheet the active character needs at runtime, then plays the universal animation against it. So the tab has **two** pickers: sheet first, then animation.
- *Mobile*: `chpk.dat` is an ic-container of character atlases. The engine hardcodes cell layout (typically 16×16, with rows per facing × walk frames per row). Tab slices using a user-adjustable cell size and plays the chosen sequence (full sheet / single row / ping-pong / etc.).
- *Object override (Android)*: mark a sprite as an **object** (door / chest / crystal) so FFSmith draws its real frame rect at a tile-relative anchor instead of the 48×48 character grid. The panel exposes `isObject` + frame `x/y/w/h` + anchor `px/py` with a live tile-aligned preview (`dst = tile/2+px, tile+py`), and Save/Remove write the `sprite_grid.json` the FFSmith baker merges (`--bake-ffsmith`). Use *Seed from field_anm* for the decoded default or *Use selected frame* to grab the frame shown in the player above.

**Tilesets** — browser for the mobile `mpk*.dat`/`cpk*.dat` pack contents and the Android tileset lookup table.

**Sprite Converter** — interactive Mobile → Android sprite/tileset converter with two source types selected via the top-bar *Source type* dropdown:
- *Characters*: maps Mobile `chpk` cells onto Android `fldchr` sheets via a JSON spec (`frame_map` + `extra_frames`). Right-side inspector exposes per-frame `h_align`, `v_align`, `scale`, `x_offset`, `y_offset`, `flip_h`.
- *Tilesets*: 2× nearest-neighbor upscale of Mobile `cpk` tile sheets into Android `mc{id}_{variant}.png` layout. Action bar exposes a *Mobile palette* dropdown (populated from `count_cpk_palettes`), the Android variant index, *Fill missing tiles from Android* checkbox, and a *Variant strategy* dropdown (`verbatim` / `swap`). Click a Mobile cell then an Android cell (or drag) to write a `cell_map` remap; right-click an Android cell for a source-override menu (Use Mobile / Use Android original / Clear remap). The **Save override** button persists the current (cpk, palette) → (mc_id, variant) pick to `cpk_to_mc_overrides.json`. For Android variants the Mobile build never shipped a palette for (an `mc` with more colour variants than the `cpk` has palettes, or the RGBA-only `mc34`/`mc60` sheets that break `swap`), the **Build custom palette...** button opens an editor where you hand-craft a Mobile palette by sampling colours straight off the Android pane (or picking arbitrary RGB). Saved palettes live in `data/custom_palettes.json` and extend the Mobile-palette dropdown as additional indices, so the regular 2× nearest-neighbour + fill-from-Android conversion can author the missing variant from Mobile pixels. A **Link auto-match** checkbox (default on) controls whether picking a cpk auto-selects its mc (and vice-versa); untick it to choose cpk and mc independently. Inside the custom-palette editor, **Pick: Mobile→Android** lets you click a Mobile-pane colour to select the index to replace, then click the Android pane for its replacement. **Save tileset build** records the current palette + cell remaps + force-Android cells as a *build* bound to `(cpk, variant)` (stored under a `builds` key in `data/custom_palettes.json`); builds resolve chapter-agnostically with the highest-numbered chapter winning, and are honoured by the Maps "Android, mobile tilesets" view and by both the *Extract maps (mobile tilesets)* and *Mass convert tilesets* export paths.

The four panes (Mobile | Android | Preview | Inspector) sit inside a `ttk.PanedWindow` with draggable sashes. Auto-match between the Mobile and Android pickers uses `cpk_to_mc_overrides.json` first, then `cpk_to_mc.json`, falling back to closest-numeric-ID.

**Backgrounds** — `bg.dat` viewer (mobile sprite-container subset).

**Battle Effects** — animated battle-effect sprite viewer.

**Monsters** — bestiary. Mobile uses big-endian boot_data section 12 (with section 16 as fallback); Android uses LE section 9 via the shared name+desc+body record layout.

**Music** — `snd.dat` and `res.bin`. `snd.dat` is an uncompressed 3-bank container of raw MFi (`melo…`) melodies exported as `.mld` (banks 0/1 = BGM, bank 2 = SFX); the Music tab pulls them from every loaded Mobile chapter and the Android `.obb` (single save or **Export all**). The audio-name list comes from `res.bin`. MFi v5 → `.mid` conversion is deferred.

**Abilities** — magic / passive / command, all from the Android boot_data section TOC (sections 2 / 3 / 4 in the namedesc TOC).

**Items** — item list. Mobile §4 (BE), Android §5 (LE).

**Jobs** — class records. Mobile §20 (BE), Android §6 (LE).

**Cross-Ref** — filterable browser tying enemy or character records to their sprite, stats, and the formations they appear in. Useful for spotting unused sprites or formation gaps.

---

## The `ffd/` package, module by module

### `binary.py`
Endian-aware integer readers (`be_u8`, `be_s8`, `be_u16`, `be_u32`, `le_u16`, `le_u32`), `read_pstr_sjis` for length-prefixed Shift-JIS strings, `safe_decode_ascii` for displaying ambiguous text.

### `constants.py`
- `SP_BASE = 64`, `DIR_POS = 16804` — header offsets inside `.sp` files.
- `SP_SLOTS` — the 14 canonical scratchpad labels (Prologue → Postgame).
- `KNOWN_DAT_FILES` — every `.dat`/`.bin` filename that may appear inside a scratchpad.
- `CPK_NAMES`, `MPK_NAMES` — `cpk0..9.dat` / `mpk0..9.dat`.
- `CHARA_TABLE` — `(chara_set_index, japanese_name, romaji_name, chpk_entry, palette_index)` for every playable character.
- `ELEMENTS`, `STATUSES` — element/status bit labels.

### `gui_stub.py`
Imports `tkinter` and `PIL.ImageTk` defensively, exposing `HAS_GUI` / `HAS_TK` / `HAS_IMAGETK` booleans and re-exporting Tk modules. Means `import ffd` works on a headless box; only `FFDApp().mainloop()` actually requires Tk.

### `data/ffdata.py`
The central `FFData` model. Holds raw bytes from every loaded source (`.sp` slots, `.obb`, `.apk`, `.jar`, `.jam`), exposes lookup helpers used by every viewer tab, owns the sidecar JSON caches, and notifies registered change-listeners so tabs refresh automatically on load/clear. Sidecar paths (`mc_overrides_path()`, `cpk_to_mc_path()`, `cpk_to_mc_overrides_path()`) all resolve to fixed locations in `Python/data/` — see `_data_dir()`. The folder is auto-created so first-time saves on a fresh checkout succeed.

### `containers/`
- **`sp.py`** — `parse_sp(path)` decodes a DoCoMo `.sp` scratchpad: skip the 64-byte header, read the directory at `DIR_POS = 0x41A4` (length-prefixed, optionally zipped), and yield each contained `.dat`. Returns `OrderedDict[filename, bytes]`.
- **`archive.py`** — `load_zip_container(path)` handles `.apk`/`.jar`/`.obb`; `load_folder_as_archive(path, kind)` mimics archive load semantics over a real folder.
- **`jam.py`** — `load_jam_manifest(path)` parses the DoCoMo `.jam` manifest sitting next to the mobile `.jar`.
- **`obb.py`** — Android `.obb` decoder. The file is **not** a real ZIP — it's a XOR-obfuscated custom container. The decoder:
  - Detects payload types by magic: `\x89PNG` → `.png`, `OggS` → `.ogg`, `INP\x??` → strip 4 bytes → `.png`, `mtxs\x00\x00\x00\x00…` → strip 16 bytes → `.ogg`.
  - `ICP\x??` is a custom Square Enix tile/pixel container; `decode_icp` ports Colmines92's ICP2PNG logic to emit a palettised PNG (PLTE + tRNS + IDAT). Falls back to `.dat` if Pillow is missing.
  - Message files (`bem`, `dbgmes`, `msg0..15`, `sysmes`, `system_message`) are renamed `.msd` (bytes unchanged).
  - Output is intended to match Colmines92's `FFDimensionsTool` `proper_obb/` byte-for-byte.

### `images/ic.py`
The `ic` image format used everywhere on mobile (and embedded in many Android files too):
```
"ic" magic (2B)
width  (BE u16)
height (BE u16)
nc     (u8 — palette colour count)
palette: nc × BGR triplets
flag   (u8) — 0xFF = sequential / no tile table
[tile_table]   1 or 2 bytes per cell (depending on image size)
tile_data      8×8 tiles, 4bpp if nc ≤ 16 else 8bpp
```
`parse_ic(data, offset=0)` returns an `ICImage` (which holds the source buffer + offsets so tile data isn't eagerly decoded). `render_ic(ic, palette_index=0)` returns a Pillow `Image`. `find_ic_offsets(blob)` scans for embedded `ic` magic across an arbitrary buffer.

### `sprites/container.py`
`parse_sprite_container(data)` walks the front-of-file offset table and yields `(entry_index, variant_index, ICImage_or_None, raw_subset)` for sprite-containers like `chpk` / `ene` / `bg` / `feimg` / `img_etc` / `cpk`. `iter_dat_entries` is a thin iterator wrapper. `parse_bip(data)` reads the bip-format icon container. `extract_hidden_gifs(data)` rescues stashed GIF89a payloads.

### `maps/`
- **`mobile.py`** — `parse_mobile_map_chunk(chunk)` decodes a single mobile map: tileset cpk entry IDs at byte 5/6, palette indices at 7/8, w×h at 9/10, BE u32 layer flags at 30..34, Shift-JIS map name, then tile data (3 bytes/tile if both layers active, 2 bytes/tile single-layer). `parse_mobile_mpk(...)`, `scan_mobile_mpk_chunks(...)`, `parse_mpkh_index(...)` walk multi-chunk packs.
- **`android.py`** — Port of `FieldClass::LoadMapInfo` from `libjniproxy.so`. Uses a streaming `_RomReader` (mirrors `SetRomRead + RomReadByte/UByte/ShortBig/IntBig`) because `mc_id` isn't at a fixed offset — it appears after a variable-length per-layer descriptor + tile/attribute payload. **73% strict (mc_id + variant) match against 168 manually annotated maps** as of 2026-05-13. Of the remaining 27%, ~15 cases are "engine says slot 0 = -1" (no tileset) and the rest are low-confidence override defaults the engine disagrees with.
- **`mc_overrides.py`** — Per-byte tile words in Android maps have a high byte that is only ever 0x00 or 0x01. The original `(hb<<1)|variant` interpretation made `mc_type` always 0, which forced every tile to render against `mc0_0.png` (wrong for most maps). Real encoding: **`high_byte == variant`** (0 or 1) and the *primary tileset* (mc_id) is implicit at the map level. Annotation lookup is two-tiered: explicit `by_map["g{group}p{pack}m{map_id}"]` overrides, then `by_group["0xXX_Y"]` defaults for the `(chunk[18], chunk[5])` bucket. See `seed_mc_overrides_from_engine.py` for the auto-fill flow.

### `boot/sections.py`
The `boot_data.dat` section TOC walker. Mobile is big-endian, Android re-encoded as little-endian; `detect_boot_endian(boot)` picks. `parse_boot_toc(boot, endian)` returns `[(start, end), …]`. `boot_section_be` / `boot_section_le` return the slice for a section starting at a given byte-offset pointer.

Section labels for both platforms:
- `MOBILE_BOOT_SECTION_LABELS` — derived from `class_20.java`.
- `ANDROID_BOOT_SECTION_LABELS` — discovered through 2026-05-13 decoding pass.
- `ANDROID_BOOT_LOADERS` — the loader function dispatch table.

`_parse_android_namedesc_section(boot, toc_off, body_size)` is the shared decoder for items, magic, passive abilities, command abilities, jobs, monsters — every one of those is the same `name + desc + fixed-size body` layout, only `toc_off` and `body_size` differ.

### `tilesets/parser.py`
`parse_mpk_index_mobile` / `parse_cpk_index_mobile` walk the variable-width pack indexes embedded in mobile `boot_data.dat`. `parse_android_tileset_lookup` reads the selector→mc_id map from the Android boot data. `flat_pack_index` flattens nested pack tables. `load_mobile_tileset` and `MobileTilesetResolver` provide a high-level "give me the right tile sheet for cpk entry X" API.

### `monsters/parser.py`
`parse_enemies_mobile(boot)` — BE section 12 primary, falls back to section 16. `parse_monsters_android(boot)` — LE section 9 via the namedesc decoder. `parse_enemy_names_android` reads the bestiary name list. `parse_bem(data)` reads `bem.dat` (mobile), a flat array of length-prefixed Shift-JIS strings used for ability/monster name lookups.

### `items/parser.py`
`parse_items_mobile` — BE section 4: name + desc + item_type + equip_type + price (BE u32) + atk/df/mag/… + element/status bitmasks. `parse_items_android` — LE section 5 via namedesc.

### `jobs/parser.py`
`parse_jobs_mobile` — BE section 20: name + desc + job_id + sprite_ow/sprite_btl + palette_ow/palette_btl + base stats (HP, MP, str, …). `parse_jobs_android` — LE section 6.

### `abilities/parser.py`
All three are Android-only and use the same namedesc decoder, differing only in TOC offset + body size:
- `parse_magic_android` — toc 0x08, body 54 (same layout as items).
- `parse_passive_abilities_android` — toc 0x0c, body 24.
- `parse_command_abilities_android` — toc 0x10, body 25.

### `characters/parser.py`
`parse_chara_set(data)` decodes `chara_set.dat`: per-character record with `chpk` sprite entry, palette indices, and an embedded equipment list. Pairs with `constants.CHARA_TABLE` for canonical romaji names.

### `text/parser.py`
`parse_message(data)` decodes mobile `message.dat` (multi-section length-prefixed Shift-JIS). `parse_msd(data)` decodes Android `.msd` (same shape but UTF-8); falls back to a flat string scan for files like `bem.msd`. `MESSAGE_SECTION_LABELS` names the 16+ sections (Common UI, Ch1-7 Light/Dark, Cutscenes, Challenge Dungeon, etc.).

### `music/parser.py`
`parse_snd(data)` parses the `snd.dat` container — three big-endian sound banks, each a `u16` count + `u32` offset table — into a list of `SndEntry` (bank, role, slot index, format, raw bytes), one per non-empty melody (every one an MFi `melo…` `.mld`). `parse_resbin(data)` and `parse_audio_names_resbin(data)` decode the Android `res.bin` audio-name table.

### `animation/parser.py`
`parse_field_anm(data)` decodes Android `field_anm.dat`. Verified against `MtxAnmCtrl::SetAnimeData` and `MtxAnmData::Draw` in `libjniproxy.so`. File layout: LE u32 `n_entries` (63), then `n_entries` × LE u32 absolute offsets. Each entry has six sub-section offsets (header, keyframes, parts, …) producing a flat frame table plus decoded sub-animations (static / walk / etc.) with playback metadata so callers don't have to re-walk the raw structures.

### `formats/form_bin.py`
`parse_form_bin(data)` decodes `form.bin` enemy formations: BE u16 offset table, then per-formation `inner_id`, enemy count, per-enemy `(x, y, z, enemy_type)` BE u16/u8 records, plus drops.

### `events/`
- **`opcodes.py`** — `EVENT_SCRIPT_OPCODES` covers 96 opcodes in the range 0x00..0xAB (with gaps), each entry containing `name`, `fmt`, and `desc` (platform info is embedded in the desc as `[Mobile]` / `[Android]` tags). Sources:
  - Android: `FieldClass::MoveScript` switch (line 125488 of `libjniproxy_c.c`); `GetBuffToWord/GetBuffToLong` = big-endian.
  - Mobile: `class_16.java::method_785` dispatcher (line 11586) over the same per-NPC length-prefixed blocks.
  - Both platforms store each command as a length-prefixed packet, so operand length is exactly `(block_len - 1)`. `fmt` is advisory (for pretty-printing), not the source of truth for length.
  - `_decode_event_operands(fmt, operands)` parses one packet; `disassemble_script_block` formats a single block.
- **`mobile.py`** — `map_event_script_region(parsed, raw)` returns the byte slice after tile data ends. `_mobile_true_event_offset` reconstructs the true event offset from the chunk header's `field_356` flags (not stored explicitly). `parse_mobile_event_region`, `disassemble_event_region` build per-NPC script tables.
- **`android.py`** — `parse_android_event_pack(data)` reads `[EDO][palette/scene-info][event_count][event_records…]`. Each event record has a 0x3f-byte fixed header (id u16-BE at +0, type at +0x07, boot condition at +0x08, chara image id u16-BE at +0x2b, variant at +0x2d), then `script_count` u16-BE, then `script_count` length-prefixed scripts. `disassemble_android_event_pack` formats. `scan_android_event_packs` bulk-scans every `.dat` for event packs. Engine references: `FieldClass::LoadCommonEvent` (line 96813), `FieldClass::LoadEventData` (line 106753).
- **`strings.py`** — `extract_sjis_strings(data, min_len)` for ad-hoc string mining.

### `cross_ref/tab.py`
Cross-reference browser. Subject = enemies or characters, filtered live, with sprite render, stat dump, and "appears in formations" list pulled from `form.bin`.

### `files_io/`
- **`files_tab.py`** — the `Files` tab UI (load `.sp`/`.obb`/`.apk`/`.jar`/`.jam`, status per slot).
- **`extract_tab.py`** — the `Extract` tab UI + `EXTRACT_OPTIONS` table that drives the checkboxes (name, label, default-on flag, mobile-applicable, android-applicable, output-subfolder).

### `gui_core/`
- **`app.py`** — `FFDApp(tk.Tk)`. Builds the menu (File → Load .sp / .obb / .apk / .jar / .jam / folder; Help → About), the notebook in `TAB_ORDER`, and the status bar. Per-tab construction failures get a loud `[FFDApp] FAILED to build XxxTab` banner and a red placeholder tab so regressions are obvious.
- **`base.py`** — `TabBase(ttk.Frame)`. Accepts either an `FFData` or an app instance (for tabs that need cross-notebook refreshes, e.g. `MapAnnotationTab`).
- **`helpers.py`** — `pil_to_photo`, `_scaled`, `open_in_default_app`, `format_element_bits`, `format_status_bits`, `hex_dump`, `_hex_dump`.
- **`image_panel.py`** — shared zoomable image panel.
- **`thumb_list.py`** — thumbnail-grid widget used by several tabs.

---

## Standalone tools

### `tools/boot_data_analyze.py`
Command-line decoder for `boot_data.dat`. Prints the section TOC with both endian interpretations side-by-side and Mobile/Android section identity labels. Mobile section identities are derived from `class_20.java` in the decompiled mobile sources; Android section identities come from the 2026-05-13 decoding pass and are listed in `MEMORY.md` (`ffd_boot_data_format.md`). Useful when investigating a new `.sp` or a different `.obb` version.

### `tools/seed_mc_overrides_from_engine.py`
One-shot helper that runs `parse_android_map_engine()` over every parsable Android map (1,679 maps as of last count) and pre-seeds `mc_overrides.json` with the engine's `(mc_id_slot0, variant_slot0)` answer, marking each as `auto_from="engine_parser"` + `auto_confidence=1.0`.

Priority rules:

1. Existing entry with `user_confirmed=True` → preserved untouched (manual annotation is ground truth).
2. Engine returns slot0 `-1` (no tileset) → skip; renderer falls back to `by_group` / default.
3. Existing entry matches engine answer → bump metadata to engine-derived but leave values.
4. Otherwise → overwrite low-confidence guess with engine answer.

Idempotent. Saves a timestamped backup of the original `mc_overrides.json` before any write.

```bash
python3 tools/seed_mc_overrides_from_engine.py            # dry-run preview
python3 tools/seed_mc_overrides_from_engine.py --apply    # actually write
python3 tools/seed_mc_overrides_from_engine.py --apply --proper-obb PATH
```

### `tools/regenerate_cpk_to_mc.py`

Palette-aware SAD matcher that regenerates `cpk_to_mc.json` from scratch. For every (chapter, cpk_entry, palette_idx) combination it computes alpha+luminance sum-of-absolute-differences against every Android (mc_id, variant) sheet, masked to pixels where Mobile alpha > 0. Output records the BEST overall match at the top level (back-compat with v2 callers) plus a `by_palette` sub-dict giving the best (mc_id, variant) per Mobile palette index.

Loads `mc*.png` from `Android/proper_obb/` by default (~0.6s) instead of re-decrypting the OBB archive on every run (~41s). Pass `--obb` to fall back to OBB loading when the extracted folder isn't available.

Supports `--resume` (skip chapters already in the output file) and `--only-chapters X,Y` for chunked runs that fit inside short CI budgets; per-chapter incremental saves mean a partial run survives a timeout.

Requires NumPy in addition to Pillow.

```bash
python3 tools/regenerate_cpk_to_mc.py \
    --sp-dir ../Mobile/Scratchpads \
    --mc-dir ../Android/proper_obb \
    --out ../cpk_to_mc.json
# chunked run:
python3 tools/regenerate_cpk_to_mc.py --resume --only-chapters Chapter1,Chapter3 ...
```

---

## FFSmith engine bundles (`--bake-ffsmith`)

The companion clean-room C++ engine **FFSmith** (`../Engine`) consumes assets
baked by the toolkit rather than re-parsing raw formats. Bake a bundle from
the Android data:

```bash
# from the pre-extracted proper_obb/ folder (fast):
python ffd_toolkit.py --bake-ffsmith out_bundle --proper ../Android/proper_obb --limit 30
# or straight from the encrypted OBB:
python ffd_toolkit.py --bake-ffsmith out_bundle --obb ../Android/main.obb --only g0_p0_m501
```

Output: `manifest.json`, `maps/*.ffmap` (flat little-endian maps, **FFM4** —
header carries the map's default spawn, events carry their id, trigger rect and
31-byte `CheckEventAppear` condition block), `tex/mc*_*.tex` (raw-RGBA `FTEX`
tilesheets), `data/common_events.ffmap` (the shared CallEvent pool, map 10000),
and `data/start.bin` (`FSTR` — the New Game start table from boot_data scenario
section 1; record 0 = the retail opening map).
The engine's map renderer mirrors `ExtractTab._render_android_map` and is
verified byte-identical to the toolkit render. Format spec:
`../Engine/docs/ASSET_PIPELINE.md`.

---

## Key file format findings

A compressed cheat sheet of the formats this toolkit parses. The full per-byte detail lives in each module's docstring; this is the bird's-eye view.

| Format | Where | Endian | Used by | Notes |
|---|---|---|---|---|
| `.sp` scratchpad | Mobile | BE | `containers/sp.py` | 64-byte header, directory at 0x41A4, optional zip wrapper |
| `.obb` (FFD) | Android | — | `containers/obb.py` | XOR-obfuscated custom container; INP/mtxs/ICP magics for embedded payloads |
| `ic` image | Both | BE dims | `images/ic.py` | "ic" magic, BGR palette, optional tile table, 8×8 4/8bpp tiles |
| sprite container | Both | BE | `sprites/container.py` | Front-of-file offset table → ic entries with palette variants |
| Mobile map chunk | Mobile | BE | `maps/mobile.py` | Tileset IDs at byte 5/6, layer flags at 30..34, then tile data |
| Android map chunk | Android | BE u32 size + streaming | `maps/android.py` | Variable-length per-layer descriptor; mc_id not at fixed offset |
| `boot_data.dat` TOC | Mobile / Android | BE / LE | `boot/sections.py` | Packed u32 array; last entry = filesize terminator |
| Android namedesc | Android | LE | `boot/sections.py` | Shared layout: name + desc + fixed-size body. Items §5, magic §2, jobs §6, monsters §9 |
| `field_anm.dat` | Android | LE | `animation/parser.py` | 63 entries; tex_id=0 because engine binds sheet at runtime |
| `chpk.dat` | Mobile | BE | `sprites/container.py` | Character atlases; engine hardcodes cell layout (typically 16×16) |
| `message.dat` | Mobile | BE | `text/parser.py` | Multi-section length-prefixed Shift-JIS |
| `.msd` | Android | LE | `text/parser.py` | Same shape as message.dat but UTF-8 |
| `snd.dat` | Mobile + Android | BE | `music/parser.py` | 3-bank container of raw MFi (`melo…`) `.mld` melodies |
| `form.bin` | Mobile | BE | `formats/form_bin.py` | u16 offset table → per-formation enemy+drop records |
| event scripts | Both | BE operands | `events/opcodes.py` | Per-command length-prefixed packets; 96 opcodes catalogued (range 0x00..0xAB with gaps) |
| `cpk_to_mc.json` | Both (sidecar) | — | `maps/mc_overrides.py`, `sprites/mobile_tile_to_android.py` | SAD-matcher output: `{chapter: {cpk_entry: {mc_id, variant, best_sad, by_palette: {N: {…}}}}}`. Regenerate via `tools/regenerate_cpk_to_mc.py` |
| `cpk_to_mc_overrides.json` | Both (sidecar) | — | `maps/mc_overrides.py` | Manual user overrides. `{entries: {ChapterDense: {cpk: {mc_id, variant, by_palette?: {N: {mc_id, variant}}}}}}`. Takes precedence over `cpk_to_mc.json`. Written by the Sprite Converter's *Save override* button |

---

## The `mc_overrides` annotation workflow

Android map rendering depends on knowing each map's primary tileset (`mc_id`). The engine doesn't store this at a fixed offset — it's computed during a streaming chunk walk. Until the chunk walker hits 100% on every map, we keep a sidecar JSON of manual + engine-derived annotations.

The lookup pipeline when rendering an Android map:

1. **Engine parser** (`maps/android.py::parse_android_map_engine`) attempts to derive `(mc_id, variant)` from the chunk bytes.
2. If `mc_overrides.json` has an explicit `by_map["g{group}p{pack}m{map_id}"]` entry with `user_confirmed=True`, it wins regardless.
3. Otherwise the engine result is used (and recorded in `by_map` with `auto_confidence=1.0`).
4. If the engine returns slot 0 = -1 (no tileset), fall back to the `by_group["0x{chunk18}_{chunk5}"]` bucket default.
5. Last resort: `mc0_0`.

To bulk-populate annotations from the engine parser, run `tools/seed_mc_overrides_from_engine.py --apply`. To hand-correct stragglers, use the **Map Annotations** tab.

---

## Notes & known limitations

- **The Android map parser is at 73% strict match.** The remaining 27% are mostly "engine says no tileset" (renderer correctly falls back) plus a small tail of disagreements that need eyeball verification before promoting either interpretation.
- **ICP is still partially undecoded.** The current `decode_icp` ports Colmines92's logic and produces the right output for most files, but there's a long tail of variant prefixes whose semantics aren't pinned down. See `MEMORY.md` (`ffd_obb_container_formats.md`).
- **Only 6 of the 14 mobile chapters have been scratchpad-dumped** so far (Ch1, Ch3, Ch4, Ch5, GladiatorHall, Online). The rest are considered lost media until a dump appears.
- **No automated tests yet.** Eyeball-verify is the current QA process; the renderer outputs are diffed visually against known-good images. If you're considering adding tests, parser-level fixtures of small known chunks would be the highest-value place to start.

---

## Related tools and credits

### Tools used in the project

- **[Colmines92's `FFDimensionsTool`](https://github.com/Colmines92)** — Windows GUI extractor for the Android `.obb`. Output of `FFDimensionsTool` in "proper" mode is the byte-for-byte reference target for `ffd.containers.obb`. The `proper_obb/` folder in the project tree was produced by this tool.
- **YYCHR** — a free tile/graphics editor (originally built for NES ROM hacking). YYCHR was the stepping stone used to manually figure out the mobile sprite layout before it could be parsed programmatically: drop in a raw `.dat` blob, scrub through bit-depths and tile widths, and the structure becomes visible by eye. PowerPanda's sprite research (see Source material below) was carried out by hand in YYCHR before being formalised into the parsers in `ffd/sprites/` and `ffd/images/ic.py`.

### Source material

- **Mobile `.sp` scratchpad extraction & Java research** — **GuyPerfect** was the first to successfully extract the original `.dat` files from the Mobile version's `.sp` scratchpads, cracking the DoCoMo FOMA container format that had previously kept those assets sealed. From there, GuyPerfect did the extensive research on the decompiled Java classes (`class_16.java::method_785`, `class_20.java::method_940`, etc., all in `Mobile/Decompiled_Java_Classes/`) that identified what each `.dat` actually contained — boot data sections, item/job/monster records, message tables, map chunks, the whole layout. Every mobile-side parser in this toolkit builds on that foundation.
- **Mobile spritesheet structure & rendering** — **PowerPanda** did the original graphical research on how mobile spritesheets are laid out in `chpk.dat` / `cpk*.dat` / `mpk*.dat` and how the engine renders them. This was painstaking manual work done in **YYCHR** — scrubbing through bit-depths, tile sizes, and palette offsets in the raw `.dat` blobs by eye until the structure resolved. The sprite-container parser (`ffd/sprites/container.py`) and the `ic` image format decoder + renderer (`ffd/images/ic.py`) trace directly to that work.
- Together, GuyPerfect's `.sp` extraction breakthrough plus the Java analysis, combined with PowerPanda's sprite-layout research, are what **made asset extraction from the Mobile version a reality**. Before this work, the mobile build was effectively a black box; afterwards, every `.dat` file inside it can be parsed, sliced, and rendered.
- **`libjniproxy.so` decompilation** — the Android engine port. Most map / animation / event findings cite line numbers in `Decomp/Functions/libjniproxy_c.c`.

### Acknowledgements

The toolkit itself was developed by Jack (`sourmelee`) with Claude as a research collaborator. Engine references in docstrings cite the decompiled sources directly so future debuggers can chase any claim back to its primary source.
