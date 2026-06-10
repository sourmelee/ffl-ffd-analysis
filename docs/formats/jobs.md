# Format: Jobs, Characters & Abilities

*Audit 2026-06-10. Parsers: `ffd/jobs/parser.py`, `ffd/characters/parser.py`, `ffd/abilities/parser.py`.*

## Jobs — HIGH (structure), MEDIUM (body fields)

boot_data Mobile **§5** (BE pointer @TOC byte 20 — a legacy comment said "section 20", that was the *byte offset*; behavior was always right), Android **§6** (LE @0x18). Record = name + desc + **126-byte body**, body BE on both. Counts: Mobile Ch1 = 31, Android = 33; Mobile is chapter-scoped with duplicate-name placeholder slots until jobs are introduced. `decode_job_body` decodes the high-confidence prefix (sprite_ow/sprite_btl, palette_ow/palette_btl, base stats); the rest exposed as `tail_uN_*` for diffing. **Per-job HP%/MP% growth multipliers presumed in here — unmapped** (blocks battle exact-match).

## `chara_set.dat` — HIGH

Same record layout both platforms (records BE on both): u16-BE count; per character: name(pstr SJIS), 2×u8, 10 skip, 5×u16-BE, u8, **6×u16-BE equipment**, 6×u8. Header differs: Mobile 12 B (3×u32-BE: records_start, sect2, filesize), Android 16 B (4×u32-LE: version=2, records_start, sect2, filesize). Mobile chapter-scoped (Ch1 = 20 recs) vs Android full roster (21). Byte-identical for the core cast; genuine rename at id 12 (グラム → 黒騎士) and Mobile placeholder 予備1 where Android has Eduardo. Decoded per-character stats job/level/STR/SPD/VIT/INT/MND (0.7.9; engine-verified via `ReadStartData`/`MEMBER_STATUS`) + CHPK field-sprite id (0.7.19). `CHARA_TABLE` (constants.py) supplies romaji names.

## Abilities (Android-only parsers) — HIGH structure

Shared namedesc decoder, differing only in TOC offset + body size: magic toc 0x08 **body 54** (same layout family as items), passive toc 0x0c body 24, command toc 0x10 body 25. Counts: 512 / 113 / 50. Body field semantics largely unmapped. The baked `spells.bin` is a **hardcoded 11-spell list** (`CAST` in `_bake_menu_data`) with tier-approximation MP/power and real names from system_message §9 — placeholder-grade; the magic body (54 B, same family as items) awaits decoding. Mobile equivalents exist in the Mobile TOC (magic at §1 per the comparison-stub note — Unverified).

## Multi-language names

All of the above splice display names from `system_message.msd` (§5 chars, §6 command, §7 items, §8 jobs, §9 magic, §10 passive, §13 monsters) — see text.md.
