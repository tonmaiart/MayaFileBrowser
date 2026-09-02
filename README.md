# cache/plugins/MayaFileBrowser/

Maya-side asset browser — a standalone tool launched from inside Maya (not a
UkoreHub UI panel). Extracted out of `add-on/MayaToolkit` on 2026-07-13;
folded into `plugins/repo_internal/maya_launcher/UkoreBrowser/` as one of 7 nested
tools during the 2026-07-14 consolidation; split back out to its own
top-level plugin on 2026-07-19 (see `cache/plugins/maya_launcher/README.md`
for why); moved out to its own standalone git clone under `cache/plugins/`
once every `repo_internal` plugin made that same move (see
`UkoreHubDev`'s `plugins/README.md`). **Renamed from `UkoreBrowser` to
`MayaFileBrowser` on 2026-08-10** to avoid confusion with other
similarly-named, unrelated things (see `UkoreHubDev`'s
`developer/app/GLOSSARY.md`, "'UkoreBrowser' vs. 'Browser Links'") — the
folder, manifest `name`, and settings-tab label all changed, but the
manifest/technical `id` stays `"ukore_browser"` (see `plugin.py`) to avoid
silently un-enabling this plugin for every repo that already opted in, and
the Maya-side package name under `maya-scripts/UkoreBrowser/` stays
`UkoreBrowser` too — see "Maya-scripts package name" below for why that one
can't be renamed at all. Still depends on MayaToolkit's `tmlib`/`UkoreMaya`
packages **and** on `cache/plugins/PublishApi` staying on PYTHONPATH (see
"External dependencies" below), so both must stay enabled alongside this
plugin for it to keep working.

## Shape

- `manifest.json` / `plugin.py` — standard plugin registration (see
  `plugins/README.md`). Since this plugin lives in its own standalone git
  clone rather than inside UkoreHub's own `plugins` package tree,
  `plugin.py` adds its own folder to `sys.path` and imports its sibling
  `mayafilebrowser_settings_page.py` by bare module name (same sys.path
  convention as `cache/plugins/maya_launcher/plugin.py` — **but not the
  same filename**: that plugin's own sibling file is also named
  `settings_page.py`, and since both plugins insert their own folder into
  `sys.path` and bare-import a same-named module, whichever one
  `discover_plugins()` imports first claims that name in `sys.modules` and
  the other's import silently resolves to the wrong file. This broke this
  plugin outright on 2026-08-10 — see `mayafilebrowser_settings_page.py`'s
  own top-of-file note in `plugin.py` for the fuller story. Keep this
  filename unique across every `cache/plugins/` plugin's sibling modules)
  instead of a `plugins.repo_internal...`
  dotted import. It also contributes a PYTHONPATH (`maya-scripts/`) entry
  to `cache/plugins/maya_launcher/`'s shared `maya_launcher_env_bridge`
  `PluginConfigStore` (same convention as
  `cache/plugins/MayaToolkit/plugin.py`) — no file opener, since this
  tool is launched from a Maya menu, not triggered by opening a
  file. No direct import relationship with `maya_launcher` — just the
  shared `PluginConfigStore` id convention. **Also** registers a
  `CATEGORY_REPO` Settings tab (`mayafilebrowser_settings_page.py`, see below) — a
  UkoreHub-side page, not Maya-side, unlike everything else `plugin.py`
  does.
- `mayafilebrowser_settings_page.py` — `MayaFileBrowserSettingsPage`: the "Repo Studio
  Setting" tab (Repository Setting popup > Maya File Browser). As of
  2026-09-02 this loads `MayaFileBrowserSettingsWindow.ui` at runtime via
  `QUiLoader` (same pattern `project_editor`'s settings pages use) instead
  of building the widget tree in code — see "Extra tab paths (settings UI
  rewrite, 2026-09-02)" below for the full shape and what this replaced.
  **Not to be confused with** `browser_config.py`'s recent-files cache
  (below) — same base filename, completely different location and
  purpose: that one is keyed per browsed repo, unrelated to this settings
  page. Read back on the Maya side by `core/repo_context.py`'s
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
      active repo, delegating to `cache/plugins/PublishApi`'s
      `repo_paths` module (`get_active_repo()`, `get_pipeline_refs()`,
      `resolve_ref()`) for the *active* repo — same source of truth
      `MayaPublisher` builds its publish-root resolution on. Its own
      `_get_repo(project_id, repo_id)` still constructs `core.store.MetadataStore`
      directly (same off-disk convention, Maya's Python has no `PluginAPI`)
      for `_get_hidden_root_tab_keys()`/`_get_pipeline_refs_for()`, since
      those need an *explicit* repo — see their own docstrings for why.
      Falls back to Maya's current workspace dir if there's no active repo.
    - `browser_config.py` — recent-files persistence (paths stored relative
      to the repo root), one file per repo. As of 2026-08-23 the file
      itself lives under UkoreHub's own per-machine `cache/` dir (via
      `PublishApi.repo_paths.find_cache_dir()`), keyed by a hash of the
      repo root — **not** inside the repo being browsed. Previously stored
      at `<repo_root>/.ukorehub/ukore_browser.json`, which left a stray
      untracked file/folder in every browsed production repo;
      `BrowserConfig._load()` migrates that legacy file in and deletes it
      the first time a given repo is opened after this change.
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

## Extra tab paths (settings UI rewrite, 2026-09-02)

`mayafilebrowser_settings_page.py` used to be a hand-built widget tree: one
box per active-repo pipeline connection with a checkbox (hide/show that
connection's root tab), a rename field, and an inline "+ Add sub-path tab"
row with two free-typed `QLineEdit`s (sub-path, label). That checkbox
hide/rename feature was **dropped** in this rewrite — the page now loads
`MayaFileBrowserSettingsWindow.ui` (one `QTableWidget`, columns "Tab Name" /
"Extra Path" / "Used Connect Path", plus a single "Add" button) via
`QUiLoader`, and lists every connection's extra tabs flat across all
connections instead of nesting them per connection box. The old
`"repo_hidden_root_tabs"`/`root_tab_overrides[key]["label"]` data (hidden
set + connection rename) is still read on the Maya side by
`core/repo_context.py`'s `get_pipeline_root_tabs()` for repos that already
had it saved, but nothing in this plugin writes either of those two keys
anymore — bring the hide/rename UI back deliberately (its own `.ui`
section) if that's needed again.

Clicking "Add" opens `AddExtraPathDialogue.ui` (`_AddExtraPathDialog` in the
same file): pick which connection (`comboBox_custom_path`, one entry per
`pipeline_inputs` ref, same `_describe_ref()` text as before), type a tab
name, then "Browse Relative Path..." opens `QFileDialog.getExistingDirectory`
rooted at that connection's `CustomPath` folder resolved from disk — same
"reject anything picked from outside the root" rule `project_editor`'s own
CustomPath "Browse..." button uses. Switching the connection combo clears
whatever relative path was already browsed, since it was resolved against
the *previous* connection's root. `lineEdit_full_extra_path` previews the
result as `<target repo name>/<custom path's own path>/<relative path>` —
a logical path for confirmation, not a real filesystem path. Both "Browse"
and "Add" re-resolve and existence-check the connection's root (and, on
Add, the full picked folder) on disk before accepting — a deleted repo,
deleted `CustomPath`, or a folder removed after Browse but before Add all
surface as a `QMessageBox.critical`, not a silent no-op or stale save.
Saved shape is unchanged from before this rewrite —
`root_tab_overrides["<ref_key>"]["extra_paths"]`:
`[{"id", "sub_path", "label"}]` — so extra tabs saved by the old UI still
show up in the new table; only `"label"` is no longer optional (the new
dialog requires a tab name, where the old free-typed field could be left
blank and fell back to the sub-path on the Maya side).

There's no way to remove or edit an existing row from this page yet — only
`pushButton_add_extra_path` exists in the `.ui`. Add that deliberately
(new button + `.ui` change) if it's actually needed, rather than assuming
it belongs here.

## External dependencies (MayaToolkit + PublishApi)

This plugin does **not** vendor `tmlib` or `UkoreMaya` — both packages
still live at `cache/plugins/MayaToolkit/maya-scripts/{tmlib,UkoreMaya}/` and are
imported by name (`tmlib.ui.interface_template`, `tmlib.module.PySide`,
`UkoreMaya.core.template_ui`, `UkoreMaya.core.menu_utils`,
`UkoreMaya.core.function`). It also doesn't vendor its own repo/pipeline
path-resolution logic anymore as of 2026-07-19 — `core/repo_context.py`
imports `PublishApi.repo_paths` instead (see below). Both of these only
resolve because `cache/plugins/MayaToolkit/plugin.py` and
`cache/plugins/PublishApi/plugin.py` each contribute their own
`maya-scripts/` folder to the same `maya_launcher_env_bridge` PYTHONPATH
bridge this plugin uses — **if either is ever disabled for a repo (via
Repository Setting > Enable Plugin, which `cache/plugins/maya_launcher/`
gates its bridge merge on), MayaFileBrowser
breaks.** Don't "fix" this by vendoring `tmlib`/`UkoreMaya`/`PublishApi`'s
logic in here without a deliberate decision to do so; see
`cache/plugins/maya_launcher/README.md` for the general shape of the
bridge convention every Maya tool plugin here relies on.

## Maya menu registration (Ukore Menu only)

This plugin's only in-Maya launch entry point is the "Ukore Menu"
registration in `maya-scripts/UkoreBrowser/__init__.py`
(`UkoreMenu.registry.register_item(...)`, id `maya_file_browser`), fired
via the `post_open_mel` launch hook this file's `register()` sets up
(order 10) so `import UkoreBrowser` runs before `UkoreMenu` rebuilds its
menu (order 99) — see the comment above `launch_hooks` in this file.

A second registration used to also exist: `maya-plug-ins/mayaFileBrowser.py`
was a small standalone Maya plug-in, force-loaded via a
`MAYA_PLUG_IN_PATH` contribution, that inserted a "Maya File Browser..."
item directly into MayaToolkit's own "Ukore Studio Tool" menu
(`UkoreStudioToolMenu`) without editing `MayaToolkit` itself. Removed
2026-08-14 at the user's request — this plugin's `plugin.py` no longer
contributes `MAYA_PLUG_IN_PATH`, and `maya-plug-ins/mayaFileBrowser.py`
was deleted. Don't reintroduce this second registration without a
deliberate decision to do so.

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
builds a brand-new `MainWindow()` on every open, so without locking,
changing the active repo in UkoreHub would silently retarget the *next*
time UkoreBrowser is opened (including via the auto-launch hook in
`UkoreMaya/core/function.py`), which reads as the path changing out from
under you mid-session. The lock used to live in a local
`repo_context._get_locked_active_repo()` wrapper, but was centralized into
`PublishApi.repo_paths.get_active_repo()` itself on 2026-08-31 (see that
function's docstring) — every PublishApi consumer gets session-locked
behavior for free now, not just UkoreBrowser. `get_active_repo_path()` and
`get_pipeline_root_tabs()` below just call
`PublishApi.repo_paths.get_active_repo()` directly. If UkoreHub had no
active repo yet when Maya started, the lock stays open (every call
re-resolves) until one is actually found. An artist can manually resync
mid-session without restarting Maya via "Match Repo to Ukore Hub" (the
bottom-most item in the "General" section of the Ukore Tools menu,
registered by `PublishApi`, calls `PublishApi.reset_active_repo_lock()`).
The explicit root-tab buttons
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
`cache/plugins/PublishApi/README.md`)
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
Studio Setting tab (`mayafilebrowser_settings_page.py`, `_get_hidden_root_tab_keys`, see
above). A shown connection's label can be renamed, and extra tabs
appended for sub-paths underneath it, via that same Settings tab
(`_get_root_tab_overrides`, `"root_tab_overrides"` — see the settings-page
bullet above); an extra tab is only emitted if `ref_path / sub_path`
actually resolves to a real directory, so a stale/typo'd sub-path just
quietly drops instead of showing a dead tab.
`ui/main_window.py`'s `_build_root_tabs()` turns this into a row of
checkable buttons inserted at row 0 of the central grid layout (unused by
`ui.ui`, whose own rows start at 1) — clicking one calls `_switch_root(path)`,
which re-points `root_path`, the recent-files `BrowserConfig`, the
`QFileSystemModel`, and the Miller columns at that repo, same shape
`__init__` uses to set things up the first time. No-ops entirely (no tab
row added) if there's no active repo.

## Maya-scripts package name stays `UkoreBrowser`

The 2026-08-10 rename only touched the plugin's own folder, manifest
`name`, and settings-tab label — it deliberately did **not** touch
`maya-scripts/UkoreBrowser/`, the Maya-side Python package. Renaming that
folder would break `tmlib.core.File.launch("UkoreBrowser")`'s hardcoded
import path (called from `UkoreMaya/core/menu_utils.py:browser()` and the
auto-launch hook in `UkoreMaya/core/function.py` — both external callers
this plugin doesn't own), plus `ui/main_window.py`'s hardcoded
`super().__init__("UkoreBrowser")` toolkit name and `ui.ui`'s Qt Designer
lookup by that same name. So inside Maya, artists still see/launch "Ukore
Browser" via the Studio Tool menu; only the UkoreHub-side plugin identity
and Settings label changed. Don't "fix" this mismatch by renaming the
Maya-side package — see `interface.py`'s own comment for the same warning.

## Working on this plugin

Read/edit only files under this folder for a MayaFileBrowser-only task — see
`plugins/README.md`'s plugin-scoping note (and the `ukorehub-plugin` skill)
for why sibling plugins shouldn't be opened unless the task explicitly
touches them.
