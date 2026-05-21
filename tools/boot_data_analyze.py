"""
Boot Data analyzer for FFD/FFL — decode the section TOC.

Mobile (Big-Endian) and Android (Little-Endian) both use the same TOC:
boot_data starts with an array of u32 offsets where section[i] = boot[u32(i*4) : u32((i+1)*4)].
The last entry in the TOC is the end-of-file (= section[N-1].end).

Mobile section identities (derived from class_20.java in Decompiled_Java_Classes):
  0  method_951(§0)    string table (field_932/field_934) — u16 count, then pairs of pascal strings
  1  method_938(§4)    class_6[]  records  (u16 count)
  2  method_945(§8)    class_3[]  records  (u16 count)
  3  method_943(§12)   class_14[] records  (u16 count, parallel int[]/bool[] arrays)
  4  method_936(§32)   class_13[] records  (u16 count; reads from offset 32, i.e. section 8 — see below)
  5  method_941(§20)   class_8[]  records  (u16 count)
  6  method_947(§24)   class_11[] records  (u16 count)
  7  (§28 start)       field_994 constants/lookup buffer (start)
  8  (§32 end)         field_994 constants/lookup buffer (end)
  9  method_1117(§36)  variable-width pack table (4 hdr bytes + field_1134[0..3])
 10  method_940(§40)   raw -> field_1042
 11  method_1134(§44)  int[][] tables (u8 count + array of int[]s)
 12  method_1143(§48)  preload-pack table  (4 hdr bytes + field_1138[0..3] + var-int packs)
 13  method_940(§52)   raw -> field_1075
 14  method_940(§56)   raw -> (singleton or small buffer)
 15..20  method_940(§60..§80)  raw -> field_1041/1043/1044/1045/1046/1047

NOTE: Android probably has fewer sections — likely 16 (indices 0..15).
"""
from __future__ import annotations
import os, sys, struct, argparse
from pathlib import Path

# -----------------------------------------------------------------
# Reader primitives
# -----------------------------------------------------------------
def u32_le(b, o): return struct.unpack_from("<I", b, o)[0]
def u32_be(b, o): return struct.unpack_from(">I", b, o)[0]
def u16_le(b, o): return struct.unpack_from("<H", b, o)[0]
def u16_be(b, o): return struct.unpack_from(">H", b, o)[0]

# -----------------------------------------------------------------
# TOC parser
# -----------------------------------------------------------------
def parse_toc(buf: bytes, endian: str = "le"):
    """
    Returns list of (start, end) tuples, one per section.

    Method_940 in Mobile reads section[i] = buf[u32(i*4) : u32((i+1)*4)].
    The TOC is a packed array of monotonically non-decreasing u32 offsets, the
    LAST of which equals the file size (end-of-section-N-1 terminator).

    Walk u32 entries until we read one equal to file size — that's the terminator.
    (Section[0] data may overlap with the trailing TOC bytes; that's fine — it just
    means section[0] is unused or stores metadata pointing at later sections.)
    """
    rd = u32_le if endian == "le" else u32_be
    n = len(buf)

    offs = []
    i = 0
    prev = -1
    while i + 4 <= n:
        v = rd(buf, i)
        if v < prev or v > n:
            break
        offs.append(v)
        i += 4
        if v == n:               # hit the file-size terminator
            break
        prev = v
    sections = [(offs[k], offs[k+1]) for k in range(len(offs) - 1)]
    return sections, offs

# -----------------------------------------------------------------
# Section preview helpers
# -----------------------------------------------------------------
def hex_preview(b: bytes, n: int = 32) -> str:
    return b[:n].hex(' ')

def looks_like_pascal_string_table(sec: bytes) -> bool:
    """heuristic: starts with u16_BE count, then pascal strings"""
    if len(sec) < 4:
        return False
    n = u16_be(sec, 0)
    if not (1 <= n <= 2000):
        return False
    p = 2
    for _ in range(min(n, 3)):
        if p >= len(sec): return False
        L = sec[p]
        if L == 0 or L > 64: return False
        p += 1 + L
        if p > len(sec): return False
    return True

def try_decode_pascal_table(sec: bytes, max_show: int = 6, encoding: str = "shift_jis"):
    """Decode initial entries of a pascal-string-pairs table (Mobile §0 layout)."""
    out = []
    try:
        n = u16_be(sec, 0)
        p = 2
        for i in range(min(n, max_show)):
            L = sec[p]; p += 1
            s = sec[p:p+L].decode(encoding, errors="replace")
            p += L
            out.append(s)
        return n, out
    except Exception as e:
        return None, [f"<decode error: {e}>"]

def try_decode_preload_pack(sec: bytes):
    """
    method_1143 layout (Mobile §48 = Android §48 for preload mc-id packs):
       offset 0..3   : 4 ignored bytes? (4 method_1030 calls)
       offset 4..7   : field_1138[0..3] (u8s)
       Then for each of field_1138[3] packs, a count of `field_1138[0]`-wide ints,
       and each entry uses var-width reads from field_1138[1] and field_1138[2].
    Toolkit experiments showed the Android header is 2 bytes (count?), then 12 packs × 16 bytes.
    Let's decode using both interpretations and see which makes sense.
    """
    # Interp A: 4 hdr bytes + field_1138[4] u8 hdr + variable
    if len(sec) < 8:
        return None
    hdr = list(sec[:8])
    n_packs = sec[7]
    return {
        "interp_method_1143_hdr": hdr,
        "n_packs_field_1138_3": n_packs,
        "size": len(sec),
    }

# Mapping section index -> (label, preview_fn)
SECTION_LABELS = {
    0:  ("Pascal string table (mob/spell names?)",   "string_table"),
    1:  ("class_6[] records",                        "records"),
    2:  ("class_3[] records",                        "records"),
    3:  ("class_14[] records",                       "records"),
    4:  ("class_13[] records",                       "records"),
    5:  ("class_8[] records",                        "records"),
    6:  ("class_11[] records",                       "records"),
    7:  ("field_994 (constants buffer, start)",      "raw"),
    8:  ("field_994 (constants buffer, end)",        "raw"),
    9:  ("method_1117 — variable-width pack table",  "preload"),
    10: ("raw -> field_1042",                        "raw"),
    11: ("method_1134 — int[][] tables",             "preload"),
    12: ("method_1143 — preload mc-id pack table",   "preload"),
    13: ("raw -> field_1075",                        "raw"),
    14: ("raw -> field_? (Android-truncated?)",      "raw"),
    15: ("raw -> field_1041",                        "raw"),
}

def analyze(path: Path, endian: str = "le", verbose: bool = True):
    buf = path.read_bytes()
    print(f"=== {path} ===")
    print(f"  size: {len(buf)} bytes,  endian: {endian.upper()}")
    sections, offs = parse_toc(buf, endian)
    print(f"  TOC entries: {len(offs)} ({len(sections)} sections + 1 terminator)")
    print(f"  TOC ends at offset {len(offs)*4}")
    print()
    print(f"  {'idx':>3}  {'start':>8}  {'end':>8}  {'size':>8}  label")
    print(f"  {'---':>3}  {'-----':>8}  {'---':>8}  {'----':>8}  -----")
    for i, (s, e) in enumerate(sections):
        label, kind = SECTION_LABELS.get(i, ("(unknown)", "raw"))
        print(f"  {i:>3}  {s:>8}  {e:>8}  {e-s:>8}  {label}")
        if not verbose: continue
        sec = buf[s:e]
        print(f"        hex[0..32]: {hex_preview(sec, 32)}")
        if kind == "string_table" and looks_like_pascal_string_table(sec):
            n, sample = try_decode_pascal_table(sec)
            print(f"        decoded as pascal table:  count={n}  sample={sample}")
        elif kind == "preload":
            print(f"        preload analysis: {try_decode_preload_pack(sec)}")
    print()
    return sections, offs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", help="boot_data.dat files to analyze")
    ap.add_argument("--endian", default="auto", choices=["auto", "le", "be"])
    args = ap.parse_args()

    defaults = [
        Path("D:/FFD/cowork/Java Analysis Final Fantasy Legemensions/Android/proper_obb/boot_data.dat"),
    ]
    paths = [Path(p) for p in args.paths] if args.paths else defaults

    for p in paths:
        if not p.exists():
            print(f"missing: {p}")
            continue
        endian = args.endian
        if endian == "auto":
            # Probe: first u32 LE should be < file size; if both are < size, prefer LE (Android)
            buf = p.read_bytes()
            le0, be0 = u32_le(buf, 0), u32_be(buf, 0)
            n = len(buf)
            if be0 <= n and le0 > n: endian = "be"
            elif le0 <= n and be0 > n: endian = "le"
            else:
                # Tie-breaker: BE is Mobile, LE is Android. Look for high zero bytes.
                endian = "le" if buf[3] == 0 and buf[7] == 0 else "be"
        analyze(p, endian=endian)
