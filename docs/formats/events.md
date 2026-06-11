# Format: Event Scripts

*Audit 2026-06-10. Parsers: `ffd/events/{opcodes,android,mobile}.py`. Execution semantics: `Engine/docs/systems/event_vm.md` + `scripting.md`. Sources: `FieldClass::MoveScript` (c:125488/139119), `MoveEventScript` (c:138937), `ScriptIf` (c:134322); Mobile `class_16.method_785` (l:11586).*

## Shared command encoding — HIGH

Both platforms store each command as a **length-prefixed packet**: `u8 len; script[0]=opcode; script[1..len-1]=operands`. Operands are **big-endian** (`GetBuffToWord/GetBuffToLong`). Opcode space 0x00..0xAB with gaps; **96 opcodes catalogued** in `EVENT_SCRIPT_OPCODES` (name, advisory fmt, desc with `[Mobile]`/`[Android]` tags). The fmt string is for pretty-printing only — `len` is the source of truth.

## Android event pack — HIGH

```
u32-BE EDO (event data offset); [4..EDO+3] palette/scene info
u8 event_count; then events back-to-back:
  0x3f-byte fixed header: id u16-BE @+0 · type @+0x07 · boot @+0x08
                          appear block @+0x09..0x27 (31 B, CheckEventAppear)
                          rect w/h (header bytes 4/5; CheckRangeEvent)
                          img u16-BE @+0x2b · variant @+0x2d
  u16-BE script_count; script_count length-prefixed scripts
```
Common events live in **map 10000** (named by `field_constant.dat` @0x8d; `FieldClass::LoadCommonEvent` c:96813), byte-identical in all 15 groups, 26 routines: 0x104 move-map, 0x103 spawn, 0x101 chapter change→prologue battle, 0x107 system-flag reset, 0x114–0x116 party management, 0x117 full heal…

## Mobile event region — HIGH

Lives in the map-chunk tail after tile + attribute data; the true offset is **reconstructed** from header `field_356` flags (`_mobile_true_event_offset`) — not stored. Per-NPC script tables (`parse_mobile_event_region`).

## Execution-critical opcode semantics (RE'd 0.7.24–0.7.25, HIGH)

- Block advance registry (`this+0xf438`): 0/1 jump, 3 fall-through, 4 end.
- `0x3d ScriptIf` = **if-NOT-goto** (two GetReference operands, compare op, target block; jumps on FAIL).
- `0x3f`/`0x40` = jump / random-jump to block indices. `0x3c` = choice (value→block pairs; cancel→next block). `0x57` = end.
- `0x41 MapChange` = five BE words **map, layer, x, y, dir** with a per-operand var-indirection mask (all 15 real uses fully indirect). x/y were once mis-slotted — fixed 0.7.25.
- `0x66` = **CallEvent(id, startBlock)** — the old "SetEntityAction action 0x04 = warp" reading was an artifact of id 0x104 being the shared move-map routine (Incorrect → corrected 0.7.25).
- `0x6b BulkSetVars` sub2 writes (key,val) into var bank 2 — the door-warp preamble (var0=map, 2=x, 3=y, 4=dir consumed by 0x104's 0x41).
- `0x03/0x04` set variable/flag with calc-op/bank semantics; `0x00` SetMessage, `0x01` ScriptSentence (cinematic text).
- Boot conditions: 0 auto, 1 talk, 4/5 parallel-while-appear, 6 range-in step, 7 range-in always (fires on load), 8 confirm-in-rect; **2/3 hypothesized step variants, unconfirmed**.
- **Spawn position can select story branches** (HIGH, found via a live bug 2026-06-10): m0 places adjacent 1-tile boot-7 dispatchers — (1,1) = light-side prologue (23 scripts → m101 chain), (2,1) = dark-side/Nacht intro (11 scripts → m1500 chain). Getting the map-default spawn wrong by one tile plays a different chapter's intro. Engines must apply the FFM header spawn *before* any center-fallback (FFSmith `loadInto` had this order swapped; fixed).

## Hypotheses / open

- Choice option *value* = message id of the choice line (works in practice; the real text source unconfirmed).
- ~~`0x50 ScriptEncount` operand layout~~ **DECODED 2026-06-10** (`FieldClass::ScriptEncount` c:120371): seven (indirect-flag u8, BE u16) pairs at offsets (1,2),(4,5),(7,8),(10,0xb),(0xd,0xe),(0x10,0x11),(0x13,0x14) = formation id, battle-bg id, bg variant, battle-condition 1–3 (flag table DAT_00418f94 — values unread), battle BGM, BGM-compare (p4==p5 → "keep BGM" flag), behavior flags (bit0 clear → cond-flag 0x10, bit1 → result-flag 2). Implemented in FFSmith (VM pause → formation battle → script resume; result via GetReference target 8). Still open within 0x50: the exact meaning of the condition-flag table values and `bsc.dat` battle scripts.
- Page register (`+0xe474`) full semantics; `0x32` wait timing; NPC-move op family parameters (catalogued, not semantically decoded); fade/palette ops.
