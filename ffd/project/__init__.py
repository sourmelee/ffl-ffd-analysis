"""Project save/load — turn an :class:`~ffd.data.ffdata.FFData` snapshot
into a single ``.ffdproj`` JSON file (and back) so the toolkit can boot
straight into a configured workspace instead of re-loading every asset
through the File menu.

See :mod:`ffd.project.serialize` for the file format and resolver logic.
"""

from __future__ import annotations

from .serialize import (
    PROJECT_FORMAT,
    PROJECT_VERSION,
    PROJECT_EXT,
    CONFIG_FILENAME,
    RECENT_LIMIT,
    ProjectLoadResult,
    save_project,
    load_project,
    apply_project,
    cleanup_bundle_temp_dir,
    config_path,
    load_config,
    save_config,
    remember_project,
    forget_project,
    get_recent_projects,
    get_last_project,
)

__all__ = [
    "PROJECT_FORMAT",
    "PROJECT_VERSION",
    "PROJECT_EXT",
    "CONFIG_FILENAME",
    "RECENT_LIMIT",
    "ProjectLoadResult",
    "save_project",
    "load_project",
    "apply_project",
    "cleanup_bundle_temp_dir",
    "config_path",
    "load_config",
    "save_config",
    "remember_project",
    "forget_project",
    "get_recent_projects",
    "get_last_project",
]
