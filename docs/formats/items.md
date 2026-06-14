# Format: Items

*Audit 2026-06-10; body fields re-verified 2026-06-13 from `LoadItemData`. Parser: `ffd/items/parser.py`. (Not in the original requested doc list — added because items are their own decoded table.)*

## Records — HIGH

boot_data Mobile **§4** (BE pointer), Android **§5** (LE pointer). Shared namedesc layout: u16 count; per record 0xff sentinel (deleted slot) OR pstr name + pstr desc + **54-byte body**. 640 records. Potion (id 420): byte-identical name+desc cross-platform; 51/54 body bytes identical (delta surfaced by ComparisonTab `register_items`).

History (Incorrect→fixed 2026-05-22): the legacy Mobile parser passed a *section index* where the helper wanted a *byte offset* (read §1 magic instead of §4 items) and assumed a 50-byte body — garbage from record 1 on.

## Body fields

*Offsets re-verified 2026-06-13 from the engine's own deserializer
`GameClass::LoadItemData` (libjniproxy.so_new.c @149955) + combat consumers.*

- off 0 `item_type` — HIGH: 0 consumable/key, 1–15 weapon classes, 16 shield, 17–19 head, 20–22 body, 23 hands/accessory (verified against 640 names).
- off 1–4 `price` — **HIGH**: BE u32 over body[1..4] (`LoadItemData` reads `CONCAT13(body[1],body[2],body[3],body[4])`). body[1] is the always-0 high byte the old parser mislabelled `equip_type`; the prior `price@2` decode was off by a byte. Confirmed by known shop prices (Potion 30 G, Hi-Potion 150 G, X-Potion 3000 G, Elixir 50000 G).
- off 5 `use_category` — HIGH (consumables): 1 = HP, 2 = MP, 3 = full, 5 = revive.
- off 32 `primary_stat` — **HIGH**: the equip stat the game actually uses — **weapon ATK** for item_type 1–15, **armor DEF** for 16–23 (struct+0 in `LoadItemData`; the weapon path reads it in `CalcMagicDmg`'s `case 8` weapon branch). Verified against the localized "ATK n"/"DEF n" descriptions: **206/209 weapons + 164/167 armor match exactly**; the ~6 mismatches are stale flavour text, i.e. the body field is *more* accurate than the description. The FFSmith bake now uses this instead of the old desc-regex. FF5-PC corroborates the offset independently: FF5's `LoadItemData` (`FUN_0046b380`) reads on-disk body[32] into the in-memory item slot at `+0x18` (same byte, same meaning).
- off 33 `accuracy` — HIGH (weapons): hit-rate (struct+2).
- Other fields (`weight`, `flags`, `element`, `status`, `hp_bonus`, …) remain MEDIUM/exploratory and are not used by the bake.
- Use-effect amount (how much HP a Potion *restores*) — still **unmapped**: it is not a literal body field (Potion's "100" appears nowhere in its body). `use_category` (body[5]) classifies the effect, but the magnitude lives in a separate effect table referenced from the use-item path — left for a follow-up.

## Multi-language

Names/descs ×6 languages from `system_message.msd` §7 (text.md).
