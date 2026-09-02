from __future__ import annotations

import os
import uuid
from pathlib import Path

from PySide6.QtCore import QFile, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QLineEdit,
    QMenu,
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


def _load_ui(filename: str, parent: QWidget) -> QWidget:
    loader = QUiLoader()
    ui_file = QFile(str(_PLUGIN_DIR / filename))
    ui_file.open(QFile.ReadOnly)
    try:
        return loader.load(ui_file, parent)
    finally:
        ui_file.close()


class _AddExtraPathDialog(QDialog):
    """AddExtraPathDialogue.ui wiring — "Browse Relative Path..." opens a
    folder picker rooted at the active repo's own absolute path (resolved
    by the caller via `api.local_config.workspace_root` / `Repo.local_path`
    — see `MayaFileBrowserSettingsPage._active_repo_root()`), rejecting
    anything picked from outside it (same convention project_editor's own
    CustomPath "Browse..." button uses), and previews the full path as
    `<repo name>/<relative path>`.
    Doubles as the Edit dialog when `initial_tab_name`/
    `initial_relative_path` are given (`confirm_text` swapped to "Change")
    — same dialog class, same validation, the settings page tells the two
    apart by whether it passes an existing extra's id into the save
    afterward, not by anything this dialog itself tracks."""

    def __init__(
        self,
        parent: QWidget,
        *,
        repo_root: Path,
        repo_name: str,
        initial_tab_name: str = "",
        initial_relative_path: str = "",
        confirm_text: str = "Add",
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Extra Tab Path" if confirm_text == "Add" else "Edit Extra Tab Path")
        self._repo_root = repo_root
        self._repo_name = repo_name
        self._relative_path: str = initial_relative_path

        form = _load_ui("AddExtraPathDialogue.ui", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(form)

        self._line_tab_name: QLineEdit = form.findChild(QLineEdit, "lineEdit_tabName")
        self._line_relative_path: QLineEdit = form.findChild(QLineEdit, "lineEdit_relative_path")
        self._line_full_path: QLineEdit = form.findChild(QLineEdit, "lineEdit_full_extra_path")
        btn_browse: QPushButton = form.findChild(QPushButton, "pushButton_browse_relative_path")
        btn_cancel: QPushButton = form.findChild(QPushButton, "pushButton_cancel")
        btn_confirm: QPushButton = form.findChild(QPushButton, "pushButton_confirm")
        btn_confirm.setText(confirm_text)

        btn_browse.clicked.connect(self._on_browse)
        btn_cancel.clicked.connect(self.reject)
        btn_confirm.clicked.connect(self._on_confirm)

        self.result_tab_name: str = ""
        self.result_relative_path: str = ""

        self._line_tab_name.setText(initial_tab_name)
        self._line_relative_path.setText(initial_relative_path)
        self._update_full_path_preview()

    def _update_full_path_preview(self) -> None:
        if self._relative_path:
            self._line_full_path.setText(f"{self._repo_name}/{self._relative_path}")
        else:
            self._line_full_path.clear()

    def _on_browse(self) -> None:
        if not self._repo_root.is_dir():
            QMessageBox.critical(
                self, "Add Extra Tab Path", f"The current repo's folder doesn't exist on disk:\n{self._repo_root}"
            )
            return

        chosen = QFileDialog.getExistingDirectory(self, "Browse Relative Path", str(self._repo_root))
        if not chosen:
            return

        try:
            relative = Path(chosen).resolve().relative_to(self._repo_root.resolve())
        except ValueError:
            QMessageBox.critical(
                self,
                "Add Extra Tab Path",
                "That folder isn't inside the current repo — pick a sub-folder of it instead.",
            )
            return

        self._relative_path = str(relative).replace(os.sep, "/")
        self._line_relative_path.setText(self._relative_path)
        self._update_full_path_preview()

    def _on_confirm(self) -> None:
        tab_name = self._line_tab_name.text().strip()

        if not tab_name:
            QMessageBox.warning(self, "Add Extra Tab Path", "Enter a tab name.")
            return
        if not self._relative_path:
            QMessageBox.warning(self, "Add Extra Tab Path", "Browse and pick a relative path first.")
            return

        # Re-validate on confirm too — the repo folder or the picked
        # sub-folder may have gone stale (moved/deleted) since Browse.
        if not self._repo_root.is_dir():
            QMessageBox.critical(
                self, "Add Extra Tab Path", f"The current repo's folder doesn't exist on disk:\n{self._repo_root}"
            )
            return
        full_path = self._repo_root / self._relative_path
        if not full_path.is_dir():
            QMessageBox.critical(
                self,
                "Add Extra Tab Path",
                f"That folder doesn't exist under the repo anymore:\n{full_path}",
            )
            return

        self.result_tab_name = tab_name
        self.result_relative_path = self._relative_path
        self.accept()


class MayaFileBrowserSettingsPage(QWidget):
    """Repo Studio Setting for MayaFileBrowser (formerly UkoreBrowser) —
    MayaFileBrowserSettingsWindow.ui loaded at runtime via QUiLoader (same
    pattern project_editor's own settings pages use). Manages the "extra
    tab" feature: a studio admin adds a tab for a sub-folder underneath the
    *active repo's own* absolute path (e.g. a "Renders/Final" folder shown
    as its own root tab in Maya File Browser), picked by browsing rather
    than typed by hand so it can be validated against the real folder on
    disk. Right-click a row for Edit (reopens the same dialog pre-filled,
    "Add" swapped for "Change") / Remove.

    As of 2026-09-02 this is no longer tied to a connected pipeline
    CustomPath (there used to be a "Custom Path" picker in the Add dialog,
    resolving the folder through project_editor's pipeline_inputs/
    CustomPath catalog on some *other* repo) — every extra tab is now
    relative to the current repo's own folder directly, at the user's own
    request to simplify the flow (the resolved path for a pipeline
    connection whose target repo wasn't cloned locally yet, or whose
    CustomPath.path had been hand-edited to something unexpected, was
    confusing to debug and not actually needed for what this feature is
    for). tableWidget_extra_path's third ("Used Connect Path") column is
    hidden rather than removed from the .ui, since it no longer has
    anything meaningful to show.

    Persists into this repo's own Repo.plugin_data[TOOL_ID] ("ukore_browser",
    kept for backward compatibility — see plugin.py) under
    "extra_root_tabs": a flat `[{"id", "sub_path", "label"}]` list — replacing
    the old per-connection-keyed "root_tab_overrides" shape, which is left
    in place, unread and unwritten by this page, for any repo that already
    had one saved. Read back on the Maya side by
    maya-scripts/UkoreBrowser/core/repo_context.py's
    get_pipeline_root_tabs()."""

    def __init__(self, parent=None, *, api):
        super().__init__(parent)
        self._api = api
        self._project_id: str | None = None
        self._repo_id: str | None = None
        # Parallel to table rows: the extra dict for the row at that index.
        self._row_data: list[dict] = []

        form = _load_ui("MayaFileBrowserSettingsWindow.ui", self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(form)

        self._table: QTableWidget = form.findChild(QTableWidget, "tableWidget_extra_path")
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnHidden(2, True)  # "Used Connect Path" — no longer meaningful, see class docstring
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

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
            self._table.setRowCount(0)
            self._row_data = []
            self._btn_add.setEnabled(False)
            return

        self._btn_add.setEnabled(True)
        self._reload_table()

    def _active_repo(self):
        if self._project_id is None or self._repo_id is None:
            return None
        try:
            return self._api.metadata.get_repo(self._project_id, self._repo_id)
        except NotFoundError:
            return None

    def _active_repo_root(self) -> Path | None:
        repo = self._active_repo()
        if repo is None:
            return None
        return Path(self._api.local_config.workspace_root) / repo.local_path

    def _active_repo_name(self) -> str:
        repo = self._active_repo()
        return repo.name if repo is not None else ""

    def _reload_table(self) -> None:
        self._table.setRowCount(0)
        self._row_data = []
        for extra in self._get_extras():
            self._append_row(extra)

    def _append_row(self, extra: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(extra.get("label", "")))
        self._table.setItem(row, 1, QTableWidgetItem(extra.get("sub_path", "")))
        self._row_data.append(extra)

    def _get_extras(self) -> list[dict]:
        return self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID).get(
            "extra_root_tabs", []
        )

    def _mutate_data(self, mutate) -> None:
        data = dict(self._api.metadata.get_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID))
        mutate(data)
        self._api.metadata.set_repo_plugin_data(self._project_id, self._repo_id, TOOL_ID, data)

    def _write_extra(self, *, extra_id: str, tab_name: str, relative_path: str) -> None:
        def mutate(data):
            extras = [e for e in data.get("extra_root_tabs", []) if e.get("id") != extra_id]
            extras.append({"id": extra_id, "sub_path": relative_path, "label": tab_name})
            data["extra_root_tabs"] = extras

        self._mutate_data(mutate)
        self._reload_table()

    def _open_dialog(self, **kwargs) -> _AddExtraPathDialog | None:
        root = self._active_repo_root()
        if root is None:
            QMessageBox.warning(self, "Add Extra Tab Path", "No active repo — select a repo first.")
            return None
        return _AddExtraPathDialog(self, repo_root=root, repo_name=self._active_repo_name(), **kwargs)

    def _on_add_clicked(self) -> None:
        if self._project_id is None or self._repo_id is None:
            return

        dialog = self._open_dialog()
        if dialog is None or dialog.exec() != QDialog.Accepted:
            return

        self._write_extra(
            extra_id=str(uuid.uuid4()),
            tab_name=dialog.result_tab_name,
            relative_path=dialog.result_relative_path,
        )

    def _on_table_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        self._table.selectRow(row)

        menu = QMenu(self)
        edit_action = menu.addAction("Edit...")
        remove_action = menu.addAction("Remove")
        action = menu.exec(self._table.viewport().mapToGlobal(pos))
        if action == edit_action:
            self._edit_row(row)
        elif action == remove_action:
            self._remove_row(row)

    def _edit_row(self, row: int) -> None:
        extra = self._row_data[row]
        dialog = self._open_dialog(
            initial_tab_name=extra.get("label", ""),
            initial_relative_path=extra.get("sub_path", ""),
            confirm_text="Change",
        )
        if dialog is None or dialog.exec() != QDialog.Accepted:
            return

        self._write_extra(
            extra_id=extra.get("id", str(uuid.uuid4())),
            tab_name=dialog.result_tab_name,
            relative_path=dialog.result_relative_path,
        )

    def _remove_row(self, row: int) -> None:
        extra = self._row_data[row]
        display_name = extra.get("label") or extra.get("sub_path", "")
        confirm = QMessageBox.question(
            self,
            "Remove Extra Tab Path",
            f'Remove the "{display_name}" tab?',
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        extra_id = extra.get("id")

        def mutate(data):
            data["extra_root_tabs"] = [e for e in data.get("extra_root_tabs", []) if e.get("id") != extra_id]

        self._mutate_data(mutate)
        self._reload_table()


def migrate_legacy_data(api) -> None:
    """One-time cutover from the old data/plugins/core/ukore_browser.json
    PluginConfigStore blob's "repo_hidden_root_tabs" key into each repo's
    own Repo.plugin_data. Safe to call on every register(), not just once
    — a previous successful run leaves this key empty, so there's nothing
    left to migrate."""
    from plugin_api import NotFoundError

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
