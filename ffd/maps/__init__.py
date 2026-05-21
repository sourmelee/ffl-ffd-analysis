"""Map parsing for both the mobile (mpk/cpk) and Android (mpkh + .obb)
builds, plus the user-managed ``mc_overrides.json`` annotation layer.

Tabs (``MapTab``, ``MapAnnotationTab``) live alongside the parsers
because both consume the same domain types.
"""

from .mobile import (
    parse_mobile_map_chunk,
    scan_mobile_mpk_chunks,
    parse_mobile_mpk,
    parse_mpkh_index,
)
from .android import (
    _RomReader,
    parse_android_map_engine,
    parse_android_map_chunk,
)
from .mc_overrides import (
    MC_OVERRIDES_FILENAME,
    CPK_TO_MC_FILENAME,
    empty_mc_overrides,
    load_mc_overrides,
    save_mc_overrides,
    map_key,
    bucket_key,
    load_cpk_to_mc,
    invert_cpk_to_mc,
    lookup_primary_mc,
)

__all__ = [
    # mobile
    "parse_mobile_map_chunk", "scan_mobile_mpk_chunks",
    "parse_mobile_mpk", "parse_mpkh_index",
    # android
    "_RomReader", "parse_android_map_engine", "parse_android_map_chunk",
    # mc_overrides
    "MC_OVERRIDES_FILENAME", "CPK_TO_MC_FILENAME",
    "empty_mc_overrides", "load_mc_overrides", "save_mc_overrides",
    "map_key", "bucket_key", "load_cpk_to_mc", "invert_cpk_to_mc",
    "lookup_primary_mc",
]
