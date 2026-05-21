"""File container loaders: ``.sp`` scratchpads, ZIP-style archives,
folders, and ``.jam`` manifests. Every loader returns the same shape —
an ``OrderedDict`` mapping ``filename -> bytes`` — which is what every
viewer in the toolkit expects.
"""

from .sp import parse_sp
from .archive import load_zip_container, load_folder_as_archive
from .jam import load_jam_manifest
from .obb import (
    is_ffd_obb_path, load_obb_as_dict,
    decode_icp, is_icp_payload, convert_for_proper_mode,
)

__all__ = [
    "parse_sp",
    "load_zip_container",
    "load_folder_as_archive",
    "load_jam_manifest",
    "is_ffd_obb_path", "load_obb_as_dict", "decode_icp", "is_icp_payload", "convert_for_proper_mode",
]
