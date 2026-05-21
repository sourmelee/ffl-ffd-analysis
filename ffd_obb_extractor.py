"""Backwards-compat shim. The real module is now ``ffd.containers.obb``.

External scripts doing ``import ffd_obb_extractor`` continue to work via
this alias; new code should import from ``ffd.containers.obb`` directly.
"""

from ffd.containers.obb import *  # noqa: F401,F403
from ffd.containers.obb import (  # re-export the names the original surface used
    is_ffd_obb_path, load_obb_as_dict,
    decode_icp, is_icp_payload, convert_for_proper_mode,
    sanitize_filepath,
)
