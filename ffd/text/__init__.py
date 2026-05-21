"""Story / dialogue text — ``message.dat`` (mobile) and ``.msd`` (Android)."""

from .parser import (
    MESSAGE_SECTION_LABELS,
    parse_message,
    parse_msd,
    _msd_read_strings,
)

__all__ = [
    "MESSAGE_SECTION_LABELS",
    "parse_message",
    "parse_msd",
    "_msd_read_strings",
]
