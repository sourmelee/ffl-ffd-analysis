"""Central data model. Every tab/viewer wires itself to a single
:class:`FFData` instance to discover loaded scratchpads, archives, and
sidecar JSONs (mc_overrides, cpk_to_mc).
"""

from .ffdata import FFData

__all__ = ["FFData"]
