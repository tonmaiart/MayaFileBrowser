from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

from core.exceptions import NotFoundError

TOOL_ID = "ukore_browser"


def _ref_key(ref: dict) -> str:
    return "{}:{}:{}".format(ref.get("project_id"), ref.get("repo_id"), ref.get("custom_path_id"))


class UkoreBrowserSettingsPage(QWidget):
    """Repo Studio Setting for UkoreBrowser — unlike MayaPublisher's
    per-ticket "which pipeline connection does this ticket publish into"
    picker (chosen entirely in Maya via Manage Tickets...), UkoreBrowser
    genuinely shows several root tabs at once (its whole point is
    browsing multiple pipeline-connected repos side by side), so this is
    a **multi-select** checkbox list instead — one row per active-repo
    pipeline connection ("Connect Pipeline Input Path...", each a
    specific CustomPath within a target repo, see
    plugins/core/project_editor/pipeline_store.py), letting a studio
    admin hide ones that would just clutter the tab bar rather than
    picking exactly one.

    Stores the HIDDEN set (opt-out): a brand-new pipeline ref (or a
    brand-new tool version state entirely) should default to shown/
    enabled rather than requiring someone to notice and re-check it.
    Persists into this plugin's own PluginConfigStore
    (data/plugins/core/ukore_browser.json, key "repo_hidden_root_tabs"),
    read back on the Maya side by
    maya-scripts/UkoreBrowser/core/repo_context.py's
    get_pipeline_root_tabs(). Same self-resolving-active-repo `refresh()`
    pattern as interface/settings/browser_links_settings_page.py."""

    def __init__(self, parent=None, *, api):
        super().__init__(parent)
        self._api = api
        self._project_id: str | None = None
        self._repo_id: str | None = None
        self._refs: list[dict] = []
        self._checkboxes: dict[str, QCheckBox] = {}

        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)

        layout = QVBoxLayout(self)
        layout.addWidget(self.hint_label)
        layout.addWidget(self._rows_container)
        layout.addStretch()

        self.refresh()

    def refresh(self) -> None:
        """Re-resolves the active project/repo and rebuilds the checkbox
        list — called on construction and every time this tab becomes
        active (SettingsTabSpec.on_activated)."""
        project_id = self._api.local_config.active_project_id
        repo_id = self._api.local_config.active_repo_id
        self._project_id = project_id
        self._repo_id = repo_id
        self._clear_rows()

        if not project_id or not repo_id:
            self.hint_label.setText("Select a repo to see this information.")
            return

        entry = self._api.metadata.get_repo_plugin_data(project_id, repo_id, "project_editor")
        self._refs = entry.get("pipeline_inputs", [])

        if not self._refs:
            self.hint_label.setText(
                "This repo has no pipeline connections declared in Project Editor yet — "
                "UkoreBrowser has nothing to show extra root tabs for."
            )
            return

        self.hint_label.setText(
            "Uncheck a connection to hide it from UkoreBrowser's root-tab row without removing "
            "the pipeline connection itself."
        )
        hidden = set(self._get_hidden())
        for ref in self._refs:
            checkbox = QCheckBox(self._describe_ref(ref))
            checkbox.setChecked(_ref_key(ref) not in hidden)
            checkbox.toggled.connect(lambda _checked, r=ref: self._on_toggled(r))
            self._rows_layout.addWidget(checkbox)
            self._checkboxes[_ref_key(ref)] = checkbox

    def _clear_rows(self) -> None:
        self._checkboxes = {}
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _describe_ref(self, ref: dict) -> str:
        try:
            target_name = self._api.metadata.get_repo(ref["project_id"], ref["repo_id"]).name
        except NotFoundError:
            return "(deleted repo)"
        target_entry = self._api.metadata.get_repo_plugin_data(ref["project_id"], ref["repo_id"], "project_editor")
        custom_path = next(
            (cp for cp in target_entry.get("custom_paths", []) if cp["id"] == ref.get("custom_path_id")), None
        )
        label = custom_path["label"] if custom_path else "(deleted custom path)"
        return f"{target_name} — {label}"

    def _get_hidden(self) -> list[str]:
        return self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID).get(
            "repo_hidden_root_tabs", []
        )

    def _on_toggled(self, ref: dict) -> None:
        if self._project_id is None or self._repo_id is None:
            return
        hidden = set(self._get_hidden())
        ref_key = _ref_key(ref)
        if self._checkboxes[ref_key].isChecked():
            hidden.discard(ref_key)
        else:
            hidden.add(ref_key)
        data = dict(self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID))
        data["repo_hidden_root_tabs"] = sorted(hidden)
        self._api.metadata.set_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID, data)


def migrate_legacy_data(api) -> None:
    """One-time cutover from the old data/plugins/core/ukore_browser.json
    PluginConfigStore blob's "repo_hidden_root_tabs" key into each repo's
    own Repo.plugin_data. Safe to call on every register(), not just once
    — a previous successful run leaves this key empty, so there's nothing
    left to migrate."""
    legacy_store = api.plugin_config_store(TOOL_ID, shared=True)
    hidden_map = legacy_store.get("repo_hidden_root_tabs", {})
    if not hidden_map:
        return
    for repo_key, hidden in hidden_map.items():
        project_id, _, repo_id = repo_key.partition(":")
        try:
            data = dict(api.metadata.get_repo_plugin_data(project_id, repo_id, TOOL_ID))
            data["repo_hidden_root_tabs"] = hidden
            api.metadata.set_repo_plugin_data(project_id, repo_id, TOOL_ID, data)
        except NotFoundError:
            pass  # project/repo no longer exists — drop the stale entry
    legacy_store.set("repo_hidden_root_tabs", {})
