"""Pure "keep only the latest version of each file" logic, extracted out of
the Qt proxy model so it can be exercised without a QAbstractItemModel."""

from __future__ import annotations

import re

RE_VERSION = re.compile(r"([_-]?v)(\d{3})", re.IGNORECASE)

ALLOWED_EXT_PATTERN = re.compile(
    r".*\.(ma|mb|blend|fbx|obj|avi|mp4|jpg|png|mov|prproj|mp3|py|json|ini|txt|tga)$",
    re.IGNORECASE,
)


def compute_latest_version_names(entries: list[tuple[str, bool]]) -> set[str]:
    """entries: (filename, is_dir) pairs for one folder's direct children.

    Returns the subset of filenames to keep when only the highest ``_vNNN``
    per base name should be shown. Directories are always kept. Files with no
    version suffix are treated as their own highest version (kept as-is).
    """
    latest: dict[str, tuple[int, str]] = {}  # base_name -> (version, filename)

    for filename, is_dir in entries:
        if is_dir:
            latest[filename.lower()] = (999999, filename)
            continue

        if not ALLOWED_EXT_PATTERN.match(filename):
            continue

        match = RE_VERSION.search(filename)
        if match:
            base_name = filename[: match.start()].rstrip("_-").lower()
            version = int(match.group(2))
        else:
            base_name = filename.lower()
            version = 999999

        old_version, _ = latest.get(base_name, (-1, ""))
        if version > old_version:
            latest[base_name] = (version, filename)

    return {name for _, name in latest.values()}
