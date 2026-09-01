from __future__ import annotations

import uuid

from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from plugin_api import NotFoundError

TOOL_ID = "ukore_browser"


def _ref_key(ref: dict) -> str:
    return "{}:{}:{}".format(ref.get("project_id"), ref.get("repo_id"), ref.get("custom_path_id"))


class MayaFileBrowserSettingsPage(QWidget):
    """Repo Studio Setting for MayaFileBrowser (formerly UkoreBrowser) — unlike MayaPublisher's
    per-ticket "which pipeline connection does this ticket publish into"
    picker (chosen entirely in Maya via Manage Tickets...), MayaFileBrowser
    genuinely shows several root tabs at once (its whole point is
    browsing multiple pipeline-connected repos side by side), so this is
    a **multi-select** checkbox list instead — one row per active-repo
    pipeline connection ("Connect Pipeline Input Path...", each a
    specific CustomPath within a target repo, see
    plugins/core/project_editor/pipeline_store.py), letting a studio
    admin hide ones that would just clutter the tab bar rather than
    picking exactly one. Each row also lets the admin rename the tab's
    label and append extra tabs for sub-paths underneath that connection
    (e.g. a "Renders/Final" folder shown as its own tab), rather than
    always showing the connection's own CustomPath root as-is.

    Stores the HIDDEN set (opt-out): a brand-new pipeline ref (or a
    brand-new tool version state entirely) should default to shown/
    enabled rather than requiring someone to notice and re-check it. The
    rename/extra-paths customization is stored separately as an opt-in
    "root_tab_overrides" map, keyed by the same ref key, so a ref with no
    customization takes no extra space and falls back to the default
    label/no extra tabs.
    Persists into this repo's own Repo.plugin_data[TOOL_ID]
    ("ukore_browser", the technical id kept for backward compatibility —
    see plugin.py) under keys "repo_hidden_root_tabs" and
    "root_tab_overrides", via api.metadata.get_repo_plugin_data/
    set_repo_plugin_data — moved off the old standalone
    data/plugins/core/ukore_browser.json PluginConfigStore blob by
    migrate_legacy_data() below. Read back on the Maya side by
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
        self._extra_layouts: dict[str, QVBoxLayout] = {}

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
        """Re-resolves the active project/repo and rebuilds the row list —
        called on construction and every time this tab becomes active
        (SettingsTabSpec.on_activated)."""
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
                "Maya File Browser has nothing to show extra root tabs for."
            )
            return

        self.hint_label.setText(
            "Uncheck a connection to hide it from Maya File Browser's root-tab row without removing "
            "the pipeline connection itself. Rename a tab, or add extra tabs for sub-paths underneath it, below."
        )
        hidden = set(self._get_hidden())
        overrides = self._get_overrides()
        for ref in self._refs:
            key = _ref_key(ref)
            self._rows_layout.addWidget(self._build_ref_row(ref, key, key not in hidden, overrides.get(key, {})))

    def _build_ref_row(self, ref: dict, key: str, checked: bool, override: dict) -> QWidget:
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)
        box_layout = QVBoxLayout(box)

        top_row = QHBoxLayout()
        checkbox = QCheckBox()
        checkbox.setChecked(checked)
        checkbox.toggled.connect(lambda _checked, r=ref: self._on_toggled(r))
        self._checkboxes[key] = checkbox
        top_row.addWidget(checkbox)

        top_row.addWidget(QLabel("Name:"))
        label_edit = QLineEdit(override.get("label", ""))
        label_edit.setPlaceholderText(self._describe_ref(ref))
        label_edit.editingFinished.connect(lambda r=ref, le=label_edit: self._on_label_edited(r, le))
        top_row.addWidget(label_edit, 1)
        box_layout.addLayout(top_row)

        extras_container = QWidget()
        extras_layout = QVBoxLayout(extras_container)
        extras_layout.setContentsMargins(20, 0, 0, 0)
        self._extra_layouts[key] = extras_layout
        box_layout.addWidget(extras_container)

        for extra in override.get("extra_paths", []):
            extras_layout.addWidget(self._build_extra_row(ref, key, extra))

        add_btn = QPushButton("+ Add sub-path tab")
        add_btn.clicked.connect(lambda _checked, r=ref, k=key: self._on_add_extra(r, k))
        box_layout.addWidget(add_btn)

        return box

    def _build_extra_row(self, ref: dict, key: str, extra: dict) -> QWidget:
        extra_id = extra.setdefault("id", str(uuid.uuid4()))

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        sub_path_edit = QLineEdit(extra.get("sub_path", ""))
        sub_path_edit.setPlaceholderText("Sub-path under this connection, e.g. Renders/Final")
        label_edit = QLineEdit(extra.get("label", ""))
        label_edit.setPlaceholderText("Tab name (defaults to the sub-path)")
        remove_btn = QToolButton()
        remove_btn.setText("✕")

        def save(r=ref, k=key, eid=extra_id, se=sub_path_edit, le=label_edit):
            self._on_extra_edited(r, k, eid, se.text().strip(), le.text().strip())

        sub_path_edit.editingFinished.connect(save)
        label_edit.editingFinished.connect(save)
        remove_btn.clicked.connect(lambda _checked, r=ref, k=key, eid=extra_id, w=row: self._on_remove_extra(r, k, eid, w))

        row_layout.addWidget(sub_path_edit, 2)
        row_layout.addWidget(label_edit, 1)
        row_layout.addWidget(remove_btn)
        return row

    def _clear_rows(self) -> None:
        self._checkboxes = {}
        self._extra_layouts = {}
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

    def _get_overrides(self) -> dict:
        return self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID).get(
            "root_tab_overrides", {}
        )

    def _mutate_data(self, mutate) -> None:
        data = dict(self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID))
        mutate(data)
        self._api.metadata.set_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID, data)

    def _mutate_override(self, key: str, mutate) -> None:
        """Shared read-modify-write for one ref's entry in root_tab_overrides
        — mutate(entry) edits the dict in place; an entry left empty (no
        label, no extra_paths) is dropped entirely rather than persisted
        as a no-op {}."""

        def apply(data):
            overrides = dict(data.get("root_tab_overrides", {}))
            entry = dict(overrides.get(key, {}))
            mutate(entry)
            if entry.get("label") or entry.get("extra_paths"):
                overrides[key] = entry
            else:
                overrides.pop(key, None)
            data["root_tab_overrides"] = overrides

        self._mutate_data(apply)

    def _on_toggled(self, ref: dict) -> None:
        if self._project_id is None or self._repo_id is None:
            return
        hidden = set(self._get_hidden())
        key = _ref_key(ref)
        if self._checkboxes[key].isChecked():
            hidden.discard(key)
        else:
            hidden.add(key)
        self._mutate_data(lambda data: data.__setitem__("repo_hidden_root_tabs", sorted(hidden)))

    def _on_label_edited(self, ref: dict, label_edit: QLineEdit) -> None:
        if self._project_id is None or self._repo_id is None:
            return
        text = label_edit.text().strip()

        def mutate(entry):
            if text:
                entry["label"] = text
            else:
                entry.pop("label", None)

        self._mutate_override(_ref_key(ref), mutate)

    def _on_add_extra(self, ref: dict, key: str) -> None:
        if self._project_id is None or self._repo_id is None:
            return
        new_extra = {"id": str(uuid.uuid4()), "sub_path": "", "label": ""}

        def mutate(entry):
            entry["extra_paths"] = list(entry.get("extra_paths", [])) + [new_extra]

        self._mutate_override(key, mutate)
        self._extra_layouts[key].addWidget(self._build_extra_row(ref, key, new_extra))

    def _on_extra_edited(self, ref: dict, key: str, extra_id: str, sub_path: str, label: str) -> None:
        if self._project_id is None or self._repo_id is None:
            return

        def mutate(entry):
            extra_paths = list(entry.get("extra_paths", []))
            for extra in extra_paths:
                if extra.get("id") == extra_id:
                    extra["sub_path"] = sub_path
                    extra["label"] = label
                    break
            entry["extra_paths"] = extra_paths

        self._mutate_override(key, mutate)

    def _on_remove_extra(self, ref: dict, key: str, extra_id: str, row_widget: QWidget) -> None:
        if self._project_id is None or self._repo_id is None:
            return

        def mutate(entry):
            entry["extra_paths"] = [e for e in entry.get("extra_paths", []) if e.get("id") != extra_id]

        self._mutate_override(key, mutate)
        row_widget.setParent(None)
        row_widget.deleteLater()


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
