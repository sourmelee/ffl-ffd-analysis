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


# ---------------------------------------------------------------------------
# Magic body field decode (HIGH confidence)
# ---------------------------------------------------------------------------
#
# Offsets traced from GameClass::LoadMagicData (libjniproxy.so_new.c @150182,
# magic struct = 0x58 bytes) and confirmed in the battle consumers:
#   body[0]  school        struct+0x10  1 = white, 2 = black (list filter +
#                          INT/MND bonus path in GetMagicUseLostValue).
#   body[6]  cost_type     struct+0x18  1/2 = spell costs MP.
#   body[7]  mp_cost       struct+0x19  base MP — CONFIRMED: the value
#                          GetMagicUseLostValue (@90534) returns as the cost.
#   body[16] effect_cat    struct+0x24  1 = HP damage, 2 = HP recovery,
#                          5..8 = status (SetMagicStatus @95336).
#   body[18] formula       struct+0x28  damage-formula selector
#                          (CalcMagicDmg switch @93146: 1/2 = magic-stat
#                          INT/MND, 3/4/5 = stat-derived, 6 = fixed, 7 = random,
#                          8 = weapon-based).
#   body[19] power         struct+0x2a  potency — CONFIRMED: iVar21 in CalcMagicDmg.
#   body[20] factor        struct+0x2c  secondary multiplier (CalcMagicDmg).
#   body[31] element       struct+0x3d  element mask fed to CalcElementPoint
#                          (1=Fire 2=Ice 4=Thunder 16=Holy ...).
# Verified by reconstructing the full table: every named spell's MP/power/element
# matches canonical FF values (Fire/Fira/Firaga = 5/10/32 MP, pow 14/40/90; the
# Cure->Curaga heal tiers; correct elements and summon affinities).

_ELEMENT_NAMES = {0: "", 1: "Fire", 2: "Ice", 4: "Thunder", 8: "Wind",
                  16: "Holy", 32: "Poison", 64: "Earth", 128: "Water"}


# effect_cat -> coarse kind used by the engine bake (0 damage / 1 heal / 2 status)
def _magic_kind(effect_cat: int) -> int:
    if effect_cat == 2:
        return 1            # HP recovery
    if effect_cat == 1:
        return 0            # HP damage
    return 2                # status / buff / special


def decode_magic_body(body: bytes) -> dict:
    """Decode the 54-byte magic body to a flat field dict (BE on both platforms)."""
    if len(body) < 32:
        return {}
    el = body[31]
    return {
        "school":     body[0],
        "cost_type":  body[6],
        "mp_cost":    body[7],
        "effect_cat": body[16],
        "formula":    body[18],
        "power":      body[19],
        "factor":     body[20],
        "element":    el,
        "element_name": _ELEMENT_NAMES.get(el, f"?{el}"),
        "kind":       _magic_kind(body[16]),
    }
