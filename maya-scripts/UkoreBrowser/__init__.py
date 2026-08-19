import maya.cmds as cmds

try:
    from UkoreMenu import registry, MenuItemSpec, ReloadHandlerSpec, reload_package

    registry.register_item(
        MenuItemSpec(
            id="maya_file_browser",
            label="Maya File Browser...",
            category="General",
            command="from tmlib.core import File; File.launch('UkoreBrowser')",
            order=10,
        )
    )
    registry.register_reload_handler(
        ReloadHandlerSpec(
            id="ukore_browser",
            label="Maya File Browser",
            callback=lambda: reload_package("UkoreBrowser"),
            order=20,
        )
    )
except ImportError:
    pass