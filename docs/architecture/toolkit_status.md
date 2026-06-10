# Toolkit Capability Report

*Audit snapshot 2026-06-10, toolkit **0.7.25** (`ffd/__init__.py`), 65 commits, ~24K LOC in `ffd/` + `tools/`. Confidence labels: HIGH/MEDIUM/LOW; claim statuses per the audit method (Confirmed / Partial / Inferred / Unverified / Incorrect).*

## Shape

A Tk GUI (**20 tabs** — note README says "18 tabs", stale) over a headless parser library. Every tab consumes the same parsers a script would; `gui_stub.py` lets `import ffd` work without Tk. Central `FFData` model holds raw bytes from `.sp`/`.obb`/`.apk`/`.jar`/`.jam` sources plus the sidecar JSON caches. CLI entry points: GUI (default), `--bake-ffsmith`, `--android-export`, `--android-encode`, `--compare`.

## Extraction coverage

| Source | Status |
|---|---|
| Mobile `.sp` scratchpads | ✅ HIGH — full directory decode (`containers/sp.py`); 6 of 14 chapters dumped (rest lost media) |
| Android `.obb` | ✅ HIGH — XOR-0x14 container, FAT, INP/mtxs/ICP payloads; **byte-identical repack** (`dict_to_obb` round-trips) |
| `.apk`/`.jar`/folders | ✅ HIGH — zip/folder loaders |
| ICP images | ✅ pixel-perfect 2137/2137 decode + a working **encoder** (`android_export/icp.py`); long tail of variant prefixes still semantically unpinned (MEDIUM) |

## Parsing coverage by domain (status × confidence)

| Domain | Mobile | Android | Notes |
|---|---|---|---|
| Maps | ✅ HIGH | ✅ HIGH structure; **mc_id 73% strict** (MEDIUM) | `parse_android_map_engine` = LoadMapInfo port; remainder covered by mc_overrides annotations |
| Tilesets | ✅ HIGH (cpk/mpk indexes, palettes) | ✅ HIGH (mc png + lookup table) | + cpk→mc SAD matcher, manual overrides, custom palettes, builds |
| Collision/chip attrs | — (mobile capk unparsed — see unresolved) | ✅ HIGH (pass/anim/floor bits) | `maps/capk.py` |
| Sprites/images | ✅ HIGH (ic, containers, hidden GIFs) | ✅ HIGH (fldchr PNG, ICP) | + Mobile→Android converters (chars + tilesets) |
| Animations | ◑ chpk grid is engine-hardcoded, user-adjusted (MEDIUM) | ✅ HIGH (`field_anm`, `btlanm_sp`) | spritegeo + sprite_grid.json overrides |
| Events | ✅ HIGH (region reconstruction, disassembly) | ✅ HIGH (packs, 96-opcode table, real branch semantics 0.7.24/25) | shared opcode DB |
| Text | ✅ HIGH (message.dat) | ✅ HIGH (.msd, system_message 6-lang, msg{N} banks) | |
| Items/Jobs/Monsters/Abilities/Characters | ✅ HIGH (BE §4/§5/§8, chara_set) | ✅ HIGH (LE §5/§6/§9, §2/§3/§4) | namedesc shared decoder; bodies partially field-mapped (see formats/) |
| boot_data | ✅ HIGH TOC + labels (~21 sections) | ✅ HIGH all 16 sections enumerated; §1 scenario decoded 0.7.24 | |
| Audio | ✅ HIGH (snd.dat MFi banks → .mld) | ✅ HIGH (OGG banks, bgm_loop, res.bin names) | MFi→MIDI deferred (trac stream undecoded) |
| Formations | ✅ HIGH (form.bin) | — Android formation source unconfirmed | |
| Saves | n/a | original `save.bin` **undecoded**; FFSmith FSAV is engine-side | |
| Battle/AI logic | tables only — runtime logic lives in the engine RE effort | | |

## The FFSmith baker (`android_export/ffsmith_bake.py`)

Bakes the complete engine bundle (FFM4 maps + FTEX sheets/sprites + 14 binary data tables + text + font + ui + audio). Authoritative format spec: `asset_pipeline.md` (this docs tree). 1,655 maps / 141 tilesheets at last full bake. ffmpeg required for audio (skips with warning otherwise). **Module docstring still says FFM1 — stale** (contradictions #1).

## Comparison framework

`comparison/registry.py`: **4 wired** AssetKinds (Items, Character, Monster, Job — with cross-chapter ALL_SOURCES merge and 6-language name splice) + **5 stubs** (Magic, Sprite, Animation, Map, Text). HANDOFF_NEXT_CHAT.md's "8 unwired AssetKinds" is stale.

## Cross-reference accuracy

Item/monster/job/character record identity verified cross-platform by byte comparison (Potion name byte-identical, 51/54 body bytes; Goblin 62/64; chara records byte-identical for the core cast). Mobile chapter-scoping (per-chapter §8/§5/chara_set with 0xff sentinels) confirmed.

## Known limitations (current, confirmed against code)

- Android map mc_id at 73% strict; fallback chain engine→by_map→by_group→mc0_0.
- ICP variant-prefix tail unpinned; `decode_icp` is a port of Colmines92's logic, not a from-spec decoder.
- **No automated tests anywhere in the repo** (README says so; confirmed — no test files). 0.7.22's "unit-tested headlessly" for sprite_grid refers to session-time checks, not checked-in tests.
- Only 6/14 chapters available; Mobile coverage is structurally chapter-limited.
- MFi `trac` event stream undecoded → no MIDI conversion.
- Monster/job/item body bytes only partially field-mapped (deltas exposed as `tail_uN_*` for the comparison tab).
