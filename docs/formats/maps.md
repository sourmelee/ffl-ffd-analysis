# Format: Maps

*Audit 2026-06-10. Parsers: `ffd/maps/mobile.py`, `ffd/maps/android.py`, `ffd/maps/capk.py`, `ffd/maps/mc_overrides.py`. Baked form: FFM4 (see `../architecture/asset_pipeline.md`).*

## Mobile map chunk (BE) — HIGH

From `parse_mobile_map_chunk`: tileset cpk entry ids at bytes 5/6, palette indices at 7/8, w×h at 9/10, BE u32 layer flags at 30..34, Shift-JIS map name, then tile data — 3 bytes/tile when both layers active, 2 bytes/tile single-layer. Maps pack into `mpk*.dat`; per-pack index optional in boot_data (`parse_mpk_index_mobile`), else a forward-walking heuristic scan (`scan_mobile_mpk_chunks`) — MEDIUM for index-less packs. Event scripts live in the chunk tail; the true event offset must be reconstructed from header `field_356` flags (`events/mobile.py:_mobile_true_event_offset`).

## Android map pack — HIGH

`mpkh*.dat` = index (per-map id/offset/size, `parse_mpkh_index`); `mpk*.dat` = chunks. Map key convention: `g{group}_p{pack}_m{id}` (group = story bank 0–15).

## Android map chunk — engine-accurate streaming parse

`parse_android_map_engine` is a line-by-line port of `FieldClass::LoadMapInfo` (caller skips a 4-byte size prefix; streaming `RomRead*` BE readers). Decoded walk (all HIGH, each field cited to libjniproxy line ranges in the source docstring):

```
u8 discard; u8 bool; i16 (this[0x5b4]); i16 width; i16 height; i16; i32 color
7×u8: field_bgm, battle_bgm, battle_bg, battle_bg_water, ?, ?, encount_ratio
u8 n_layers
per layer (7B header): has_tile, flag_b, flag_a, +4 bytes
per layer with has_tile: w*h*2 tile words; +w*h if flag_a; +w*h if flag_b
spawn: u8 layer, i16 x, i16 y, u8 dir          (FieldClass+0xdc48..54)
i8 mc_id_slot0, u8 variant_slot0; i8 mc_id_slot1, u8 variant_slot1
has_far u8 + 2 params; has_BG u8 + 2 params + 2×i16   (LoadFar/LoadBGLayerAnime consume 0 stream bytes)
u8 overhead_threshold                          (FieldClass+0xdc2c; layers > threshold draw above chars)
3 × u8 bools (0xdc30/0xdc31/0xdc32 — meaning open)
u8 n_encount; n × 7-byte areas: u16BE formation-set id, u8 rate, u8 x, y, w, h
                                               (LoadEncountData c:119075; decoded 2026-06-10)
```

**Tile word semantics (HIGH, hard-won):** high byte is the **slot selector / variant only** (observed values 0/1) — NOT part of a tile id. mc_id is implicit at map level via the slots above. The old `(hb<<1)|variant` reading was Incorrect.

**Match rate (MEDIUM):** 73% strict (mc_id+variant) vs 168 manual annotations (2026-05-13); ~15 of the misses are "engine says slot0 = −1" (no tileset — fallback correct), the rest are unverified disagreements. Resolution chain when rendering: engine parse → `by_map` user_confirmed override → `by_group["0x{chunk18}_{chunk5}"]` bucket default → mc0_0 (`mc_overrides.py:lookup_primary_mc`).

**Spawn x/y in the §1 scenario table are vestigial** — never read by the engine; `SetMapChange` layer = −1 consumes the map-header default instead (HIGH, RE'd 0.7.25).

## Chip attributes (`capk.dat`, Android) — see also Engine/docs/systems/collision.md

LE u32 TOC, section for mc_id at `TOC[mc_id+1]`; u16-BE count; 7-byte records = u32-BE A + u24-BE B.
A bits: `&0xF` 4-dir passability (HIGH); bit8 animated, 9–10 anim type, 11–14 frames, 15–17 speed (HIGH); `(A>>18)&0x3F` floor attr, bit 0x10 damage (HIGH; only value 0x12 observed, 47 chips all in mc63). **Hypotheses:** floor values 1/8/12/15 suspected one-way/stairs/encounter markers — unmapped. Word B meaning unknown.

## Unknowns

- Per-map wrap flags (CheckMovePass wraps via record+3/+4 when set) — location in the chunk header not pinned; not baked.
- The per-step random-encounter **roll formula** (how rate × encount_ratio × steps decide a battle) — areas/ids are decoded (above), the roll is not; FFSmith's `--encounters` uses an approximation.
- The 27% mc_id tail; `chunk[18]`/`chunk[5]` bucket bytes' real meaning (the bucketing works empirically — Inferred).
- Layer attribute planes flag_a/flag_b content (skipped over, never decoded).
- Mobile capk equivalent (Mobile collision source unparsed; Mobile maps render without a pass grid).
