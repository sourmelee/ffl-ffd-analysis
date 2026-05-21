"""Magic / passive / command-ability parsers for the Android boot_data.

All three share the generic name+desc+body record layout decoded by
:func:`ffd.boot.sections._parse_android_namedesc_section`. Only the TOC
offset and body size differ.
"""

from __future__ import annotations

from ..boot.sections import _parse_android_namedesc_section


def parse_magic_android(boot: bytes):
    """Magic / spells. body=54 — same format as items."""
    return _parse_android_namedesc_section(boot, 0x08, 54)


def parse_passive_abilities_android(boot: bytes):
    """Passive abilities. body=24."""
    return _parse_android_namedesc_section(boot, 0x0c, 24)


def parse_command_abilities_android(boot: bytes):
    """Command abilities. body=25."""
    return _parse_android_namedesc_section(boot, 0x10, 25)
