# Format: Tilesets

*Audit 2026-06-10. Parsers: `ffd/tilesets/parser.py`, `ffd/maps/mc_overrides.py`, `ffd/sprites/mobile_tile_to_android.py`; tools `regenerate_cpk_to_mc.py`.*

## Mobile (cpk/mpk) — HIGH

`cpk0..9.dat` are sprite-container packs of `ic` images (tile sheets); `mpk0..9.dat` hold map chunks. boot_data embeds variable-width pack indexes (`parse_cpk_index_mobile` / `parse_mpk_index_mobile`; `flat_pack_index` flattens). `MobileTilesetResolver` answers "tile sheet for cpk entry X" with palette selection (`cpk_native_palette`, `render_cpk_with_palette`, `count_cpk_palettes`).

## Android (mc) — HIGH

Tile sheets ship as paletted PNGs in the OBB: `mc{id}_{variant}.png` (variant = palette recolor). Sheet width ≥512 ⇒ 32-px tiles else 16 (the renderer/compositor heuristic). A selector→mc_id lookup exists in boot data (`parse_android_tileset_lookup`). Two sheets (mc34, mc60) are truncated 395-byte sources — the baker tolerates them (0.7.13 fix).

## Cross-platform mapping (cpk → mc)

Three-layer resolution, in priority order:
1. `data/cpk_to_mc_overrides.json` — manual picks (Sprite Converter "Save override"), optionally per-palette (`by_palette`). HIGH (human-confirmed).
2. `data/cpk_to_mc.json` — palette-aware SAD matcher output (alpha+luminance sum-of-absolute-differences, masked to Mobile alpha>0; best match per (chapter, cpk, palette)). MEDIUM (statistical).
3. Closest-numeric-ID fallback in the GUI auto-match. LOW.

## Mobile→Android tileset conversion — HIGH (toolkit feature, not an RE claim)

`convert_mobile_tileset_to_android`: 2× nearest-neighbor upscale into the Android canvas; `fill_from_android` back-fills fully-transparent cells from the original mc png; optional `cell_map` remaps; variant strategies `verbatim` (use Android variant png) or `swap` (palette LUT extracted from mc{id}_0 vs mc{id}_v applied to Mobile pixels — breaks on RGBA-only mc34/mc60). **Custom palettes** (`data/custom_palettes.json`): hand-built Mobile palettes appear as extra palette indices; **builds** bind (palette + cell remaps + force-Android cells) to (cpk, variant), resolved chapter-agnostically (highest chapter wins), honored by the Maps mobile-tilesets view and both export paths.

## Confidence notes / unknowns

- The cpk↔mc correspondence is **observational** (pixel matching + eyeballing), not engine-derived; the Android port's actual asset-conversion table, if one exists, was never found.
- Android tile-sheet *palette variant selection at runtime* comes from the map header slots (maps.md); per-chip palette behavior beyond that is not modeled.
- Mobile cpk sheets sometimes ship fewer palettes than Android has variants — custom palettes exist precisely to author the missing ones (human judgment, flagged as such in the JSON).
