from __future__ import annotations

import sys
from pathlib import Path

from interface.settings_tab_registry import CATEGORY_REPO, SettingsTabSpec

# This plugin lives in its own standalone git repo (cloned into
# cache/plugins/MayaFileBrowser/), not inside UkoreHub's own `plugins`
# package tree, so sibling files can't be reached via `plugins.repo_internal...`
# — make this folder importable by its own bare module names instead (same
# convention as cache/plugins/maya_launcher/plugin.py).
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from settings_page import MayaFileBrowserSettingsPage, migrate_legacy_data

# Technical id — kept as "ukore_browser" even after the folder/display rename
# to MayaFileBrowser, since it's the key already stored in existing repos'
# required_plugin_ids and Repo.plugin_data (and in maya_launcher_env_bridge's
# contributions/labels dicts). Changing it would silently un-enable this
# plugin for every repo that already opted in and orphan their saved
# repo_hidden_root_tabs data.
TOOL_ID = "ukore_browser"
TOOL_LABEL = "Maya File Browser"
# Convention-only string match with cache/plugins/maya_launcher/plugin.py
# — both resolve to the same active Project's plugin_data via
# ProjectPluginConfigStore, no coupling API needed. See that plugin's README
# for the full "contributions"/"labels" shape this writes into.
MAYA_ENV_BRIDGE_PLUGIN_ID = "maya_launcher_env_bridge"
ANY_VERSION = "*"


def register(api) -> None:
    migrate_legacy_data(api)
    tool_root = Path(__file__).resolve().parent

    bridge = api.project_plugin_config_store(MAYA_ENV_BRIDGE_PLUGIN_ID)
    if bridge is None:
        return
    contributions = bridge.get("contributions", {})
    contributions[TOOL_ID] = {
        # api.app_root is contributed too so `import core.storage.metadata_store` /
        # `core.vcs.paths` resolves inside Maya's Python — that's how this tool's
        # vendored core/repo_context.py talks to UkoreHub's own Project/Repo model to
        # find the active repo root.
        "PYTHONPATH": {ANY_VERSION: [str(tool_root / "maya-scripts"), str(api.app_root)]},
    }
    bridge.set("contributions", contributions)
    labels = bridge.get("labels", {})
    labels[TOOL_ID] = TOOL_LABEL
    bridge.set("labels", labels)

    api.register_settings_tab(
        SettingsTabSpec(
            key=TOOL_ID,
            label=TOOL_LABEL,
            order=124,
            page_factory=lambda: MayaFileBrowserSettingsPage(api=api),
            on_activated=lambda page: page.refresh(),
            category=CATEGORY_REPO,
        )
    )
