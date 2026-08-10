# Backward-compat shim: `tmlib.core.File.launch("UkoreBrowser")` does
# `importlib.import_module("UkoreBrowser.interface").MainWindow()` — this
# import path is a hard contract used by UkoreMaya/core/menu_utils.py and
# function.py, so it must keep resolving even though the real implementation
# now lives under UkoreBrowser/ui/main_window.py.
from UkoreBrowser.ui.main_window import MainWindow

__all__ = ["MainWindow"]
