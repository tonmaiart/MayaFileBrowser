from __future__ import annotations

from tmlib.module.PySide import QtCore, QtGui, QtWidgets


class PopupMessage(QtWidgets.QDialog):
    def __init__(self, text, duration=5000, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.Dialog
            | QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setModal(False)

        layout = QtWidgets.QVBoxLayout(self)
        self.label = QtWidgets.QLabel(text)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet(
            """
            QLabel {
                background-color: rgba(30, 30, 30, 200);
                color: white;
                font-size: 22px;
                font-weight: bold;
                border-radius: 15px;
                padding: 25px;
            }
        """
        )
        layout.addWidget(self.label)
        self.setLayout(layout)

        self.opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_in = QtCore.QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in.setDuration(400)
        self.fade_in.setStartValue(0)
        self.fade_in.setEndValue(1)

        self.fade_out = QtCore.QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out.setDuration(800)
        self.fade_out.setStartValue(1)
        self.fade_out.setEndValue(0)
        self.fade_out.finished.connect(self.close)

        QtCore.QTimer.singleShot(duration, self.fade_out.start)
        self.fade_in.start()

    def show_centered(self):
        """ให้ popup อยู่กลางหน้าจอของ parent"""
        if self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - self.height()) // 2
        else:
            screen = QtGui.QGuiApplication.primaryScreen().availableGeometry()
            x = (screen.width() - self.width()) // 2
            y = (screen.height() - self.height()) // 2
        self.move(x, y)
        self.show()
