"""Project-wide constants drawn from ``FFD_REVERSE_ENGINEERING.md``.

These are imported by both parser code and GUI code, so they live in
their own leaf module to avoid pulling in Tk just to read a chapter
slot name.
"""

from __future__ import annotations


SP_BASE = 64
DIR_POS = 16804  # 0x41A4

# 14 named scratchpad slots
SP_SLOTS = [
    "Prologue",
    "Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4", "Chapter 5",
    "Chapter 6", "Chapter 7", "Chapter 8", "Chapter 9", "Chapter 10",
    "Finale Part 1", "Finale Part 2", "Postgame",
]

# Known mobile data files (any subset may exist in a given .sp)
KNOWN_DAT_FILES = [
    "boot_data.dat", "chara_set.dat", "chpk.dat", "ene.dat", "bg.dat",
    "feimg.dat", "img_etc.dat", "bip.dat", "snd.dat", "bem.dat",
    "form.bin", "capk.dat", "message.dat", "field_anm.dat",
    "btlefc_sp.dat", "layout.dat",
]

# Mobile cpk files: cpk0.dat .. cpk9.dat (variable per chapter)
CPK_NAMES = [f"cpk{i}.dat" for i in range(10)]

# Mobile mpk files: mpk0.dat .. mpk9.dat (variable per chapter)
MPK_NAMES = [f"mpk{i}.dat" for i in range(10)]

# Character → chpk entry mapping (FFD_REVERSE_ENGINEERING.md §10)
# (chara_set_index, japanese_name, romaji_name, chpk_entry, palette_index)
CHARA_TABLE = [
    (0,  "ソール",       "Sol",          13, 0),
    (1,  "アイギス",     "Aigis",        14, 1),
    (2,  "ダスク",       "Dusk",         15, 2),
    (3,  "セーラ",       "Sarah",        16, 3),
    (4,  "ナハト",       "Nacht",        17, 4),
    (5,  "アルバ",       "Alba",         18, 5),
    (6,  "ディアナ",     "Diana",        19, 6),
    (7,  "グレイブ",     "Glaive",       20, 7),
    (8,  "？？？？",     "Elgo",         21, 0),
    (9,  "バルバラ",     "Barbara",      22, None),
    (10, "フレイ",       "Frey",         23, 14),
    (11, "エドアルド",   "Eduardo",       2, 12),
    (12, "黒騎士",       "Black Knight", 25, 15),
    (13, "アルジイ",     "Argy",         26, 16),
    (14, "マトーヤ",     "Matoya",       27, 17),
    (15, "ガウェイン",   "Gawain",       28, 18),
    (16, "ジンナイ",     "Jinnai",       29, 19),
    (17, "ソピアー",     "Sophia",        3, 20),
    (18, "仮面の男",     "Masked Man",    1, 21),
    (19, "エドアルド",   "Eduardo (2)",  24, 12),
]

ELEMENTS = ["Fire", "Ice", "Lightning", "Wind",
            "Earth", "Water", "Holy", "Dark"]
STATUSES = ["Poison", "Blind", "Sleep", "Paralysis",
            "Confuse", "Silence", "Mini", "Toad",
            "Petrify", "Death", "Berserk", "Float"]
