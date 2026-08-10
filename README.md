# plugins/repo_internal/UkoreBrowser/

Maya-side asset browser — a standalone tool launched from inside Maya (not a
UkoreHub UI panel). Extracted out of `add-on/MayaToolkit` on 2026-07-13;
folded into `plugins/repo_internal/maya_launcher/UkoreBrowser/` as one of 7 nested
tools during the 2026-07-14 consolidation; split back out to this top-level
plugin on 2026-07-19 (see `plugins/repo_internal/maya_launcher/README.md` for why).
Still depends on MayaToolkit's `tmlib`/`UkoreMaya` packages **and** on
`plugins/repo_internal/PublishApi` staying on PYTHONPATH (see "External
dependencies" below), so both must stay enabled alongside this plugin for
it to keep working.

## Shape

- `manifest.json` / `plugin.py` — standard plugin registration (see
  `plugins/README.md`). `plugin.py` contributes PYTHONPATH entries to
  `plugins/repo_internal/maya_launcher/`'s shared `maya_launcher_env_bridge`
  `PluginConfigStore` (same convention as
  `plugins/repo_internal/MayaToolkit/plugin.py`) — no file opener, since this
  tool is launched explicitly from a Maya menu, not triggered by opening a
  file. No direct import relationship with `maya_launcher` — just the
  shared `PluginConfigStore` id convention. **Also** registers a
  `CATEGORY_REPO` Settings tab (`settings_page.py`, see below) — a
  UkoreHub-side page, not Maya-side, unlike everything else `plugin.py`
  does.
- `settings_page.py` — `UkoreBrowserSettingsPage`: the "Repo Studio
  Setting" tab (Repository Setting popup > Ukore Browser) — unlike
  MayaPublisher's per-ticket "which pipeline connection does this ticket
  publish into" picker (chosen entirely in Maya via Manage Tickets...),
  this is a **multi-select** checkbox list (one row per active-repo
  pipeline connection) letting a studio admin hide specific connections
  from the root-tab row without removing the pipeline connection itself —
  UkoreBrowser genuinely wants to show several root tabs at once, unlike
  MayaPublisher which needs exactly one destination per ticket. Stores the
  *hidden* set (opt-out), not the shown set, in this repo's own
  `core/models.py` `Repo.plugin_data["ukore_browser"]`, key
  `"repo_hidden_root_tabs"` (`data/projects/<project_id>.json` — moved off
  the old standalone `data/plugins/core/ukore_browser.json` blob;
  `migrate_legacy_data(api)` in this same file does the one-time cutover).
  **Not to be confused with**
  `<browsed repo root>/.ukorehub/ukore_browser.json` (`browser_config.py`'s
  recent-files cache, below) — same base filename, completely different
  location and purpose: that one lives inside whichever production repo is
  being browsed, unrelated to this repo-hidden-tabs setting.
  Read back on the Maya side by `core/repo_context.py`'s
  `get_pipeline_root_tabs()`.
- `maya-scripts/UkoreBrowser/` — the Maya-side Python package, contributed
  to `PYTHONPATH` so `import UkoreBrowser` works inside Maya:
  - `interface.py` — **do not delete**: a one-line backward-compat shim
    (`from UkoreBrowser.ui.main_window import MainWindow`).
    `tmlib.core.File.launch("UkoreBrowser")` (called from
    `UkoreMaya/core/menu_utils.py:browser()` and the auto-launch hook in
    `UkoreMaya/core/function.py`) hardcodes the import path
    `UkoreBrowser.interface.MainWindow` — this file exists purely to keep
    that contract working without touching either caller.
  - `core/` — Qt-free logic:
    - `repo_context.py` — auto-detects the browse root from UkoreHub's own
      active repo, delegating to `plugins/repo_internal/PublishApi`'s
      `repo_paths` module (`get_active_repo()`, `get_pipeline_refs()`,
      `resolve_ref()`) for the *active* repo — same source of truth
      `MayaPublisher` builds its publish-root resolution on. Its own
      `_get_repo(project_id, repo_id)` still constructs `core.store.MetadataStore`
      directly (same off-disk convention, Maya's Python has no `PluginAPI`)
      for `_get_hidden_root_tab_keys()`/`_get_pipeline_refs_for()`, since
      those need an *explicit* repo — see their own docstrings for why.
      Falls back to Maya's current workspace dir if there's no active repo.
    - `browser_config.py` — recent-files persistence, stored **relative to
      the repo root** under `<repo_root>/.ukorehub/ukore_browser.json` (one
      file per repo, not a single global file mixing every repo/project).
    - `version_filter.py` — pure "keep only the latest `_vNNN`" logic.
    - `file_ops.py` — plain filesystem ops (create/rename/delete/open in
      explorer).
    - `maya_ops.py` — the only file that touches `maya.cmds` /
      `UkoreMaya.core` (reference import, scene open/save, workspace set).
  - `ui/` — PySide widgets: `main_window.py` (`MainWindow`, wiring only —
    delegates all real work to `core/`), `file_model.py` (the extension /
    latest-version filter proxy model), `popup.py`, `menus.py`.
  - `ui.ui` — Qt Designer layout. Loaded by
    `tmlib.ui.interface_template.ToolkitWindow` via
    `importlib.import_module("UkoreBrowser")` + `__path__[0]/ui.ui` — this
    is why `MainWindow.__init__` hardcodes `super().__init__("UkoreBrowser")`
    instead of deriving the toolkit name from `__file__` (it now lives one
    level deeper, under `ui/`, than the original single-file version did).
  - `template/` — `template.ma`/`template.blend`, copied when creating a new
    scene file from the browser's "+" menu.

## External dependencies (MayaToolkit + PublishApi)

This plugin does **not** vendor `tmlib` or `UkoreMaya` — both packages
still live at `plugins/repo_internal/MayaToolkit/maya-scripts/{tmlib,UkoreMaya}/` and are
imported by name (`tmlib.ui.interface_template`, `tmlib.module.PySide`,
`UkoreMaya.core.template_ui`, `UkoreMaya.core.menu_utils`,
`UkoreMaya.core.function`). It also doesn't vendor its own repo/pipeline
path-resolution logic anymore as of 2026-07-19 — `core/repo_context.py`
imports `PublishApi.repo_paths` instead (see below). Both of these only
resolve because `plugins/repo_internal/MayaToolkit/plugin.py` and
`plugins/repo_internal/PublishApi/plugin.py` each contribute their own
`maya-scripts/` folder to the same `maya_launcher_env_bridge` PYTHONPATH
bridge this plugin uses — **if either is ever disabled for a repo (via
Repository Setting > Enable Plugin, which `plugins/repo_internal/maya_launcher/`
gates its bridge merge on), UkoreBrowser
breaks.** Don't "fix" this by vendoring `tmlib`/`UkoreMaya`/`PublishApi`'s
logic in here without a deliberate decision to do so; see
`plugins/repo_internal/maya_launcher/README.md` for the general shape of the
bridge convention every Maya tool plugin here relies on.

## Root-path detection

`core/repo_context.get_root_path()` is the entry point for `self.root_path`
(what the Miller-column project/class/scene/shot/element lists and the
file-system model are rooted at): (1) the active UkoreHub repo (via
`PublishApi.repo_paths.get_active_repo()` — see "External dependencies"
above) if set; (2) `cmds.workspace(q=True, rd=True)`. There is no more
hardcoded drive path — don't reintroduce one. **Deliberately not** the
current scene file's folder — that used to be priority 1, but rooting the
Miller columns at the scene's own (usually leaf, subfolder-less) folder
left all 5 of them permanently empty.

**Session-locked, not live, as of 2026-08-04**: `tmlib.core.File.launch`
builds a brand-new `MainWindow()` on every open, and
`PublishApi.repo_paths.get_active_repo()` reads UkoreHub's
`local_config.json` fresh off disk — so without locking, changing the
active repo in UkoreHub would silently retarget the *next* time
UkoreBrowser is opened (including via the auto-launch hook in
`UkoreMaya/core/function.py`), which reads as the path changing out from
under you mid-session. `repo_context._get_locked_active_repo()` resolves
the active repo once per Maya session and reuses that result — both
`get_active_repo_path()` and `get_pipeline_root_tabs()` below go through
it — so whichever repo UkoreBrowser first opened against stays the browse
root for the rest of that Maya session regardless of later repo switches
in UkoreHub. Relies on `UkoreBrowser.core.repo_context` never itself being
`importlib.reload`'d (`File.launch` only reloads the `UkoreBrowser.interface`
shim), so the module-level cache survives every reopen for the life of
the Maya process and resets on the next Maya launch. If UkoreHub had no
active repo yet when Maya started, the lock stays open (every call
re-resolves) until one is actually found. The explicit root-tab buttons
below (`_switch_root`) are unaffected — they're a deliberate user action,
not the auto-detected default.

Where the browser lands on open (`self.current_browse_path`) is separate:
`get_initial_browse_path(root_path)` returns the current scene file's
folder if one is open and it's actually inside `root_path`, else
`root_path` itself — so you still start out where you're working, without
that affecting what the columns are rooted at.

## Pipeline root tabs

`core/repo_context.get_pipeline_root_tabs()` calls
`PublishApi.repo_paths.resolve_ref()`/`get_custom_path()` (same source of
truth `MayaPublisher` resolves its publish root through — see
`plugins/repo_internal/PublishApi/README.md`)
— but **not** that module's own `get_pipeline_refs()`, since that takes no
repo argument and always resolves whatever is *currently* live in
UkoreHub, which would bypass the session lock above. Instead,
`repo_context._get_pipeline_refs_for(project_id, repo_id)` reads the same
`project_editor.json` `pipeline_inputs` entry directly, keyed by the
locked project/repo instead of the live one. Returns the
session-locked active repo (same lock as `get_root_path()` above — see
"Root-path detection") plus
every repo it has connected to via "Connect Pipeline Input Path..." in
Project Editor, each resolved down to its specific declared `CustomPath`
rather than just the target repo's root (e.g. `RigPublish`'s "Character"
`CustomPath`, not all of `RigPublish`), as `{"label", "path"}` dicts —
minus whichever refs a studio admin has hidden via this plugin's own Repo
Studio Setting tab (`settings_page.py`, `_get_hidden_root_tab_keys`, see
above).
`ui/main_window.py`'s `_build_root_tabs()` turns this into a row of
checkable buttons inserted at row 0 of the central grid layout (unused by
`ui.ui`, whose own rows start at 1) — clicking one calls `_switch_root(path)`,
which re-points `root_path`, the recent-files `BrowserConfig`, the
`QFileSystemModel`, and the Miller columns at that repo, same shape
`__init__` uses to set things up the first time. No-ops entirely (no tab
row added) if there's no active repo.

## Working on this plugin

Read/edit only files under this folder for a UkoreBrowser-only task — see
`plugins/README.md`'s plugin-scoping note (and the `ukorehub-plugin` skill)
for why sibling plugins shouldn't be opened unless the task explicitly
touches them.
# MayaFileBrowser
