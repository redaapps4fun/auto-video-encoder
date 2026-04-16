"""System tray icon with minimize-to-tray and context menu."""

from __future__ import annotations

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal

from ui.resources import APP_NAME, get_icon_path


class TrayIcon(QSystemTrayIcon):
    """System tray icon for the encoder application.

    Provides Show/Exit context menu and handles close-to-tray behavior.
    """

    show_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        icon = QIcon(get_icon_path())
        self.setIcon(icon)
        self.setToolTip(APP_NAME)

        menu = QMenu()
        action_show = QAction(f"Show {APP_NAME}", menu)
        action_show.triggered.connect(self.show_requested.emit)
        menu.addAction(action_show)

        menu.addSeparator()

        action_exit = QAction("Exit", menu)
        action_exit.triggered.connect(self.exit_requested.emit)
        menu.addAction(action_exit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_requested.emit()

    def show_balloon(self, title: str, message: str):
        self.showMessage(title, message, QSystemTrayIcon.Information, 3000)

    @staticmethod
    def confirm_exit_while_encoding() -> bool:
        result = QMessageBox.question(
            None,
            APP_NAME,
            "An encode is running. Are you sure you want to exit?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes
