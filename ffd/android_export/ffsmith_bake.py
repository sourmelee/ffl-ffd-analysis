"""Bake FFSmith-ready asset bundles from the Android OBB.

The FFSmith engine (``../Engine``) never re-solves raw on-disk formats; the
toolkit is the single source of truth. See ``Engine/docs/ASSET_PIPELINE.md``.

Output (under ``out_dir``):
    manifest.json
    maps/g{G}_p{P}_m{M}.ffmap     # flat little-endian baked map (FFM1, format below)
    tex/mc{N}_{V}.tex             # raw RGBA tilesheet ("FTEX")

``.ffmap`` (FFM1, little-endian):
    magic     "FFM1"      4 bytes
    width     u16
    height    u16
    n_layers  u16
    mc_slot0  i16         primary tileset id   (-1 = none)
    var_slot0 u16
    mc_slot1  i16         secondary tileset id (-1 = none)
    var_slot1 u16
    reserved  u32
    per layer: width*height * u16   tile words (low = tile_num, high = slot 0/1)
    event_len u32 + event bytes
    has_pass  u8          1 if a passability grid follows
    pass      width*height u8       per-cell 4-dir pass nibble (0 = solid; from capk.dat)

Maps: parse_android_map_chunk + parse_android_map_engine. Collision: capk.dat
(see ffd/maps/capk.py). Tilesheets: decoded from the OBB's mc*.png via PIL.
"""

from __future__ import annotations

import io
import json
import re
import struct
from pathlib import Path

from ..containers.obb import load_obb_as_dict
from ..maps.android import parse_android_map_chunk, parse_android_map_engine
from ..maps.mobile import parse_mpkh_index
from ..maps.capk import parse_capk, pass_nibble, parse_capk_anim, parse_capk_floor
from ..events.android import parse_android_event_pack

FFMAP_MAGIC = b"FFM5"
FTEX_MAGIC = b"FTEX"
BUNDLE_VERSION = 3


class _FolderFiles:
    """Lazy name->bytes mapping over a folder of extracted files (proper_obb)."""

    def __init__(self, root):
        self.root = Path(root)
        self._names = [p.name for p in self.root.iterdir() if p.is_file()]

    def __iter__(self):
        return iter(self._names)

    def __contains__(self, key):
        return (self.root / Path(key).name).exists()

    def __getitem__(self, key):
        return (self.root / Path(key).name).read_bytes()


def iter_android_maps(files):
    """Yield (group, pack, map_id, raw_chunk) for every Android map."""
    mpkhs = sorted(k for k in files if Path(k).name.startswith("mpkh"))
    for mpkh_key in mpkhs:
        base_idx = "".join(c for c in Path(mpkh_key).stem if c.isdigit())
        packs = parse_mpkh_index(files[mpkh_key])
        for pi, entries in enumerate(packs):
            pname = f"mpk{base_idx}_{pi}.dat"
            pk_key = next((k for k in files if Path(k).name == pname), None)
            if not pk_key:
                continue
            pk = files[pk_key]
            for (mid, off, sz) in entries:
                if off + sz > len(pk):
                    continue
                yield int(base_idx), pi, mid, pk[off:off + sz]


_WARNED_TEX = set()


def _load_tex_rgba(files, mc_id, variant):
    from PIL import Image, ImageFile
    for v in (variant, 0):
        name = f"mc{mc_id}_{v}.png"
        key = next((k for k in files if Path(k).name == name), None)
        if not key:
            continue
        try:
            im = Image.open(io.BytesIO(files[key])).convert("RGBA")
        except OSError:
            # Truncated/corrupt source asset (e.g. an incomplete OBB extraction).
            # Recover what PIL can rather than aborting the entire bake.
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            try:
                im = Image.open(io.BytesIO(files[key])).convert("RGBA")
            except Exception:
                if name not in _WARNED_TEX:
                    print(f"[bake] WARNING: tileset {name} is unreadable (truncated source); skipping")
                    _WARNED_TEX.add(name)
                continue
            finally:
                ImageFile.LOAD_TRUNCATED_IMAGES = False
            if name not in _WARNED_TEX:
                print(f"[bake] WARNING: tileset {name} is truncated; loaded partial image")
                _WARNED_TEX.add(name)
        return im.width, im.height, v, im.tobytes()
    return None


def _build_pass_grid(parsed, engine, capk):
    """Per-cell 4-dir pass nibble from capk.dat (base layer 0). None if no data."""
    if capk is None or engine is None or not parsed.get("layers"):
        return None
    w, h = parsed["w"], parsed["h"]
    mc0, mc1 = engine["mc_id_slot0"], engine["mc_id_slot1"]
    base = parsed["layers"][0]
    grid = bytearray(w * h)
    for i, cell in enumerate(base):
        if i >= len(grid):
            break
        _mc_type, hb, lb = cell
        mc = mc1 if (hb == 1 and mc1 >= 0) else mc0
        grid[i] = pass_nibble(capk, mc, lb)
    return bytes(grid)


def _build_events(raw):
    """Structured events (NPCs/triggers/scripts) from the map chunk's event pack.
    header[2]=tile_x, [3]=tile_y, [7]=type, [8]=boot; chara_img/var + scripts."""
    res = parse_android_event_pack(raw)
    if res.get("parse_error") or not res.get("events"):
        return []
    out = []
    for ev in res["events"]:
        h = ev["header"]
        out.append({
            "id": ev.get("event_id", 0),
            "x": h[2] if len(h) > 2 else 0,
            "y": h[3] if len(h) > 3 else 0,
            # trigger-rect size (FieldClass::CheckRangeEvent: boots 6/7/8 fire
            # while the player is inside [x, x+w) x [y, y+h))
            "w": max(1, h[4]) if len(h) > 4 else 1,
            "hgt": max(1, h[5]) if len(h) > 5 else 1,
            "type": ev["type"], "boot": ev["boot"],
            "img": ev["chara_img"], "var": ev["chara_var"],
            # appear-condition block (FieldClass::CheckEventAppear): 6 slots at
            # header[9..0x27] — flag(5) flag(5) variable(9) item(3) member(3)
            # timer(6); slot present when its first byte != 0.
            "appear": bytes(h[9:9 + 31]) if len(h) >= 40 else b"\x00" * 31,
            "scripts": ev["scripts"],
        })
    return out


def _write_tex(path, w, h, rgba):
    with open(path, "wb") as f:
        f.write(FTEX_MAGIC)
        f.write(struct.pack("<II", w, h))
        f.write(rgba)


def _write_ffmap(path, parsed, engine, pass_grid, events):
    w, h = parsed["w"], parsed["h"]
    layers = parsed["layers"]
    mc0 = engine["mc_id_slot0"] if engine else -1
    v0 = engine["variant_slot0"] if engine else 0
    mc1 = engine["mc_id_slot1"] if engine else -1
    v1 = engine["variant_slot1"] if engine else 0
    event = parsed.get("_event", b"")
    with open(path, "wb") as f:
        f.write(FFMAP_MAGIC)
        f.write(struct.pack("<HHH", w, h, len(layers)))
        f.write(struct.pack("<hHhH", mc0, v0 & 0xFFFF, mc1, v1 & 0xFFFF))
        # reserved u32 packs three small map-header bytes (all fit in a byte):
        #   bits 0..7  overhead-layer threshold (layer index)
        #   bits 8..15 field_bgm  (ReserveBGM id -> snd0_{id}.ogg; 255 = none)
        #   bits 16..23 battle_bgm (Get*Bgm; 255 = none)
        thr = (engine or {}).get("overhead_threshold", 0) or 0
        fbgm = (engine or {}).get("field_bgm", 255)
        bbgm = (engine or {}).get("battle_bgm", 255)
        resv = (thr & 0xFF) | ((fbgm & 0xFF) << 8) | ((bbgm & 0xFF) << 16)
        f.write(struct.pack("<I", resv & 0xFFFFFFFF))
        # FFM4: map default spawn (FieldClass+0xdc48..54; used when SetMapChange
        # layer == -1, e.g. New Game).  255 = none.
        sx = (engine or {}).get("spawn_x", -1)
        sy = (engine or {}).get("spawn_y", -1)
        sd = (engine or {}).get("spawn_dir", 0)
        f.write(struct.pack("<BBB",
                            sx & 0xFF if 0 <= sx <= 254 else 255,
                            sy & 0xFF if 0 <= sy <= 254 else 255,
                            sd & 0xFF))
        # FFM5: random-encounter areas (LoadMapInfo tail -> LoadEncountData):
        # u8 n, then n x { u16 set_id (formation id in the map's story-bank
        # section of form.bin), u8 rate, u8 x, y, w, h }.
        areas = (engine or {}).get("encount_areas") or []
        f.write(struct.pack("<B", min(len(areas), 255)))
        for a in areas[:255]:
            f.write(struct.pack("<HBBBBB", a["set_id"] & 0xFFFF,
                                a["rate"] & 0xFF, a["x"] & 0xFF,
                                a["y"] & 0xFF, a["w"] & 0xFF, a["h"] & 0xFF))
        for layer in layers:
            buf = bytearray()
            for (_mc_type, hb, lb) in layer:
                buf += struct.pack("<H", ((hb & 0xFF) << 8) | (lb & 0xFF))
            f.write(bytes(buf))
        f.write(struct.pack("<I", len(event)))
        f.write(event)
        if pass_grid and len(pass_grid) == w * h:
            f.write(struct.pack("<B", 1))
            f.write(pass_grid)
        else:
            f.write(struct.pack("<B", 0))
        # FFM4 events block (+event id, rect w,h, 31 appear bytes per event)
        f.write(struct.pack("<H", len(events)))
        for ev in events:
            img = ev["img"] if -32768 <= ev["img"] <= 32767 else -1
            f.write(struct.pack("<HBBBBBBhB", ev.get("id", 0) & 0xFFFF,
                                ev["x"] & 0xFF, ev["y"] & 0xFF,
                                ev.get("w", 1) & 0xFF, ev.get("hgt", 1) & 0xFF,
                                ev["type"] & 0xFF, ev["boot"] & 0xFF, img,
                                ev["var"] & 0xFF))
            ap = ev.get("appear", b"\x00" * 31)
            f.write(ap[:31].ljust(31, b"\x00"))
            f.write(struct.pack("<H", len(ev["scripts"])))
            for sc in ev["scripts"]:
                f.write(struct.pack("<H", len(sc)))
                f.write(bytes(sc))


# --- Field dialogue text + font atlas (M3b font/text) ---------------------
# Field dialogue is PER-AREA: the engine loads msg{N}.msd (FieldClass+0x380, set by
# GameClass::ReadStoryMessageData -> SetMessageList), where N is the area/story bank
# (GameClass+0x19fe0).  N is story-state, but maps cluster 1:1 with the 16 banks by
# map GROUP, so we bake bank = group.  msg{N}.msd: u16-BE message count, then count
# messages x 6 languages x 2 slots (dialogue text, speaker name); each string =
# u16-BE len + UTF-8 + NUL.  English text = language 1, slot 0  =>  index msg*12 + 2.
# (Verified vs FieldClass::MoveScript/GetMessageData + GameClass::LoadMessageData_UTF8;
# the earlier system_message.msd section-4 source was a wrong-but-coherent guess.)
_FONT_FIRST, _FONT_LAST, _FONT_COLS, _FONT_CW, _FONT_CH = 32, 127, 16, 8, 14


def _clean_message(s: str) -> str:
    import re
    return re.sub(r"<cha\d>", "Hero", s)   # party-name placeholders -> generic


def _read_msg_bank(files, bank):
    """{msg_id: english_text} from msg{bank}.msd (per-area dialogue bank)."""
    name = f"msg{bank}.msd"
    blob = files.get(name) if hasattr(files, "get") else None
    if blob is None and name in files:
        blob = files[name]
    if not blob or len(blob) < 2:
        return {}
    count = (blob[0] << 8) | blob[1]
    p = 2
    strs = []
    for _ in range(count * 12):                 # 6 languages x 2 slots (text, name)
        if p + 2 > len(blob):
            break
        L = (blob[p] << 8) | blob[p + 1]; p += 2
        if p + L > len(blob):
            break
        strs.append(blob[p:p + L].decode("utf-8", "replace") if L else ""); p += L
        if p < len(blob):
            p += 1                              # NUL terminator
    out = {}
    for m in range(count):
        i = m * 12 + 2                          # English (lang 1) dialogue-text slot
        if i < len(strs) and strs[i]:
            out[m] = _clean_message(strs[i])
    return out


def _bake_ui(files, out_dir):
    """Bake UI images (title logo) the engine needs, as FTEX."""
    baked = []
    try:
        from PIL import Image
        for src, dst in [("TitleLogo.png", "title.tex"), ("btlbg0_0.png", "btlbg.tex")]:
            blob = files.get(src) if hasattr(files, "get") else (files[src] if src in files else None)
            if not blob:
                continue
            im = Image.open(io.BytesIO(blob)).convert("RGBA")
            _write_tex(Path(out_dir) / "ui" / dst, im.width, im.height, im.tobytes())
            baked.append(dst)
    except Exception as e:
        print("[bake] ui skipped:", e)
    return baked


def _bake_menu_data(files, out_dir):
    """Bake item + character tables for the M5 menu pages (data/items.bin, data/chars.bin).
    Item: id -> English name + desc (desc already embeds stats, e.g. "ATK 7").
    Char: id -> English name + 6 equipment item-ids (resolved to item names by the engine)."""
    counts = {"items": 0, "chars": 0}
    def _get(nm):
        return files.get(nm) if hasattr(files, "get") else (files[nm] if nm in files else None)
    try:
        from ..items.parser import parse_items_android, decode_item_body
        from ..characters.parser import parse_chara_set_android
        from ..text.system_message import SystemMessageLookup
        sm = SystemMessageLookup(_get("system_message.msd") or b"")
        boot = _get("boot_data.dat")
        items = parse_items_android(boot) if boot else []
        recs = []
        for iid, it in enumerate(items):
            if not it:
                continue
            name = sm.name("Item", iid, "en") or it.get("name", "")
            desc = sm.desc("Item", iid, "en") or it.get("desc", "")
            if not name:
                continue
            # Real equip stats from the decoded body (GameClass::LoadItemData):
            # body[32] is the primary stat — weapon ATK or armor DEF, keyed by
            # item_type. This replaces the old "ATK n"/"DEF n" description regex,
            # which disagreed with the game on ~6 items (stale flavour text);
            # the body field is what the engine actually uses.
            d = decode_item_body(it["body"]) if it.get("body") else {}
            atk = d.get("attack", 0)
            dfn = d.get("defense", 0)
            itype = d.get("item_type", 0)
            recs.append((iid, name, desc, atk, dfn, itype))
        with open(Path(out_dir) / "data" / "items.bin", "wb") as f:
            f.write(b"FITM"); f.write(struct.pack("<I", len(recs)))
            for iid, name, desc, atk, dfn, itype in recs:
                nb = name.encode("utf-8"); db = desc.encode("utf-8")
                f.write(struct.pack("<IH", iid, len(nb))); f.write(nb)
                f.write(struct.pack("<H", len(db))); f.write(db)
                f.write(struct.pack("<HHB", atk & 0xffff, dfn & 0xffff, itype & 0xff))  # weapon ATK / armor DEF / item_type
        counts["items"] = len(recs)
        cs = _get("chara_set.dat")
        chars = parse_chara_set_android(cs) if cs else []
        # level-growth table = boot_data section 8 (engine memcpy boot[TOC[8]:TOC[9]] -> +0x213f8;
        # 9-byte/level entries: HPbase u16-BE @+2, MPbase u16-BE @+4, base-STAT u8 @+6).
        # maxHP/MP = base[level] * jobHP%/MP% / 100; the five attributes (STR/SPD/VIT/INT/MND)
        # all derive from the SINGLE base-stat byte @+6 scaled by each job's stat% (body[11..15])
        # -- see GameClass::SetJobStatus libjniproxy.so_new.c 152644-152705. base6 grows ~20->32
        # over L0-15 (a sane per-level curve); FF5 SetMemberStatus (FUN_00468490) confirms layout.
        hpb, mpb, statb, thr = [], [], [], []
        if boot and len(boot) >= 68:
            t = [struct.unpack_from("<I", boot, i * 4)[0] for i in range(17)]
            s8 = boot[t[8]:t[9]]
            for L in range(len(s8) // 9):
                e = s8[L*9:L*9+9]
                hpb.append((e[2] << 8) | e[3]); mpb.append((e[4] << 8) | e[5])
                statb.append(e[6])
            # EXP thresholds (LevelUp reads BE u32 @ s8[0x10 + 9*i]); level = #thresholds passed.
            for i in range(98):
                o = 0x10 + 9 * i
                thr.append(int.from_bytes(s8[o:o+4], "big") if o + 4 <= len(s8) else (thr[-1] if thr else 0))
        def _growth(tbl, lvl):
            return tbl[max(0, min(lvl, len(tbl) - 1))] if tbl else 0
        with open(Path(out_dir) / "data" / "chars.bin", "wb") as f:
            f.write(b"FCHR"); f.write(struct.pack("<I", len(chars)))
            for c in chars:
                en = sm.name("Character", c["id"], "en") or c.get("name", "")
                nb = en.encode("utf-8")
                f.write(struct.pack("<IH", c["id"], len(nb))); f.write(nb)
                eq = (list(c.get("equipment", [])) + [0]*6)[:6]
                for e in eq:
                    f.write(struct.pack("<H", e & 0xffff))
                lvl = c.get("level", 1)
                f.write(struct.pack("<BB", c.get("job", 0) & 0xff, lvl & 0xff))
                for k in ("str", "spd", "vit", "int", "mnd"):
                    f.write(struct.pack("<H", c.get(k, 0) & 0xffff))
                f.write(struct.pack("<HH", _growth(hpb, lvl) & 0xffff, _growth(mpb, lvl) & 0xffff))
                f.write(struct.pack("<H", c.get("f186", 0) & 0xffff))   # CHPK field-sprite id
        counts["chars"] = len(chars)
        # level table: EXP thresholds + per-level HP/MP growth + base-stat (boot section 8).
        with open(Path(out_dir) / "data" / "levels.bin", "wb") as f:
            f.write(b"FLVL")
            f.write(struct.pack("<H", len(thr)))
            for v in thr:
                f.write(struct.pack("<I", v & 0xFFFFFFFF))
            f.write(struct.pack("<H", len(hpb)))
            for L in range(len(hpb)):
                f.write(struct.pack("<HH", hpb[L] & 0xFFFF, mpb[L] & 0xFFFF))
            # trailing per-level base-stat block (FLVL 0.7.28); back-tolerant: older
            # loaders stop after the HP/MP block. The five attributes derive from this.
            f.write(struct.pack("<H", len(statb)))
            for v in statb:
                f.write(struct.pack("<H", v & 0xFFFF))
        counts["levels"] = len(thr)
        from ..monsters.parser import parse_monsters_android, decode_monster_body
        mons = parse_monsters_android(boot) if boot else []
        mrecs = []
        for mid, m in enumerate(mons):
            if not m:
                continue
            en = sm.name("Monster", mid, "en") or m.get("name", "")
            if not en or en.startswith("DBG"):
                continue
            b = decode_monster_body(m["body"])
            hp = b.get("max_hp", 0)
            if hp <= 0 or hp > 60000:
                continue
            bd = m["body"]
            exp = int.from_bytes(bd[6:10], "big") if len(bd) >= 10 else 0
            gil = int.from_bytes(bd[10:14], "big") if len(bd) >= 14 else 0
            # Real combat fields (GameClass::LoadMonsterData c:151254 +
            # BattleClass::SetBtlEnemyParam c:88427): level = body[0],
            # HP = BE u32 @ body[2], weapon-attack = body[15],
            # DEF = body[18], MDEF = body[19], evade = body[20],
            # magic-evade = body[21], attack-stat range = body[24..25].
            # The enemy's attack STAT (BTLACT+0x3c) is its LEVEL; MP = HP/8.
            lvl = bd[0] if bd else 1
            hp2 = int.from_bytes(bd[2:6], "big") if len(bd) >= 6 else hp
            watk = bd[15] if len(bd) > 15 else 0
            dfn = bd[18] if len(bd) > 18 else 0
            mdef = bd[19] if len(bd) > 19 else 0
            eva = bd[20] if len(bd) > 20 else 0
            meva = bd[21] if len(bd) > 21 else 0
            amin = bd[24] if len(bd) > 24 else 0
            amax = bd[25] if len(bd) > 25 else 0
            # Battle graphic = mon{group}_{variant}.png: group = BE-u16 body[56..57],
            # variant = body[58] (SetBtlEnemyModel mon%d_%d -> in-mem +0x46 group / +0x48
            # variant; LoadMonsterData packs body[54..63] into +0x44..+0x4c).  Each
            # (group,variant) is ONE static image (the _N files are distinct monsters /
            # recolours, NOT animation frames).
            mgrp = ((bd[56] << 8) | bd[57]) if len(bd) >= 58 else 0xffff
            mvar = bd[58] if len(bd) >= 59 else 0
            mrecs.append((mid, en, min(hp2, 65535), watk, dfn,
                          min(lvl, 255), exp, gil, mdef, eva, meva, amin, amax,
                          mgrp, mvar))
        # Monster battle sprites: bake one static image per (group,variant) used, to
        # tex/mon{group}_{variant}.tex.  The FFD mon{N}_{M}.png "variants" are distinct
        # monsters/recolours (same silhouette, different palette) -- NOT animation frames.
        try:
            from PIL import Image, ImageFile
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            for (g, v) in sorted({(r[13], r[14]) for r in mrecs}):
                key = f"mon{g}_{v}.png"
                if key not in files:
                    continue
                try:
                    im = Image.open(io.BytesIO(files[key])).convert("RGBA")
                    data = im.tobytes()
                    if im.width * im.height * 4 != len(data):
                        continue
                    _write_tex(Path(out_dir) / "tex" / f"mon{g}_{v}.tex", im.width, im.height, data)
                except Exception:
                    continue
        except Exception as _e:
            print(f"[bake] monster sprites skipped: {_e}")
        with open(Path(out_dir) / "data" / "monsters.bin", "wb") as f:
            f.write(b"FMN2"); f.write(struct.pack("<I", len(mrecs)))
            for (mid, en, hp, atk, df, lvl, exp, gil,
                 mdef, eva, meva, amin, amax, mgrp, mvar) in mrecs:
                nb = en.encode("utf-8")
                f.write(struct.pack("<IH", mid, len(nb))); f.write(nb)
                f.write(struct.pack("<HHHBII", hp, atk, df, lvl, exp & 0xFFFFFFFF, gil & 0xFFFFFFFF))
                f.write(struct.pack("<BBBBB", mdef, eva, meva, amin, amax))
                f.write(struct.pack("<HB", mgrp & 0xffff, mvar & 0xff))   # battle sprite: group u16 + variant u8
        counts["monsters"] = len(mrecs)
        # Real spell table, decoded from the boot magic section body (54 B, same
        # family as items).  Replaces the old hardcoded 11-spell approximation:
        # MP cost = body[7] (GameClass::GetMagicUseLostValue), power = body[19]
        # and effect category = body[16] (BattleClass::CalcMagicDmg), element =
        # body[31].  We bake every named HP-damage / HP-heal spell (kind 0/1);
        # status/buff spells (kind 2) are skipped — the engine has no status
        # system yet, and the per-turn MP gate keeps the menu naturally short.
        # FSPL record: id u16, type u8 (0 dmg/1 heal), mp u16, power u16,
        # element u8, namelen u16, name.
        from ..abilities.parser import parse_magic_android, decode_magic_body
        mag = parse_magic_android(boot) if boot else []
        srecs = []
        for sid, sp in enumerate(mag):
            if not sp:
                continue
            nm = sm.name("Magic", sid, "en") or sp.get("name", "")
            if not nm or nm.startswith("DBG") or not nm.strip():
                continue
            d = decode_magic_body(sp.get("body", b""))
            if not d or d["kind"] == 2:        # skip status/buff for now
                continue
            srecs.append((sid, d["kind"], d["mp_cost"], d["power"], d["element"], nm))
        with open(Path(out_dir) / "data" / "spells.bin", "wb") as f:
            f.write(b"FSPL"); f.write(struct.pack("<I", len(srecs)))
            for sid, typ, mp, pw, el, nm in srecs:
                nb = nm.encode("utf-8")
                f.write(struct.pack("<HBHHBH", sid, typ, mp, pw, el, len(nb)))
                f.write(nb)
        counts["spells"] = len(srecs)
        # Per-job growth multipliers (HIGH — GameClass::SetJobStatus): the engine
        # scales the shared level-table base HP/MP/stats by these percents.
        # FJOB record: job_id u16, hp_pct/mp_pct/str/spd/vit/int/mnd u8.
        from ..jobs.parser import parse_jobs_android, decode_job_body
        jobs = parse_jobs_android(boot) if boot else []
        jrecs = []
        for jid, j in enumerate(jobs):
            if not j:
                continue
            jb = decode_job_body(j.get("body", b""))
            if not jb:
                continue
            jrecs.append((jid, jb["hp_pct"], jb["mp_pct"], jb["str_pct"],
                          jb["spd_pct"], jb["vit_pct"], jb["int_pct"], jb["mnd_pct"]))
        with open(Path(out_dir) / "data" / "jobs.bin", "wb") as f:
            f.write(b"FJOB"); f.write(struct.pack("<I", len(jrecs)))
            for rec in jrecs:
                f.write(struct.pack("<H", rec[0]))
                f.write(struct.pack("<BBBBBBB", *(min(255, v) for v in rec[1:])))
        counts["jobs"] = len(jrecs)
    except Exception as e:
        print("[bake] menu data skipped:", e)
    return counts


def _bake_messages(files, out_dir, banks):
    """Bake text/msg{N}.bin for each area bank N (= map group)."""
    total = 0
    for bank in sorted(set(banks)):
        msgs = _read_msg_bank(files, bank)
        if not msgs:
            continue
        with open(Path(out_dir) / "text" / f"msg{bank}.bin", "wb") as f:
            f.write(b"FMSG"); f.write(struct.pack("<I", len(msgs)))
            for mid, text in sorted(msgs.items()):
                b = text.encode("utf-8")
                f.write(struct.pack("<II", mid, len(b))); f.write(b)
        total += len(msgs)
    return total


def _bake_font(out_dir):
    try:
        from PIL import Image, ImageFont, ImageDraw
        import glob as _glob
        cands = (_glob.glob("/usr/share/fonts/**/DejaVuSansMono.ttf", recursive=True)
                 or _glob.glob("/usr/share/fonts/**/*Mono*.ttf", recursive=True))
        font = ImageFont.truetype(cands[0], 12) if cands else ImageFont.load_default()
        cols, cw, ch = _FONT_COLS, _FONT_CW, _FONT_CH
        n = _FONT_LAST - _FONT_FIRST
        rows = (n + cols - 1) // cols
        atlas = Image.new("RGBA", (cols * cw, rows * ch), (0, 0, 0, 0))
        d = ImageDraw.Draw(atlas)
        for c in range(_FONT_FIRST, _FONT_LAST):
            gx = ((c - _FONT_FIRST) % cols) * cw
            gy = ((c - _FONT_FIRST) // cols) * ch
            d.text((gx, gy - 1), chr(c), font=font, fill=(255, 255, 255, 255))
        _write_tex(Path(out_dir) / "text" / "font.tex", atlas.width, atlas.height, atlas.tobytes())
        with open(Path(out_dir) / "text" / "font.meta", "wb") as f:
            f.write(b"FMET")
            f.write(struct.pack("<HHHHH", cw, ch, cols, _FONT_FIRST, n))
        return True
    except Exception as e:
        print("[bake] font skipped:", e); return False




def _pstr_at_content(data, needle):
    """Extract the length-prefixed (u8) string in `data` that STARTS with `needle`."""
    nb = needle.encode("utf-8"); idx = data.find(nb)
    if idx < 1:
        return None
    L = data[idx - 1]
    if 0 < L <= 255 and idx + L <= len(data):
        try:
            st = data[idx:idx + L].decode("utf-8")
            if st.startswith(needle):
                return st
        except Exception:
            return None
    return None


def _bake_intro(files, out_dir):
    """Bake the New Game intro strings (data/intro.bin): the prologue crawl + chapter label,
    extracted by content from msg0.msd (slot indices drift, so we match on text)."""
    msd = files["msg0.msd"] if "msg0.msd" in files else b""
    prologue = (_pstr_at_content(msd, "In an age long past") or "") if msd else ""
    chapter = (_pstr_at_content(msd, "Prologue") or "Prologue") if msd else "Prologue"
    pb = prologue.encode("utf-8"); cb = chapter.encode("utf-8")
    with open(Path(out_dir) / "data" / "intro.bin", "wb") as f:
        f.write(b"FINT")
        f.write(struct.pack("<H", len(pb))); f.write(pb)
        f.write(struct.pack("<H", len(cb))); f.write(cb)
    return 1 if prologue else 0



def _bake_sprite_geo(files, out_dir):
    """Bake per-sprite field geometry (data/spritegeo.bin, magic ``FSG2``) so
    FFSmith draws object sprites (doors / crystals / chests / effects) with their
    REAL frames instead of the hardcoded 48x48 character grid or a mis-keyed
    field_anm sub-rect.

    Geometry is keyed by sprite IMG id (``fldchrN``) from the per-sheet
    classification table (``ffd/animation/sheet_anim.py`` -> ``data/sheet_anim.json``):
    there are ~218 sheets but only ~63 field_anm entries, so the old entry-indexed
    seed mis-aligned every object.  Modes -> code: char(0, 48x48 grid path, no geo),
    static(1, whole opaque bbox; isObject 1=frame0 / 2=loop), grid(2, in-sheet frame strip / effect boxes),
    multifile(3, frames are sibling ``fldchr{img}_{k}`` textures), special(4, left
    on the grid path).  Optional ``sprite_grid.json`` overrides still merge on top.
    """
    from ..animation.sheet_anim import load_table
    table = {}
    if "sheet_anim.json" in files:
        try:
            table = json.loads(files["sheet_anim.json"].decode("utf-8"))
        except Exception:
            table = {}
    if not table:
        data_path = Path(__file__).resolve().parents[2] / "data" / "sheet_anim.json"
        table = load_table(str(data_path))
    _MODE = {"char": 0, "static": 1, "grid": 2, "multifile": 3, "special": 4,
             "battlechar": 5}
    geo = {}
    for key, rec in table.items():
        m = re.match(r"fldchr(\d+)$", key)
        if not m:
            continue
        img = int(m.group(1))
        mode = rec.get("mode", "static")
        code = _MODE.get(mode, 1)
        if mode in ("char", "battlechar"):  # both use the 48x48 grid path, not a field object
            geo[img] = {"mode": code, "isObject": 0, "px": 0, "py": 0, "frames": []}
            continue
        if mode == "multifile":
            if rec.get("frames"):          # explicit per-file crop (e.g. airship cell)
                frames = [list(map(int, f)) for f in rec["frames"]]
            else:
                szs = rec.get("frame_sizes") or [rec.get("size", [0, 0])]
                frames = [[0, 0, int(w), int(h)] for (w, h) in szs]
        else:
            frames = [list(map(int, f)) for f in rec.get("frames", [])]
            if not frames:
                w, h = rec.get("size", [0, 0])
                frames = [[0, 0, int(w), int(h)]]
        f0 = frames[0]
        # isObject tri-state: 0 = not an object (char grid path), 1 = object shown
        # at frame 0 (doors/chests/props -- state sheets, no auto-cycle), 2 = object
        # that loops its frames (ambient effects: fire/flames -- "anim" in the table).
        is_obj = (0 if mode in ("char", "battlechar", "special")
                  else (2 if rec.get("anim") else 1))
        # Anchor: the table carries the FFD part-offset (whole objects) or a
        # centre-bottom default; the engine draws at (tile-centre+px, tile-bottom+py).
        px = int(rec.get("px", -(f0[2] // 2)))
        py = int(rec.get("py", -f0[3]))
        geo[img] = {"mode": code, "isObject": is_obj,
                    "px": px, "py": py, "frames": frames}
    # merge legacy manual overrides (Animation tab authoring)
    if "sprite_grid.json" in files:
        try:
            ov = json.loads(files["sprite_grid.json"].decode("utf-8"))
            for k, v in ov.items():
                g = geo.setdefault(int(k),
                                   {"mode": 1, "isObject": 0, "px": 0, "py": 0,
                                    "frames": [[0, 0, 0, 0]]})
                if "isObject" in v:
                    g["isObject"] = int(v["isObject"])
                if "px" in v:
                    g["px"] = int(v["px"])
                if "py" in v:
                    g["py"] = int(v["py"])
                if all(kk in v for kk in ("fx", "fy", "fw", "fh")):
                    g["frames"] = [[int(v["fx"]), int(v["fy"]),
                                    int(v["fw"]), int(v["fh"])]]
                    if g["mode"] == 0:
                        g["mode"] = 1
        except Exception:
            pass
    with open(Path(out_dir) / "data" / "spritegeo.bin", "wb") as f:
        f.write(b"FSG2")
        f.write(struct.pack("<H", len(geo)))
        for img in sorted(geo):
            g = geo[img]
            frames = g["frames"][:255]
            f.write(struct.pack("<HBBhhH", img, g["mode"], g["isObject"],
                                g["px"], g["py"], len(frames)))
            for (x, y, w, h) in frames:
                f.write(struct.pack("<hhHH", int(x), int(y), int(w), int(h)))
    return len(geo)


def _bake_common_events(files, out_dir):
    """data/common_events.ffmap: the shared CallEvent pool (map 10000, named by
    field_constant.dat @0x8d; FieldClass::LoadCommonEvent).  Identical in every
    group, event-only (no tile layers) — baked once as a 1x1 FFM4 shell."""
    for (g, p, mid, raw) in iter_android_maps(files):
        if mid != 10000:
            continue
        events = _build_events(raw)
        if not events:
            return 0
        shell = {"w": 1, "h": 1, "layers": [], "_event": b""}
        _write_ffmap(Path(out_dir) / "data" / "common_events.ffmap", shell, None, None, events)
        return len(events)
    return 0


def _bake_start(files, out_dir):
    """data/start.bin (FSTR): the New Game start table from boot_data scenario
    section 1 (GameClass::LoadScenarioData).  One record per story bank:
    u16 map, u8 x, u8 y, u8 before_story.  New Game = record 0."""
    if "boot_data.dat" not in files:
        return 0
    from ..boot.scenario import parse_scenario_android
    recs = parse_scenario_android(files["boot_data.dat"])
    if not recs:
        return 0
    with open(Path(out_dir) / "data" / "start.bin", "wb") as f:
        f.write(b"FSTR")
        f.write(struct.pack("<H", len(recs)))
        for r in recs:
            f.write(struct.pack("<HBBB", r["map"] & 0xFFFF, r["x"] & 0xFF,
                                r["y"] & 0xFF, r["before_story"] & 0xFF))
    return len(recs)


def _bake_encounters(files, out_dir):
    """Bake form.bin (BattleClass::LoadFormation, c:103535) -> data/encounters.bin.

    FENC (LE): "FENC" u8 n_banks; per bank: u8 bank, u16 n_recs; per rec:
    u16 formation_id, u8 no_escape, i16 battle_script, u8 n_enemies x
    { u16 enemy_id, i16 x, i16 y, u8 flags }, u8 n_entries x
    { u8 slot, u8 value, i16 param }.
    """
    from ..formats.form_bin import parse_form_bin_android
    raw = files.get("form.bin") if hasattr(files, "get") else (
        files["form.bin"] if "form.bin" in files else None)
    if not raw:
        print("[bake] form.bin missing -- no encounters baked")
        return 0
    banks = parse_form_bin_android(raw)
    n = 0
    with open(Path(out_dir) / "data" / "encounters.bin", "wb") as f:
        f.write(b"FENC")
        f.write(struct.pack("<B", len(banks)))
        for bank in sorted(banks):
            recs = banks[bank]
            f.write(struct.pack("<BH", bank, len(recs)))
            for fid in sorted(recs):
                r = recs[fid]
                f.write(struct.pack("<HBh", fid, r["no_escape"] & 0xFF,
                                    r["battle_script"]))
                f.write(struct.pack("<B", len(r["enemies"])))
                for e in r["enemies"]:
                    f.write(struct.pack("<HhhB", e["enemy_id"] & 0xFFFF,
                                        e["x"], e["y"], e["flags"] & 0xFF))
                f.write(struct.pack("<B", len(r["entries"])))
                for m in r["entries"]:
                    f.write(struct.pack("<BBh", m["slot"] & 0xFF,
                                        m["value"] & 0xFF, m["param"]))
                n += 1
    return n


def _bake_audio(files, out_dir):
    """Transcode the Android Ogg Vorbis BGM (bank 0) + SFX (bank 2) to IMA-ADPCM
    WAV into <out>/audio/, and bake the per-BGM loop-flag table into data/audio.bin.

    IMA-ADPCM WAV (~2x the OGG, vs ~9x for raw PCM) is decoded natively by SDL2's
    SDL_LoadWAV, so FFSmith needs no OGG decoder and no new deps.  See
    [[ffd_android_audio]]: ReserveBGM(id) -> audio/snd0_{id}.wav (looped per
    bgm_loop.dat), ReserveSE(id) -> audio/snd2_{id}.wav.  bgm_loop.dat = BE u16
    count + one loop-flag byte per BGM index (nonzero = loop the whole track).
    audio.bin (FAUD): magic + u16 loop_count + loop_count flag bytes.

    Requires ffmpeg on PATH at bake time; if absent, audio is skipped (warned).
    """
    import re as _re, shutil as _sh, subprocess as _sp, tempfile as _tf, os as _os
    adir = Path(out_dir) / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _sh.which("ffmpeg")
    rx = _re.compile(r"^snd([02])_(\d+)\.ogg$", _re.IGNORECASE)
    names = [n for n in files if rx.match(Path(n).name)]
    n_bgm = n_sfx = 0
    if ffmpeg:
        root = getattr(files, "root", None)
        for name in names:
            base = Path(name).name
            m = rx.match(base)
            src = str(Path(root) / base) if root is not None else None
            tmp = None
            if not src or not _os.path.exists(src):
                tmp = _tf.NamedTemporaryFile(suffix=".ogg", delete=False)
                tmp.write(files[name]); tmp.close(); src = tmp.name
            dst = str(adir / (base[:-4] + ".wav"))
            try:
                _sp.run([ffmpeg, "-y", "-v", "error", "-i", src,
                         "-acodec", "adpcm_ima_wav", dst], check=True)
                if m.group(1) == "0":
                    n_bgm += 1
                else:
                    n_sfx += 1
            except Exception:
                pass
            finally:
                if tmp:
                    _os.unlink(tmp.name)
    else:
        print("[bake] WARNING: ffmpeg not found on PATH; audio NOT baked. "
              "Install ffmpeg and re-bake to enable music/SFX.")
    loop = b""
    if "bgm_loop.dat" in files:
        raw = files["bgm_loop.dat"]
        if len(raw) >= 2:
            cnt = (raw[0] << 8) | raw[1]
            loop = bytes(raw[2:2 + cnt])
    with open(Path(out_dir) / "data" / "audio.bin", "wb") as f:
        f.write(b"FAUD")
        f.write(struct.pack("<H", len(loop)))
        f.write(loop)
    return {"bgm": n_bgm, "sfx": n_sfx, "bgm_loop": len(loop),
            "format": "adpcm_ima_wav" if ffmpeg else "none",
            "se": {"decide": 1, "success": 2, "error": 3}}


def bake(obb_path=None, out_dir=".", *, proper_dir=None, limit=None, only=None,
         src_files=None):
    if src_files is not None:
        files = src_files; source_name = "files"
    elif proper_dir is not None:
        files = _FolderFiles(proper_dir); source_name = Path(proper_dir).name
    elif obb_path is not None:
        files = load_obb_as_dict(obb_path, mode="proper"); source_name = Path(obb_path).name
    else:
        raise ValueError("bake() needs obb_path, proper_dir, or src_files")

    capk = parse_capk(files["capk.dat"]) if "capk.dat" in files else None

    out = Path(out_dir)
    (out / "maps").mkdir(parents=True, exist_ok=True)
    (out / "tex").mkdir(parents=True, exist_ok=True)
    (out / "sprites").mkdir(parents=True, exist_ok=True)
    (out / "text").mkdir(parents=True, exist_ok=True)
    (out / "ui").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)

    manifest = {"version": BUNDLE_VERSION, "source": source_name,
                "collision": bool(capk), "maps": [], "tilesheets": [], "sprites": []}
    # chip-animation table (per-tileset animated chips; FieldClass::GetUpdateChipID).
    chipanim = parse_capk_anim(files["capk.dat"]) if "capk.dat" in files else {}
    with open(out / "data" / "chipanim.bin", "wb") as f:
        f.write(b"FCAN"); f.write(struct.pack("<I", len(chipanim)))
        for _mc in sorted(chipanim):
            _lst = chipanim[_mc]
            f.write(struct.pack("<HH", _mc, len(_lst)))
            for _inner, _typ, _frames, _speed in _lst:
                f.write(struct.pack("<HBBB", _inner, _typ, _frames, _speed))
    manifest["chipanim"] = sum(len(v) for v in chipanim.values())
    # chip floor-attribute table (damage floors etc.; FieldClass::GetFloorAttributeOfChara).
    chipfloor = parse_capk_floor(files["capk.dat"]) if "capk.dat" in files else {}
    with open(out / "data" / "chipfloor.bin", "wb") as f:
        f.write(b"FCFL"); f.write(struct.pack("<I", len(chipfloor)))
        for _mc in sorted(chipfloor):
            _rows = chipfloor[_mc]
            f.write(struct.pack("<HH", _mc, len(_rows)))
            for _inner, _fl in _rows:
                f.write(struct.pack("<HB", _inner, _fl & 0xff))
    manifest["chipfloor"] = sum(len(v) for v in chipfloor.values())
    needed_tex = set()
    groups_seen = set()
    needed_sprites = set()
    n = 0
    for (g, p, mid, raw) in iter_android_maps(files):
        key = f"g{g}_p{p}_m{mid}"
        if only and key != only:
            continue
        parsed = parse_android_map_chunk(raw)
        if not parsed:
            continue
        end_field = parsed.get("end_field", 0)
        if 0 < end_field <= len(raw):
            parsed["_event"] = raw[end_field:]
        engine = parse_android_map_engine(raw) if len(raw) > 30 else None
        pass_grid = _build_pass_grid(parsed, engine, capk)
        events = _build_events(raw)
        for ev in events:
            if ev["img"] > 0: needed_sprites.add((ev["img"], ev["var"]))
        _write_ffmap(out / "maps" / f"{key}.ffmap", parsed, engine, pass_grid, events)
        groups_seen.add(g)

        s0 = (engine["mc_id_slot0"], engine["variant_slot0"]) if engine else (-1, 0)
        s1 = (engine["mc_id_slot1"], engine["variant_slot1"]) if engine else (-1, 0)
        for (mc, v) in (s0, s1):
            if mc is not None and mc >= 0:
                needed_tex.add((mc, v))
        manifest["maps"].append({
            "id": key, "file": f"maps/{key}.ffmap",
            "w": parsed["w"], "h": parsed["h"], "n_layers": parsed["n_layers"],
            "slot0": [int(s0[0]), int(s0[1])], "slot1": [int(s1[0]), int(s1[1])],
            "events": len(events)})
        n += 1
        if limit and n >= limit:
            break

    baked_tex = set()
    for (mc, v) in sorted(needed_tex):
        res = _load_tex_rgba(files, mc, v)
        if res is None:
            continue
        w, h, resolved_v, rgba = res
        stem = f"mc{mc}_{resolved_v}"
        if stem in baked_tex:
            continue
        _write_tex(out / "tex" / f"{stem}.tex", w, h, rgba)
        baked_tex.add(stem)
        manifest["tilesheets"].append({"stem": stem, "w": w, "h": h})

    baked_sprites = set()
    for (img, var) in sorted(needed_sprites):
        from PIL import Image as _Img
        rgba = None; w = h = 0
        for nm in (f"fldchr{img}_{var}.png", f"fldchr{img}_0.png", f"fldchr{img}.png"):
            if nm in files:
                im = _Img.open(io.BytesIO(files[nm])).convert("RGBA")
                w, h, rgba = im.width, im.height, im.tobytes(); break
        if rgba is None: continue
        stem = f"fldchr{img}_{var}"
        if stem in baked_sprites: continue
        _write_tex(out / "sprites" / f"{stem}.tex", w, h, rgba)
        baked_sprites.add(stem)
        manifest["sprites"].append({"stem": stem, "img": img, "var": var, "w": w, "h": h})

    n_msgs = _bake_messages(files, out, groups_seen)
    has_font = _bake_font(out)
    ui_imgs = _bake_ui(files, out)
    menu_counts = _bake_menu_data(files, out)
    _bake_intro(files, out)
    manifest["start"] = _bake_start(files, out)
    manifest["encounters"] = _bake_encounters(files, out)
    manifest["common_events"] = _bake_common_events(files, out)
    _bake_sprite_geo(files, out)
    manifest["audio"] = _bake_audio(files, out)
    manifest["text"] = {"messages": n_msgs, "font": has_font,
                        "banks": sorted(groups_seen)}
    manifest["ui"] = ui_imgs
    manifest["menu_data"] = menu_counts

    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest
# (end of ffsmith_bake.py)
