"""Mobile vs Android comparison framework.

Phase 1 of the seamless-conversion roadmap (Mobile FFL <-> Android FFD).
This package surfaces field-level structural deltas between paired
assets, normalising endianness + text encoding first so the diff shows
real layout differences rather than byte-order noise.

Public surface:
    ASSET_KINDS                  -- registry of comparable asset types
    AssetKind                    -- dataclass describing one type
    compare_records              -- run an AssetKind against (m_idx, a_idx)
    diff_dicts / diff_bytes      -- the diff primitives the tab calls
    run_cli                      -- headless --compare driver

The registry is the extension point. Adding a new asset type = a new
AssetKind entry; the tab + CLI pick it up automatically.
"""

from .registry import AssetKind, ASSET_KINDS, compare_records, list_asset_kinds
from .diff import diff_dicts, diff_bytes, DiffRow
from .cli import run_cli

__all__ = [
    "AssetKind", "ASSET_KINDS", "compare_records", "list_asset_kinds",
    "diff_dicts", "diff_bytes", "DiffRow",
    "run_cli",
]
