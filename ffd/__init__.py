"""
FF Dimensions / Legends Unified Toolkit (package)
=================================================

Modular re-organisation of the original ``ffd_toolkit.py`` mega-module.
The public surface is preserved: every name that used to be importable
as ``from ffd_toolkit import X`` is re-exported from ``ffd_toolkit`` for
backward compatibility, and the GUI is launched the same way:

    python ffd_toolkit.py

Internally the code is split by domain (containers/, images/, sprites/,
maps/, events/, boot/, etc.). Each domain folder holds both its parsers
and any Tkinter Tab classes that consume them.

Optional GUI dependencies (tkinter, PIL.ImageTk) are imported via
:mod:`ffd.gui_stub`, so headless callers can ``import ffd`` even on
systems without Tk installed.
"""

from __future__ import annotations

# Canonical toolkit version. Bump on each release per semver:
# - MAJOR: breaking changes to parsers / .ffdproj format / public API
# - MINOR: backward-compatible new features (new tab, new parser, new menu)
# - PATCH: bug fixes only
# Keep CHANGELOG.md in sync.
__version__ = "0.7.12"

# Constants and binary helpers are foundational - re-exported so older
# parser-only callers can keep doing ``from ffd_toolkit import be_u32``.
from .binary import (
    be_u8, be_s8, be_u16, be_u32, le_u16, le_u32,
    read_pstr_sjis, safe_decode_ascii,
)
from .constants import (
    SP_BASE, DIR_POS, SP_SLOTS, KNOWN_DAT_FILES,
    CPK_NAMES, MPK_NAMES, CHARA_TABLE, ELEMENTS, STATUSES,
)
from .gui_stub import HAS_GUI, HAS_TK, HAS_IMAGETK

__all__ = [
    "__version__",
    # binary
    "be_u8", "be_s8", "be_u16", "be_u32", "le_u16", "le_u32",
    "read_pstr_sjis", "safe_decode_ascii",
    # constants
    "SP_BASE", "DIR_POS", "SP_SLOTS", "KNOWN_DAT_FILES",
    "CPK_NAMES", "MPK_NAMES", "CHARA_TABLE", "ELEMENTS", "STATUSES",
    # gui availability
    "HAS_GUI", "HAS_TK", "HAS_IMAGETK",
]
