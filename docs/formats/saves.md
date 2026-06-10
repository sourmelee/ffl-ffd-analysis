# Format: Saves

*Audit 2026-06-10.*

## Original game save (`save.bin`) — UNDECODED

Known surface only (MEDIUM, from function reading): `GameClass::SaveGameData`/`SetGameData` write ~15 KB per slot containing full party `MEMBER_STATUS` (records at `GameClass + idx*0x4c4 + 0x1a180`), inventory, gil, position, flags. No byte-level layout has been recovered; no parser exists. **This is the canonical RE gap if save-compat with the real game ever matters.**

## FFSmith `save.dat` (`FSAV`) — HIGH (engine-defined, fully specified)

Writer/reader: `Engine/src/main.cpp` (writeSave/readSave). Little-endian.

| Ver | Added | Date |
|---|---|---|
| 1 | map key (pstr16), x u16, y u16, facing u8, sprite img i32 | M7 |
| 2 | party count u8 × {charIdx, hp, mp as i32}; inventory u16 × {id, count i32}; gil i32 | 2026-06-08 |
| 3 | +equip i32×6 per member (225 B total round-trip verified) | 2026-06-08 |
| 4 | +level, exp i32×2 per member | 2026-06-08 |
| 5 | +script-state blob: u32 len + SST payload | 2026-06-10 |

Reader accepts any version ≥ its features; writer always emits 5.

## SST blob (script state) — HIGH

`"SST" + 0x01`, then fixed-order LE u32 dump: f0[4], f2[3], f5, f1[8][16], f3[8][16], f4[8], v0[128], v2[512], v3[24], v4[8][8], page, msgBank, storyState, sys5, sys7, sys6, timer → **4,032 bytes**. Deserializer requires exact size+magic. Verified by `--vmtest` round-trip and an independent Python parser (session-side, not committed).

## Notes

- Older docs mention FSAV v2/v3 as current — see Engine contradiction report #4.
- FSAV stores `charIdx` (index into chars.bin), so saves are **bundle-dependent**: rebaking with a different character table silently corrupts party identity (no hash check — LOW-priority hardening idea: store the manifest source hash).
