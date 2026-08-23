"""Per-repo recent-files persistence for UkoreBrowser.

Replaces the old single global ``~/ukore_file_browser.json`` (which mixed
recent files across every repo/project on the machine) with a file scoped to
the repo being browsed, storing paths relative to the repo root so the config
stays valid even if the workspace root's drive letter differs machine to
machine.

Persisted under UkoreHub's own per-machine cache/ dir (via
``PublishApi.repo_paths.find_cache_dir()``), keyed by a hash of the repo
root, instead of inside the repo itself — an earlier version wrote to
``<repo_root>/.ukorehub/ukore_browser.json``, which left a stray
git-untracked file/folder inside every browsed production repo. A repo that
still has that legacy file gets it migrated in and deleted on first load.
"""

from __future__ import annotations

import hashlib
import json
import os

from PublishApi.repo_paths import find_cache_dir

_LEGACY_CONFIG_DIRNAME = ".ukorehub"
_LEGACY_CONFIG_FILENAME = "ukore_browser.json"
_CACHE_SUBDIR = os.path.join("plugins", "MayaFileBrowser", "recent")


class BrowserConfig:
    def __init__(self, repo_root: str, max_recent: int = 10):
        self.repo_root = os.path.normpath(repo_root)
        self.max_recent = max_recent
        key = hashlib.sha1(self.repo_root.encode("utf-8")).hexdigest()
        self._config_path = os.path.join(str(find_cache_dir()), _CACHE_SUBDIR, "{}.json".format(key))
        self._legacy_config_path = os.path.join(self.repo_root, _LEGACY_CONFIG_DIRNAME, _LEGACY_CONFIG_FILENAME)
        self._recent_relpaths: list[str] = self._load()

    def _load(self) -> list[str]:
        if os.path.isfile(self._config_path):
            return self._read(self._config_path)

        if os.path.isfile(self._legacy_config_path):
            recent = self._read(self._legacy_config_path)
            self._recent_relpaths = recent
            self._save()
            self._remove_legacy()
            return recent

        return []

    def _read(self, path: str) -> list[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return list(data.get("recent_files", []))
        except Exception:
            return []

    def _remove_legacy(self) -> None:
        try:
            os.remove(self._legacy_config_path)
            os.rmdir(os.path.dirname(self._legacy_config_path))
        except OSError:
            pass

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump({"recent_files": self._recent_relpaths}, f, indent=4)

    def get_recent_files(self) -> list[str]:
        """Absolute paths, most-recent first."""
        return [os.path.normpath(os.path.join(self.repo_root, rel)) for rel in self._recent_relpaths]

    def add_recent_file(self, abs_path: str) -> list[str]:
        rel = os.path.relpath(os.path.normpath(abs_path), self.repo_root)
        if rel in self._recent_relpaths:
            self._recent_relpaths.remove(rel)
        self._recent_relpaths.insert(0, rel)
        self._recent_relpaths = self._recent_relpaths[: self.max_recent]
        self._save()
        return self.get_recent_files()
