"""MainWindow - primary application window with all controls."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QPushButton, QLabel, QPlainTextEdit,
    QComboBox, QCheckBox, QFileDialog, QStackedWidget, QMessageBox,
)
from PySide6.QtGui import QFont, QIcon, QTextCursor
from PySide6.QtCore import QTimer, Slot

from config import ConfigManager
from encoder_engine import EncoderEngine
from tools import tool_valid
from ui.mode_abr import ABRModePanel
from ui.mode_crf import CRFModePanel
from ui.mode_advanced import AdvancedModePanel
from ui.tray_icon import TrayIcon
from ui.tools_setup import ToolsSetupDialog
from ui.resources import APP_NAME, VIDEO_EXTENSIONS, get_icon_path


class MainWindow(QMainWindow):

    def __init__(self, config: ConfigManager, parent: QWidget | None = None):
        super().__init__(parent)
        self._config = config
        self._engine: EncoderEngine | None = None
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._do_save)

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(get_icon_path()))
        self.setMinimumSize(620, 600)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        self._build_paths_group(root)
        self._build_mode_selector(root)
        self._build_common_controls(root)
        self._build_buttons(root)
        self._build_status_area(root)
        self._build_log(root)

        self._setup_tray()
        self._load_config()
        self._connect_change_signals()
        self._check_tools()

    # ==================================================================
    #  BUILD UI SECTIONS
    # ==================================================================

    def _build_paths_group(self, parent_layout: QVBoxLayout):
        grp = QGroupBox("Paths")
        form = QFormLayout(grp)

        self.edit_source = QLineEdit()
        btn_source = QPushButton("Browse")
        btn_source.setFixedWidth(60)
        btn_source.clicked.connect(lambda: self._browse_dir(self.edit_source, "Select Source Watch Folder"))
        row_source = QHBoxLayout()
        row_source.addWidget(self.edit_source, 1)
        row_source.addWidget(btn_source)
        form.addRow("Source Folder:", row_source)

        self.edit_output = QLineEdit()
        btn_output = QPushButton("Browse")
        btn_output.setFixedWidth(60)
        btn_output.clicked.connect(lambda: self._browse_dir(self.edit_output, "Select Output Root Folder"))
        row_output = QHBoxLayout()
        row_output.addWidget(self.edit_output, 1)
        row_output.addWidget(btn_output)
        form.addRow("Output Folder:", row_output)

        self.edit_hb = QLineEdit()
        btn_hb_browse = QPushButton("Browse")
        btn_hb_browse.setFixedWidth(60)
        btn_hb_browse.clicked.connect(lambda: self._browse_file(self.edit_hb, "Select HandBrakeCLI", "Executable (*.exe);;All Files (*)"))
        self.btn_hb_dl = QPushButton("Download")
        self.btn_hb_dl.setFixedWidth(70)
        self.btn_hb_dl.clicked.connect(lambda: self._download_tool("handbrake"))
        row_hb = QHBoxLayout()
        row_hb.addWidget(self.edit_hb, 1)
        row_hb.addWidget(btn_hb_browse)
        row_hb.addWidget(self.btn_hb_dl)
        form.addRow("HandBrakeCLI:", row_hb)

        self.edit_ff = QLineEdit()
        btn_ff_browse = QPushButton("Browse")
        btn_ff_browse.setFixedWidth(60)
        btn_ff_browse.clicked.connect(lambda: self._browse_file(self.edit_ff, "Select ffprobe", "Executable (*.exe);;All Files (*)"))
        self.btn_ff_dl = QPushButton("Download")
        self.btn_ff_dl.setFixedWidth(70)
        self.btn_ff_dl.clicked.connect(lambda: self._download_tool("ffprobe"))
        row_ff = QHBoxLayout()
        row_ff.addWidget(self.edit_ff, 1)
        row_ff.addWidget(btn_ff_browse)
        row_ff.addWidget(self.btn_ff_dl)
        form.addRow("ffprobe:", row_ff)

        self.edit_exts = QLineEdit()
        self.edit_exts.setPlaceholderText(".mkv .mp4 .avi .mov ...")
        form.addRow("Video Extensions:", self.edit_exts)

        parent_layout.addWidget(grp)

    def _build_mode_selector(self, parent_layout: QVBoxLayout):
        row = QHBoxLayout()
        row.addWidget(QLabel("Encoding Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("ABR Mode", "abr")
        self.combo_mode.addItem("CRF Mode", "crf")
        self.combo_mode.addItem("Advanced Mode", "advanced")
        row.addWidget(self.combo_mode, 1)
        parent_layout.addLayout(row)

        self.mode_stack = QStackedWidget()
        self.panel_abr = ABRModePanel()
        self.panel_crf = CRFModePanel()
        self.panel_advanced = AdvancedModePanel()
        self.mode_stack.addWidget(self.panel_abr)
        self.mode_stack.addWidget(self.panel_crf)
        self.mode_stack.addWidget(self.panel_advanced)
        parent_layout.addWidget(self.mode_stack)

        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)

    def _build_common_controls(self, parent_layout: QVBoxLayout):
        row = QHBoxLayout()

        self.chk_delete = QCheckBox("Delete source file when done")
        row.addWidget(self.chk_delete)

        row.addStretch()

        self.chk_auto_start = QCheckBox("Start watcher on app launch")
        row.addWidget(self.chk_auto_start)

        parent_layout.addLayout(row)

    def _build_buttons(self, parent_layout: QVBoxLayout):
        row = QHBoxLayout()

        self.btn_start = QPushButton("\u25b6  Start")
        self.btn_start.setFont(QFont("Segoe UI", 10, QFont.Bold))
        self.btn_start.setFixedHeight(34)
        self.btn_start.clicked.connect(self.start_encoder)
        row.addWidget(self.btn_start)

        self.btn_stop = QPushButton("\u25a0  Stop")
        self.btn_stop.setFont(QFont("Segoe UI", 10))
        self.btn_stop.setFixedHeight(34)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_encoder)
        row.addWidget(self.btn_stop)

        row.addStretch()

        btn_clear = QPushButton("Clear Log")
        btn_clear.clicked.connect(lambda: (self.log_view.clear(), self.edit_progress.clear()))
        row.addWidget(btn_clear)

        parent_layout.addLayout(row)

    def _build_status_area(self, parent_layout: QVBoxLayout):
        self.lbl_status = QLabel("Status:  Ready")
        self.lbl_status.setFont(QFont("Segoe UI", 9, QFont.Bold))
        parent_layout.addWidget(self.lbl_status)

        self.lbl_stats = QLabel("Processed: 0   Encoded: 0   Copied: 0   Skipped: 0   Queued: 0")
        self.lbl_stats.setFont(QFont("Consolas", 8))
        parent_layout.addWidget(self.lbl_stats)

        self.edit_progress = QLineEdit()
        self.edit_progress.setReadOnly(True)
        self.edit_progress.setFont(QFont("Consolas", 8))
        parent_layout.addWidget(self.edit_progress)

    def _build_log(self, parent_layout: QVBoxLayout):
        parent_layout.addWidget(QLabel("Activity Log:"))

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 8))
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        parent_layout.addWidget(self.log_view, 1)

    def _setup_tray(self):
        self._tray = TrayIcon(self)
        self._tray.show_requested.connect(self._show_from_tray)
        self._tray.exit_requested.connect(self._exit_app)
        self._tray.show()

    # ==================================================================
    #  CONFIG LOAD / SAVE
    # ==================================================================

    def _load_config(self):
        cfg = self._config
        self.edit_source.setText(cfg.get("source_base", ""))
        self.edit_output.setText(cfg.get("output_base", ""))
        self.edit_hb.setText(cfg.get("handbrake_cli", ""))
        self.edit_ff.setText(cfg.get("ffprobe", ""))

        exts = cfg.get("video_extensions", VIDEO_EXTENSIONS)
        self.edit_exts.setText(" ".join(exts))

        self.chk_delete.setChecked(cfg.get("delete_source", True))
        self.chk_auto_start.setChecked(cfg.get("auto_start_watcher", False))

        mode = cfg.get("encoding_mode", "abr")
        idx = self.combo_mode.findData(mode)
        if idx >= 0:
            self.combo_mode.setCurrentIndex(idx)

        self.panel_abr.load_from_config(cfg.get_section("abr"))
        self.panel_crf.load_from_config(cfg.get_section("crf"))
        self.panel_advanced.load_from_config(cfg.get_section("advanced"))

    def _schedule_save(self):
        self._save_timer.start()

    def _do_save(self):
        cfg = self._config
        cfg.set("source_base", self.edit_source.text())
        cfg.set("output_base", self.edit_output.text())
        cfg.set("handbrake_cli", self.edit_hb.text())
        cfg.set("ffprobe", self.edit_ff.text())

        exts_text = self.edit_exts.text().strip()
        cfg.set("video_extensions", [e.strip().lower() for e in exts_text.split() if e.strip()])

        cfg.set("delete_source", self.chk_delete.isChecked())
        cfg.set("auto_start_watcher", self.chk_auto_start.isChecked())
        cfg.set("encoding_mode", self.combo_mode.currentData())

        cfg.set_section("abr", self.panel_abr.save_to_config())
        cfg.set_section("crf", self.panel_crf.save_to_config())
        cfg.set_section("advanced", self.panel_advanced.save_to_config())

        cfg.save()

    def _connect_change_signals(self):
        for edit in [self.edit_source, self.edit_output, self.edit_hb,
                     self.edit_ff, self.edit_exts]:
            edit.textChanged.connect(self._schedule_save)
        self.chk_delete.toggled.connect(self._schedule_save)
        self.chk_auto_start.toggled.connect(self._schedule_save)
        self.combo_mode.currentIndexChanged.connect(self._schedule_save)

        self.panel_abr.changed.connect(self._schedule_save)
        self.panel_crf.changed.connect(self._schedule_save)
        self.panel_advanced.changed.connect(self._schedule_save)

    # ==================================================================
    #  MODE SWITCHING
    # ==================================================================

    def _on_mode_changed(self, index: int):
        self.mode_stack.setCurrentIndex(index)

    # ==================================================================
    #  BROWSE HELPERS
    # ==================================================================

    def _browse_dir(self, target: QLineEdit, title: str):
        path = QFileDialog.getExistingDirectory(self, title, target.text())
        if path:
            target.setText(path)

    def _browse_file(self, target: QLineEdit, title: str, filt: str):
        path, _ = QFileDialog.getOpenFileName(self, title, str(Path(target.text()).parent), filt)
        if path:
            target.setText(path)

    # ==================================================================
    #  TOOLS CHECK / DOWNLOAD
    # ==================================================================

    def _check_tools(self):
        """Show the Tools Setup dialog if either CLI tool is missing."""
        hb_ok = tool_valid(self.edit_hb.text())
        ff_ok = tool_valid(self.edit_ff.text())
        if hb_ok and ff_ok:
            return

        dlg = ToolsSetupDialog(
            missing_hb=not hb_ok,
            missing_ff=not ff_ok,
            current_hb=self.edit_hb.text(),
            current_ff=self.edit_ff.text(),
            parent=self,
        )
        if dlg.exec() == ToolsSetupDialog.Accepted:
            self.edit_hb.setText(dlg.handbrake_path())
            self.edit_ff.setText(dlg.ffprobe_path())
            self._do_save()

    def _download_tool(self, which: str):
        """Open a single-tool download dialog for re-downloading."""
        dlg = ToolsSetupDialog(
            missing_hb=(which == "handbrake"),
            missing_ff=(which == "ffprobe"),
            current_hb=self.edit_hb.text(),
            current_ff=self.edit_ff.text(),
            parent=self,
        )
        if dlg.exec() == ToolsSetupDialog.Accepted:
            if which == "handbrake":
                self.edit_hb.setText(dlg.handbrake_path())
            else:
                self.edit_ff.setText(dlg.ffprobe_path())
            self._do_save()

    # ==================================================================
    #  START / STOP
    # ==================================================================

    @Slot()
    def start_encoder(self):
        self._do_save()

        self._engine = EncoderEngine(self._config)
        self._engine.log_message.connect(self._on_log)
        self._engine.stats_updated.connect(self._on_stats)
        self._engine.progress_updated.connect(self._on_progress)
        self._engine.state_changed.connect(self._on_state_changed)
        self._engine.error_occurred.connect(self._on_error)
        self._engine.finished.connect(self._on_engine_finished)

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._engine.start()

    @Slot()
    def stop_encoder(self):
        if self._engine:
            self._engine.stop()

    # ==================================================================
    #  ENGINE SIGNAL HANDLERS
    # ==================================================================

    @Slot(str)
    def _on_log(self, msg: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {msg}")
        self.log_view.moveCursor(QTextCursor.End)
        self.lbl_status.setText(f"Status:  {msg}")

    @Slot(dict)
    def _on_stats(self, s: dict):
        self.lbl_stats.setText(
            f"Processed: {s['total']}   Encoded: {s['encoded']}   "
            f"Copied: {s['copied']}   Skipped: {s['skipped']}   "
            f"Queued: {s['queued']}"
        )

    @Slot(str)
    def _on_progress(self, line: str):
        self.edit_progress.setText(line)

    @Slot(str)
    def _on_state_changed(self, state: str):
        pass

    @Slot(str)
    def _on_error(self, msg: str):
        QMessageBox.warning(self, APP_NAME, msg)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)

    @Slot()
    def _on_engine_finished(self):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.edit_progress.clear()

    # ==================================================================
    #  WINDOW / TRAY
    # ==================================================================

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._tray.show_balloon(APP_NAME, "Running in the background. Right-click tray to show or exit.")

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _exit_app(self):
        if self._engine and self._engine.state != "idle":
            if not TrayIcon.confirm_exit_while_encoding():
                return
            self._engine.stop()
            self._engine.wait(5000)

        self._tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()
