"""Tileset / pack-index parsers for both builds.

* :func:`parse_mpk_index_mobile` and :func:`parse_cpk_index_mobile` walk
  the variable-width pack indexes embedded in mobile ``boot_data.dat``.
* :func:`parse_android_tileset_lookup` reads the selector→mc_id map from
  the Android port.
* :class:`MobileTilesetResolver` is the high-level helper that loads
  tileset images on demand from a chapter's cpk files.
"""

from __future__ import annotations

import struct
from typing import Optional

from PIL import Image

from ..binary import be_u32, le_u32
from ..images.ic import parse_ic, render_ic, _decode_palette_rgb


def parse_mpk_index_mobile(boot: bytes):
    """
    Mobile boot_data section at byte 36: variable-width pack index.
    Returns list of packs, each pack = [(entry_id, size), ...].
    """
    if len(boot) < 40:
        return []
    ptr = be_u32(boot, 36)
    if ptr + 8 > len(boot):
        return []
    p = ptr + 4   # skip 4 bytes
    if p + 4 > len(boot):
        return []
    cnt_b   = boot[p]; p += 1
    id_b    = boot[p]; p += 1
    sz_b    = boot[p]; p += 1
    n_packs = boot[p]; p += 1

    def rN(width):
        nonlocal p
        v = 0
        for k in range(width):
            if p + k >= len(boot):
                return v
            v = (v << 8) | boot[p+k]
        p += width
        return v

    packs = []
    for _pi in range(n_packs):
        if p >= len(boot):
            break
        n_entries = rN(cnt_b)
        if n_entries > 4096:
            break
        entries = []
        for _ in range(n_entries):
            mid = rN(id_b)
            sz  = rN(sz_b)
            entries.append((mid, sz))
        packs.append(entries)
    return packs


def parse_cpk_index_mobile(boot: bytes):
    """Mobile boot_data section at byte 48 = cpk tileset index."""
    if len(boot) < 52:
        return []
    ptr = be_u32(boot, 48)
    if ptr + 8 > len(boot):
        return []
    p = ptr + 4
    if p + 4 > len(boot):
        return []
    cnt_b   = boot[p]; p += 1
    id_b    = boot[p]; p += 1
    sz_b    = boot[p]; p += 1
    n_packs = boot[p]; p += 1

    def rN(width):
        nonlocal p
        v = 0
        for k in range(width):
            if p + k >= len(boot):
                return v
            v = (v << 8) | boot[p+k]
        p += width
        return v

    packs = []
    for _pi in range(n_packs):
        if p >= len(boot):
            break
        n_entries = rN(cnt_b)
        if n_entries > 4096:
            break
        entries = []
        for _ in range(n_entries):
            mid = rN(id_b)
            sz  = rN(sz_b)
            entries.append((mid, sz))
        packs.append(entries)
    return packs


def parse_android_tileset_lookup(boot: bytes) -> dict:
    """
    Android boot_data.dat section at byte 48 contains a lookup table that
    maps an in-map tileset_selector_id (the high byte of each tile word) to
    the actual mc{N} entry_id used to load mc{N}_0.png from the .obb.

    Format (LE): pointer at byte 48 → section_ptr. At section_ptr+2 starts
    an array of bytes where index = selector_id, value = mc_entry_id.

    Returns dict: selector_id -> mc_entry_id
    (if boot_data unavailable or section unreadable, returns empty dict)
    """
    if len(boot) < 52:
        return {}
    try:
        ptr = le_u32(boot, 48)
        if ptr + 2 >= len(boot):
            return {}
        # First 2 bytes at section are a count or header; skip them
        arr_start = ptr + 2
        # The lookup array runs until end of section or for 256 entries
        result = {}
        for i in range(min(256, len(boot) - arr_start)):
            selector_id = i
            mc_entry_id = boot[arr_start + i]
            if mc_entry_id != 0 or i == 0:  # 0 is valid for selector 0
                result[selector_id] = mc_entry_id
        return result
    except Exception:
        return {}


def flat_pack_index(packs):
    """
    Convert pack list ([[(eid, sz), ...], ...]) into a flat dict
    eid -> (pack_idx, byte_offset_in_pack, byte_size).
    """
    out = {}
    for pi, entries in enumerate(packs):
        cum = 0
        for (eid, sz) in entries:
            out[eid] = (pi, cum, sz)
            cum += sz
    return out


def load_mobile_tileset(cpk_data: bytes, chunk_off: int, chunk_sz: int,
                        pal_idx: int = 0) -> Optional["Image.Image"]:
    """
    Extract a single tileset image (RGBA) from a cpk*.dat chunk.
    Mirrors the working reference's _load_tileset_img.
    """
    chunk = cpk_data[chunk_off:chunk_off + chunk_sz]
    if len(chunk) < 4:
        return None
    first4 = struct.unpack(">I", chunk[:4])[0]
    if first4 == 0 or first4 % 4 != 0 or first4 > len(chunk):
        return None
    n_sub = first4 // 4
    ic_rel = first4
    if ic_rel + 2 > len(chunk) or chunk[ic_rel:ic_rel+2] != b"ic":
        # Maybe direct entry: ic at +8
        if first4 == 8 and chunk[8:10] == b"ic":
            ic = parse_ic(chunk, 8)
            if ic is None:
                return None
            return render_ic(ic)
        return None
    ic = parse_ic(chunk, ic_rel)
    if ic is None:
        return None
    pal = ic.palette
    nc = ic.nc
    # Apply palette override if pal_idx > 0
    if 0 < pal_idx < n_sub:
        pal_rel = struct.unpack(">I",
                                chunk[pal_idx*4:(pal_idx+1)*4])[0]
        if pal_idx + 1 < n_sub:
            nxt = struct.unpack(">I",
                                chunk[(pal_idx+1)*4:(pal_idx+2)*4])[0]
        else:
            nxt = chunk_sz
        if 0 < pal_rel < nxt <= chunk_sz and (nxt - pal_rel) >= nc * 3:
            pal = _decode_palette_rgb(chunk[pal_rel:pal_rel + nc*3], nc)
    return render_ic(ic, palette=pal)


class MobileTilesetResolver:
    """
    Loads cpk tilesets on demand by (entry_id, palette_idx).
    Caches results per (entry_id, palette_idx) tuple.
    """
    def __init__(self, sp_files):
        """
        sp_files: dict[filename -> bytes] for ONE chapter scratchpad
        """
        self.cpk_files = {}
        for name, blob in sp_files.items():
            if name.startswith("cpk") and name.endswith(".dat"):
                # cpk{N}.dat — extract N
                stem = name[3:-4]
                try:
                    self.cpk_files[int(stem)] = blob
                except ValueError:
                    pass
        boot = sp_files.get("boot_data.dat")
        self.cpk_index = (flat_pack_index(parse_cpk_index_mobile(boot))
                          if boot else {})
        self.cache = {}

    def get(self, entry_id: int, pal_idx: int = 0):
        key = (entry_id, pal_idx)
        if key in self.cache:
            return self.cache[key]
        if entry_id == 255 or entry_id not in self.cpk_index:
            self.cache[key] = None
            return None
        pack, off, sz = self.cpk_index[entry_id]
        if pack not in self.cpk_files:
            self.cache[key] = None
            return None
        img = load_mobile_tileset(self.cpk_files[pack], off, sz, pal_idx)
        self.cache[key] = img
        return img

    def get_all_tilesets(self):
        """Return dict of (entry_id, pal_idx=0) → image for all known entries."""
        out = {}
        for eid in self.cpk_index:
            img = self.get(eid, 0)
            if img is not None:
                out[eid] = img
        return out
