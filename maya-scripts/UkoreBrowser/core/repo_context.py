"""Root-path detection: rooted at the active UkoreHub repo, falling back to
Maya's own current workspace when UkoreHub has no active repo (e.g. Maya was
opened outside of UkoreHub, or no repo has been selected yet).

Path/pipeline-metadata resolution itself goes through PublishApi
(plugins/repo_internal/PublishApi/maya-scripts/PublishApi/repo_paths.py) as of
2026-07-19, instead of this file carrying its own duplicate copy of
find_data_dir()/store construction — so UkoreBrowser and MayaPublisher
share exactly one source of truth for what the active repo/pipeline
metadata is. See that plugin's README.

Session-locking (added here 2026-08-04, and used to live in a
UkoreBrowser-local `_get_locked_active_repo()` wrapper around
PublishApi.repo_paths.get_active_repo()) was centralized into
`PublishApi.repo_paths.get_active_repo()` itself on 2026-08-31 — see that
function's docstring. This module now just calls it directly and inherits
the lock for free, same as every other PublishApi consumer. Manual resync
mid-session (without restarting Maya) is available via "Change Project" in
the Ukore Tools menu, which calls PublishApi.reset_active_repo_lock()."""

from __future__ import annotations

from pathlib import Path

from PublishApi import repo_paths as publish_api_repo_paths


def get_active_repo_path() -> str | None:
    """Absolute path to UkoreHub's session-locked active repo (see module
    docstring), or None if there isn't one yet (no workspace configured,
    no active repo ever selected this session, the repo folder doesn't
    exist on disk, or PublishApi isn't importable yet — e.g. this plugin's
    PYTHONPATH contribution hasn't taken effect)."""
    try:
        _project, _repo, repo_path = publish_api_repo_paths.get_active_repo()
        if repo_path is None or not repo_path.is_dir():
            return None
        return str(repo_path)
    except Exception:
        return None


def get_root_path() -> str:
    """The browser's root: the active UkoreHub repo, else Maya's current
    workspace directory. Deliberately NOT the current scene file's folder —
    the Miller-column project/class/scene/shot/element lists are built
    relative to this root, and rooting at the scene's own (usually leaf,
    subfolder-less) folder left them permanently empty."""
    repo_path = get_active_repo_path()
    if repo_path is not None:
        return repo_path

    import maya.cmds as cmds

    return cmds.workspace(q=True, rd=True)


def get_initial_browse_path(root_path: str) -> str:
    """Where the browser should land on open: the current Maya scene
    file's folder if one is open and it's actually inside root_path (so
    you start out where you're working), else root_path itself."""
    from UkoreBrowser.core.maya_ops import get_current_scene_path

    scene_path = get_current_scene_path()
    if scene_path:
        scene_dir = Path(scene_path).parent
        try:
            scene_dir.relative_to(root_path)
        except ValueError:
            return root_path
        if scene_dir.is_dir():
            return str(scene_dir)

    return root_path


def _ref_key(ref: dict) -> str:
    """Same compound-key format plugins/repo_internal/UkoreBrowser/settings_page.py
    uses for its Repo Studio Setting checkbox list — a ref has no id of
    its own, so (target project, target repo, target CustomPath) together
    identify one specific pipeline connection."""
    return "{}:{}:{}".format(ref.get("project_id"), ref.get("repo_id"), ref.get("custom_path_id"))


def _get_repo(project_id: str, repo_id: str):
    """Constructs MetadataStore straight off disk (Maya's Python has no
    PluginAPI instance to go through) and looks up one specific repo by id
    — shared by the two lookups below, which both just want a field off
    that repo's own plugin_data (core/models.py's Repo)."""
    from core.exceptions import NotFoundError
    from core.storage.metadata_store import MetadataStore

    store = MetadataStore(publish_api_repo_paths.find_data_dir() / "projects.json")
    try:
        return store.get_repo(project_id, repo_id)
    except NotFoundError:
        return None


def _get_hidden_root_tab_keys(project_id: str, repo_id: str) -> set[str]:
    """The set of ref keys a studio admin has hidden from the root-tab row
    for this repo, via UkoreBrowser's own Repo Studio Setting tab — read
    off this repo's own plugin_data["ukore_browser"] (core/models.py's Repo)."""
    repo = _get_repo(project_id, repo_id)
    if repo is None:
        return set()
    hidden = repo.plugin_data.get("ukore_browser", {}).get("repo_hidden_root_tabs", [])
    return set(hidden)


def _get_root_tab_overrides(project_id: str, repo_id: str) -> dict:
    """Per-ref customization a studio admin has set via this plugin's own
    Repo Studio Setting tab (mayafilebrowser_settings_page.py): a rename of
    the tab's label and/or extra sub-path tabs appended under it. Keyed by
    the same ref key as _get_hidden_root_tab_keys — read off this repo's own
    plugin_data["ukore_browser"]["root_tab_overrides"]."""
    repo = _get_repo(project_id, repo_id)
    if repo is None:
        return {}
    return repo.plugin_data.get("ukore_browser", {}).get("root_tab_overrides", {})


def _get_pipeline_refs_for(project_id: str, repo_id: str) -> list[dict]:
    """Same lookup as PublishApi.repo_paths.get_pipeline_refs(), but for an
    explicit (project_id, repo_id) instead of that function's own internal
    "whatever is live in UkoreHub right now" resolution — get_pipeline_refs()
    takes no repo argument, so calling it as-is here would fetch pipeline
    connections for the *currently* active repo even after this module has
    locked onto an earlier one (see module docstring), showing the locked
    repo's own tab alongside a different repo's connections. Reads off that
    repo's own plugin_data["project_editor"] directly instead."""
    repo = _get_repo(project_id, repo_id)
    if repo is None:
        return []
    return repo.plugin_data.get("project_editor", {}).get("pipeline_inputs", [])


def get_pipeline_root_tabs() -> list[dict]:
    """Root-path tab options for the browser's top tab bar: the active
    repo itself, plus every repo it has connected to via "Connect
    Pipeline Input Path..." in Project Editor (via
    PublishApi.repo_paths.get_pipeline_refs/resolve_ref/get_custom_path),
    each resolved down to its specific declared CustomPath rather than
    just the target repo's root — minus whichever ones a studio admin has
    hidden via this plugin's own Repo Studio Setting tab
    (_get_hidden_root_tab_keys above). A shown connection's tab label can
    be renamed, and extra tabs can be appended for sub-paths underneath
    it, via that same Settings tab (_get_root_tab_overrides above) — an
    extra tab is only included if its resolved folder actually exists, so
    a stale/typo'd sub-path just quietly drops instead of showing a dead
    tab. Returns [] if there's no active repo. Each item: {"label": str,
    "path": str}.

    Uses the same session-locked active repo as get_active_repo_path()
    (see module docstring) — otherwise the root-tab row would drift back
    to whatever repo is live in UkoreHub even while root_path itself
    stays locked, showing tabs for a different repo than the one actually
    being browsed."""
    try:
        project, repo, repo_path = publish_api_repo_paths.get_active_repo()
        if project is None or repo_path is None or not repo_path.is_dir():
            return []

        tabs = [{"label": repo.name, "path": str(repo_path)}]
        hidden_keys = _get_hidden_root_tab_keys(project.id, repo.id)
        overrides = _get_root_tab_overrides(project.id, repo.id)

        for ref in _get_pipeline_refs_for(project.id, repo.id):
            ref_key = _ref_key(ref)
            if ref_key in hidden_keys:
                continue
            resolved = publish_api_repo_paths.resolve_ref(ref)
            if resolved is None:
                continue
            _ref_project, ref_repo, ref_repo_path = resolved
            custom_path = publish_api_repo_paths.get_custom_path(
                ref["project_id"], ref["repo_id"], ref.get("custom_path_id")
            )
            if custom_path is None:
                continue
            ref_path = ref_repo_path / custom_path["path"]
            if not ref_path.is_dir():
                continue

            override = overrides.get(ref_key, {})
            label = override.get("label") or "{} — {}".format(ref_repo.name, custom_path["label"])
            tabs.append({"label": label, "path": str(ref_path)})

            for extra in override.get("extra_paths", []):
                sub_path = extra.get("sub_path", "").strip()
                if not sub_path:
                    continue
                extra_path = ref_path / sub_path
                if extra_path.is_dir():
                    tabs.append({"label": extra.get("label") or sub_path, "path": str(extra_path)})

        return tabs
    except Exception:
        return []
