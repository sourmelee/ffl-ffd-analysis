# Format: Battle Effects / VFX

*Audit 2026-06-10.*

## Status: VIEWER-ONLY, format largely undecoded

- The toolkit's **Battle Effects tab** (`ffd/battle_effects/tab.py`, 116 lines) renders Mobile effect sprites as sprite-container/ic images — i.e. the *image* side parses fine (sprites.md); the *animation/timing/composition* side does not exist.
- Original engine: `MtxEfcCtrl` (effects middleware) + the BTLACT `+0x648` effect-actor pointer. Neither has been read (Inferred placement only).
- `btlanm_sp.dat` covers battle *actor* animation (animations.md), not spell/hit VFX.
- FFSmith renders no battle effects at all.

## When this matters

Battle-presentation fidelity (post battle-logic milestones). Suggested start: `MtxEfcCtrl::*` method surface + FFV twin diff, and a scan for effect-data containers in the OBB (candidate `.dat`s with no current owner are listed in the OBB inventory dialog — none have been attributed to VFX yet, Unverified).
