"""DoCoMo ``.sp`` scratchpad parser (FFD_REVERSE_ENGINEERING.md §1).

A scratchpad is a fixed-header binary container holding the per-chapter
``.dat`` blobs (``boot_data.dat``, ``chpk.dat``, ``cpk*.dat``, etc.).
``parse_sp`` returns a flat ``filename -> bytes`` map.
"""

from __future__ import annotations

import io
import zipfile
from collections import OrderedDict
from pathlib import Path

from ..binary import be_u16, be_u32
from ..constants import SP_BASE, DIR_POS


def parse_sp(path) -> "OrderedDict[str, bytes]":
    """
    Parse a DoCoMo .sp scratchpad file.
    Returns an OrderedDict mapping filename -> raw bytes.
    """
    raw = Path(path).read_bytes()
    if len(raw) < SP_BASE + DIR_POS + 9:
        raise ValueError(f"{path}: file too small to be a scratchpad")

    data = raw[SP_BASE:]                       # everything past file header

    # ---- Directory header ---------------------------------------------------
    if DIR_POS + 9 > len(data):
        raise ValueError("scratchpad has no directory header")
    dir_size  = be_u32(data, DIR_POS)
    dir_flags = data[DIR_POS + 8]
    dir_data_raw = data[DIR_POS + 9 : DIR_POS + 9 + dir_size]

    if dir_flags & 1:
        try:
            with zipfile.ZipFile(io.BytesIO(dir_data_raw)) as zf:
                dir_data = zf.read(zf.namelist()[0])
        except Exception:
            dir_data = dir_data_raw
    else:
        dir_data = dir_data_raw

    # ---- Entries ------------------------------------------------------------
    if len(dir_data) < 2:
        return OrderedDict()
    n_files = be_u16(dir_data, 0)
    if n_files == 0 or 2 + n_files * 13 > len(dir_data):
        return OrderedDict()

    entries = []
    for i in range(n_files):
        e = 2 + i * 13
        name_off  = be_u32(dir_data, e)
        data_off  = be_u32(dir_data, e + 4)
        flags     = dir_data[e + 12]
        entries.append((name_off, data_off, flags))

    file_data_region_start = DIR_POS + 9 + dir_size
    file_data_region = data[file_data_region_start:]

    # name_data_offset values are relative to the start of dir_data
    files = OrderedDict()
    for i, (name_off, data_off, flags) in enumerate(entries):
        if i + 1 < n_files:
            name_end = entries[i + 1][0]
            data_end = entries[i + 1][1]
        else:
            # last entry: name extends until first known boundary; data
            # extends to end of region.
            # The names section sits between entries[-1][0] and the next
            # well-defined boundary. Heuristic: stop at next 0x00.
            name_end = name_off
            while name_end < len(dir_data) and dir_data[name_end] != 0:
                name_end += 1
            data_end = len(file_data_region)

        name = bytes(dir_data[name_off:name_end]).decode("ascii",
                                                         errors="replace")
        name = name.rstrip("\x00").strip()
        if not name:
            name = f"_unnamed_{i}"

        raw_blob = bytes(file_data_region[data_off:data_end])
        if flags & 1:
            try:
                with zipfile.ZipFile(io.BytesIO(raw_blob)) as zf:
                    raw_blob = zf.read(zf.namelist()[0])
            except Exception:
                pass

        files[name] = raw_blob

    return files
