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
import struct
from pathlib import Path

from ..containers.obb import load_obb_as_dict
from ..maps.android import parse_android_map_chunk, parse_android_map_engine
from ..maps.mobile import parse_mpkh_index
from ..maps.capk import parse_capk, pass_nibble
from ..events.android import parse_android_event_pack

FFMAP_MAGIC = b"FFM2"
FTEX_MAGIC = b"FTEX"
BUNDLE_VERSION = 2


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


def _load_tex_rgba(files, mc_id, variant):
    from PIL import Image
    for v in (variant, 0):
        name = f"mc{mc_id}_{v}.png"
        key = next((k for k in files if Path(k).name == name), None)
        if key:
            im = Image.open(io.BytesIO(files[key])).convert("RGBA")
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
            "x": h[2] if len(h) > 2 else 0,
            "y": h[3] if len(h) > 3 else 0,
            "type": ev["type"], "boot": ev["boot"],
            "img": ev["chara_img"], "var": ev["chara_var"],
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
        f.write(struct.pack("<I", 0))
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
        # FFM2 events block
        f.write(struct.pack("<H", len(events)))
        for ev in events:
            img = ev["img"] if -32768 <= ev["img"] <= 32767 else -1
            f.write(struct.pack("<BBBBhBH", ev["x"] & 0xFF, ev["y"] & 0xFF,
                                ev["type"] & 0xFF, ev["boot"] & 0xFF, img,
                                ev["var"] & 0xFF, len(ev["scripts"])))
            for sc in ev["scripts"]:
                f.write(struct.pack("<H", len(sc)))
                f.write(bytes(sc))


# --- Field dialogue text + font atlas (M3b font/text) ---------------------
# Field scenario messages live in system_message.msd; SetMessage msg_id indexes
# the active language's strings directly (engine GetMessageData -> array[id]).
# Strings are stored 6-languages-interleaved per record (ja,en,fr,zh_cn,zh_tw,ko);
# English = slot 1.  Section 4 is the scenario/cutscene bank used by the early
# maps (m500/m501).  Per-map bank selection for other chapters is a follow-up.
FIELD_MSG_SECTION = 4
_FONT_FIRST, _FONT_LAST, _FONT_COLS, _FONT_CW, _FONT_CH = 32, 127, 16, 8, 14


def _clean_message(s: str) -> str:
    import re
    return re.sub(r"<cha\d>", "Hero", s)   # party-name placeholders -> generic


def _field_messages_en(files, section=FIELD_MSG_SECTION):
    """Return {msg_id: english_string} from system_message.msd section `section`."""
    blob = files.get("system_message.msd") if hasattr(files, "get") else None
    if blob is None and "system_message.msd" in files:
        blob = files["system_message.msd"]
    if not blob:
        return {}
    from ..text.system_message import _read_toc
    toc = _read_toc(blob)
    if section + 1 >= len(toc):
        return {}
    start, end = toc[section], toc[section + 1]
    if not (0 <= start < end <= len(blob)) or start + 2 > end:
        return {}
    count = struct.unpack_from(">H", blob, start)[0]
    p = start + 2
    out = {}
    for rec in range(count):
        slots = []
        for _ in range(6):                         # 6 languages per record
            if p + 2 > end:
                slots.append(""); continue
            L = struct.unpack_from(">H", blob, p)[0]; p += 2
            if p + L > end:
                slots.append(""); break
            slots.append(blob[p:p + L].decode("utf-8", "replace") if L else ""); p += L
            if p < end:
                p += 1                              # NUL terminator
        en = slots[1] if len(slots) > 1 else ""
        if en:
            out[rec] = _clean_message(en)
    return out


def _bake_messages(files, out_dir):
    msgs = _field_messages_en(files)
    path = Path(out_dir) / "text" / "messages.bin"
    with open(path, "wb") as f:
        f.write(b"FMSG"); f.write(struct.pack("<I", len(msgs)))
        for mid, text in sorted(msgs.items()):
            b = text.encode("utf-8")
            f.write(struct.pack("<II", mid, len(b))); f.write(b)
    return len(msgs)


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

    manifest = {"version": BUNDLE_VERSION, "source": source_name,
                "collision": bool(capk), "maps": [], "tilesheets": [], "sprites": []}
    needed_tex = set()
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

    n_msgs = _bake_messages(files, out)
    has_font = _bake_font(out)
    manifest["text"] = {"messages": n_msgs, "font": has_font,
                        "msg_section": FIELD_MSG_SECTION}

    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest
