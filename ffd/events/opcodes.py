"""Event-script opcode database + per-block disassembler.

Key: opcode byte. Value: dict with mnemonic, description, operand
format, platform.

``fmt`` string operand grammar (one char per slot, starting at args[0])::

    'B' u8 / 'b' i8  / 'W' u16-BE / 'w' i16-BE / 'L' u32-BE / 'l' i32-BE
    '*' remaining bytes (raw)
    '.' single byte (alias of B) used for filler/unused slots

Sources:

* Android: ``Decomp/Functions/libjniproxy_c.c`` ``FieldClass::MoveScript``
  switch (line 125488), ``GetBuffToWord/GetBuffToLong = big-endian``.
* Mobile: ``Decompiled_Java_Classes/class_16.java`` ``method_785`` dispatcher
  (line 11586) over the same per-NPC length-prefixed blocks.

Both platforms store each event command as one length-prefixed packet,
so the operand length is exactly ``(block_len - 1)``. The ``fmt``
string is advisory (for pretty-printing), not the source of truth for
length.
"""

from __future__ import annotations


EVENT_SCRIPT_OPCODES = {
    0x00: {"name": "SetMessage",          "fmt": "WBWBBB*", "desc": "Show dialogue text box (msg_id, flags, wait bit)"},
    0x01: {"name": "ScriptSentence",      "fmt": "B*",     "desc": "Advance/chain message sentence"},
    0x02: {"name": "SetScrollMode",       "fmt": "BW",     "desc": "Set message text scroll mode + delay (BE word)"},
    0x03: {"name": "SetReferenceVariable","fmt": "BBWWWWWL","desc": "var[w3][w5] = var OP ref(w7,w9,w11,L13); b1=calc op (0=set,1..8=+,-,*,/,%,&,|,^), b2=indirection mask"},
    0x04: {"name": "SetReferenceFlag",    "fmt": "BWWW",   "desc": "Flag write: mask@1, then BE words type,bit,control (0=clear,1=set,2=toggle); types 0-4 field banks, 5=global"},
    0x05: {"name": "SetLightingMode",     "fmt": "B*",     "desc": "Map lighting toggle [Mobile]"},
    0x06: {"name": "SetDarkness",         "fmt": "BB",     "desc": "Fade darkness on/off with timer"},
    0x07: {"name": "AddMoney",            "fmt": "BL",     "desc": "Add/subtract money (BE long) [Android]"},
    0x08: {"name": "AddItem",             "fmt": "BWB",    "desc": "Add/remove item (item_id BE, count) [Android]"},
    0x09: {"name": "EquipItem",           "fmt": "BBW",    "desc": "Equip or unequip item on member"},
    0x0b: {"name": "ChangeJob",           "fmt": "BBBB",   "desc": "Change party member's active job"},
    0x0d: {"name": "LearnForgetAbility",  "fmt": "BBWB",   "desc": "Learn or forget ability for member"},
    0x0e: {"name": "LearnForgetMagic",    "fmt": "BBWB",   "desc": "Learn or forget magic spell"},
    0x10: {"name": "SetMemberHP",         "fmt": "BBWB",   "desc": "Set/add HP for member(s)"},
    0x11: {"name": "SetMemberMP",         "fmt": "BBWB",   "desc": "Set/add MP for member(s)"},
    0x12: {"name": "SetMemberCondition",  "fmt": "BBLB",   "desc": "Set/clear status condition bits (BE long)"},
    0x13: {"name": "FullHeal",            "fmt": "b",      "desc": "Full heal member (b=-1 = all)"},
    0x14: {"name": "SetPartyFormation",   "fmt": "B*",     "desc": "Initialise party entry list"},
    0x16: {"name": "OpenPartyMenu",       "fmt": "*",      "desc": "Open party selection screen"},
    0x17: {"name": "SetPartyLineup",      "fmt": "BBBBBBBBBB","desc": "Set full party lineup (8 slot pairs + 2 trailers)"},
    0x18: {"name": "AddRemovePartyMember","fmt": "BBBBBB", "desc": "Add or remove individual party member"},
    0x1a: {"name": "SetCharaAppearance",  "fmt": "BBBB*",  "desc": "Set character sprite and map appearance"},
    0x1b: {"name": "CameraFollow",        "fmt": "BB",     "desc": "Camera follows NPC by event_id"},
    0x1f: {"name": "SetCharaSpeed",       "fmt": "BB",     "desc": "Set NPC walk speed (0xFF = reset)"},
    0x20: {"name": "TeleportNPC",         "fmt": "BBBBBBBBB", "desc": "Teleport NPC (id, dir, x, y, dx, dy, …)"},
    0x21: {"name": "SetNPCVisible",       "fmt": "Bb",     "desc": "Show/hide NPC by event_id (flag 0x400)"},
    0x22: {"name": "SetNPCOffsetX",       "fmt": "BW",     "desc": "NPC pixel X-offset (BE word)"},
    0x23: {"name": "SetNPCOffsetY",       "fmt": "BW",     "desc": "NPC pixel Y-offset (BE word)"},
    0x24: {"name": "SetNPCPassable",      "fmt": "Bb",     "desc": "NPC collision on/off (flag 0x40)"},
    0x25: {"name": "AddEffect",           "fmt": "BBBBBBBBBBBBBBBBB", "desc": "Spawn VFX (full record)"},
    0x26: {"name": "RemoveEffect",        "fmt": "B",      "desc": "Remove VFX by observe_id"},
    0x27: {"name": "SetPaletteChange",    "fmt": "BBBBBBBBBB","desc": "Palette/colour transition effect"},
    0x28: {"name": "UpdatePaletteChange", "fmt": "BB",     "desc": "Update palette change (mode 0)"},
    0x29: {"name": "StopPaletteChange",   "fmt": "BB",     "desc": "Stop palette change (mode 1)"},
    0x2a: {"name": "SetFade",             "fmt": "BBBBBBBBB", "desc": "Screen fade (target, mode, RGBA, duration)"},
    0x2b: {"name": "SetBGColor",          "fmt": "BBBB",   "desc": "Set background colour (RGB + fade dur)"},
    0x2c: {"name": "ScreenShake",         "fmt": "BBBB",   "desc": "Screen shake effect"},
    0x2e: {"name": "SetTileAnim",         "fmt": "BBBBB",  "desc": "Set tile animation keyframe"},
    0x2f: {"name": "FillMapRect",         "fmt": "BBBBBBBB","desc": "Fill tile rectangle in map layer"},
    0x30: {"name": "SetSkipMode",         "fmt": "B",      "desc": "Enable/disable message auto-skip"},
    0x31: {"name": "ResetMessageMode",    "fmt": "*",      "desc": "Reset message advance mode"},
    0x32: {"name": "WaitTrigger",         "fmt": "W",      "desc": "Wait for event/trigger index (BE word)"},
    0x34: {"name": "BGMFade",             "fmt": "BB",     "desc": "Fade BGM (type, duration)"},
    0x35: {"name": "PlayBGM",             "fmt": "BW",     "desc": "Play background music (track BE word)"},
    0x36: {"name": "PlaySE",              "fmt": "BW",     "desc": "Play sound effect (sfx BE word)"},
    0x37: {"name": "StopBGM",             "fmt": "*",      "desc": "Stop background music"},
    0x38: {"name": "PlaySEDefault",       "fmt": "*",      "desc": "Play SE (no ID, default)"},
    0x39: {"name": "SetAudioField1",      "fmt": "B",      "desc": "Set audio control byte A"},
    0x3a: {"name": "SetAudioField2",      "fmt": "B",      "desc": "Set audio control byte B"},
    0x3b: {"name": "YesNoDialog",         "fmt": "WWBBBB", "desc": "Yes/no choice dialog"},
    0x3c: {"name": "MultiChoiceDialog",   "fmt": "BB*",    "desc": "Choice select: flags, N, then N×(value BE16, target block BE16); cancel→next block"},
    0x3d: {"name": "ScriptIf",            "fmt": "B*",     "desc": "If-NOT-goto: mask@1, left ref(b3,w4,w6,L8), right ref(b13,w14,w16,L18), op w@22, target block w@24; jumps when condition FAILS"},
    0x3f: {"name": "Jump",                "fmt": "W",      "desc": "Unconditional jump to script BLOCK index (BE word)"},
    0x40: {"name": "RandomJump",          "fmt": "B*",     "desc": "Jump to block w@(2+2*Rand(N)) of the N-entry list"},
    0x41: {"name": "MapChange",           "fmt": "B*",     "desc": "Warp: mask@1 then 5 BE words map,x,y,dir,sub (mask bit=operand is var index)"},
    0x42: {"name": "ChangeViewMode",      "fmt": "B*",     "desc": "Toggle field/cinematic camera"},
    0x43: {"name": "SetOblique",          "fmt": "BBBB",   "desc": "Set oblique / isometric camera angle"},
    0x4f: {"name": "OpenShop",            "fmt": "BB",     "desc": "Open shop menu"},
    0x50: {"name": "StartBattle",         "fmt": "WBBB",   "desc": "Trigger battle encounter (BE word + flags)"},
    0x51: {"name": "OpenItemBag",         "fmt": "B",      "desc": "Open item bag / equipment menu"},
    0x52: {"name": "ReadString",          "fmt": "*",      "desc": "Read string from script buffer"},
    0x53: {"name": "SetConnectCertify",   "fmt": "B*",     "desc": "Online network cert check [Android]"},
    0x54: {"name": "WaitBattle",          "fmt": "*",      "desc": "Yield to battle result state [Android]"},
    0x55: {"name": "MovePlayer",          "fmt": "BBBB",   "desc": "Move player character to position"},
    0x57: {"name": "ScriptEnd",           "fmt": "*",      "desc": "End script / break execution"},
    0x5a: {"name": "ChangeNPCSprite",     "fmt": "BBBBBBBB","desc": "Change NPC sprite (source_mode 0..3)"},
    0x5e: {"name": "DungeonReset",        "fmt": "B",      "desc": "Reset dungeon floor"},
    0x61: {"name": "SetConnect",          "fmt": "BBB*",   "desc": "Set network connect state [Android]"},
    0x64: {"name": "SetMapFlags",         "fmt": "BBB",    "desc": "Set/clear map environment flags"},
    0x66: {"name": "SetEntityAction",     "fmt": "BB*",    "desc": "Set entity action (byte[4]: 0x04=move-map/warp, 0x03=spawn NPC)"},
    0x67: {"name": "WaitForEvent",        "fmt": "B",      "desc": "Wait for game event to complete"},
    0x68: {"name": "StartEntityAction",   "fmt": "BBBB*",  "desc": "Start NPC action sequence"},
    0x69: {"name": "WaitEntityAction",    "fmt": "B",      "desc": "Wait for NPC action to finish"},
    0x6b: {"name": "BulkSetVars",         "fmt": "BB*",    "desc": "Bulk-assign vars (sub@b[1]: 2=script-var bank); warp idiom sets var0=map,2=x,3=y,4=dir"},
    0x6c: {"name": "NameInput",           "fmt": "WWBB",   "desc": "Open name-entry dialog"},
    0x6d: {"name": "LearnForgetJob",      "fmt": "BB",     "desc": "Learn or forget job class"},
    0x6e: {"name": "SetTimer",            "fmt": "BW",     "desc": "Set timer/counter field"},
    0x6f: {"name": "MergePartyData",      "fmt": "B*",     "desc": "Merge/combine party data [Android]"},
    0x70: {"name": "SetAppFlags",         "fmt": "BB",     "desc": "Set/clear app-level flags"},
    0x71: {"name": "SetPartyConfig",      "fmt": "BBB",    "desc": "Set party slot count or item bag number"},
    0x72: {"name": "SetMapZoom",          "fmt": "BBBB",   "desc": "Set map zoom level"},
    0x73: {"name": "AddJP",               "fmt": "BBBB",   "desc": "Add Job Points to member(s)"},
    0x74: {"name": "SetEncountEffect",    "fmt": "B",      "desc": "Set encounter transition effect"},
    0x75: {"name": "PlayJingle",          "fmt": "BW",     "desc": "Play jingle sound"},
    0x76: {"name": "ShowHelpDialog",      "fmt": "BBB",    "desc": "Show help/tutorial dialog"},
    0x77: {"name": "OpenTextBox",         "fmt": "BB",     "desc": "Open message text box"},
    0x78: {"name": "WaitMessage",         "fmt": "B",      "desc": "Yield until message is dismissed"},
    0x79: {"name": "SetNPCName",          "fmt": "BB",     "desc": "Set NPC display name from message data"},
    0x7a: {"name": "SetCharaFlags",       "fmt": "BBBBBBB*","desc": "Set/clear NPC flag bits"},
    0x7b: {"name": "SetPartyMemory",      "fmt": "BB*",    "desc": "Set party memory/inheritance param"},
    0x7c: {"name": "SetMemberLevel",      "fmt": "BB*",    "desc": "Set/adjust party member level"},
    0x96: {"name": "AnimConfig",          "fmt": "BBBBBBBBBBB","desc": "Camera/animation config (float args) [Android]"},
    0xa0: {"name": "AddButton",           "fmt": "BBBBBBBBBBBBBB","desc": "Add script UI button [Android]"},
    0xa1: {"name": "RemoveButton",        "fmt": "B",      "desc": "Remove script UI button [Android]"},
    0xaa: {"name": "OpenSpecialMenu",     "fmt": "BB*",    "desc": "Open special menu [Android]"},
    0xab: {"name": "SetCharaParam",       "fmt": "BBBB*",  "desc": "Set character data parameter [Android]"},
}


def _decode_event_operands(opcode: int, args: bytes):
    """
    Pretty-print a packed operand byte string using the per-opcode `fmt`
    grammar from EVENT_SCRIPT_OPCODES. Returns a list of human-readable
    field strings like ['B=0x05', 'W=0x0103', 'L=0x00000010']; '*' eats
    the remaining bytes as a single hex blob.
    """
    info = EVENT_SCRIPT_OPCODES.get(opcode)
    fmt = (info or {}).get("fmt", "*")
    out, p = [], 0
    n = len(args)
    for ch in fmt:
        if p >= n:
            break
        if ch in "B.":
            out.append(f"B=0x{args[p]:02x}");                              p += 1
        elif ch == "b":
            v = args[p] if args[p] < 0x80 else args[p] - 0x100
            out.append(f"b={v}");                                          p += 1
        elif ch == "W":
            if p + 2 > n: break
            out.append(f"W=0x{(args[p]<<8)|args[p+1]:04x}");               p += 2
        elif ch == "w":
            if p + 2 > n: break
            u = (args[p] << 8) | args[p+1]
            s = u if u < 0x8000 else u - 0x10000
            out.append(f"w={s}");                                          p += 2
        elif ch == "L":
            if p + 4 > n: break
            v = (args[p]<<24) | (args[p+1]<<16) | (args[p+2]<<8) | args[p+3]
            out.append(f"L=0x{v:08x}");                                    p += 4
        elif ch == "l":
            if p + 4 > n: break
            u = (args[p]<<24) | (args[p+1]<<16) | (args[p+2]<<8) | args[p+3]
            s = u if u < 0x80000000 else u - 0x100000000
            out.append(f"l={s}");                                          p += 4
        elif ch == "*":
            out.append("*=" + args[p:].hex())
            p = n
            break
    # Trailing bytes not covered by fmt
    if p < n:
        out.append("+" + args[p:].hex())
    return out


def disassemble_script_block(data: bytes, version: str = "mobile") -> str:
    """
    Disassemble a single script block (one length-prefixed event command).
    data[0] = opcode, data[1..] = raw argument bytes.

    Format used by both Mobile (class_16.method_785 / per-NPC array) and
    Android (FieldClass::MoveScript / LoadEventData length-prefixed list).
    """
    if not data:
        return "  (empty block)"
    opcode = data[0] & 0xFF
    args   = data[1:]
    info   = EVENT_SCRIPT_OPCODES.get(opcode)
    name   = (info or {}).get("name", "???")
    arg_hex = " ".join(f"{b:02x}" for b in args) if args else "(no args)"

    decoded = _decode_event_operands(opcode, args) if info else []
    detail = ("  ; " + ", ".join(decoded)) if decoded else ""

    # Add the highest-value semantic notes on top of generic field decode
    try:
        if opcode == 0x00 and len(args) >= 5:
            msg_id = (args[0] << 8) | args[1]
            detail += f"  ; msg_id={msg_id}"
        elif opcode in (0x35, 0x36, 0x75) and len(args) >= 3:
            track_id = (args[1] << 8) | args[2]
            detail += f"  ; track={track_id}"
        elif opcode == 0x3f and len(args) >= 2:
            offset = (args[0] << 8) | args[1]
            detail += f"  ; -> block {offset}"
        elif opcode == 0x40 and len(args) >= 3:
            n = args[0]
            tgts = [(args[1 + 2*i] << 8) | args[2 + 2*i]
                    for i in range(n) if 2 + 2*i < len(args)]
            detail += f"  ; random -> blocks {tgts}"
        elif opcode == 0x41 and len(args) >= 11:
            mask = args[0]
            ws = [(args[1 + 2*i] << 8) | args[2 + 2*i] for i in range(5)]
            ind = ["var" if (mask >> i) & 1 else "" for i in range(5)]
            detail += (f"  ; map={ind[0]}{ws[0]} x={ind[1]}{ws[1]} y={ind[2]}{ws[2]}"
                       f" dir={ind[3]}{ws[3]} sub={ind[4]}{ws[4]}")
        elif opcode == 0x3d and len(args) >= 0x19:
            # ScriptIf (FieldClass::ScriptIf): jump to target when cond FAILS.
            b = bytes([opcode]) + bytes(args)
            mask = b[1]
            lt, lp, lk = b[3], (b[4] << 8) | b[5], (b[6] << 8) | b[7]
            li = (b[8] << 24) | (b[9] << 16) | (b[10] << 8) | b[11]
            rt, rp, rk = b[0xd], (b[0xe] << 8) | b[0xf], (b[0x10] << 8) | b[0x11]
            ri = (b[0x12] << 24) | (b[0x13] << 16) | (b[0x14] << 8) | b[0x15]
            op = (b[0x16] << 8) | b[0x17]
            tgt = (b[0x18] << 8) | b[0x19]
            OPS = {0: "==", 1: "!=", 2: ">", 3: "<", 4: ">=", 5: "<=",
                   6: "&", 7: "!both", 8: "!="}
            REF = {1: "flag", 2: "bool", 3: "var", 4: "chara", 5: "party",
                   6: "event", 7: "item", 8: "battle", 9: "imm", 10: "imm",
                   0xb: "etc", 0xe: "mappos", 0xf: "rand", 0x11: "map"}

            def _ref(t, p2, k, i):
                nm = REF.get(t, f"t{t}")
                if t in (9, 10):
                    return str(i)
                return f"{nm}({p2},{k},{i})"
            detail += (f"  ; ifnot {_ref(lt, lp, lk, li)} {OPS.get(op, '?')} "
                       f"{_ref(rt, rp, rk, ri)} -> block {tgt}")
        elif opcode == 0x3c and len(args) >= 2:
            n = args[1]
            pairs = [((args[2 + 4*i] << 8) | args[3 + 4*i],
                      (args[4 + 4*i] << 8) | args[5 + 4*i])
                     for i in range(n) if 5 + 4*i < len(args)]
            detail += f"  ; choices (value->block): {pairs}"
    except (IndexError, TypeError):
        pass

    return f"  {opcode:02X}  {name:<26} | {arg_hex}{detail}"
