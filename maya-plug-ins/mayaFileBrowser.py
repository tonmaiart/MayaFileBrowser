"""Maya plug-in: adds a "Maya File Browser..." item to the very top of the
existing "Ukore Studio Tool" menu (built by MayaToolkit's own
maya-plug-ins/ukoreMaya.py) WITHOUT editing that file — deliberate, so this
plugin stays a self-contained cache/plugins/ clone instead of coupling to
MayaToolkit's own menu-building code. Convention-only coupling, same shape
as every PluginConfigStore id convention elsewhere in this codebase: this
only assumes the menu's name/parent/label (MENU_MAIN/MENU_PARENT/MENU_LABEL
below) stay those exact strings, matching ukoreMaya.py's own MENU_MAIN/
MENU_LABEL/MENU_PARENT constants — no import of MayaToolkit's modules.

Ordering: this plugin's own manifest `requires: ["maya_toolkit", ...]`
(see ../plugin.py) documents the intent, but the actual ordering guarantee
comes from maya_launcher's force-load step iterating contributed tool ids
*sorted alphabetically* ("maya_toolkit" < "ukore_browser") — MayaToolkit's
ukoreMaya.py plug-in is force-loaded (and its own evalDeferred(loadMenu)
queued) before this one, so "UkoreStudioToolMenu" already exists by the
time _add_menu_item below runs. Falls back to creating the menu itself
(same call ukoreMaya.py's loadMenu() makes) if it's somehow missing —
e.g. MayaToolkit disabled for this repo while this plugin stays enabled —
so this doesn't hard-depend on that ordering holding.

insertAfter="" is Maya's documented way to place a new menuItem at the
very top of an existing menu, ahead of every item already in it — that's
how this lands first regardless of how many tools MayaToolkit itself adds
above it.
"""

import maya.cmds as cmds
import maya.api.OpenMaya as om

MENU_MAIN = "UkoreStudioToolMenu"
MENU_LABEL = "Ukore Studio Tool"
MENU_PARENT = "MayaWindow"

ITEM_NAME = "mayaFileBrowserMenuItem"


def maya_useNewAPI():
    pass


def _add_menu_item():
    if not cmds.menu(f"{MENU_PARENT}|{MENU_MAIN}", exists=True):
        cmds.menu(
            MENU_MAIN,
            label=MENU_LABEL,
            parent=MENU_PARENT,
            tearOff=True,
            allowOptionBoxes=True,
        )

    if cmds.menuItem(ITEM_NAME, exists=True):
        cmds.deleteUI(ITEM_NAME)

    cmds.menuItem(
        ITEM_NAME,
        label="Maya File Browser...",
        parent=MENU_MAIN,
        insertAfter="",  # top of the menu, ahead of everything else in it
        command="from tmlib.core import File; File.launch('UkoreBrowser')",
    )


def _post_load_setup():
    _add_menu_item()


def initializePlugin(plugin):
    om.MFnPlugin(plugin)
    # Deferred, same reasoning as ukoreMaya.py's own initializePlugin:
    # MayaLauncher force-loads every contributed plug-in very early, before
    # "MayaWindow" (and MayaToolkit's own menu) necessarily exist yet.
    cmds.evalDeferred(_post_load_setup)


def uninitializePlugin(plugin):
    om.MFnPlugin(plugin)
    if cmds.menuItem(ITEM_NAME, exists=True):
        cmds.deleteUI(ITEM_NAME)
