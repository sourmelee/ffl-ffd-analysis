"""Android event-pack parser + disassembler + scanner.

Engine sources (line numbers refer to ``Decomp/Functions/libjniproxy_c.c``):

* ``FieldClass::LoadCommonEvent``  (line  96813)
* ``FieldClass::LoadEventData``    (line 106753)

Container layout (one .dat pack per scene)::

    [0..3]               u32-BE  event_data_offset (EDO)
    [4..EDO+3]           other section (palette / scene info — not events)
    [EDO+4]              u8      event_count
    [EDO+5..]            event records, one after another

Per-event record::

    [+0x00..0x06]   event header bytes (id u16-BE at +0, flags at +7..+8, …)
    [+0x07]         u8 type (chara | object | trigger…)
    [+0x08]         u8 boot condition
    [+0x2b..0x2c]   u16-BE chara image id
    [+0x2d]         u8 chara image variant
    [+0x00..0x3e]   0x3f bytes total fixed header
    [+0x3f..0x40]   u16-BE script_count
    [+0x41..]       script_count entries, each:
                      u8 len; len bytes (script[0]=opcode, script[1..]=operands)

After the last script the next event begins immediately.
"""

from __future__ import annotations

import struct

from ..binary import be_u32
from .opcodes import disassemble_script_block


def parse_android_event_pack(buf: bytes) -> dict:
    """
    Parse an Android event-pack buffer (typically pulled from a .dat in
    the OBB).  Returns:

      {
        "edo": int,                    # event_data_offset (u32-BE at file[0])
        "event_count": int,            # number of events declared
        "events": [
            {
              "header": bytes(0x3f),   # raw 63-byte event header
              "event_id":   int,       # header u16-BE @ +0
              "type":       int,       # header u8 @ +7
              "boot":       int,       # header u8 @ +8
              "chara_img":  int,       # header u16-BE @ +0x2b
              "chara_var":  int,       # header u8 @ +0x2d
              "scripts":   [bytes,...] # length-prefix-stripped command bytes
            }, …
        ],
        "parse_error": str or None,
      }

    Returns parse_error if the buffer doesn't fit the expected layout.
    """
    if len(buf) < 5:
        return {"edo": 0, "event_count": 0, "events": [],
                "parse_error": "buffer too small"}
    try:
        edo = be_u32(buf, 0)
        if edo + 5 > len(buf):
            return {"edo": edo, "event_count": 0, "events": [],
                    "parse_error": f"event_data_offset {edo} out of range"}
        event_count = buf[edo + 4] & 0xFF
        pos = edo + 5
        events = []
        for _ in range(event_count):
            if pos + 0x41 > len(buf):
                return {"edo": edo, "event_count": event_count, "events": events,
                        "parse_error": f"truncated event header at +0x{pos:x}"}
            header = bytes(buf[pos:pos + 0x3f])
            n_scripts = (buf[pos + 0x3f] << 8) | buf[pos + 0x40]
            sp = pos + 0x41
            scripts = []
            for _ in range(n_scripts):
                if sp >= len(buf):
                    break
                slen = buf[sp] & 0xFF
                sp += 1
                if sp + slen > len(buf):
                    scripts.append(bytes(buf[sp:]))
                    sp = len(buf)
                    break
                scripts.append(bytes(buf[sp:sp + slen]))
                sp += slen
            events.append({
                "header":    header,
                "event_id":  (header[0] << 8) | header[1],
                "type":      header[7] & 0xFF,
                "boot":      header[8] & 0xFF,
                "chara_img": (header[0x2b] << 8) | header[0x2c],
                "chara_var": header[0x2d] & 0xFF,
                "scripts":   scripts,
            })
            pos = sp
        return {"edo": edo, "event_count": event_count, "events": events,
                "parse_error": None}
    except (IndexError, struct.error) as e:
        return {"edo": 0, "event_count": 0, "events": [],
                "parse_error": f"parse exception: {e}"}


def disassemble_android_event_pack(buf: bytes) -> str:
    """
    Multi-event disassembly of a whole Android event pack (as found inside
    the OBB).  Same output shape as disassemble_event_region() for Mobile.
    """
    r = parse_android_event_pack(buf)
    lines = []
    if r["parse_error"]:
        lines.append(f"[Parse error: {r['parse_error']}]")
    lines.append(f"Event pack — event_data_offset=0x{r['edo']:x}, "
                 f"event_count={r['event_count']}")
    lines.append("")
    for i, ev in enumerate(r["events"]):
        lines.append(
            f"=== Event[{i}]  id=0x{ev['event_id']:04x}  type={ev['type']}  "
            f"boot=0x{ev['boot']:02x}  chara_img={ev['chara_img']}/"
            f"{ev['chara_var']}  scripts={len(ev['scripts'])} ==="
        )
        for j, s in enumerate(ev["scripts"]):
            if not s:
                lines.append(f"    [{j}] (empty)")
                continue
            lines.append(disassemble_script_block(s, version="android") +
                         f"    ; ev[{i}] script[{j}] ({len(s)}B)")
        lines.append("")
    return "\n".join(lines)


def scan_android_event_packs(obb_files: dict) -> list:
    """
    Walk an OBB and yield a list of files whose contents pass the Android
    event-pack header check (u32-BE EDO < file len, event_count > 0,
    first event header looks sensible).  Each entry is:
        {"name": str, "blob": bytes, "info": parse_result_dict}

    This is a heuristic discovery pass — we don't have a global manifest
    that says "these specific files are event packs", so we sniff.
    """
    out = []
    if not obb_files:
        return out
    for name, blob in obb_files.items():
        if not blob or len(blob) < 0x50:
            continue
        try:
            edo = be_u32(blob, 0)
        except Exception:
            continue
        # Plausibility: EDO must point into the file, event_count must be
        # nonzero & reasonable, and the first event header must have a
        # nonzero chara/scripts count or known type byte.
        if edo == 0 or edo + 5 > len(blob):
            continue
        ec = blob[edo + 4] & 0xFF
        if ec == 0 or ec > 200:
            continue
        info = parse_android_event_pack(blob)
        if info["parse_error"] or not info["events"]:
            continue
        # Drop false positives: at least one event must hold ≥1 script.
        if not any(ev["scripts"] for ev in info["events"]):
            continue
        out.append({"name": name, "blob": blob, "info": info})
    out.sort(key=lambda d: d["name"].lower())
    return out
