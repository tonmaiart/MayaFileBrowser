from __future__ import annotations

import sys
from pathlib import Path

from plugin_api import CATEGORY_REPO, SettingsTabSpec

# This plugin lives in its own standalone git repo (cloned into
# cache/plugins/MayaFileBrowser/), not inside UkoreHub's own `plugins`
# package tree, so sibling files can't be reached via `plugins.repo_internal...`
# — make this folder importable by its own bare module names instead (same
# convention as cache/plugins/maya_launcher/plugin.py). Named
# mayafilebrowser_settings_page.py, NOT the generic "settings_page.py" —
# cache/plugins/maya_launcher/plugin.py uses that exact same sys.path +
# bare-import convention with its OWN file also named settings_page.py;
# since both insert their folder into sys.path and both bare-import a
# module by that same generic name, whichever plugin discover_plugins()
# happens to import first claims "settings_page" in sys.modules and the
# other plugin's import silently resolves to the WRONG file (an ImportError
# for whichever symbol it was actually looking for) — confirmed this is
# exactly what broke this plugin on 2026-08-10 (maya_launcher sorts first
# under Windows' case-insensitive path ordering). Keep this filename unique
# across every cache/plugins/ plugin's own sibling modules — don't rename
# it back to something generic like "settings_page.py"/"core.py"/"utils.py".
_PLUGIN_DIR = Path(__file__).resolve().parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from mayafilebrowser_settings_page import MayaFileBrowserSettingsPage, migrate_legacy_data

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
        # maya-plug-ins/mayaFileBrowser.py — force-loaded by maya_launcher
        # alongside every other contributed Maya plug-in (see that plugin's
        # _force_load_plugin_names). Its own initializePlugin inserts a menu
        # item into MayaToolkit's existing "Ukore Studio Tool" menu rather
        # than this plugin launching itself some other way — see that
        # file's own module docstring and this plugin's README, "MayaToolkit
        # menu integration", for why this needed no edit to MayaToolkit
        # itself. tool_id "maya_toolkit" sorts before "ukore_browser"
        # alphabetically, so maya_launcher force-loads/queues MayaToolkit's
        # own menu-building plug-in first — see that section for the full
        # ordering argument and the same-menu-name convention this relies on.
        "MAYA_PLUG_IN_PATH": {ANY_VERSION: [str(tool_root / "maya-plug-ins")]},
    }
    bridge.set("contributions", contributions)
    labels = bridge.get("labels", {})
    labels[TOOL_ID] = TOOL_LABEL
    bridge.set("labels", labels)

    # Auto-import UkoreBrowser right after Maya opens a file so its
    # UkoreMenu.register_item() call (in maya-scripts/UkoreBrowser/__init__.py)
    # runs before UkoreMenu itself rebuilds the menu (order 99), same
    # convention as UkoreReferenceEditor/plugin.py — otherwise the menu item
    # doesn't appear until something else imports UkoreBrowser (e.g. the
    # Settings tab launching it once).
    hooks = bridge.get("launch_hooks", {})
    hooks[TOOL_ID] = {
        "order": 10,
        "post_open_mel": 'python("try:\\n    import UkoreBrowser\\nexcept ImportError:\\n    pass");',
    }
    bridge.set("launch_hooks", hooks)

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

