"""Event-script subsystem.

Both Mobile (FOMA) and Android event scripts share the same opcode set
(0x00..0xab) and length-prefixed command encoding, but the containers
differ — mobile scripts live inside the map chunk's tail, Android
scripts live in dedicated event-pack ``.dat`` files. This package keeps
the shared opcode database in :mod:`ffd.events.opcodes` and per-build
parsers / disassemblers in their own modules.
"""

from .opcodes import (
    EVENT_SCRIPT_OPCODES,
    _decode_event_operands,
    disassemble_script_block,
)
from .mobile import (
    map_event_script_region,
    _mobile_true_event_offset,
    parse_mobile_event_region,
    disassemble_event_region,
)
from .android import (
    parse_android_event_pack,
    disassemble_android_event_pack,
    scan_android_event_packs,
)
from .strings import extract_sjis_strings

__all__ = [
    "EVENT_SCRIPT_OPCODES",
    "_decode_event_operands",
    "disassemble_script_block",
    "map_event_script_region",
    "_mobile_true_event_offset",
    "parse_mobile_event_region",
    "disassemble_event_region",
    "parse_android_event_pack",
    "disassemble_android_event_pack",
    "scan_android_event_packs",
    "extract_sjis_strings",
]
