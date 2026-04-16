"""ABR Mode Panel - preset resolution dropdown, encoder, and audio bitrate."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QComboBox, QSpinBox, QHBoxLayout, QLabel,
)
from PySide6.QtCore import Signal

from ui.resources import ABR_PRESETS, SIMPLE_ENCODERS


class ABRModePanel(QWidget):
    """Panel shown when ABR encoding mode is selected."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        # Preset resolution
        self.combo_preset = QComboBox()
        for name, p in ABR_PRESETS.items():
            self.combo_preset.addItem(f"{name}  ({p['width']}x{p['height']} @ {p['vb']} kbps)", name)
        self.combo_preset.addItem("Custom", "Custom")
        layout.addRow("Resolution Preset:", self.combo_preset)

        # Custom fields (shown only when Custom selected)
        self._custom_row = QWidget()
        custom_layout = QHBoxLayout(self._custom_row)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(128, 15360)
        self.spin_width.setValue(1280)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(128, 8640)
        self.spin_height.setValue(720)
        self.spin_vb = QSpinBox()
        self.spin_vb.setRange(50, 100000)
        self.spin_vb.setValue(1000)
        self.spin_vb.setSuffix(" kbps")
        custom_layout.addWidget(self.spin_width)
        custom_layout.addWidget(QLabel("x"))
        custom_layout.addWidget(self.spin_height)
        custom_layout.addWidget(QLabel("@"))
        custom_layout.addWidget(self.spin_vb)
        custom_layout.addStretch()
        layout.addRow("Custom W x H @ Bitrate:", self._custom_row)
        self._custom_row.setVisible(False)

        # Encoder
        self.combo_encoder = QComboBox()
        for label, flag in SIMPLE_ENCODERS:
            self.combo_encoder.addItem(label, flag)
        layout.addRow("Encoder:", self.combo_encoder)

        # Audio bitrate
        self.spin_audio = QSpinBox()
        self.spin_audio.setRange(32, 640)
        self.spin_audio.setValue(128)
        self.spin_audio.setSuffix(" kbps")
        layout.addRow("Audio Bitrate:", self.spin_audio)

        # Connections
        self.combo_preset.currentIndexChanged.connect(self._on_preset_changed)
        self.combo_preset.currentIndexChanged.connect(self._emit_changed)
        self.combo_encoder.currentIndexChanged.connect(self._emit_changed)
        self.spin_width.valueChanged.connect(self._emit_changed)
        self.spin_height.valueChanged.connect(self._emit_changed)
        self.spin_vb.valueChanged.connect(self._emit_changed)
        self.spin_audio.valueChanged.connect(self._emit_changed)

    def _emit_changed(self):
        self.changed.emit()

    def _on_preset_changed(self):
        is_custom = self.combo_preset.currentData() == "Custom"
        self._custom_row.setVisible(is_custom)

    def load_from_config(self, cfg_section: dict):
        preset = cfg_section.get("preset", "720p")
        idx = self.combo_preset.findData(preset)
        if idx >= 0:
            self.combo_preset.setCurrentIndex(idx)
        else:
            self.combo_preset.setCurrentIndex(self.combo_preset.findData("Custom"))

        self.spin_width.setValue(cfg_section.get("custom_width", 1280))
        self.spin_height.setValue(cfg_section.get("custom_height", 720))
        self.spin_vb.setValue(cfg_section.get("custom_vb", 1000))
        self.spin_audio.setValue(cfg_section.get("audio_bitrate", 128))

        encoder = cfg_section.get("encoder", "nvenc_h265")
        idx = self.combo_encoder.findData(encoder)
        if idx >= 0:
            self.combo_encoder.setCurrentIndex(idx)

    def save_to_config(self) -> dict:
        preset = self.combo_preset.currentData()
        return {
            "preset": preset,
            "encoder": self.combo_encoder.currentData(),
            "custom_width": self.spin_width.value(),
            "custom_height": self.spin_height.value(),
            "custom_vb": self.spin_vb.value(),
            "audio_bitrate": self.spin_audio.value(),
        }
