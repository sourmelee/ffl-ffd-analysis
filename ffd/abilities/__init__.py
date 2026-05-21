"""Abilities domain — magic, passive, and command abilities.

All three live in Android boot sections 2/3/4 respectively. No mobile-
specific equivalent (mobile decodes them through chara_set + bem.dat).
"""

from .parser import (
    parse_magic_android,
    parse_passive_abilities_android,
    parse_command_abilities_android,
)

__all__ = [
    "parse_magic_android",
    "parse_passive_abilities_android",
    "parse_command_abilities_android",
]
