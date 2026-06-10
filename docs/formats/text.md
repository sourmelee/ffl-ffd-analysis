# Format: Text & Messages

*Audit 2026-06-10. Parsers: `ffd/text/{parser,system_message}.py`; bake: `_read_msg_bank`/`_bake_messages` in `ffsmith_bake.py`.*

## `message.dat` (Mobile) — HIGH
Multi-section, length-prefixed **Shift-JIS**. Section labels in `MESSAGE_SECTION_LABELS` (Common UI, Ch1–7 Light/Dark, Cutscenes, Challenge Dungeon, …).

## `.msd` (Android) — HIGH
Same multi-section shape, **UTF-8**, 16 LE u32 section offsets (last = filesize). `parse_msd` probes the header and falls back to a flat string scan (e.g. `bem.msd`). The OBB decoder renames `bem/dbgmes/msg0..15/sysmes/system_message` payloads to `.msd` (allowlist; bytes unchanged).

## `system_message.msd` — HIGH (decoded 2026-05-22)
Master localized name/description table for every asset type. Per section: u16-BE record count; per record, per slot: u16-BE strlen + UTF-8 + NUL. **Six languages** (ja, en, fr, zh-Hans, zh-Hant, ko); description-bearing types use 12 slots (name+desc interleaved per language). Section → asset map (record counts cross-checked against boot_data tables): §5 Characters(21×6), §6 Command abilities(50×12), §7 Items(640×12), §8 Jobs(33×12), §9 Magic(512×12), §10 Passive(113×12), §13 Monsters(645×6).

## `msg{N}.msd` (field dialogue banks) — HIGH
One per story bank N (= map group, 16 banks; engine: `ReadStoryMessageData`→`SetMessageList`→`FieldClass+0x380`). String encoding: u16-**BE** length + payload + NUL terminator; per message 6 languages × 2 slots (text, speaker name); **English text = msg×12+2**. History: a u8-length misparse once suggested "slot drift" — that was a parse bug, not a format property; and an early FFSmith cut wrongly used system_message §4 as field dialogue (coincidentally coherent). Both are settled — don't relitigate.

## Baked form
`text/msg{N}.bin` (`FMSG`, English slot only) + `data/intro.bin` (`FINT`, prologue + chapter label extracted **by content** from msg0 — robust to offset drift). Speaker-name slots and the other 5 languages are parsed but not baked (engine is ASCII-only today).

## Open
- Control codes inside message strings (color/pause/name-insertion escapes) — not inventoried; FFSmith renders raw text, `_clean_message` strips minimally.
- Story-state **bank variants** (the same map group under different story states) — flagged during M4 as "resolved by the state machine," never fully verified (MEDIUM).
