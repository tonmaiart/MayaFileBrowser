from __future__ import annotations

import os
import uuid
from pathlib import Path

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from plugin_api import NotFoundError

TOOL_ID = "ukore_browser"
_PLUGIN_DIR = Path(__file__).resolve().parent


def _ref_key(ref: dict) -> str:
    return "{}:{}:{}".format(ref.get("project_id"), ref.get("repo_id"), ref.get("custom_path_id"))


def _load_ui(filename: str, parent: QWidget) -> QWidget:
    loader = QUiLoader()
    ui_file = QFile(str(_PLUGIN_DIR / filename))
    ui_file.open(QFile.ReadOnly)
    try:
        return loader.load(ui_file, parent)
    finally:
        ui_file.close()


def _get_custom_path(api, ref: dict) -> dict | None:
    target_entry = api.metadata.get_repo_plugin_data(ref["project_id"], ref["repo_id"], "project_editor")
    return next(
        (cp for cp in target_entry.get("custom_paths", []) if cp["id"] == ref.get("custom_path_id")), None
    )


def _resolve_custom_path_root(api, ref: dict) -> Path | None:
    """Resolves a pipeline_inputs ref to the target repo's declared CustomPath
    folder on disk. PluginAPI has no ready-made helper for this — mirrors the
    worked example in developer/app/docs/plugins/project_editor.md
    ("resolving a pipeline connection all the way to an actual filesystem
    path takes two lookups")."""
    try:
        target_repo = api.metadata.get_repo(ref["project_id"], ref["repo_id"])
        custom_path = _get_custom_path(api, ref)
    except NotFoundError:
        return None
    if custom_path is None:
        return None
    target_repo_path = Path(api.local_config.workspace_root) / target_repo.local_path
    return target_repo_path / custom_path["path"]


def _describe_ref(api, ref: dict) -> str:
    try:
        target_name = api.metadata.get_repo(ref["project_id"], ref["repo_id"]).name
    except NotFoundError:
        return "(deleted repo)"
    custom_path = _get_custom_path(api, ref)
    label = custom_path["label"] if custom_path else "(deleted custom path)"
    return f"{target_name} — {label}"


class _AddExtraPathDialog(QDialog):
    """AddExtraPathDialogue.ui wiring — pick which connected CustomPath the
    new tab belongs to, browse a sub-folder under it (rejecting anything
    outside that folder, same convention project_editor's own CustomPath
    "Browse..." button uses), and preview the full logical path from the
    target repo's name down through the chosen relative path."""

    def __init__(self, parent: QWidget, *, api, refs: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Add Extra Tab Path")
        self._api = api
        self._selected_root: Path | None = None
        self._relative_path: str = ""

        form = _load_ui("AddExtraPathDialogue.ui", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(form)

        self._line_tab_name: QLineEdit = form.findChild(QLineEdit, "lineEdit_tabName")
        self._combo_custom_path: QComboBox = form.findChild(QComboBox, "comboBox_custom_path")
        self._line_relative_path: QLineEdit = form.findChild(QLineEdit, "lineEdit_relative_path")
        self._line_full_path: QLineEdit = form.findChild(QLineEdit, "lineEdit_full_extra_path")
        btn_browse: QPushButton = form.findChild(QPushButton, "pushButton_browse_relative_path")
        btn_cancel: QPushButton = form.findChild(QPushButton, "pushButton_cancel")
        btn_confirm: QPushButton = form.findChild(QPushButton, "pushButton_confirm")

        for ref in refs:
            self._combo_custom_path.addItem(_describe_ref(api, ref), ref)
        self._combo_custom_path.currentIndexChanged.connect(self._on_custom_path_changed)
        self._on_custom_path_changed(self._combo_custom_path.currentIndex())

        btn_browse.clicked.connect(self._on_browse)
        btn_cancel.clicked.connect(self.reject)
        btn_confirm.clicked.connect(self._on_confirm)

        self.result_ref: dict | None = None
        self.result_tab_name: str = ""
        self.result_relative_path: str = ""

    def _current_ref(self) -> dict | None:
        index = self._combo_custom_path.currentIndex()
        return self._combo_custom_path.itemData(index) if index >= 0 else None

    def _on_custom_path_changed(self, _index: int) -> None:
        # Switching which connection this tab belongs to invalidates any
        # relative path already browsed under the previous one.
        self._selected_root = None
        self._relative_path = ""
        self._line_relative_path.clear()
        self._line_full_path.clear()

    def _on_browse(self) -> None:
        ref = self._current_ref()
        if ref is None:
            QMessageBox.warning(self, "Add Extra Tab Path", "Pick a custom path first.")
            return

        root = _resolve_custom_path_root(self._api, ref)
        if root is None:
            QMessageBox.critical(
                self, "Add Extra Tab Path", "That custom path no longer exists (deleted repo or custom path)."
            )
            return
        if not root.is_dir():
            QMessageBox.critical(
                self, "Add Extra Tab Path", f"The custom path's folder doesn't exist on disk:\n{root}"
            )
            return

        chosen = QFileDialog.getExistingDirectory(self, "Browse Relative Path", str(root))
        if not chosen:
            return

        try:
            relative = Path(chosen).resolve().relative_to(root.resolve())
        except ValueError:
            QMessageBox.critical(
                self,
                "Add Extra Tab Path",
                "That folder isn't inside the selected custom path — pick a sub-folder of it instead.",
            )
            return

        self._selected_root = root
        self._relative_path = str(relative).replace(os.sep, "/")
        self._line_relative_path.setText(self._relative_path)
        self._update_full_path_preview(ref)

    def _update_full_path_preview(self, ref: dict) -> None:
        target_repo = self._api.metadata.get_repo(ref["project_id"], ref["repo_id"])
        custom_path = _get_custom_path(self._api, ref)
        parts = [target_repo.name, custom_path["path"] if custom_path else "", self._relative_path]
        self._line_full_path.setText("/".join(part.strip("/") for part in parts if part))

    def _on_confirm(self) -> None:
        ref = self._current_ref()
        tab_name = self._line_tab_name.text().strip()

        if ref is None:
            QMessageBox.warning(self, "Add Extra Tab Path", "Pick a custom path first.")
            return
        if not tab_name:
            QMessageBox.warning(self, "Add Extra Tab Path", "Enter a tab name.")
            return
        if not self._relative_path or self._selected_root is None:
            QMessageBox.warning(self, "Add Extra Tab Path", "Browse and pick a relative path first.")
            return

        # Re-validate on confirm too — the custom path or the picked folder
        # may have gone stale (deleted repo/custom path/folder) since Browse.
        root = _resolve_custom_path_root(self._api, ref)
        if root is None or not root.is_dir():
            QMessageBox.critical(
                self, "Add Extra Tab Path", "That custom path is no longer valid — browse and pick a relative path again."
            )
            return
        full_path = root / self._relative_path
        if not full_path.is_dir():
            QMessageBox.critical(
                self,
                "Add Extra Tab Path",
                f"That folder doesn't exist under the custom path anymore:\n{full_path}",
            )
            return

        self.result_ref = ref
        self.result_tab_name = tab_name
        self.result_relative_path = self._relative_path
        self.accept()


class MayaFileBrowserSettingsPage(QWidget):
    """Repo Studio Setting for MayaFileBrowser (formerly UkoreBrowser) —
    MayaFileBrowserSettingsWindow.ui loaded at runtime via QUiLoader (same
    pattern project_editor's own settings pages use), replacing the
    hand-built widget tree this page used before. Manages the "extra tab"
    feature only: a studio admin adds a tab for a sub-folder underneath one
    of this repo's connected pipeline CustomPaths (e.g. a "Renders/Final"
    folder shown as its own root tab in Maya File Browser), picked by
    browsing rather than typed by hand so it can be validated against the
    real folder on disk. Persists into this repo's own
    Repo.plugin_data[TOOL_ID] ("ukore_browser", kept for backward
    compatibility — see plugin.py) under "root_tab_overrides", keyed by
    connection ref, via api.metadata.get_repo_plugin_data/
    set_repo_plugin_data — same storage shape the previous UI used, so
    already-saved extra tabs still show up here. Read back on the Maya side
    by maya-scripts/UkoreBrowser/core/repo_context.py's
    get_pipeline_root_tabs()."""

    def __init__(self, parent=None, *, api):
        super().__init__(parent)
        self._api = api
        self._project_id: str | None = None
        self._repo_id: str | None = None
        self._refs: list[dict] = []

        form = _load_ui("MayaFileBrowserSettingsWindow.ui", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(form)

        self._table: QTableWidget = form.findChild(QTableWidget, "tableWidget_extra_path")
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)

        self._btn_add: QPushButton = form.findChild(QPushButton, "pushButton_add_extra_path")
        self._btn_add.clicked.connect(self._on_add_clicked)

        self.refresh()

    def refresh(self) -> None:
        """Re-resolves the active project/repo and rebuilds the table —
        called on construction and every time this tab becomes active
        (SettingsTabSpec.on_activated)."""
        project_id = self._api.local_config.active_project_id
        repo_id = self._api.local_config.active_repo_id
        self._project_id = project_id
        self._repo_id = repo_id

        if not project_id or not repo_id:
            self._refs = []
            self._table.setRowCount(0)
            self._btn_add.setEnabled(False)
            return

        entry = self._api.metadata.get_repo_plugin_data(project_id, repo_id, "project_editor")
        self._refs = entry.get("pipeline_inputs", [])
        self._btn_add.setEnabled(bool(self._refs))
        self._reload_table()

    def _reload_table(self) -> None:
        self._table.setRowCount(0)
        overrides = self._get_overrides()
        for ref in self._refs:
            for extra in overrides.get(_ref_key(ref), {}).get("extra_paths", []):
                self._append_row(ref, extra)

    def _append_row(self, ref: dict, extra: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(extra.get("label", "")))
        self._table.setItem(row, 1, QTableWidgetItem(extra.get("sub_path", "")))
        self._table.setItem(row, 2, QTableWidgetItem(_describe_ref(self._api, ref)))

    def _get_overrides(self) -> dict:
        return self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID).get(
            "root_tab_overrides", {}
        )

    def _mutate_data(self, mutate) -> None:
        data = dict(self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID))
        mutate(data)
        self._api.metadata.set_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID, data)

    def _on_add_clicked(self) -> None:
        if self._project_id is None or self._repo_id is None or not self._refs:
            return

        dialog = _AddExtraPathDialog(self, api=self._api, refs=self._refs)
        if dialog.exec() != QDialog.Accepted:
            return

        key = _ref_key(dialog.result_ref)
        new_extra = {
            "id": str(uuid.uuid4()),
            "sub_path": dialog.result_relative_path,
            "label": dialog.result_tab_name,
        }

        def mutate(data):
            overrides = dict(data.get("root_tab_overrides", {}))
            entry = dict(overrides.get(key, {}))
            entry["extra_paths"] = list(entry.get("extra_paths", [])) + [new_extra]
            overrides[key] = entry
            data["root_tab_overrides"] = overrides

        self._mutate_data(mutate)
        self._reload_table()


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
