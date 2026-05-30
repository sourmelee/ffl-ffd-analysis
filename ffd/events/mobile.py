"""Mobile (FOMA) event-script extractor + disassembler.

Mobile event scripts live in the tail of each map chunk, after both
tile-index data and the optional attribute layers. The true event
offset is not stored explicitly — it has to be reconstructed from the
chunk header's field_356 flags. See :func:`_mobile_true_event_offset`.
"""

from __future__ import annotations

import struct

from .opcodes import disassemble_script_block


def map_event_script_region(parsed_map: dict, raw_chunk: bytes):
    """
    Given a parsed mobile/Android map dict (with 'end_off' and tile region
    info) and the raw chunk bytes, return the slice of bytes that contains
    the event script — i.e. everything after the tile data ends.

    For mobile maps, parsed dict has:
        end_off, w, h, name_len, name, tile_start, bytes_per_tile
    For Android maps, parsed dict has:
        end_off, w, h, tile_start, n_layers
    Both: event scripts live from end_off → end of chunk.
    """
    end = parsed_map.get("end_off", 0)
    if end <= 0 or end >= len(raw_chunk):
        return b""
    return raw_chunk[end:]


def _mobile_true_event_offset(chunk: bytes) -> int:
    """
    Compute the byte offset within a Mobile map chunk where the event
    region (trigger zones + NPC data) begins. This is AFTER the tile
    index data AND the attribute-layer data.

    The toolkit's parse_mobile_map_chunk.tile_end only covers tile index
    bytes; attribute bytes (field_347) follow and must be skipped too.

    Attribute data: h × (w//2 + 1) bytes per active attribute layer.
    Attribute layer 0 is present when field_356 bit 16 is set.
    Attribute layer 1 is present when field_356 bit 17 is set.
    """
    if len(chunk) < 38:
        return -1
    w = chunk[9]
    h = chunk[10]
    if w == 0 or h == 0 or w > 200 or h > 200:
        return -1
    field_356 = struct.unpack(">I", chunk[30:34])[0]
    ts0_id = chunk[5]
    ts1_id = chunk[6]
    name_len = chunk[34]
    tile_start = 35 + name_len

    layer0 = bool(field_356 & 1)
    layer1 = bool(field_356 & 2)
    n_ts = (1 if ts0_id != 0xFF else 0) + (1 if ts1_id != 0xFF else 0)
    if layer0 and layer1:
        bpt = 3
    elif n_ts == 2:
        bpt = 2
    else:
        bpt = 1

    tile_idx_end = tile_start + w * h * bpt

    # Attribute data (field_347): present when bits 16 or 17 of field_356
    attr_size = 0
    for bit in (16, 17):
        if field_356 & (1 << bit):
            attr_size += h * (w // 2 + 1)

    return tile_idx_end + attr_size


def parse_mobile_event_region(chunk: bytes) -> dict:
    """
    Parse the event script region from a raw Mobile map chunk (as extracted
    by scan_mobile_mpk_chunks — no 4-byte size prefix).

    Returns a dict:
      "triggers": list of dicts
          {"action_id": int, "type": int, "x": int, "y": int,
           "x_end": int, "y_end": int}
      "npcs": list of dicts
          {"record": bytes(60), "scripts": list of bytes,
           "event_id": int, "npc_type": int}
      "event_offset": int  (byte offset where event region starts)
      "parse_error": str or None
    """
    event_start = _mobile_true_event_offset(chunk)
    if event_start < 0:
        return {"triggers": [], "npcs": [], "event_offset": 0,
                "parse_error": "bad map header"}
    if event_start >= len(chunk):
        return {"triggers": [], "npcs": [], "event_offset": event_start,
                "parse_error": "no event region (chunk ends at tile data)"}

    pos = event_start

    # --- Trigger zones ---
    try:
        n_triggers = chunk[pos] & 0xFF
        pos += 1
        triggers = []
        for _ in range(n_triggers):
            if pos + 7 > len(chunk):
                break
            action_id = (chunk[pos] << 8) | chunk[pos + 1]
            t_type    = chunk[pos + 2] & 0xFF
            x_raw     = chunk[pos + 3] & 0xFF
            y_raw     = chunk[pos + 4] & 0xFF
            w_raw     = chunk[pos + 5] & 0xFF
            h_raw     = chunk[pos + 6] & 0xFF
            triggers.append({
                "action_id": action_id,
                "type":      t_type,
                "x":         x_raw,
                "y":         y_raw,
                "x_end":     max(0, x_raw + w_raw - 1),
                "y_end":     max(0, y_raw + h_raw - 1),
            })
            pos += 7
    except (IndexError, struct.error) as e:
        return {"triggers": [], "npcs": [], "event_offset": event_start,
                "parse_error": f"trigger parse error: {e}"}

    # --- NPC records + scripts ---
    try:
        if pos >= len(chunk):
            return {"triggers": triggers, "npcs": [], "event_offset": event_start,
                    "parse_error": "EOF before NPC count"}
        n_npcs = chunk[pos] & 0xFF
        pos += 1

        npcs = []
        for i in range(n_npcs):
            if pos + 60 > len(chunk):
                break
            record = bytes(chunk[pos:pos + 60])
            pos += 60

            if pos + 2 > len(chunk):
                break
            n_scripts = (chunk[pos] << 8) | chunk[pos + 1]
            pos += 2

            scripts = []
            for j in range(n_scripts):
                if pos >= len(chunk):
                    break
                slen = chunk[pos] & 0xFF
                pos += 1
                if pos + slen > len(chunk):
                    scripts.append(bytes(chunk[pos:]))
                    pos = len(chunk)
                    break
                scripts.append(bytes(chunk[pos:pos + slen]))
                pos += slen

            # Decode known NPC record fields
            event_id  = (record[0] << 8) | record[1]  # u16-BE at [0:2]
            npc_type  = record[7] & 0xFF               # type byte at [7]

            npcs.append({
                "record":   record,
                "scripts":  scripts,
                "event_id": event_id,
                "npc_type": npc_type,
            })

        return {
            "triggers":     triggers,
            "npcs":         npcs,
            "event_offset": event_start,
            "parse_error":  None,
        }

    except (IndexError, struct.error) as e:
        return {"triggers": triggers, "npcs": [], "event_offset": event_start,
                "parse_error": f"NPC parse error: {e}"}


def disassemble_event_region(chunk: bytes) -> str:
    """
    Full human-readable disassembly of a Mobile map chunk's event region.
    Returns a string suitable for display in a text widget.
    """
    result = parse_mobile_event_region(chunk)

    lines = []
    if result["parse_error"]:
        lines.append(f"[Parse error: {result['parse_error']}]")

    lines.append(f"Event region @ +0x{result['event_offset']:04x}")
    lines.append("")

    # Trigger zones
    triggers = result["triggers"]
    lines.append(f"=== Trigger Zones ({len(triggers)}) ===")
    for i, t in enumerate(triggers):
        lines.append(
            f"  [{i}] action_id=0x{t['action_id']:04x}  type={t['type']}"
            f"  x={t['x']}..{t['x_end']}  y={t['y']}..{t['y_end']}"
        )
    if not triggers:
        lines.append("  (none)")
    lines.append("")

    # NPC records
    npcs = result["npcs"]
    lines.append(f"=== NPCs ({len(npcs)}) ===")
    for i, npc in enumerate(npcs):
        lines.append(
            f"\n  NPC[{i}]  event_id=0x{npc['event_id']:04x}"
            f"  type={npc['npc_type']}"
            f"  scripts={len(npc['scripts'])}"
        )
        for j, script in enumerate(npc["scripts"]):
            if not script:
                lines.append(f"    script[{j}]: (empty)")
                continue
            # Note: the dict-unpack `name, _ = EVENT_SCRIPT_OPCODES.get(...)`
            # was a long-standing bug — values in EVENT_SCRIPT_OPCODES are
            # 3-key dicts ({name, fmt, desc}), not 2-tuples, so any known
            # opcode would raise "too many values to unpack (expected 2)".
            # The unpacked `name` was never used; disassemble_script_block
            # handles the mnemonic itself.
            opcode = script[0] & 0xFF  # noqa: F841 (kept for clarity)
            lines.append(
                disassemble_script_block(script) +
                f"    ; npc[{i}] script[{j}] ({len(script)}B)"
            )
    if not npcs:
        lines.append("  (none)")

    return "\n".join(lines)
