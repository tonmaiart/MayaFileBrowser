"""Root-path detection: rooted at the active UkoreHub repo, falling back to
Maya's own current workspace when UkoreHub has no active repo (e.g. Maya was
opened outside of UkoreHub, or no repo has been selected yet).

Path/pipeline-metadata resolution itself goes through PublishApi
(plugins/repo_internal/PublishApi/maya-scripts/PublishApi/repo_paths.py) as of
2026-07-19, instead of this file carrying its own duplicate copy of
find_ukorehub_root()/store construction — so UkoreBrowser and MayaPublisher
share exactly one source of truth for what the active repo/pipeline
metadata is. See that plugin's README.

Lazy-locked per Maya session as of 2026-08-04: `get_active_repo()` reads
UkoreHub's `local_config.json` fresh off disk every call, and
`tmlib.core.File.launch("UkoreBrowser")` builds a brand-new `MainWindow()`
on every open — so without the cache below, switching the active repo in
UkoreHub would silently retarget the *next* UkoreBrowser open, which reads
as "the path changes out from under me" to anyone who reopens the tool
often (including the auto-launch hook in `UkoreMaya/core/function.py`).
`_get_locked_active_repo()` below resolves the active repo once and reuses
that result for the rest of the session. This relies on this module
(`UkoreBrowser.core.repo_context`) never itself being `importlib.reload`'d
— only `UkoreBrowser.interface` is, by `File.launch` — so the module-level
cache below survives every "open UkoreBrowser" call for the life of the
Maya process and resets on the next Maya launch."""

from __future__ import annotations

from pathlib import Path

from PublishApi import repo_paths as publish_api_repo_paths

_active_repo_locked = False
_cached_active_repo: tuple = (None, None, None)


def _get_locked_active_repo():
    """(project, repo, repo_path) for UkoreBrowser's session-locked active
    repo. Resolves via PublishApi.repo_paths.get_active_repo() the first
    time it finds one and remembers it from then on, ignoring later active
    -repo changes in UkoreHub for the rest of this Maya session — see the
    module docstring above. Until a repo is actually found, every call
    re-resolves (nothing to lock onto yet), so UkoreBrowser still picks up
    an active repo set in UkoreHub *after* Maya was opened, as long as it
    hasn't already locked onto one."""
    global _active_repo_locked, _cached_active_repo

    if _active_repo_locked:
        return _cached_active_repo

    result = publish_api_repo_paths.get_active_repo()
    if result[0] is not None:
        _cached_active_repo = result
        _active_repo_locked = True
    return result


def get_active_repo_path() -> str | None:
    """Absolute path to UkoreBrowser's session-locked active repo (see
    module docstring), or None if there isn't one yet (no workspace
    configured, no active repo ever selected this session, the repo
    folder doesn't exist on disk, or PublishApi isn't importable yet —
    e.g. this plugin's PYTHONPATH contribution hasn't taken effect)."""
    try:
        _project, _repo, repo_path = _get_locked_active_repo()
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
    root = publish_api_repo_paths.find_ukorehub_root()
    from core.exceptions import NotFoundError
    from core.storage.metadata_store import MetadataStore

    store = MetadataStore(root / "data" / "projects.json")
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
    (_get_hidden_root_tab_keys above). Returns [] if there's no active
    repo. Each item: {"label": str, "path": str}.

    Uses the same session-locked active repo as get_active_repo_path()
    (see module docstring) — otherwise the root-tab row would drift back
    to whatever repo is live in UkoreHub even while root_path itself
    stays locked, showing tabs for a different repo than the one actually
    being browsed."""
    try:
        project, repo, repo_path = _get_locked_active_repo()
        if project is None or repo_path is None or not repo_path.is_dir():
            return []

        tabs = [{"label": repo.name, "path": str(repo_path)}]
        hidden_keys = _get_hidden_root_tab_keys(project.id, repo.id)

        for ref in _get_pipeline_refs_for(project.id, repo.id):
            if _ref_key(ref) in hidden_keys:
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
            if ref_path.is_dir():
                tabs.append({"label": "{} — {}".format(ref_repo.name, custom_path["label"]), "path": str(ref_path)})

        return tabs
    except Exception:
        return []
