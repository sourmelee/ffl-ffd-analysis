"""``boot_data.dat`` — the master TOC + tables file.

Mobile boot_data is big-endian; the Android port re-encoded it as
little-endian. Section ordering also differs between the two builds.
This package keeps the endian-agnostic TOC walker (:func:`parse_boot_toc`)
alongside the per-build section labels and per-table parsers.

Note: per-table parsers for monsters, items, jobs, abilities, etc. live
in their respective domain packages (``ffd.monsters``, ``ffd.items``,
etc.). The ``ANDROID_BOOT_LOADERS`` map and the generic helper
:func:`_parse_android_namedesc_section` live here because they are
shared by all of them.
"""

from .sections import (
    boot_section_be,
    boot_section_le,
    detect_boot_endian,
    parse_boot_toc,
    boot_section_label,
    ANDROID_BOOT_SECTION_LABELS,
    MOBILE_BOOT_SECTION_LABELS,
    ANDROID_BOOT_LOADERS,
    _parse_android_namedesc_section,
)

__all__ = [
    "boot_section_be", "boot_section_le",
    "detect_boot_endian", "parse_boot_toc", "boot_section_label",
    "ANDROID_BOOT_SECTION_LABELS", "MOBILE_BOOT_SECTION_LABELS",
    "ANDROID_BOOT_LOADERS", "_parse_android_namedesc_section",
]
