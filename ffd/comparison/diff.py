"""Diff primitives shared by the ComparisonTab and the --compare CLI.

Two modes:
    diff_dicts(m, a, hide_identical=True) -> [DiffRow, ...]
        Semantic diff: walks union of keys, flags mismatches. Bytes are
        deferred to diff_bytes so per-byte indexing stays readable.
    diff_bytes(m_bytes, a_bytes, hide_identical=True) -> [DiffRow, ...]
        Raw byte diff: one row per index, "DIFF" tag on mismatches.

DiffRow is a thin namedtuple-shaped tuple so callers can splat it
straight into a Treeview without rebuilding a record class per use.
"""

from __future__ import annotations

from typing import Any, Iterable, List, NamedTuple, Optional


_MISSING = object()


class DiffRow(NamedTuple):
    field:   str       # "name", "body[20]", "icon_r", ...
    mobile:  str       # str() of the value, or "<missing>"
    android: str
    same:    bool      # True if M and A agree


def _fmt(v: Any) -> str:
    if v is _MISSING:
        return "<missing>"
    if isinstance(v, (bytes, bytearray)):
        # Compact hex preview, full byte diff lives in diff_bytes.
        return v[:16].hex(" ") + (" ..." if len(v) > 16 else "")
    if isinstance(v, str):
        return v
    return repr(v)


def diff_dicts(m: Optional[dict], a: Optional[dict],
               *, hide_identical: bool = True,
               bytes_field: Optional[str] = "body") -> List[DiffRow]:
    """Field-by-field diff between two record dicts.

    Bytes fields are folded down to a single "same length, n bytes
    differ" summary row; the caller switches to ``diff_bytes`` to see
    the per-byte spread. This keeps the GUI diff tractable when the
    primary payload is a 54-byte blob.

    Either input may be None (deleted slot on one side); we emit
    "<missing>" rows for everything on the other side.
    """
    out: List[DiffRow] = []
    if m is None and a is None:
        return out
    keys: list = []
    seen = set()
    for src in (m, a):
        if not src:
            continue
        for k in src.keys():
            if k not in seen:
                seen.add(k); keys.append(k)
    for k in keys:
        mv = m.get(k, _MISSING) if m else _MISSING
        av = a.get(k, _MISSING) if a else _MISSING
        if isinstance(mv, (bytes, bytearray)) or isinstance(av, (bytes, bytearray)):
            mb = mv if isinstance(mv, (bytes, bytearray)) else b""
            ab = av if isinstance(av, (bytes, bytearray)) else b""
            n = max(len(mb), len(ab))
            diffs = sum(1 for i in range(n)
                        if (i < len(mb) and i < len(ab) and mb[i] != ab[i])
                        or (i >= len(mb)) or (i >= len(ab)))
            same = diffs == 0 and len(mb) == len(ab)
            row = DiffRow(
                field=f"{k} ({len(mb)}B/{len(ab)}B, {diffs} byte diff)",
                mobile=_fmt(mv) if mv is not _MISSING else "<missing>",
                android=_fmt(av) if av is not _MISSING else "<missing>",
                same=same,
            )
        else:
            same = (mv is not _MISSING and av is not _MISSING and mv == av)
            row = DiffRow(field=k, mobile=_fmt(mv), android=_fmt(av), same=same)
        if hide_identical and row.same:
            continue
        out.append(row)
    return out


def diff_bytes(m_bytes: Optional[bytes], a_bytes: Optional[bytes],
               *, hide_identical: bool = True,
               prefix: str = "byte") -> List[DiffRow]:
    """Per-byte diff. Emits one row per index in the union of lengths.

    ``prefix`` is what the field column reads as -- "byte" for a raw
    blob, or "body" when comparing a decoded record's body sub-field.
    """
    m_bytes = m_bytes or b""
    a_bytes = a_bytes or b""
    n = max(len(m_bytes), len(a_bytes))
    out: List[DiffRow] = []
    for i in range(n):
        mv = m_bytes[i] if i < len(m_bytes) else _MISSING
        av = a_bytes[i] if i < len(a_bytes) else _MISSING
        same = (mv is not _MISSING and av is not _MISSING and mv == av)
        if hide_identical and same:
            continue
        out.append(DiffRow(
            field=f"{prefix}[{i}]",
            mobile=("0x%02x" % mv) if mv is not _MISSING else "<missing>",
            android=("0x%02x" % av) if av is not _MISSING else "<missing>",
            same=same,
        ))
    return out


def summarise_diff(rows: Iterable[DiffRow]) -> str:
    rows = list(rows)
    n_diff = sum(1 for r in rows if not r.same)
    n_same = sum(1 for r in rows if r.same)
    return f"{n_diff} differ / {n_same} match (of {len(rows)} shown)"
