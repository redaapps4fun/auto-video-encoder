"""CRF Mode Panel - quality factor selection with encoder and resolution."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QFormLayout, QComboBox, QSpinBox, QSlider, QHBoxLayout, QLabel,
)
from PySide6.QtCore import Signal, Qt

from ui.resources import CRF_PRESETS, ABR_PRESETS, SIMPLE_ENCODERS


class CRFModePanel(QWidget):
    """Panel shown when CRF encoding mode is selected."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QFormLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)

        # CRF preset dropdown
        self.combo_crf = QComboBox()
        for label, val in CRF_PRESETS.items():
            self.combo_crf.addItem(label, val)
        self.combo_crf.addItem("Custom", -1)
        layout.addRow("Quality (CRF):", self.combo_crf)

        # Custom CRF slider + spinbox
        self._custom_row = QWidget()
        crf_layout = QHBoxLayout(self._custom_row)
        crf_layout.setContentsMargins(0, 0, 0, 0)
        self.slider_crf = QSlider(Qt.Horizontal)
        self.slider_crf.setRange(0, 51)
        self.slider_crf.setValue(22)
        self.spin_crf = QSpinBox()
        self.spin_crf.setRange(0, 51)
        self.spin_crf.setValue(22)
        crf_layout.addWidget(self.slider_crf, 1)
        crf_layout.addWidget(self.spin_crf)
        crf_layout.addWidget(QLabel("(0 = lossless, 51 = worst)"))
        layout.addRow("Custom CRF Value:", self._custom_row)
        self._custom_row.setVisible(False)

        # Encoder
        self.combo_encoder = QComboBox()
        for label, flag in SIMPLE_ENCODERS:
            self.combo_encoder.addItem(label, flag)
        layout.addRow("Encoder:", self.combo_encoder)

        # Resolution
        self.combo_resolution = QComboBox()
        self.combo_resolution.addItem("Source (no resize)", "Source")
        for name, p in ABR_PRESETS.items():
            self.combo_resolution.addItem(f"{name}  ({p['width']}x{p['height']})", name)
        self.combo_resolution.addItem("Custom", "Custom")
        layout.addRow("Output Resolution:", self.combo_resolution)

        # Custom resolution fields
        self._res_custom_row = QWidget()
        res_layout = QHBoxLayout(self._res_custom_row)
        res_layout.setContentsMargins(0, 0, 0, 0)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(128, 15360)
        self.spin_width.setValue(1280)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(128, 8640)
        self.spin_height.setValue(720)
        res_layout.addWidget(self.spin_width)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.spin_height)
        res_layout.addStretch()
        layout.addRow("Custom Resolution:", self._res_custom_row)
        self._res_custom_row.setVisible(False)

        # Audio
        self.combo_audio_enc = QComboBox()
        self.combo_audio_enc.addItem("AAC (av_aac)", "av_aac")
        self.combo_audio_enc.addItem("MP3", "mp3")
        self.combo_audio_enc.addItem("Opus", "opus")
        self.combo_audio_enc.addItem("AC3", "ac3")
        self.combo_audio_enc.addItem("Copy (passthrough)", "copy")
        layout.addRow("Audio Encoder:", self.combo_audio_enc)

        self.spin_audio = QSpinBox()
        self.spin_audio.setRange(32, 640)
        self.spin_audio.setValue(128)
        self.spin_audio.setSuffix(" kbps")
        layout.addRow("Audio Bitrate:", self.spin_audio)

        # Connections
        self.combo_crf.currentIndexChanged.connect(self._on_crf_changed)
        self.combo_crf.currentIndexChanged.connect(self._emit_changed)
        self.slider_crf.valueChanged.connect(self.spin_crf.setValue)
        self.spin_crf.valueChanged.connect(self.slider_crf.setValue)
        self.slider_crf.valueChanged.connect(self._emit_changed)
        self.combo_encoder.currentIndexChanged.connect(self._emit_changed)
        self.combo_resolution.currentIndexChanged.connect(self._on_res_changed)
        self.combo_resolution.currentIndexChanged.connect(self._emit_changed)
        self.spin_width.valueChanged.connect(self._emit_changed)
        self.spin_height.valueChanged.connect(self._emit_changed)
        self.combo_audio_enc.currentIndexChanged.connect(self._emit_changed)
        self.spin_audio.valueChanged.connect(self._emit_changed)

    def _emit_changed(self):
        self.changed.emit()

    def _on_crf_changed(self):
        is_custom = self.combo_crf.currentData() == -1
        self._custom_row.setVisible(is_custom)

    def _on_res_changed(self):
        is_custom = self.combo_resolution.currentData() == "Custom"
        self._res_custom_row.setVisible(is_custom)

    def _get_quality(self) -> int:
        val = self.combo_crf.currentData()
        if val == -1:
            return self.spin_crf.value()
        return val

    def load_from_config(self, cfg_section: dict):
        quality = cfg_section.get("quality", 22)

        found = False
        for i in range(self.combo_crf.count()):
            if self.combo_crf.itemData(i) == quality:
                self.combo_crf.setCurrentIndex(i)
                found = True
                break
        if not found:
            self.combo_crf.setCurrentIndex(self.combo_crf.findData(-1))
            self.spin_crf.setValue(quality)
            self.slider_crf.setValue(quality)

        encoder = cfg_section.get("encoder", "nvenc_h265")
        idx = self.combo_encoder.findData(encoder)
        if idx >= 0:
            self.combo_encoder.setCurrentIndex(idx)

        res_preset = cfg_section.get("resolution_preset", "720p")
        idx = self.combo_resolution.findData(res_preset)
        if idx >= 0:
            self.combo_resolution.setCurrentIndex(idx)

        self.spin_width.setValue(cfg_section.get("custom_width", 1280))
        self.spin_height.setValue(cfg_section.get("custom_height", 720))

        audio_enc = cfg_section.get("audio_encoder", "av_aac")
        idx = self.combo_audio_enc.findData(audio_enc)
        if idx >= 0:
            self.combo_audio_enc.setCurrentIndex(idx)

        self.spin_audio.setValue(cfg_section.get("audio_bitrate", 128))

    def save_to_config(self) -> dict:
        return {
            "quality": self._get_quality(),
            "encoder": self.combo_encoder.currentData(),
            "resolution_preset": self.combo_resolution.currentData(),
            "custom_width": self.spin_width.value(),
            "custom_height": self.spin_height.value(),
            "audio_encoder": self.combo_audio_enc.currentData(),
            "audio_bitrate": self.spin_audio.value(),
        }
