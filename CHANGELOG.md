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

## [0.7.24] - 2026-06-10

### Added

- **Scenario/start table decoded** (`ffd/boot/scenario.py`). `boot_data.dat`
  section 1 = `GameClass::LoadScenarioData`: 16 chapter records (Shift-JIS
  titles 序章/暁の章…) each carrying the chapter's start map id + spawn x/y +
  `BeforeStory` id. Retail New Game = record 0 → map 0 @(0,0); `e3_param.dat`
  turned out to be the E3 trade-show demo start (`g_IsE3Mode`), not retail.
  The baker now writes `data/start.bin` (`FSTR`) so FFSmith's New Game lands
  on the real opening map.
- **FFM3 map format: per-event appear conditions.** `--bake-ffsmith` now
  bakes the 31-byte `CheckEventAppear` block (event header bytes 9..0x27):
  6 slots — flag, flag, variable, item, member, timer. This is how the engine
  decides which NPCs/doors exist for the current story state (verified on
  m501's two stacked doors: global flag5 bit 10 clear → town map 500, set →
  dark-world map 1700). Loader stays backward-compatible with FFM2.

### Changed

- **Event-script disassembler: real branch semantics** (`ffd/events/opcodes.py`),
  RE'd from `FieldClass::MoveScript`/`ScriptIf`/`MoveEventScript`:
  `0x3d ScriptIf` is an *if-NOT-goto* — operands are two GetReference refs
  (flag/var/immediate/…), a comparison op and a target *script-block* index,
  jumping when the condition fails; `0x3f`/`0x40` jump to block indices;
  `0x41 MapChange` takes five BE *words* (map,x,y,dir,sub) with a per-operand
  variable-indirection mask (all 15 real uses are fully indirect);
  `0x3c MultiChoiceDialog` lists (value → target-block) choice pairs;
  `0x03/0x04` descriptions now name the real calc-op/flag-bank semantics.
  Disassembly annotates all of these inline (`ifnot flag(0,5,10) == 1 -> block 4`).

## [0.7.23] - 2026-06-09

### Added

- **Audio baking for FFSmith (M8).** `--bake-ffsmith` now bundles the Android
  game's music + sound effects so the engine isn't silent. `_bake_audio`
  transcodes the OGG banks (bank 0 = BGM, bank 2 = SFX) to **IMA-ADPCM WAV**
  (~2x the OGG, vs ~9x for raw PCM) under `<bundle>/audio/snd{0,2}_{id}.wav` via
  ffmpeg, and writes `data/audio.bin` (`FAUD`: the per-BGM loop-flag table from
  `bgm_loop.dat`). IMA-ADPCM WAV is decoded natively by SDL2's `SDL_LoadWAV`, so
  the engine needs no Ogg decoder and no new dependency. **Requires ffmpeg on
  PATH at bake time**; without it audio is skipped with a warning (the rest of
  the bake still succeeds).
- **Per-map BGM in `.ffmap`.** `parse_android_map_engine` now also returns
  `field_bgm` / `battle_bgm` / `battle_bg` / `encount_ratio` — the 7 u8 map-header
  fields decoded from `FieldClass::LoadMapInfo` (the baker already read past
  them). `field_bgm` + `battle_bgm` are packed into the `.ffmap` reserved u32
  (with the overhead threshold) so the engine plays the right track per map.

## [0.7.22] - 2026-06-09

### Added

- **Animation tab: object-override authoring panel** (Android source). Marks a field_anm sprite as
  an OBJECT so FFSmith draws its real frame rect at a tile-relative anchor instead of the 48x48
  character grid, with a live **tile-aligned preview** (shows exactly where FFSmith lands the frame:
  `dst = tile/2+px, tile+py`). Controls: `isObject` toggle, frame `x/y/w/h`, anchor `px/py`,
  *Seed from field_anm*, *Use selected frame*, *Save*, *Remove*, and a file picker. Writes the
  `sprite_grid.json` the FFSmith baker already merges (`_bake_sprite_geo`) — the manual-annotation
  path for the chest/door/crystal sprites that 0.7.21 stopped auto-classifying.
- **`ffd/animation/sprite_grid.py`** — GUI-free helpers shared by the panel and (mirrored in) the
  baker: `seed_geo_from_fa_entry`, `object_dest_rect`, `default_override_path`,
  `load/save/remove_overrides`, `render_tile_preview`. Unit-tested headlessly (seed parity with the
  baker, FFSmith placement math, JSON round-trip, preview compose).

## [0.7.21] - 2026-06-08

### Fixed

- **spritegeo.bin no longer auto-classifies sprites as objects.** The 0.7.20 heuristics (frame
  size, then walk-cycle presence) misclassified **static NPCs** (villagers/guards who don't walk)
  as objects, so FFSmith drew them with a partial frame (squashed). Now every sprite defaults to
  `isObject=0` (the known-good 48x48 character grid); object marking is purely the manual
  `sprite_grid.json` override. The field_anm frame/anchor is still seeded so an override that sets
  `isObject:1` reuses the decoded geometry.

### Added

- **Bake per-sprite field-anim geometry (`data/spritegeo.bin`).** From `field_anm.dat`: each sprite's
  default frame rect {x,y,w,h} + part offset (anchor) + an isObject flag. Lets FFSmith draw object
  sprites (doors/crystals/chests) with their REAL frame/anchor instead of the hardcoded 48x48
  character grid (each field_anm entry has its own size: chars 48x48/32x48, objects 16x16/20x24/32x16).
  An optional `sprite_grid.json` override (to be authored in the Animation tab) is merged over the seed.

### Added

- **Bake each character's field-sprite (CHPK) id into `data/chars.bin`.** From `chara_set` f186
  (the CHPK entry, e.g. Sol = 13). Lets FFSmith pick the lead character's real field sprite for
  New Game instead of auto-detecting the first map event (which could be a door).

### Added

- **Bake the New Game intro strings (`data/intro.bin`).** The prologue text crawl ("In an age
  long past... the Avalonian Empire...") and the "Prologue" chapter label, extracted by content
  from `msg0.msd` (the per-message slot index drifts, so we match on text rather than offset).
  Feeds FFSmith's New Game intro cinematics.

### Added

- **Bake monster EXP/gil rewards + a level table for FFSmith's battle loop.** `monsters.bin`
  records gain `exp` + `gil` (u32 each), decoded as BE u32 at monster body[6]/body[10] (verified:
  Goblin 10/3, Hornet 9/2 -- the prior "13367" was a wrong offset; AP at body[14] left for later).
  New `data/levels.bin` (`FLVL`): the EXP-threshold curve (`LevelUp` reads BE u32 @ section-8
  `[0x10 + 9*i]` -> 45/97/173/261...) plus per-level HP/MP growth (section-8 `[L*9+2]`/`[+4]`),
  so the engine can map EXP->level and recompute max HP/MP on level-up.

### Added

- **Bake the overhead-layer threshold (`FieldClass+0xdc2c`) into each `.ffmap`.**
  `parse_android_map_engine` now reads the threshold byte (10 bytes after slot1's
  mc/variant: has_far + far params + has_BG + BG params + BG shorts, none of which
  consume the stream), stored in the previously-reserved FFM2 u32. Layers with index
  > threshold are overhead (drawn above characters). FFSmith uses it for exact
  ground/overhead split instead of assuming threshold 0. Distribution across 1679
  maps: 1456 at 0, 220 at 1, 3 at 2.

### Added

- **Bake chip floor-attribute table (`data/chipfloor.bin`).** `ffd/maps/capk.py::parse_capk_floor`
  decodes the 6-bit floor-attribute enum `(A >> 18) & 0x3f` from each chip record; bit `0x10`
  = **damage floor** (`FieldClass::GetFloorAttributeOfChara`/`IsDamagedFloor`). Baked as `FCFL`
  (mc -> [(inner, floor_attr)]). Verified: the damage value 0x12 appears on 47 chips, all in
  tileset mc63. Lets FFSmith hurt the (persistent) party on lava/poison floors.

### Added

- **Bake chip-animation table (`data/chipanim.bin`).** New `ffd/maps/capk.py::parse_capk_anim`
  decodes per-tileset animated chips from `capk.dat` (in the 7-byte record's u32-BE word A:
  bit 8 = animated, bits 9-10 = type [0 loop / 1 ping-pong], bits 11-14 = frame count,
  bits 15-17 = speed). The baker writes `FCAN` (mc -> animated inner chips); FFSmith cycles
  `base..base+frames-1` to animate water/torches. Verified: 1136 animated chips (all 3-frame),
  22,307 animated cells on the overworld.

### Added

- **Bake item category (`item_type`) into `data/items.bin`.** Each item record now carries a
  trailing `u8` item_type (body offset 0): 0 = consumable/key item, 1-15 = weapon classes
  (knife/sword/katana/spear/axe/claw/staff/rod/bow/harp/whip/throwing/shuriken), 16 = shield,
  17-19 = head, 20-22 = body, 23 = hands/accessory. This lets FFSmith match equipment to the
  correct slot by category (shield → off-hand, hat → head, def-less accessories now equippable)
  instead of the prior atk/def heuristic. Note: `equip_type` (body offset 1) is always 0 and is
  NOT the slot discriminator. `data/items.bin` format is now `... atk:u16 def:u16 item_type:u8`.

### Fixed

- **Baker no longer aborts on a truncated source tileset.** `_load_tex_rgba` now tolerates a
  corrupt/incomplete `mc*.png` (loads the partial image and warns, e.g. `mc34_0.png`,
  `mc60_0.png` in the current extraction) instead of raising `OSError` and killing the whole
  `--bake-ffsmith` run.

## [0.7.12] - 2026-06-03

### Added

- **Bake weapon ATK / armor DEF (`data/items.bin`).** Parsed from the item descriptions
  ("ATK 7", "DEF 2") so FFSmith's damage formula has real weapon power (Knife 7, Orichalcum
  23, Graham's Sword 47, Masamune 100) and armor defense. Feeds the exact `CalcPhysicAttackDmg`
  core (W=weapon, A=STR, L=level, D=defense).

## [0.7.11] - 2026-06-03

### Added

- **Bake a castable spell table for FFSmith (`data/spells.bin`).** 11 real spells from the
  `system_message` Magic table — heals (Cure / Cura / Curaja) and damage (Fire / Blizzard /
  Thunder / Fira / Holy / Bio) — with effect type read from the descriptions. MP cost + power
  are tier approximations (boot has no clean magic-body section). Powers FFSmith's battle
  Magic command (INT-scaled damage / MND-scaled heals, gated by MP).

## [0.7.10] - 2026-06-03

### Added

- **Decoded HP/MP growth table + baked real maxHP/maxMP.** Located the level-growth table
  (boot_data §8 -> engine `GameClass+0x213f8`; 9-byte/level entries, HPbase u16-BE @+2,
  MPbase @+4) by tracing `GameClass::SetJobStatus` (maxHP = base[level] x jobHP%/100 + attr).
  `_bake_menu_data` computes per-character `maxHP/maxMP = base[level]` (job% defaulted to 100 -
  the level curve dominates) into `data/chars.bin`. E.g. Sol L3 -> HP 70 / MP 23; Aigis L10 ->
  HP 199 / MP 51.

## [0.7.9] - 2026-06-03

### Added

- **Decoded character base stats (`chara_set.dat`).** Reverse-engineered the per-character
  record layout from the engine's `GameClass::ReadStartData` + `MEMBER_STATUS` (job @+0x34,
  exp @+0x38 -> level via a 98-entry table, attributes @+0x40..): each record stores **JOB,
  LEVEL, and 7 attribute bytes** after the name. The 5 named attributes (labels from
  `system_message` §3) are **STR, SPD, VIT, INT, MND**; archetype correlation confirms the
  mapping (fighters Sol/Glaive STR 20/30 & SPD 0-5; agile Sarah/Alba STR ~0-2 & SPD 14-15).
  `parse_chara_set_*` now exposes `job/level/str/spd/vit/int/mnd` and `_bake_menu_data` writes
  them to `data/chars.bin` for FFSmith's Status page + STR-based battle damage. (HP/MP remain
  engine-computed via `SetJobStatus` — not yet replicated.)

## [0.7.8] - 2026-06-03

### Added

- **Bake battle data for FFSmith.** `_bake_menu_data` now also emits `data/monsters.bin`
  (monster id -> English name + HP / attack / defense / level, from `boot_data` §9
  `parse_monsters_android` + `decode_monster_body`; 571 monsters), and `_bake_ui` bakes
  `ui/btlbg.tex` (battle background from `btlbg0_0.png`). Powers FFSmith's M6 battle.

## [0.7.7] - 2026-06-03

### Added

- **Bake menu data for FFSmith (`_bake_menu_data`).** Emits `data/items.bin` (item id
  -> English name + description, from `system_message.msd` Item section + `boot_data` §5
  `parse_items_android`) and `data/chars.bin` (character id -> English name + 6 equipment
  item-ids, from `chara_set.dat` `parse_chara_set_android`). Item descriptions already
  embed stats ("ATK 7", "Restores 100 HP"). Powers the engine's M5 Item / Equip / Status
  menu pages. Manifest gains `menu_data` counts.

## [0.7.6] - 2026-06-03

### Added

- **Bake UI images for FFSmith (`_bake_ui`).** The baker emits `ui/title.tex` (from
  `TitleLogo.png`) so the engine can render a real title screen for the M4 state
  machine. Manifest gains a `ui` list.

## [0.7.5] - 2026-06-03

### Fixed

- **Correct field-dialogue source — per-area `msg{N}.msd` banks.** 0.7.4 baked text
  from `system_message.msd` section 4, a coincidentally-coherent but **wrong** source.
  Field dialogue is per-area: the engine loads `msg{N}.msd` (`GameClass::ReadStoryMessageData`
  -> `SetMessageList` -> `FieldClass+0x380`), N = the area bank. Maps map 1:1 to the 16
  banks by **group**, so the baker now emits `text/msg{group}.bin` per group and the engine
  picks the bank by map group. msg-file format corrected: `u16-BE count`, then messages x
  6 languages x 2 slots (dialogue text + speaker name), each `u16-BE len + UTF-8 + NUL`;
  **English text = index `msg*12 + 2`**. Verified: m501 NPC msg 170 = "Hey, ..." (was the
  wrong "...Barbara!"); msg 847 (out of §4's range) now resolves. Bank = group is a static
  stand-in for the engine's story-state bank (`GameClass+0x19fe0`); light/dark story-variant
  banks may need the M4 state machine.

## [0.7.4] - 2026-06-03

### Added

- **Field dialogue text + font baking for FFSmith (`android_export/ffsmith_bake.py`).**
  The baker now emits `text/messages.bin` (msg_id -> English string) and a bitmap-font
  atlas (`text/font.tex` + `text/font.meta`). Field scenario text is decoded from
  `system_message.msd` — 6-language-interleaved records, **English = slot 1** — matching
  the engine's `GetMessageData`, which indexes the active language's array directly by
  msg_id. `<chaN>` party-name placeholders normalize to "Hero". Font atlas is
  DejaVuSansMono (ASCII 32-126, 8x14 cells). Section 4 is the scenario bank for the
  early maps (m500/m501); per-chapter bank selection is a follow-up.

## [0.7.3] - 2026-06-03

### Added

- **Event warp extraction (`events/android.py` `event_warp()`).** Decodes a
  field event's door / map-edge warp destination from its scripts: `0x6B`
  BulkSetVars with `sub==2` sets the script-variable bank (var0 = dest map,
  var2 = x, var3 = y, var4 = facing) and `0x66` SetEntityAction with action
  byte `0x04` executes the move-map (action `0x03` = NPC spawn); `0x41`
  MapChange is the direct form used by connection maps. Validated across the
  Android data — 4507/4514 such records resolve to an in-bounds destination
  map. The multi-event disassembler now annotates each warp event with
  `>> WARP -> map M @(x,y) dir d`. (Shared decode with the FFSmith engine.)

### Changed

- **Opcode descriptions** for `0x66` SetEntityAction (action-byte semantics) and
  `0x6b` BulkSetVars (sub-bank + warp idiom) sharpened to match the decode.

## [0.7.2] - 2026-06-02

### Fixed

- **Animation tab — correct field walk cycles.** The walk preview was driven
  by `field_anm`'s decoded `sub_anims`, which do NOT map to the cardinal walk
  directions (they mix part-composition frames). New `field_walk_entries()`
  (`animation/parser.py`) defines the canonical field-character walk — 48×48
  cells, origin (1,1), pitch 50; **rows = facing** (Down/Up/Left), **cols =
  frame** (idle/walkA/walkB), **Right = Left flipped** — confirmed against
  fldchr1. `AnimationTab` now lists Walk Down/Up/Left/Right (+ idles) first and
  honors per-frame `flip_h`. Matches the FFSmith engine's sprite renderer.

## [0.7.1] - 2026-06-02

### Added

- **Field-character sprite baking.** `--bake-ffsmith` now bakes the
  `fldchr{img}_{var}.png` field-character sheets referenced by a map's NPC
  events into `sprites/*.tex` (raw RGBA) -- so FFSmith draws real NPC/player
  sprites instead of markers. `chara_img` maps directly to the `fldchr` id.
  First cut renders the standing (top-left) frame feet-aligned; per-facing +
  walk animation from `field_anm` is the next step.

## [0.7.0] - 2026-06-01

### Added

- **Event data baking (NPCs / triggers / scripts) -- map format FFM2.** The
  `--bake-ffsmith` baker now parses each map chunk's event pack
  (`parse_android_event_pack`) and bakes structured events into the map: per
  event the tile position (header[2]/[3]), type (header[7]), boot condition
  (header[8]), chara sprite id/variant, and the length-split bytecode script
  blocks. This drives FFSmith's event-script VM (talk-to-NPC + dialogue now;
  step-on triggers + warps next). Verified on `g0_p0_m501`: 7 events; the NPC
  at (4,6) yields dialogue messages 170-175.

## [0.6.0] - 2026-06-01

### Added

- **Chip-attribute collision (`capk.dat`) + passability baking.** New
  `ffd/maps/capk.py` (`parse_capk`) decodes `capk.dat`, the per-tileset chip
  attribute file: little-endian u32 TOC where `section(mc_id) = TOC[mc_id+1]`;
  each section is a u16-BE count then 7-byte chip records (u32-BE `A` + u24-BE
  `B`); `A & 0x0F` is the 4-direction passability mask (0 = solid). Decoded
  from `FieldClass::LoadChipAttribute` + `CheckMovePass` in libjniproxy.so.
  The `--bake-ffsmith` baker now emits map format **FFM1** with a per-cell
  pass-nibble grid, giving the FFSmith engine real wall/object collision.
  Verified on `g0_p0_m501`: solid cells overlay exactly on walls, furniture
  and room dividers; floors and rugs stay walkable.

## [0.5.0] - 2026-06-01

### Added

- **FFSmith engine asset baker (`--bake-ffsmith`)**: new
  `ffd/android_export/ffsmith_bake.py` emits an asset bundle consumed directly
  by the companion clean-room C++ engine **FFSmith** (`../Engine`). Output:
  `manifest.json`, `maps/g{G}_p{P}_m{M}.ffmap` (flat little-endian map: dims,
  layer tile-words, engine-resolved mc slot0/slot1, raw event region), and
  `tex/mc{N}_{V}.tex` (raw-RGBA `FTEX` tilesheets). Maps come from
  `parse_android_map_chunk` + `parse_android_map_engine`; tilesheets are
  decoded from the OBB's `mc*.png`. CLI:
  `--bake-ffsmith <out_dir> [--obb PATH | --proper DIR] [--limit N] [--only KEY]`.
- The Toolkit is now the single source of truth for the engine's content
  pipeline: FFSmith's renderer mirrors `ExtractTab._render_android_map`
  (slot dispatch on the tile-word high byte, zero-skip on `0x0000`,
  `TS = 32 if sheet width >= 512 else 16`, PIL `div255` alpha rounding).
  Verified **byte-identical** (100.0% exact pixels, max channel diff 0)
  against the toolkit render on `g0_p0_m101` (1 layer) and `g0_p0_m501`
  (2 layers, dual slot).

## [0.4.1] - 2026-06-01

### Changed

- **Extract tab -- *Audio: MFi/MLD from snd.dat* now covers Android too**:
  the `audio_snd` extractor previously walked only the Mobile chapter
  scratchpads (`find_in_sp_any_chapter`). It now also extracts the Android
  `.obb`'s `snd.dat` -- the identical MFi container -- into an
  `audio/android/` subfolder, using the same bank-aware `role_index.ext`
  naming. The option label becomes "Audio: MFi/MLD from snd.dat
  (Mobile + Android)" and its output subfolder moves from
  `audio/mobile/<chapter>` to `audio/<chapter>` (+ `audio/android`).
  Verified headless: 576 Mobile (5 chapters) + 111 Android melodies, every
  `.mld` byte-exact.

## [0.4.0] - 2026-06-01

### Fixed

- **Mobile/Android audio extraction (`music/parser.py` -- `parse_snd`)**:
  the parser assumed `snd.dat` was a stream of *gzip-wrapped* melodies and
  scanned for the `1f 8b` magic, so on the real (uncompressed) files it
  returned **zero** tracks -- audio extraction silently produced nothing.
  `parse_snd` now decodes the actual container: three big-endian sound
  banks, each a `u16` count followed by a `u32` offset table, yielding one
  entry per non-empty melody. Verified against all five Mobile chapter
  `snd.dat` files (111-118 melodies each) and the Android `proper_obb`
  copy; every blob is MFi (`melo...`) and every raw `.mld` slice
  round-trips byte-exact.

### Added

- **`SndEntry` / `BANK_ROLES` (`music/parser.py`)**: `parse_snd` now returns
  a list of `SndEntry(bank, bank_role, index, fmt, ext, data)` namedtuples.
  Each entry keeps its *original* slot index within the bank (empty slots
  counted) so it matches the engine's sound id, and detects the blob format
  from its magic (MFi `.mld` / SMF `.mid` / SMAF `.mmf`). Re-exported from
  `ffd.music` and `ffd_toolkit`.
- **Music tab -- full melody extraction + batch export**: lists every
  `snd.dat` melody across all loaded Mobile chapters and (for Android) the
  melodies inside the `.obb`'s `snd.dat` *plus* any loose streamed audio
  (`ogg`/`mp3`/...). Adds an **Export all...** button (dumps every listed
  track with a `chapter__role_index.mld` name) alongside per-track
  **Save**/**Open**.
- **Deferred `.mid` hook**: an **Export .mid** button is present but disabled
  -- these melodies are MFi **v5**, whose per-`trac` event stream is not yet
  decoded, so no fake MIDI is emitted. The container/header/`trac` layout is
  documented in `music/parser.py` for the future converter.

### Changed

- **Extract tab audio dump (`files_io/extract_tab.py`)**: the *audio
  (snd.dat)* extractor now names files `role_index.ext` (e.g. `bgm_024.mld`,
  `sfx_012.mld`) per bank instead of a single running `track_NNN.mld`,
  matching the new bank-aware parser.

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
- `.obb` XOR-obfuscated FFD container (Android build),