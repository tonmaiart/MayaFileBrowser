import os
from functools import partial
from pathlib import Path

from tmlib.module.PySide import QtCore, QtWidgets

import maya.cmds as cmds

from tmlib.ui.interface_template import ToolkitWindow
from UkoreMaya.core import template_ui

import UkoreBrowser
from UkoreBrowser.core import repo_context, browser_config, file_ops, maya_ops
from UkoreBrowser.ui.file_model import CleanExtFilter
from UkoreBrowser.ui.popup import PopupMessage
from UkoreBrowser.ui import menus

# The package root — .../plugins/repo_internal/UkoreBrowser/maya-scripts/UkoreBrowser
# — no matter which submodule this file lives under, so template/ and ui.ui
# keep resolving correctly regardless of nesting depth.
PACKAGE_DIR = Path(UkoreBrowser.__file__).resolve().parent


class MainWindow(ToolkitWindow):
    BLENDER_TEMPLATE = str(PACKAGE_DIR / "template" / "template.blend")
    MAYA_TEMPLATE = str(PACKAGE_DIR / "template" / "template.ma")

    MAX_RECENT = 10

    # ------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------
    def __init__(self):
        # Hardcoded, not derived from __file__: ToolkitWindow forwards this to
        # `importlib.import_module(toolkit_name)` to locate ui.ui, so it must
        # be the literal package name regardless of which file defines this
        # class.
        super(MainWindow, self).__init__("UkoreBrowser")

        # Root path: the active UkoreHub repo, falling back to Maya's current
        # workspace when there isn't one. Never the current scene file's
        # folder — see repo_context.get_root_path().
        self.root_path = repo_context.get_root_path().replace("\\", "/")
        self.config = browser_config.BrowserConfig(self.root_path, max_recent=self.MAX_RECENT)

        maya_ops.set_workspace_to(self.root_path)

        # Where we land on open: the current scene's folder if there is one
        # (and it's inside root_path), else root_path itself — separate from
        # root_path so the Miller columns below stay rooted at the whole
        # repo regardless of where the current scene happens to sit.
        self.current_browse_path = repo_context.get_initial_browse_path(self.root_path).replace("\\", "/")
        print("Default Directory : {}".format(self.current_browse_path))

        self.ui.lineEdit_current_path.setText(self.current_browse_path)

        # Setup FileSystemModel
        self.fs_model = QtWidgets.QFileSystemModel()
        self.fs_model.setRootPath(self.root_path)
        self.fs_model.setFilter(QtCore.QDir.NoDotAndDotDot | QtCore.QDir.AllEntries)

        self.proxy = CleanExtFilter()
        self.proxy.setSourceModel(self.fs_model)
        self.proxy.filter_latest_version = False

        self.ui.tableView_files.setModel(self.proxy)
        self.ui.tableView_files.setSortingEnabled(True)

        self.ui.tableView_files.setRootIndex(
            self.proxy.mapFromSource(self.fs_model.index(self.root_path))
        )

        # Columns
        self.columns = [
            self.ui.listWidget_project,
            self.ui.listWidget_class,
            self.ui.listWidget_scene,
            self.ui.listWidget_shot,
            self.ui.listWidget_element,
        ]

        self.search_boxes = [
            self.ui.lineEdit_search_project,
            self.ui.lineEdit_search_class,
            self.ui.lineEdit_search_scene,
            self.ui.lineEdit_search_shot,
            self.ui.lineEdit_search_element,
        ]

        self.fs_model.directoryLoaded.connect(self.on_directory_loaded)

        # SIGNALS
        self.connect_signals()

        # Context menu
        self.ui.tableView_files.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.ui.tableView_files.customContextMenuRequested.connect(
            self.open_context_menu
        )
        self.ui.tableView_files.setColumnHidden(2, True)

        # Recent
        self.build_setting_menu()

        # Root tabs (active repo + pipeline inputs/outputs)
        self._build_root_tabs()

        # INITIAL LOAD
        self.sync_columns_from_path()
        self.update_file_list()
        self.update_thumbnail()

    # ------------------------------------------------------------
    # ROOT TABS (active repo + pipeline inputs/outputs)
    # ------------------------------------------------------------
    def _build_root_tabs(self):
        """Row of buttons above the file table (row 0 of the central grid —
        unused by ui.ui, whose rows start at 1) for switching root_path
        between the active repo and its declared pipeline input/output
        repos (plugins/core/project_editor) — see
        repo_context.get_pipeline_root_tabs(). No-ops (adds nothing) if
        there's no active repo to build tabs from."""
        tabs = repo_context.get_pipeline_root_tabs()
        if not tabs:
            return

        central_layout = self.ui.centralWidget().layout()

        tab_bar = QtWidgets.QWidget()
        tab_layout = QtWidgets.QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(5, 0, 5, 0)
        tab_layout.setSpacing(4)

        self.root_tab_group = QtWidgets.QButtonGroup(tab_bar)
        self.root_tab_group.setExclusive(True)
        self.root_tab_buttons = {}

        for tab in tabs:
            btn = QtWidgets.QPushButton(tab["label"])
            btn.setCheckable(True)
            btn.setStyleSheet(
                """
                QPushButton {
                    color: white;
                    background: rgba(12, 12, 12, 255);
                    border: none;
                    border-radius: 4px;
                    padding: 4px 10px;
                }
                QPushButton:checked {
                    background: qlineargradient(spread:pad, x1:1, y1:0, x2:1, y2:1, stop:0 rgba(243, 159, 89, 255), stop:1 rgba(197, 131, 76, 255));
                    color: black;
                }
                """
            )
            btn.clicked.connect(partial(self._switch_root, tab["path"]))
            tab_layout.addWidget(btn)
            self.root_tab_group.addButton(btn)
            self.root_tab_buttons[os.path.normpath(tab["path"])] = btn

        tab_layout.addStretch()
        central_layout.addWidget(tab_bar, 0, 0)

        self._highlight_active_root_tab()

    def _highlight_active_root_tab(self):
        btn = self.root_tab_buttons.get(os.path.normpath(self.root_path))
        if btn is not None:
            btn.setChecked(True)

    def _switch_root(self, path):
        """Re-roots the whole browser (fs model, Miller columns, recent
        files) at a different tab's repo — same shape __init__ uses to set
        up root_path the first time."""
        if os.path.normpath(path) == os.path.normpath(self.root_path):
            return

        self.root_path = path.replace("\\", "/")
        self.config = browser_config.BrowserConfig(self.root_path, max_recent=self.MAX_RECENT)
        maya_ops.set_workspace_to(self.root_path)
        self.fs_model.setRootPath(self.root_path)

        self._highlight_active_root_tab()
        self.build_setting_menu()
        self.update_current_path(self.root_path)

    # ------------------------------------------------------------
    # RECENT-VERSION FILTER (no checkbox currently wired to this in ui.ui —
    # kept for a future toggle without needing to touch the proxy model)
    # ------------------------------------------------------------
    def on_latest_version_filter_toggled(self, state):
        is_checked = state == QtCore.Qt.Checked
        self.proxy.filter_latest_version = is_checked
        self.proxy.invalidate()

    def show_popup(self, text, duration=5000):
        """Show a floating popup message inside window."""
        popup = PopupMessage(text, duration, self)
        popup.adjustSize()
        popup.show_centered()

    # ------------------------------------------------------------
    # RECENT FILES
    # ------------------------------------------------------------
    def add_recent_file(self, path):
        self.config.add_recent_file(path)
        self.build_setting_menu()

    def build_setting_menu(self):
        """Create menu objects but DO NOT attach to QPushButton (it won't work)."""
        self.recent_menu, self.dict_recent_path = menus.build_recent_menu(
            self, self.config.get_recent_files(), self.open_recent
        )
        self.more_menu = menus.build_more_menu(
            self, self.open_google_drive_app, self.reload
        )
        self.create_new_menu = menus.build_create_new_menu(self, self.create_new)

    def show_recent_menu(self):
        btn = self.ui.pushButton_shortcut_recent
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        self.recent_menu.exec_(pos)

    def show_more_menu(self):
        btn = self.ui.pushButton_setting
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        self.more_menu.exec_(pos)

    def show_create_new_menu(self):
        btn = self.ui.pushButton_create_new
        pos = btn.mapToGlobal(btn.rect().bottomLeft())
        self.create_new_menu.exec_(pos)

    def open_recent(self, file_name):
        path = self.dict_recent_path[file_name]
        self.update_current_path(path)

    def save_as(self):
        current_file_name = os.path.basename(maya_ops.get_current_scene_path())

        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save as New File ", "Name:", text=current_file_name
        )

        if not ok or not name.strip():
            return

        save_path = os.path.join(self.current_browse_path, name)
        maya_ops.save_scene_as(save_path + ".ma")

    # ------------------------------------------------------------
    # SIGNALS
    # ------------------------------------------------------------
    def connect_signals(self):
        for i, lw in enumerate(self.columns):
            lw.itemClicked.connect(partial(self.on_column_clicked, i))

        for i, le in enumerate(self.search_boxes):
            le.textChanged.connect(partial(self.filter_column, i))

        self.ui.lineEdit_current_path.returnPressed.connect(self.on_path_entered)
        self.ui.pushButton_go_back.clicked.connect(self.go_back)

        self.ui.lineEdit_search_file.textChanged.connect(self.search_current_folder)
        self.ui.tableView_files.doubleClicked.connect(self.on_file_double_clicked)

        self.ui.pushButton_setting.clicked.connect(self.show_more_menu)
        self.ui.pushButton_shortcut_recent.clicked.connect(self.show_recent_menu)
        self.ui.pushButton_create_new.clicked.connect(self.show_create_new_menu)

        self.ui.pushButton_open_current_folder.clicked.connect(
            lambda x: file_ops.open_directory(self.current_browse_path)
        )

        self.ui.pushButton_save_file.clicked.connect(self.save_as)

    def on_path_entered(self):
        print(
            "======= # Path Entered : {} # =======".format(
                self.ui.lineEdit_current_path.text()
            )
        )
        self.update_current_path(self.ui.lineEdit_current_path.text())

    # ------------------------------------------------------------
    # DIRECTORY LOADED
    # ------------------------------------------------------------
    def on_directory_loaded(self, path):
        h = self.ui.tableView_files.horizontalHeader()
        h.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        h.setFixedHeight(22)

    # ------------------------------------------------------------
    # COLUMN SYSTEM
    # ------------------------------------------------------------
    def load_column_items(self, level, path):
        lw = self.columns[level]
        lw.clear()

        if not os.path.isdir(path):
            return

        try:
            entries = sorted(os.listdir(path))
        except Exception:
            return

        for name in entries:
            fp = os.path.join(path, name)
            if os.path.isdir(fp):
                lw.addItem(name)

    def sync_columns_from_path(self):
        """Rebuild ALL columns entirely from current_path."""
        for lw in self.columns:
            lw.blockSignals(True)
            lw.clear()

        try:
            rel = os.path.relpath(self.current_browse_path, self.root_path)
            parts = [] if rel == "." else rel.split(os.sep)

            self.load_column_items(0, self.root_path)
            p = self.root_path

            for level, name in enumerate(parts):
                if level >= len(self.columns):
                    break

                lw = self.columns[level]

                items = lw.findItems(name, QtCore.Qt.MatchExactly)
                if items:
                    lw.setCurrentItem(items[0])

                p = os.path.join(p, name)

                next_level = level + 1
                if next_level < len(self.columns):
                    self.load_column_items(next_level, p)

        finally:
            for lw in self.columns:
                lw.blockSignals(False)

    def on_column_clicked(self, level, current):
        if not current:
            return

        p = self.root_path
        for i in range(level + 1):
            it = self.columns[i].currentItem()
            if it:
                p = os.path.join(p, it.text())

        self.update_current_path(p.replace("\\", "/"))

    def filter_column(self, level, text):
        lw = self.columns[level]
        txt = text.lower()
        for i in range(lw.count()):
            item = lw.item(i)
            item.setHidden(txt not in item.text().lower())

    # ------------------------------------------------------------
    # PATH ENTRY + BACK
    # ------------------------------------------------------------
    def update_current_path(self, path):
        def update_path(path):
            self.current_browse_path = path
            self.ui.lineEdit_current_path.setText(self.current_browse_path)

            self.sync_columns_from_path()
            self.update_file_list()
            self.update_thumbnail()

            for lw in self.search_boxes:
                lw.setText("")

        path = os.path.normpath(path).replace("\\", "/")

        print("****** Update Current Path : {} ******".format(path))

        if os.path.isfile(path):
            print("Update Type : Set File : {}".format(path))

            folder = os.path.dirname(path)
            filename = os.path.basename(path)

            update_path(folder)

            QtCore.QTimer.singleShot(150, lambda: self.select_file_in_table(filename))
            return

        elif os.path.isdir(path):
            print("Update Type : Set Directory : {}".format(path))
            update_path(path)
            return

        else:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Path does not exist:\n{}".format(path)
            )

    def update_thumbnail(self):
        if os.path.isdir(self.current_browse_path):
            search_path = self.current_browse_path
        else:
            search_path = os.path.dirname(self.current_browse_path)

        thumbnail_path = os.path.join(search_path, "thumbnail.jpg")
        thumbnail_path = thumbnail_path.replace("\\", "/")
        print("find : ", thumbnail_path)
        if os.path.exists(thumbnail_path):
            stylesheet = (
                template_ui.get_table_view_browser_stylesheet()
                + """
            QTableView#tableView_files {{
                background-image: url("{}");
                background-repeat: no-repeat;
                background-position: center;
            background-size: 100px 100px;
                background-color: #1e1e1e;
            }}


            """.format(thumbnail_path)
            )
            self.ui.tableView_files.setStyleSheet(stylesheet)
        else:
            self.ui.tableView_files.setStyleSheet(
                template_ui.get_table_view_browser_stylesheet()
            )

    def select_file_in_table(self, filename):
        """Select the given filename inside tableView_files."""
        tv = self.ui.tableView_files
        model = self.fs_model
        proxy = self.proxy

        parent_index = model.index(self.current_browse_path)

        row_count = model.rowCount(parent_index)

        for row in range(row_count):
            index_source = model.index(row, 0, parent_index)
            name = model.fileName(index_source)

            if name.lower() == filename.lower():
                index_proxy = proxy.mapFromSource(index_source)
                tv.setCurrentIndex(index_proxy)
                tv.scrollTo(index_proxy)
                return

    def go_back(self):
        if os.path.abspath(self.current_browse_path) == os.path.abspath(self.root_path):
            return

        parent = os.path.dirname(self.current_browse_path).replace("\\", "/")

        self.update_current_path(parent)

    # ------------------------------------------------------------
    # FILE TABLE
    # ------------------------------------------------------------
    def update_file_list(self):
        if not os.path.isdir(self.current_browse_path):
            return

        idx = self.fs_model.index(self.current_browse_path)

        proxy_idx = self.proxy.mapFromSource(idx)
        self.ui.tableView_files.setRootIndex(proxy_idx)

        h = self.ui.tableView_files.horizontalHeader()
        h.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        h.setSectionResizeMode(1, QtWidgets.QHeaderView.Fixed)
        h.setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)

        h.resizeSection(1, 150)
        h.resizeSection(3, 150)

        tv = self.ui.tableView_files
        tv.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        tv.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        tv.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        tv.verticalHeader().hide()
        tv.verticalHeader().setDefaultSectionSize(1)
        tv.setIconSize(QtCore.QSize(10, 10))

    # ------------------------------------------------------------
    # FILE SEARCH
    # ------------------------------------------------------------
    def search_current_folder(self, text):
        txt = text.lower()
        parent_index = self.fs_model.index(self.current_browse_path)
        row_count = self.fs_model.rowCount(parent_index)

        for row in range(row_count):
            idx = self.fs_model.index(row, 0, parent_index)
            name = self.fs_model.fileName(idx).lower()
            self.ui.tableView_files.setRowHidden(row, txt not in name)

    # ------------------------------------------------------------
    def open_file_in_new_window(self, path):
        """Opens a file using os.startfile without any Maya logic or
        confirmation dialogs. Behaves like a standard system file open."""
        filename = os.path.basename(path)

        self.show_popup("Opening File (Default) : {}".format(filename))

        try:
            os.startfile(path)
            self.add_recent_file(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error: System Open Failed",
                "ไม่สามารถเปิดไฟล์ในระบบได้:\n{}\n\nError: {}".format(filename, e),
            )

    def on_file_double_clicked(self, index):
        src_index = self.proxy.mapToSource(index.sibling(index.row(), 0))
        path = self.fs_model.filePath(src_index)
        filename = os.path.basename(path)

        if os.path.isdir(path):
            self.update_current_path(path.replace("\\", "/"))
            return

        ext = os.path.splitext(filename)[1].lower()
        is_maya_file = ext in [".ma", ".mb"]

        self.show_popup("Opening File : {}".format(filename))

        try:
            if is_maya_file:
                if maya_ops.is_scene_modified():
                    current_scene_name = (
                        os.path.basename(maya_ops.get_current_scene_path()) or "Untitled Scene"
                    )

                    save_btn = QtWidgets.QMessageBox.Save
                    discard_btn = QtWidgets.QMessageBox.Discard
                    cancel_btn = QtWidgets.QMessageBox.Cancel

                    ask = QtWidgets.QMessageBox.warning(
                        self,
                        "Save Changes",
                        "Save changes to current scene?\n{}".format(current_scene_name),
                        save_btn | discard_btn | cancel_btn,
                        save_btn,
                    )

                    if ask == cancel_btn:
                        self.show_popup("การเปิดไฟล์ถูกยกเลิก", duration=1500)
                        return

                    elif ask == save_btn:
                        maya_ops.save_current_scene()
                        maya_ops.open_scene(path, force=False)

                    elif ask == discard_btn:
                        maya_ops.open_scene(path, force=True)

                else:
                    maya_ops.open_scene(path, force=False)

            else:
                ask = QtWidgets.QMessageBox.question(
                    self,
                    "ยืนยันการเปิดไฟล์",
                    "ต้องการเปิดไฟล์:\n{}\n\nในโปรแกรมใหม่หรือไม่?".format(filename),
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                    QtWidgets.QMessageBox.No,
                )

                if ask != QtWidgets.QMessageBox.Yes:
                    return

                os.startfile(path)

            self.add_recent_file(path)

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Error: File Operation Failed",
                "ไม่สามารถดำเนินการได้:\n{}\n\nError: {}".format(filename, e),
            )

    # ------------------------------------------------------------
    # CONTEXT MENU
    # ------------------------------------------------------------
    def open_context_menu(self, pos):
        proxy_index = self.ui.tableView_files.indexAt(pos)
        if not proxy_index.isValid():
            return

        src_index = self.proxy.mapToSource(proxy_index.sibling(proxy_index.row(), 0))
        file_path = self.fs_model.filePath(src_index)

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(template_ui.get_menu_stylesheet())

        act_copy_name = menu.addAction("Copy Name")
        act_copy = menu.addAction("Copy File Path")
        menu.addSeparator()
        act_delete = menu.addAction("Delete")
        act_rename = menu.addAction("Rename")
        menu.addSeparator()
        act_create_reference = menu.addAction("Import as Reference")
        menu.addSeparator()
        act_open_file_in_new_window = menu.addAction("Open File in New Section...")
        act = menu.exec_(self.ui.tableView_files.mapToGlobal(pos))

        if act == act_copy:
            QtWidgets.QApplication.clipboard().setText(file_path)
            self.show_popup("Copy Path", duration=500)
        elif act == act_delete:
            self.delete_with_confirm(file_path)
        elif act == act_rename:
            self.rename_dialog(file_path)
        elif act == act_create_reference:
            maya_ops.import_as_reference(file_path)
        elif act == act_open_file_in_new_window:
            self.open_file_in_new_window(path=file_path)
        elif act == act_copy_name:
            QtWidgets.QApplication.clipboard().setText(
                os.path.basename(file_path).split(".")[0]
            )
            self.show_popup("Copy Name", duration=500)

    def delete_with_confirm(self, path):
        name = os.path.basename(path)
        ask = QtWidgets.QMessageBox.question(
            self,
            "Delete",
            "ต้องการลบสิ่งนี้จริงหรือไม่?\n{}".format(name),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if ask != QtWidgets.QMessageBox.Yes:
            return

        try:
            file_ops.delete_path(path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

        self.update_file_list()

    # ------------------------------------------------------------
    # BUTTONS
    # ------------------------------------------------------------
    def reload(self):
        self.sync_columns_from_path()
        self.update_file_list()

    def open_google_drive_app(self):
        os.startfile("C:\\Program Files\\Google\\Drive File Stream\\launch.bat")
        self.show_popup("กำลังเปิด Google Drive App", duration=2000)

    def copy_current_path(self):
        QtWidgets.QApplication.clipboard().setText(self.current_browse_path)
        self.show_popup("คัดลอก Path โฟลเดอร์", duration=2000)

    def rename_dialog(self, path):
        old_name = os.path.basename(path)

        new_name, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename",
            "Rename:\n{}".format(old_name),
            text=old_name,
        )

        if not ok or not new_name.strip():
            return

        try:
            file_ops.rename_path(path, new_name)
            self.update_file_list()
            self.show_popup("Rename เสร็จแล้ว", duration=1500)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def create_new(self, type="folder"):
        """type: "folder", "maya", "blender" """
        default_name = os.path.basename(self.current_browse_path.rstrip("/"))

        name, ok = QtWidgets.QInputDialog.getText(
            self, "Create New {}".format(type.title()), "Name:", text=default_name
        )

        if not ok or not name.strip():
            return

        try:
            if type == "folder":
                file_ops.create_folder(self.current_browse_path, name)
                self.show_popup("สร้างโฟลเดอร์สำเร็จ", duration=1500)
            elif type == "maya":
                file_ops.create_from_template(self.MAYA_TEMPLATE, self.current_browse_path, name, ".ma")
                self.show_popup("สร้าง Maya file: {}.ma".format(name), duration=1500)
            elif type == "blender":
                file_ops.create_from_template(self.BLENDER_TEMPLATE, self.current_browse_path, name, ".blend")
                self.show_popup("สร้าง Blender file: {}.blend".format(name), duration=1500)
            else:
                return
            self.update_file_list()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
