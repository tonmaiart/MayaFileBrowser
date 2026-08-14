import maya.cmds as cmds

try:
    from UkoreMenu import registry, MenuItemSpec

    registry.register_item(
        MenuItemSpec(
            id="maya_file_browser",
            label="Maya File Browser...",
            category="General",
            command="from tmlib.core import File; File.launch('UkoreBrowser')",
            order=10,
        )
    )
except ImportError:
    pass