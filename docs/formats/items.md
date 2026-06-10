# Format: Items

*Audit 2026-06-10. Parser: `ffd/items/parser.py`. (Not in the original requested doc list — added because items are their own decoded table.)*

## Records — HIGH

boot_data Mobile **§4** (BE pointer), Android **§5** (LE pointer). Shared namedesc layout: u16 count; per record 0xff sentinel (deleted slot) OR pstr name + pstr desc + **54-byte body**. 640 records. Potion (id 420): byte-identical name+desc cross-platform; 51/54 body bytes identical (delta surfaced by ComparisonTab `register_items`).

History (Incorrect→fixed 2026-05-22): the legacy Mobile parser passed a *section index* where the helper wanted a *byte offset* (read §1 magic instead of §4 items) and assumed a 50-byte body — garbage from record 1 on.

## Body fields

- off 0 `item_type` — HIGH: 0 consumable/key, 1–15 weapon classes, 16 shield, 17–19 head, 20–22 body, 23 hands/accessory (verified against 640 names).
- off 1 `equip_type` — always 0 (HIGH); not the category discriminator.
- price BE u32, atk/def/mag…, element/status bitmasks — decoded by `decode_item_body` per the Mobile §4 layout notes (MEDIUM: field-by-field verification is partial; the FFSmith bake sidesteps it by regex-reading ATK/DEF from descriptions).
- Use-effect encoding (what a Potion *does*) — **unmapped**; FFSmith infers effects from description text.

## Multi-language

Names/descs ×6 languages from `system_message.msd` §7 (text.md).
