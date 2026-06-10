# Format: Sprites & Images

*Audit 2026-06-10. Parsers: `ffd/images/ic.py`, `ffd/sprites/container.py`, `ffd/containers/obb.py` (ICP/INP), `ffd/android_export/icp.py` (encoder), converters in `ffd/sprites/`.*

## `ic` image (Mobile; also embedded in Android leftovers) — HIGH

```
"ic" magic(2) | width BE u16 | height BE u16 | nc u8 (palette colours)
palette: nc × BGR triplets | flag u8 (0xFF = sequential, no tile table)
[tile table: 1–2 B/cell by image size] | tile data: 8×8 tiles, 4bpp if nc≤16 else 8bpp
```
`parse_ic` keeps tile data addressable (lazy); `render_ic` → Pillow; `find_ic_offsets` scans blobs. Foundation: PowerPanda's YYCHR research.

## Sprite containers (Mobile `chpk`/`ene`/`bg`/`feimg`/`img_etc`/`cpk`) — HIGH

Front-of-file offset table → entries → per-entry palette-variant sub-tables → ic images (`parse_sprite_container` yields (entry, variant, ICImage, raw)). `parse_bip` reads icon containers; `extract_hidden_gifs` rescues embedded GIF89a payloads (Chapter1/Online monster sprites are stored as GIFs!). Gotcha class documented in memory `ffd_animation_format`: entry/variant indexing quirks — chpk entry idx maps **directly** to Android fldchr idx.

## Android character sheets (`fldchr{N}_{V}.png`) — HIGH

Plain PNGs in the OBB. Party characters use the universal 48×48 grid (cells origin (1,1), pitch 50; rows = facing Down/Up/Left with Right = flipped Left; cols = idle/walkA/walkB) defined by `field_anm` entry geometry, NOT by the PNG. Objects (doors/chests/crystals — the cycle-less entries) have per-sprite frame rects + anchors (see animations.md). Non-48 character grids exist (Sol 32×48, tiny NPCs 16×16) — generalization still open.

## ICP container (Android paletted images) — MEDIUM overall, output pixel-perfect

12-byte header `"ICP" + filter u8 + unk1 u16 + unk2 u16 + w u16 + h u16` followed by an embedded PNG whose RGB channels smuggle `[1 junk][256×RGBA palette][W*H indices]` in reversed triplets. `decode_icp` ports Colmines92's ICP2PNG (2137/2137 files pixel-perfect); `encode_icp_dat` is the verified symmetric inverse (modding path). **Hypothesis territory:** unk1/unk2 semantics; a tail of variant prefixes not pinned. INP = PNG + 4-byte prefix (strip); mtxs = OGG + 16-byte prefix (HIGH).

## Mobile→Android sprite conversion — HIGH (toolkit feature)

`convert_mobile_sheet_to_android`: maps Mobile chpk cells (transposed 5×6 grid of 16×24, multi-cell poses) onto the Android 6×5/48×48 layout via JSON specs (`frame_map` + `extra_frames`, per-frame align/scale/offset/flip). Solves the "doubled sprite" artifact (a 2×-upscaled Mobile sheet in the Android slot makes field_anm rects sample wrong). Specs live in `ffd/sprites/mappings/*.json`.

## Unknowns

- ICP unk fields + variant prefixes (above).
- The Android engine's own palette-animation path (PaletteCtrlClass) — never read; irrelevant to extraction, relevant to FFSmith fades.
- `Mobile_Assets_In_Android_Version_unused/`: Mobile-format assets shipped unused inside the Android OBB — catalogued but their intended purpose is unknown (vestigial port material, Inferred).
