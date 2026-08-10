from __future__ import annotations

from tmlib.module.PySide import QtCore

from UkoreBrowser.core.version_filter import ALLOWED_EXT_PATTERN, compute_latest_version_names


class CleanExtFilter(QtCore.QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter_latest_version = False
        self._latest_versions_map: set[str] = set()
        self._current_parent_ptr = None

        self.setFilterRegularExpression(
            QtCore.QRegularExpression(
                ALLOWED_EXT_PATTERN.pattern,
                QtCore.QRegularExpression.CaseInsensitiveOption,
            )
        )

    # ------------------------------------------------------
    # SORTING SPEED-UP
    # ------------------------------------------------------
    def lessThan(self, left, right):
        model = self.sourceModel()
        col = left.column()

        if col == 0:  # Name
            return model.data(left).lower() < model.data(right).lower()
        elif col == 1:  # Size
            return model.size(left) < model.size(right)
        elif col == 3:  # Date Modified
            return model.lastModified(left) < model.lastModified(right)

        return super().lessThan(left, right)

    # ------------------------------------------------------
    # FILTER ROW
    # ------------------------------------------------------
    def filterAcceptsRow(self, row, parent):
        model = self.sourceModel()
        idx = model.index(row, 0, parent)

        if not idx.isValid():
            return False

        if model.isDir(idx):
            return True

        filename = model.data(idx)

        if not self.filterRegularExpression().match(filename).hasMatch():
            return False

        if self.filter_latest_version:
            parent_ptr = parent.internalPointer()

            if parent_ptr != self._current_parent_ptr:
                self._recalc_latest_versions(parent)
                self._current_parent_ptr = parent_ptr

            if filename not in self._latest_versions_map:
                return False

        return True

    # ------------------------------------------------------
    # LATEST VERSION CALC (delegates to the pure core helper)
    # ------------------------------------------------------
    def _recalc_latest_versions(self, parent):
        model = self.sourceModel()
        row_count = model.rowCount(parent)

        entries = []
        for r in range(row_count):
            idx = model.index(r, 0, parent)
            entries.append((model.data(idx), model.isDir(idx)))

        self._latest_versions_map = compute_latest_version_names(entries)

    def invalidate(self):
        self._current_parent_ptr = None
        self._latest_versions_map = set()
        super().invalidate()
