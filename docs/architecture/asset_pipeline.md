# Asset Pipeline — Authoritative Baked-Bundle Specification

*Audit 2026-06-10 (rev. 2026-07-11, toolkit 0.9.0 / map format **FFM6**). This supersedes the "Bundle layout (v0 draft)" in `Engine/docs/ASSET_PIPELINE.md` (kept there for its principles/symbiosis rules). Writer: `ffd/android_export/ffsmith_bake.py`. Reader: `Engine/src/data/bundle.cpp`. Any change must touch both and bump the relevant magic.*

All baked integers are **little-endian** unless noted. `pstr16` = u16 length + bytes (UTF-8).

## Bundle layout

```
out_dir/
  manifest.json                 version, source, maps/tilesheets/sprites TOC, counts
  maps/g{G}_p{P}_m{M}.ffmap     FFM6 baked maps
  data/common_events.ffmap      map 10000 (CallEvent pool, 26 routines) as a 1×1 FFM6 shell
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

**FFM6** (`load_ffmap` accepts FFM0–FFM6; features gate on the version digit):
```
"FFM6"; w u16; h u16; n_layers u16
mc_slot0 i16; var_slot0 u16; mc_slot1 i16; var_slot1 u16
reserved u32: byte0 = overhead threshold (FieldClass+0xdc2c)
              byte1 = field_bgm (255=none)   byte2 = battle_bgm   byte3 unused
[FFM4] spawn_x u8, spawn_y u8, spawn_dir u8   (255 = none; FieldClass+0xdc48..54)
[FFM5] n_enc u8; n × { set_id u16 (formation id, story-bank section), rate u8,
       x u8, y u8, w u8, h u8 }   random-encounter areas (LoadEncountData c:119075)
per layer: w*h × u16 tile word (low=tile, high=slot 0/1)
event_len u32 + raw event-region bytes        (legacy; superseded by events block)
[FFM1+] has_pass u8; if set: w*h × u8 pass nibble (0 = solid; from capk word A & 0xF, layer-0 tiles)
[FFM2+] n_events u16; per event:
    [FFM4] id u16
    x u8, y u8
    [FFM4] rect w u8, h u8 (0→1)
    type u8, boot u8, img i16, var u8
    [FFM3+] appear[31]                          (CheckEventAppear block, header bytes 9..0x27)
    [FFM6] move_type u8, facing u8, chara_flags u8, speed u8, off_x u8, off_y u8, freq u8
                                                (NPC movement block, header bytes +0x35..+0x3b;
                                                 InitEventDataOfChara c:119752 — spawn tile =
                                                 rect origin + off; move_type 2 wanders confined
                                                 to the event rect, GetPassFlags c:117339)
    n_scripts u16; per script: len u16 + bytecode (BE operands — see formats/events.md)
```
Known omission: per-map **wrap flags** were in the FFM0 draft spec but never baked; world-map edge wrap is unimplemented engine-side partly for this reason. Their source is now LOCATED (2026-07-11): per-LAYER bytes +3/+4 of the 0x28-byte layer records at FieldClass+0xdc40, applied as modulo-w/h in `CheckMovePass` c:114790 / `GetPassFlags` c:117339 — baking them is the N6 prerequisite. (The FFM5 tail also reads-and-skips 3 bool bytes — FieldClass+0xdc30..32 — whose meaning is still open.)

**FITM** items: `"FITM" u32 n`; per: id u32, name pstr16, desc pstr16, atk u16, def u16, item_type u8 (0 consumable/key, 1–15 weapon classes, 16 shield, 17–19 head, 20–22 body, 23 hands/acc). atk/def are the **decoded body[32] primary stat** (weapon ATK or armor DEF by item_type), 0.7.27 — replaced the old "ATK n"/"DEF n" description regex (`LoadItemData` @149955; 206/209 + 164/167 desc agreement).
**FCHR** chars: `"FCHR" u32 n`; per: id u32, name pstr16, equip 6×u16, job u8, level u8, str/spd/vit/int/mnd 5×u16, hp u16, mp u16, chpk u16 (field-sprite id).
**FMN2** monsters (0.7.26; loader also accepts old FMON): `"FMN2" u32 n`; per: id u32, name pstr16, hp u16 (BE u32 @ body[2]), atk u16 (= weapon-attack, body[15]), def u16 (body[18]), level u8 (body[0]), exp u32, gil u32 (body[6]/[10] BE), mdef u8, eva u8, meva u8, amin u8, amax u8 (body[19/20/21/24/25]). Decoded via `LoadMonsterData` c:151254 + `SetBtlEnemyParam` c:88427; enemy attack STAT = level, MP = HP/8.
**field_constant.bin** (0.9.0): `field_constant.dat` baked **verbatim** (306 B). NPC movement timing: walk-duration table @0x37 (8 × u8 ticks/step, speed clamped to [cfg[0x32], cfg[0x34]-1] per `CalcCharaAnimeSpeed` c:118074); wander-wait table @0x42 (u8 ticks, freq clamped to [cfg[0x3f], cfg[0x40]-1] per the `SetCharaAction` c:117759 wait-command branch). Retail values: walk {44,30,14,6,4,22,8,6}, wait {180,90,45,21,0}. The engine compiles in these decoded defaults, so pre-FFM6 bundles still run.

**FENC** encounters (0.7.26; from `form.bin` via `parse_form_bin_android`): `"FENC" u8 n_banks`; per bank: bank u8, n_recs u16; per record: formation_id u16, no_escape u8, battle_script i16 (bsc.dat id — unimplemented engine-side), n_enemies u8 × { enemy_id u16, x i16, y i16, flags u8 }, n_entries u8 × { slot u8, value u8, param i16 }.
**FSPL** spells (0.7.27 — gained an `element` byte): `"FSPL" u32 n`; per: id u16, type u8 (0 dmg / 1 heal), mp u16, power u16, **element u8**, name pstr16. Decoded from the magic body (`decode_magic_body`): mp = body[7], power = body[19], type from effect_cat body[16], element = body[31]. 251 real damage/heal spells (was an 11-entry hardcoded `CAST` list); status spells (effect_cat 5–8) are skipped pending an engine status system.
**FJOB** jobs (0.7.27, new): `"FJOB" u32 n`; per: job_id u16, hp_pct u8, mp_pct u8, str/spd/vit/int/mnd 5×u8. Per-job growth multipliers (percent of the FLVL base) from `decode_job_body` (body[9]/[10]/[11..15]); the engine scales `memberMaxHp`/`memberMaxMp` and level-up deltas by these (`SetJobStatus` @152572).
**FLVL** levels: `"FLVL" u16 n_thr` + n×u32 cumulative EXP thresholds (boot §8 `[0x10+9i]` BE), `u16 n_rows` + n×(maxHP u16, maxMP u16) (§8 rows `[L*9+2]`/`+4`), then (0.7.28) `u16 n_stat` + n×u16 per-level **base-stat** (§8 row `[L*9+6]`). 98 thresholds + 143 rows. The base-stat block is a back-tolerant trailer (older loaders stop after HP/MP). The five attributes (STR/SPD/VIT/INT/MND) all derive from this single base via `SetJobStatus` per-job stat% (FJOB body[11..15]); see `formats/jobs.md`.
**FSG2** sprite geometry (was `FSGE`): `"FSG2" u16 n`; per sprite: img u16, mode u8 (0 char / 1 static / 2 grid / 3 multifile / 4 special / 5 battlechar / 6 directional), isObject u8 (0 not-object / 1 object-frame-0 / 2 object-loops), anchor px i16, py i16, nframes u16, then nframes × (x i16, y i16, w u16, h u16). Keyed by **sprite img id** (fldchrN) from `data/sheet_anim.json` (per-sheet classification), NOT by field_anm entry index. `static`/`grid` frames crop the bound `fldchr{img}_0` sheet; `multifile` frames are sibling `fldchr{img}_{k}` textures. Manual `sprite_grid.json` overrides still merge on top. Loader keeps `FSGE` back-compat. _Bundle-format bump: requires an FFSmith rebuild before re-baking._
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

capk → chipanim/chipfloor → per-map (parse chunk + engine header + pass grid + events + areas → FFM6; collect needed tilesheets/sprites) → tilesheets (variant-fallback, tolerates truncated mc34/mc60 sources) → sprites → messages (groups seen) → font → ui → menu data tables → intro → start → encounters (FENC) → common events → sprite geo → audio → field_constant → manifest. `--proper DIR` (fast, extracted folder) or `--obb FILE`; `--limit N`, `--only KEY`.

## Invariants

1. Engine never parses raw formats; toolkit defines correctness (byte/pixel-match gate).
2. FFM version bumps: **rebuild the engine before rebaking** (loader is backward- but not forward-compatible).
3. Pixel art is only ever integer nearest-neighbor scaled.
4. No original assets committed; bundles are user-baked.

**FMN2 (0.7.30):** monster record gains a trailing `sprite_id u16 + nframes u8`; monster battle sprites bake to `tex/mon{sprite_id}.tex` (horizontal idle-frame strip, frame_w = texW/nframes).
