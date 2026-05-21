"""Audio domain — mobile ``snd.dat`` (gzipped MFi/MLD melodies) and the
Android ``res.bin`` 7-block container that also carries the audio name
table.
"""

from .parser import parse_snd, parse_resbin, parse_audio_names_resbin

__all__ = ["parse_snd", "parse_resbin", "parse_audio_names_resbin"]
