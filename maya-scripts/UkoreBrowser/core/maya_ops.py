"""Maya-cmds-bound operations for UkoreBrowser. Kept separate from ui/ so the
window-wiring code never touches maya.cmds directly."""

from __future__ import annotations

import os

import maya.cmds as cmds

from UkoreMaya.core import menu_utils, function


def get_current_workspace() -> str:
    return cmds.workspace(q=True, rd=True)


def get_current_scene_path() -> str:
    return cmds.file(query=True, sceneName=True)


def is_scene_modified() -> bool:
    return cmds.file(query=True, modified=True)


def save_current_scene() -> None:
    cmds.file(save=True)


def open_scene(path: str, force: bool = False) -> None:
    cmds.file(path, open=True, force=force)
    menu_utils.update_references()


def set_workspace_to(path: str) -> None:
    cmds.workspace(path, openWorkspace=True)


def save_scene_as(dest_path: str) -> None:
    cmds.file(rename=dest_path)
    cmds.file(save=True, force=True, type="mayaAscii")


def import_as_reference(path: str) -> None:
    _create_reference(path)
    function.import_all_picker()


def _create_reference(path: str) -> None:
    filename = os.path.basename(path)

    if "publish" in path:
        split_name = os.path.normpath(path).split(os.sep)
        namespace = "{}_{}_{}".format(split_name[-5], split_name[-4], split_name[-3])
        group_name = namespace
    else:
        namespace = os.path.splitext(filename)[0]
        group_name = os.path.basename(os.path.dirname(path))

    try:
        cmds.file(
            path,
            reference=True,
            namespace=namespace,
            ignoreVersion=True,
            mergeNamespacesOnClash=False,
        )

        print("# Import Reference Info")
        print("- Namespaces : {}".format(namespace))

        top_nodes = cmds.ls(assemblies=True, long=True)

        to_parent = []
        for node in top_nodes:
            short_name = node.split("|")[-1]
            if short_name.startswith(namespace + ":"):
                to_parent.append(node)
        print("To Parent : ", to_parent)

        if len(to_parent) > 1:
            if not cmds.objExists(group_name):
                top_grp = cmds.group(em=True, name=group_name)
            else:
                top_grp = group_name

            for obj in to_parent:
                try:
                    cmds.parent(obj, top_grp)
                except Exception:
                    pass

        cmds.inViewMessage(
            amg="<hl>Referenced :</hl> {}".format(group_name),
            pos="midCenter",
            fade=True,
        )

    except Exception as e:
        cmds.confirmDialog(title="Error", message=str(e))
