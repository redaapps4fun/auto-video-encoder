"""Tools Setup Dialog - download or locate HandBrakeCLI and ffprobe."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QProgressBar, QFileDialog, QMessageBox, QSizePolicy,
)
from PySide6.QtGui import QFont, QIcon
from PySide6.QtCore import Qt, QThread, Signal, Slot

from tools import (
    get_tool_path, tool_valid, tools_present,
    download_ffprobe, download_handbrake,
    handbrake_available_for_download, HANDBRAKE_LINUX_INSTRUCTIONS,
)
from ui.resources import APP_NAME, get_icon_path


class _DownloadWorker(QThread):
    """Run a download function in a background thread."""

    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, download_fn, parent=None):
        super().__init__(parent)
        self._fn = download_fn

    def run(self):
        try:
            result = self._fn(lambda done, total: self.progress.emit(done, total))
            self.finished.emit(str(result))
        except Exception as exc:
            self.error.emit(str(exc))


class _ToolRow(QGroupBox):
    """A single tool's setup row: status, download/browse options, progress."""

    path_changed = Signal(str)

    def __init__(self, tool_label: str, tool_key: str,
                 download_fn, can_download: bool, parent=None):
        super().__init__(tool_label, parent)
        self._tool_key = tool_key
        self._download_fn = download_fn
        self._can_download = can_download
        self._worker: _DownloadWorker | None = None

        layout = QVBoxLayout(self)

        self._lbl_status = QLabel()
        self._lbl_status.setFont(QFont("Segoe UI", 9))
        layout.addWidget(self._lbl_status)

        option_row = QHBoxLayout()

        self._bg = QButtonGroup(self)
        self._rb_download = QRadioButton("Download automatically")
        self._rb_manual = QRadioButton("I'll provide the path")
        self._bg.addButton(self._rb_download, 0)
        self._bg.addButton(self._rb_manual, 1)

        if can_download:
            self._rb_download.setChecked(True)
        else:
            self._rb_manual.setChecked(True)
            self._rb_download.setEnabled(False)

        option_row.addWidget(self._rb_download)
        option_row.addWidget(self._rb_manual)
        option_row.addStretch()
        layout.addLayout(option_row)

        if not can_download and tool_key == "handbrake":
            lbl_linux = QLabel(HANDBRAKE_LINUX_INSTRUCTIONS)
            lbl_linux.setWordWrap(True)
            lbl_linux.setStyleSheet("color: #888; font-size: 11px; margin: 4px 0;")
            layout.addWidget(lbl_linux)

        browse_row = QHBoxLayout()
        self._edit_path = QLineEdit()
        self._edit_path.setPlaceholderText("Path to executable...")
        browse_row.addWidget(self._edit_path, 1)
        self._btn_browse = QPushButton("Browse")
        self._btn_browse.setFixedWidth(60)
        self._btn_browse.clicked.connect(self._on_browse)
        browse_row.addWidget(self._btn_browse)
        layout.addLayout(browse_row)

        action_row = QHBoxLayout()
        self._btn_download = QPushButton("Download Now")
        self._btn_download.setFixedWidth(120)
        self._btn_download.clicked.connect(self._start_download)
        action_row.addWidget(self._btn_download)
        self._progress = QProgressBar()
        self._progress.setMinimum(0)
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        action_row.addWidget(self._progress, 1)
        layout.addLayout(action_row)

        self._bg.idToggled.connect(self._on_mode_toggled)
        self._edit_path.textChanged.connect(lambda t: self.path_changed.emit(t))
        self._update_ui_mode()
        self._refresh_status()

    def _on_mode_toggled(self, id_: int, checked: bool):
        if checked:
            self._update_ui_mode()

    def _update_ui_mode(self):
        is_download = self._rb_download.isChecked()
        self._btn_download.setVisible(is_download and self._can_download)
        self._progress.setVisible(is_download and self._can_download)
        self._edit_path.setVisible(not is_download)
        self._btn_browse.setVisible(not is_download)

    def _refresh_status(self):
        default_path = get_tool_path(
            "HandBrakeCLI" if self._tool_key == "handbrake" else "ffprobe"
        )
        if default_path.is_file():
            self._lbl_status.setText(f"Installed:  {default_path}")
            self._lbl_status.setStyleSheet("color: green; font-weight: bold;")
            self._edit_path.setText(str(default_path))
        elif self._edit_path.text() and tool_valid(self._edit_path.text()):
            self._lbl_status.setText(f"Found:  {self._edit_path.text()}")
            self._lbl_status.setStyleSheet("color: green; font-weight: bold;")
        else:
            self._lbl_status.setText("Not found")
            self._lbl_status.setStyleSheet("color: red; font-weight: bold;")

    def _on_browse(self):
        filt = "Executable (*.exe);;All Files (*)" if sys.platform == "win32" else "All Files (*)"
        tool_name = "HandBrakeCLI" if self._tool_key == "handbrake" else "ffprobe"
        path, _ = QFileDialog.getOpenFileName(
            self, f"Select {tool_name}", "", filt
        )
        if path:
            self._edit_path.setText(path)
            self._refresh_status()

    def _start_download(self):
        self._btn_download.setEnabled(False)
        self._progress.setValue(0)
        self._worker = _DownloadWorker(self._download_fn, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_download_done)
        self._worker.error.connect(self._on_download_error)
        self._worker.start()

    @Slot(int, int)
    def _on_progress(self, done: int, total: int):
        if total > 0:
            self._progress.setValue(int(done * 100 / total))
        else:
            self._progress.setMaximum(0)

    @Slot(str)
    def _on_download_done(self, path: str):
        self._progress.setMaximum(100)
        self._progress.setValue(100)
        self._btn_download.setEnabled(True)
        self._edit_path.setText(path)
        self._refresh_status()
        self.path_changed.emit(path)

    @Slot(str)
    def _on_download_error(self, msg: str):
        self._progress.setMaximum(100)
        self._progress.setValue(0)
        self._btn_download.setEnabled(True)
        QMessageBox.critical(self, APP_NAME, f"Download failed:\n\n{msg}")

    def get_path(self) -> str:
        return self._edit_path.text().strip()

    def set_path(self, path: str):
        self._edit_path.setText(path)
        self._refresh_status()

    def is_valid(self) -> bool:
        return tool_valid(self.get_path())


class ToolsSetupDialog(QDialog):
    """Dialog shown on first launch (or when tools are missing) to
    let the user download or locate HandBrakeCLI and ffprobe.
    """

    def __init__(self, missing_hb: bool = True, missing_ff: bool = True,
                 current_hb: str = "", current_ff: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Tools Setup")
        self.setWindowIcon(QIcon(get_icon_path()))
        self.setMinimumWidth(560)
        self.setModal(True)

        layout = QVBoxLayout(self)

        header = QLabel(
            "The following CLI tools are needed for encoding.\n"
            "You can download them automatically or provide their locations."
        )
        header.setWordWrap(True)
        header.setFont(QFont("Segoe UI", 10))
        layout.addWidget(header)

        can_dl_hb = handbrake_available_for_download()
        self._row_hb = _ToolRow(
            "HandBrakeCLI", "handbrake",
            download_handbrake, can_dl_hb, self,
        )
        if current_hb:
            self._row_hb.set_path(current_hb)
        layout.addWidget(self._row_hb)

        self._row_ff = _ToolRow(
            "ffprobe", "ffprobe",
            download_ffprobe, True, self,
        )
        if current_ff:
            self._row_ff.set_path(current_ff)
        layout.addWidget(self._row_ff)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_continue = QPushButton("Continue")
        self._btn_continue.setFixedHeight(32)
        self._btn_continue.setFixedWidth(120)
        self._btn_continue.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self._btn_continue.clicked.connect(self._on_continue)
        btn_row.addWidget(self._btn_continue)
        layout.addLayout(btn_row)

        self._row_hb.path_changed.connect(self._validate)
        self._row_ff.path_changed.connect(self._validate)

        self._validate()

    def _validate(self):
        both_ok = self._row_hb.is_valid() and self._row_ff.is_valid()
        self._btn_continue.setEnabled(both_ok)

    def _on_continue(self):
        if not self._row_hb.is_valid():
            QMessageBox.warning(
                self, APP_NAME,
                "HandBrakeCLI path is not valid. Please download or browse to the executable."
            )
            return
        if not self._row_ff.is_valid():
            QMessageBox.warning(
                self, APP_NAME,
                "ffprobe path is not valid. Please download or browse to the executable."
            )
            return
        self.accept()

    def handbrake_path(self) -> str:
        return self._row_hb.get_path()

    def ffprobe_path(self) -> str:
        return self._row_ff.get_path()
