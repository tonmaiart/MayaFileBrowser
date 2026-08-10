"""QMenu builders factored out of MainWindow.build_setting_menu — each just
wires actions to callbacks the caller supplies, no state of its own."""

from __future__ import annotations

import os
from functools import partial

from tmlib.module.PySide import QAction, QtWidgets

from UkoreMaya.core import template_ui


def build_recent_menu(parent, recent_files: list[str], on_open):
    """Returns (menu, name_to_path). `on_open(file_name)` fires on click."""
    menu = QtWidgets.QMenu("ไฟล์ล่าสุด...", parent)
    menu.setStyleSheet(template_ui.get_menu_stylesheet())

    name_to_path: dict[str, str] = {}
    for path in recent_files:
        file_name = os.path.basename(path)
        name_to_path[file_name] = path
        act = QAction(file_name, parent)
        act.triggered.connect(partial(on_open, file_name))
        menu.addAction(act)

    return menu, name_to_path


def build_more_menu(parent, on_open_google_drive, on_reload):
    menu = QtWidgets.QMenu(parent)
    menu.setStyleSheet(template_ui.get_menu_stylesheet())

    open_google_drive = QAction("เช็คสถานะซิงค์ Drive", parent)
    open_google_drive.triggered.connect(on_open_google_drive)
    menu.addAction(open_google_drive)

    menu.addSeparator()

    reload_action = QAction("รีโหลด", parent)
    reload_action.triggered.connect(on_reload)
    menu.addAction(reload_action)

    return menu


def build_create_new_menu(parent, on_create):
    menu = QtWidgets.QMenu(parent)
    for type_key, label in (("folder", "Folder"), ("maya", "Maya"), ("blender", "Blender")):
        act = QAction(label, parent)
        act.triggered.connect(partial(on_create, type_key))
        menu.addAction(act)
    return menu
