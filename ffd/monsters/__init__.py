"""Monster / enemy domain.

Mobile parses enemies out of boot_data section 12 (BE); the Android port
splits monsters into boot section 9 (LE) read by a dedicated 64-byte
body parser. ``parse_bem`` decodes the mobile ``bem.dat`` ability/name
table that monsters reference.
"""

from .parser import (
    parse_enemies_mobile,
    parse_monsters_android,
    parse_enemy_names_android,
    parse_bem,
)

__all__ = [
    "parse_enemies_mobile",
    "parse_monsters_android",
    "parse_enemy_names_android",
    "parse_bem",
]
