"""Tileset (cpk*.dat / mpk index / Android tileset selector) utilities.

The :class:`MobileTilesetResolver` lazy-loads cpk entries on demand and
caches them; :func:`parse_android_tileset_lookup` reads the Android
``boot_data.dat`` section that maps in-map selector IDs to mc{N} entry
IDs.
"""

from .parser import (
    parse_mpk_index_mobile,
    parse_cpk_index_mobile,
    parse_android_tileset_lookup,
    flat_pack_index,
    load_mobile_tileset,
    MobileTilesetResolver,
)

__all__ = [
    "parse_mpk_index_mobile",
    "parse_cpk_index_mobile",
    "parse_android_tileset_lookup",
    "flat_pack_index",
    "load_mobile_tileset",
    "MobileTilesetResolver",
]
