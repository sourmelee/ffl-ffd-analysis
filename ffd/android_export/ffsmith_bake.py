"""Bake FFSmith-ready asset bundles from the Android OBB.

The FFSmith engine (``../Engine``) never re-solves raw on-disk formats; the
toolkit is the single source of truth. This module emits a small, documented
bundle the engine loads directly. See ``Engine/docs/ASSET_PIPELINE.md``.

Output layout (under ``out_dir``)::

    manifest.json
    maps/g{G}_p{P}_m{M}.ffmap     # flat little-endian baked map (format below)
    tex/mc{N}_{V}.tex             # raw RGBA tilesheet ("FTEX")

``.ffmap`` v0 (little-endian)::

    magic     "FFM0"      4 bytes
    width     u16
    height    u16
    n_layers  u16
    mc_slot0  i16         primary tileset id   (-1 = none)
    var_slot0 u16
    mc_slot1  i16         secondary tileset id (-1 = none)
    var_slot1 u16
    reserved  u32         (0; wrap flags etc. land at M2)
    per layer:
      width*height * u16  tile words (low byte = tile_num, high byte = slot 0/1)
    event_len u32
    event     [event_len] raw event-region bytes (consumed by the script VM later)

``.tex`` v0 (little-endian)::

    magic   "FTEX"  4 bytes
    width   u32
    height  u32
    pixels  width*height*4   RGBA8, straight alpha, row-major top-to-bottom

Maps come from :func:`ffd.maps.android.parse_android_map_chunk` +
:func:`ffd.maps.android.parse_android_map_engine`; tilesheets are decoded from
the OBB's ``mc*.png`` via Pillow. The engine's renderer mirrors
``ExtractTab._render_android_map`` exactly (slot dispatch on the tile-word high
byte, zero-skip on word ``0x0000``, ``TS = 32 if sheet width >= 512 else 16``).
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

from ..containers.obb import load_obb_as_dict
from ..maps.android import parse_android_map_chunk, parse_android_map_engine
from ..maps.mobile import parse_mpkh_index

FFMAP_MAGIC = b"FFM0"
FTEX_MAGIC = b"FTEX"
BUNDLE_VERSION = 0


class _FolderFiles:
    """Lazy name->bytes mapping over a folder of already-extracted files
    (e.g. ``Android/proper_obb``). Mirrors the dict interface the OBB loader
    returns, but reads each file on demand so we never load all ~2500 assets."""

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
    """Yield ``(group, pack, map_id, raw_chunk)`` for every Android map.

    Mirrors ``MapTab._collect_android_maps``: walk each ``mpkh{N}.dat`` index,
    resolve ``mpk{N}_{pack}.dat``, slice each entry's chunk."""
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
    """Decode ``mc{N}_{V}.png`` to ``(w, h, rgba_bytes)``. Engine fallback:
    if the requested variant is missing, fall back to variant 0 (mirrors
    ``GameClass::LoadMapChipImage``). Returns None if neither exists."""
    from PIL import Image
    for v in (variant, 0):
        name = f"mc{mc_id}_{v}.png"
        key = next((k for k in files if Path(k).name == name), None)
        if key:
            im = Image.open(io.BytesIO(files[key])).convert("RGBA")
            return im.width, im.height, v, im.tobytes()
    return None


def _write_tex(path, w, h, rgba):
    with open(path, "wb") as f:
        f.write(FTEX_MAGIC)
        f.write(struct.pack("<II", w, h))
        f.write(rgba)


def _write_ffmap(path, parsed, engine):
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
        f.write(struct.pack("<I", 0))  # reserved
        for layer in layers:
            buf = bytearray()
            for (_mc_type, hb, lb) in layer:
                buf += struct.pack("<H", ((hb & 0xFF) << 8) | (lb & 0xFF))
            f.write(bytes(buf))
        f.write(struct.pack("<I", len(event)))
        f.write(event)


def bake(obb_path=None, out_dir=".", *, proper_dir=None, limit=None, only=None,
         src_files=None):
    """Bake an FFSmith bundle. Provide one source:
      - ``obb_path``    : path to ``main.obb`` (decrypted+indexed via the loader)
      - ``proper_dir``  : a folder of already-extracted files (e.g. proper_obb)
      - ``src_files``   : a pre-built name->bytes mapping (programmatic use)

    ``limit`` caps the number of maps; ``only`` bakes a single ``gG_pP_mM`` key.
    Returns the manifest dict.
    """
    if src_files is not None:
        files = src_files
        source_name = "files"
    elif proper_dir is not None:
        files = _FolderFiles(proper_dir)
        source_name = Path(proper_dir).name
    elif obb_path is not None:
        files = load_obb_as_dict(obb_path, mode="proper")
        source_name = Path(obb_path).name
    else:
        raise ValueError("bake() needs obb_path, proper_dir, or src_files")

    out = Path(out_dir)
    (out / "maps").mkdir(parents=True, exist_ok=True)
    (out / "tex").mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": BUNDLE_VERSION,
        "source": source_name,
        "maps": [],
        "tilesheets": [],
    }
    needed_tex = set()  # (mc_id, variant)
    n = 0

    for (g, p, mid, raw) in iter_android_maps(files):
        key = f"g{g}_p{p}_m{mid}"
        if only and key != only:
            continue
        parsed = parse_android_map_chunk(raw)
        if not parsed:
            continue
        # Carry the raw event region (bytes after the tile-data region) so the
        # baked map is forward-compatible with the script VM milestone.
        end_field = parsed.get("end_field", 0)
        if 0 < end_field <= len(raw):
            parsed["_event"] = raw[end_field:]
        engine = parse_android_map_engine(raw) if len(raw) > 30 else None
        _write_ffmap(out / "maps" / f"{key}.ffmap", parsed, engine)

        s0 = (engine["mc_id_slot0"], engine["variant_slot0"]) if engine else (-1, 0)
        s1 = (engine["mc_id_slot1"], engine["variant_slot1"]) if engine else (-1, 0)
        for (mc, v) in (s0, s1):
            if mc is not None and mc >= 0:
                needed_tex.add((mc, v))
        manifest["maps"].append({
            "id": key, "file": f"maps/{key}.ffmap",
            "w": parsed["w"], "h": parsed["h"], "n_layers": parsed["n_layers"],
            "slot0": [int(s0[0]), int(s0[1])],
            "slot1": [int(s1[0]), int(s1[1])],
        })
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

    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest
