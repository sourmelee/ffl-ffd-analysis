# Format: Animations

*Audit 2026-06-10. Parsers: `ffd/animation/parser.py` (`parse_field_anm`, `parse_btl_anm`, `field_walk_entries`), `ffd/animation/sprite_grid.py`.*

## `field_anm.dat` (Android field animations) — HIGH

Verified against `MtxAnmCtrl::SetAnimeData` + `MtxAnmData::Draw`. Layout: LE u32 n_entries (63) + absolute offsets; each entry has six sub-section offsets (header, keyframes, parts, …) yielding a flat frame table + decoded sub-animations (static, walk cycles…) with playback metadata.

**Key fact:** every frame stores `tex_id = 0` because the engine binds whichever `fldchr` sheet the active character needs at runtime and plays the *universal* animation against it. Hence the Animation tab's two pickers (sheet, then animation).

Character walk template (entry fldchr1, Jack-confirmed): 48×48 cells, origin (1,1), pitch 50; **rows = facing** (Down y1, Up y51, Left y101, Right = Left flipped); **cols = frame** (idle x1, walkA x51, walkB x101).

## Object geometry & overrides — HIGH (annotation system)

Objects = field_anm entries with **no walk-cycle sub-animation** (18 of them: chests, doors, crystals…). The baker seeds per-sprite geometry (default static frame rect + part-offset anchor) into `spritegeo.bin`; since 0.7.21 nothing is *auto*-classified as an object (the size/cycle heuristics misclassified static NPCs) — `isObject` is set only via the manual `sprite_grid.json` written by the Animation tab's override panel (live tile-aligned preview, `dst = (tile/2+px, tile+py)`). This is the manual-annotation-over-heuristics rule in action.

## `btlanm_sp.dat` (Android battle animations) — MEDIUM

Nested container; entry 0 = party template; fldchr30–49 = character sheets; chpk uses a 16×16 grid (memory `ffd_btl_anm_format`, `ffd_animation_format`). `parse_btl_anm` exists; the *playback semantics* (battle action sequencing, BTLACT 0x648 effect actor) are not decoded — extraction-grade only.

## Mobile (`chpk.dat`) — MEDIUM

ic-container of character atlases; the **engine hardcodes the cell layout** (typically 16×16; rows per facing × walk frames). No data-driven animation file was found on Mobile — the Animation tab exposes user-adjustable cell size instead. Treat any Mobile animation rendering as a best-effort reconstruction, not a decoded format.

## Open

- Non-48 *character* grids (Sol 32×48, 16×16 NPCs) need the same override path as objects.
- field_anm sub-animation types beyond static/walk (sit, talk, …) parsed but unverified against in-game playback.
- Battle animation event/timing streams (untouched).
