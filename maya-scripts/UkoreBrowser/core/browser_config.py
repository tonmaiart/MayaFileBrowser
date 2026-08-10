"""Per-repo recent-files persistence for UkoreBrowser.

Replaces the old single global ``~/ukore_file_browser.json`` (which mixed
recent files across every repo/project on the machine) with a file scoped to
the repo being browsed, storing paths relative to the repo root so the config
stays valid even if the workspace root's drive letter differs machine to
machine.
"""

from __future__ import annotations

import json
import os

_CONFIG_DIRNAME = ".ukorehub"
_CONFIG_FILENAME = "ukore_browser.json"


class BrowserConfig:
    def __init__(self, repo_root: str, max_recent: int = 10):
        self.repo_root = os.path.normpath(repo_root)
        self.max_recent = max_recent
        self._config_path = os.path.join(self.repo_root, _CONFIG_DIRNAME, _CONFIG_FILENAME)
        self._recent_relpaths: list[str] = self._load()

    def _load(self) -> list[str]:
        if not os.path.isfile(self._config_path):
            return []
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return list(data.get("recent_files", []))
        except Exception:
            return []

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
