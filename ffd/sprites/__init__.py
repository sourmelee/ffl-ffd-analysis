"""Sprite-container ``.dat`` parsers (chpk/ene/bg/feimg/img_etc/cpk/bip)
plus the Mobile->Android sprite-sheet converter.
"""

from .container import (
    parse_sprite_container,
    iter_dat_entries,
    extract_hidden_gifs,
    parse_bip,
)
from .mobile_to_android import (
    convert_mobile_sheet_to_android,
    make_starter_spec,
    load_mapping_spec,
    save_mapping_spec,
    render_diagnostic_overlay,
    MOBILE_CELL_W, MOBILE_CELL_H, MOBILE_COLS, MOBILE_ROWS,
    ANDROID_CELL_W, ANDROID_CELL_H, ANDROID_PITCH,
    ANDROID_SHEET_W, ANDROID_SHEET_H,
)

__all__ = [
    "parse_sprite_container",
    "iter_dat_entries",
    "extract_hidden_gifs",
    "parse_bip",
    "convert_mobile_sheet_to_android",
    "make_starter_spec",
    "load_mapping_spec",
    "save_mapping_spec",
    "render_diagnostic_overlay",
]
