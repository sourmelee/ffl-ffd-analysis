"""Mobile -> Android asset export + Android .dat encoder (round-trip ICP).

Public surface:

* :func:`encode_icp_dat`            - PNG bytes (or Path) -> ICP-wrapped .dat bytes.
* :func:`encode_icp_directory`      - walk a folder of PNGs, write parallel .dat tree.
* :func:`export_chapter_to_android` - take a loaded .sp slot's data files and emit
                                       Android-named, 2x-upscaled PNGs for
                                       monsters/characters/tilesets.
* :func:`export_all_chapters`       - driver that loops over every loaded slot.

The ICP encoder is symmetric to :func:`ffd.containers.obb.decode_icp` --
together they form a round-trippable pair. Byte-for-byte identity with
Square Enix's original payloads is *not* guaranteed (different PNG
compressor, padding) but pixel data and engine-relevant header bytes are
preserved.
"""

from .icp import (
    encode_icp_dat,
    encode_icp_directory,
    ICPEncodeError,
)
from .exporter import (
    AndroidExportOptions,
    export_chapter_to_android,
    export_all_chapters,
)

__all__ = [
    "encode_icp_dat", "encode_icp_directory", "ICPEncodeError",
    "AndroidExportOptions", "export_chapter_to_android", "export_all_chapters",
]
