"""Audio domain -- Mobile/Android ``snd.dat`` (raw MFi/MLD melodies) and
the Android ``res.bin`` 7-block container that also carries the audio
name table.
"""

from .parser import (
    parse_snd, parse_resbin, parse_audio_names_resbin,
    SndEntry, BANK_ROLES,
)

__all__ = [
    "parse_snd", "parse_resbin", "parse_audio_names_resbin",
    "SndEntry", "BANK_ROLES",
]
