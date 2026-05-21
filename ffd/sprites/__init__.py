"""Sprite-container ``.dat`` parsers (chpk/ene/bg/feimg/img_etc/cpk/bip).

These files share a common TOC-then-entries layout. Each entry is either
a single ic image or a sub-offset table where ``sub[0]`` is the ic and
``sub[1..]`` are RGB palette variants.
"""

from .container import (
    parse_sprite_container,
    iter_dat_entries,
    extract_hidden_gifs,
    parse_bip,
)

__all__ = [
    "parse_sprite_container",
    "iter_dat_entries",
    "extract_hidden_gifs",
    "parse_bip",
]
