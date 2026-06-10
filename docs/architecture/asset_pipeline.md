# Asset Pipeline — Authoritative Baked-Bundle Specification

*Audit 2026-06-10, toolkit 0.7.25 / bundle map format **FFM4**. This supersedes the "Bundle layout (v0 draft)" in `Engine/docs/ASSET_PIPELINE.md` (kept there for its principles/symbiosis rules). Writer: `ffd/android_export/ffsmith_bake.py`. Reader: `Engine/src/data/bundle.cpp`. Any change must touch both and bump the relevant magic.*

All baked integers are **little-endian** unless noted. `pstr16` = u16 length + bytes (UTF-8).

## Bundle layout

```
out_dir/
  manifest.json                 version, source, maps/tilesheets/sprites TOC, counts
  maps/g{G}_p{P}_m{M}.ffmap     FFM4 baked maps
  data/common_events.ffmap      map 10000 (CallEvent pool, 26 routines) as a 1×1 FFM4 shell
  tex/mc{N}_{V}.tex             FTEX tilesheets (only those referenced by baked maps)
  sprites/fldchr{IMG}_{VAR}.tex FTEX character/object sheets (only those referenced by events)
  text/msg{N}.bin               FMSG dialogue banks (one per map group seen)
  text/font.tex + font.meta     FTEX atlas + FMET metrics (DejaVuSansMono, ASCII 32+95)
  ui/title.tex, ui/btlbg.tex    title logo (currently FFL logo) + battle background
  audio/snd0_{id}.wav           BGM, IMA-ADPCM (ffmpeg transcode of OGG bank 0)
  audio/snd2_{id}.wav           SFX (bank 2)
  data/*.bin                    tables below
```

## Per-file formats

**FTEX**: `"FTEX" u32 w, u32 h, w*h*4 RGBA`.

**FFM4** (`load_ffmap` accepts FFM0–FFM4; features gate on the version digit):
```
"FFM4"; w u16; h u16; n_layers u16
mc_slot0 i16; var_slot0 u16; mc_slot1 i16; var_slot1 u16
reserved u32: byte0 = overhead threshold (FieldClass+0xdc2c)
              byte1 = field_bgm (255=none)   byte2 = battle_bgm   byte3 unused
[FFM4] spawn_x u8, spawn_y u8, spawn_dir u8   (255 = none; FieldClass+0xdc48..54)
per layer: w*h × u16 tile word (low=tile, high=slot 0/1)
event_len u32 + raw event-region bytes        (legacy; superseded by events block)
[FFM1+] has_pass u8; if set: w*h × u8 pass nibble (0 = solid; from capk word A & 0xF, layer-0 tiles)
[FFM2+] n_events u16; per event:
    [FFM4] id u16
    x u8, y u8
    [FFM4] rect w u8, h u8 (0→1)
    type u8, boot u8, img i16, var u8
    [FFM3+] appear[31]                          (CheckEventAppear block, header bytes 9..0x27)
    n_scripts u16; per script: len u16 + bytecode (BE operands — see formats/events.md)
```
Known omission: per-map **wrap flags** were in the FFM0 draft spec but never baked; world-map edge wrap is unimplemented engine-side partly for this reason.

**FITM** items: `"FITM" u32 n`; per: id u32, name pstr16, desc pstr16, atk u16, def u16, item_type u8 (0 consumable/key, 1–15 weapon classes, 16 shield, 17–19 head, 20–22 body, 23 hands/acc — `equip_type` in the raw data is always 0; item_type is the real category).
**FCHR** chars: `"FCHR" u32 n`; per: id u32, name pstr16, equip 6×u16, job u8, level u8, str/spd/vit/int/mnd 5×u16, hp u16, mp u16, chpk u16 (field-sprite id).
**FMON** monsters: `"FMON" u32 n`; per: id u32, name pstr16, hp u16, atk u16, def u16, level u8, exp u32, gil u32 (exp/gil = monster body[6]/[10] BE u32 in the source).
**FSPL** spells: `"FSPL" u32 n`; per: id u16, type u8 (0 dmg / 1 heal), mp u16, power u16, name pstr16.
**FLVL** levels: `"FLVL" u16 n_thr` + n×u32 cumulative EXP thresholds (boot §8 `[0x10+9i]` BE), `u16 n_rows` + n×(maxHP u16, maxMP u16) (§8 rows `[L*9+2]`/`+4`). 98 thresholds + 143 rows.
**FSGE** sprite geometry: `"FSGE" u16 n`; per: img u16, isObject u8, frame fx i16, fy i16, fw u16, fh u16, anchor px i16, py i16. Seeded from field_anm, merged with manual `sprite_grid.json`.
**FCAN** chip animation: `"FCAN" u32 n_tilesets`; per tileset: mc u16, cnt u16; per chip: inner u16, type u8 (loop/ping-pong), frames u8, speed u8.
**FCFL** chip floor attrs: `"FCFL" u32 n`; per tileset: mc u16, cnt u16; per chip: inner u16, floor u8 (bit 0x10 = damage).
**FMSG** messages: `"FMSG" u32 n`; per: id u32, len u32, UTF-8 bytes (English slot of `msg{N}.msd`).
**FMET** font meta: `"FMET" cw u16, ch u16, cols u16, first u16`.
**FAUD** audio: `"FAUD" u16 count` + count loop-flag bytes (from `bgm_loop.dat`; flag 1 = loop whole track).
**FSTR** start table: `"FSTR" u16 n`; per: map u16, x u8, y u8, story u8 (boot §1 scenario records; record 0 = retail New Game. x/y are **vestigial** — the engine uses the map-default spawn).
**FINT** intro: `"FINT"` + pstr16 prologue text + pstr16 chapter label (extracted by content from msg0.msd).

## Engine-side persistent formats (written by FFSmith, documented here for completeness)

**FSAV v5** (`Engine/src/main.cpp`): `"FSAV" ver u8(5); map_key pstr16; x u16; y u16; facing u8; img i32; party_count u8 × {charIdx,hp,mp i32×3; equip i32×6; level,exp i32×2}; inv_count u16 × {id,count i32×2}; gil i32; blob_len u32 + SST blob`. Versions: v1 position only; v2 +party/inv/gil; v3 +equip; v4 +level/exp; v5 +script state.
**SST v1** (`script_state.cpp`): `"SST"+0x01` + fixed-order LE u32 dump of all flag/var banks + system specials + timer = 4,032 bytes total.

## Bake pipeline order (`bake()`)

capk → chipanim/chipfloor → per-map (parse chunk + engine header + pass grid + events → FFM4; collect needed tilesheets/sprites) → tilesheets (variant-fallback, tolerates truncated mc34/mc60 sources) → sprites → messages (groups seen) → font → ui → menu data tables → intro → start → common events → sprite geo → audio → manifest. `--proper DIR` (fast, extracted folder) or `--obb FILE`; `--limit N`, `--only KEY`.

## Invariants

1. Engine never parses raw formats; toolkit defines correctness (byte/pixel-match gate).
2. FFM version bumps: **rebuild the engine before rebaking** (loader is backward- but not forward-compatible).
3. Pixel art is only ever integer nearest-neighbor scaled.
4. No original assets committed; bundles are user-baked.
