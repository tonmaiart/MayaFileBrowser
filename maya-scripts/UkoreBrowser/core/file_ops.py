"""Plain filesystem operations for UkoreBrowser — no Qt, no Maya. UI code
catches exceptions from these and shows the appropriate dialog."""

from __future__ import annotations

import os
import shutil
import subprocess


def open_directory(path: str) -> None:
    subprocess.Popen('explorer "{}"'.format(os.path.normpath(path)))


def create_folder(parent_dir: str, name: str) -> str:
    new_path = os.path.join(parent_dir, name)
    os.makedirs(new_path, exist_ok=False)
    return new_path


def create_from_template(template_path: str, parent_dir: str, name: str, ext: str) -> str:
    new_file = os.path.join(parent_dir, "{}{}".format(name, ext))
    shutil.copy(template_path, new_file)
    return new_file


def delete_path(path: str) -> None:
    if os.path.isfile(path):
        os.remove(path)
    else:
        shutil.rmtree(path)


def rename_path(path: str, new_name: str) -> str:
    folder = os.path.dirname(path)
    new_path = os.path.join(folder, new_name)
    os.rename(path, new_path)
    return new_path
