"""Advanced Mode Panel - tabbed UI exposing all HandBrakeCLI options."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QTabWidget, QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QLineEdit, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
)
from PySide6.QtCore import Signal

from ui.resources import (
    ALL_ENCODERS, AUDIO_ENCODERS, MIXDOWNS, SAMPLE_RATES, FRAMERATES,
    ANAMORPHIC_MODES, CROP_MODES, COLOR_RANGES, COLOR_MATRICES,
    DENOISE_TYPES, DENOISE_STRENGTHS, NLMEANS_TUNES,
    SHARPEN_TYPES, SHARPEN_STRENGTHS,
    DEBLOCK_STRENGTHS, DEBLOCK_TUNES,
    DEINTERLACE_TYPES, COMB_DETECT_MODES, COLORSPACE_PRESETS,
    CONTAINER_FORMATS, HDR_METADATA_OPTIONS, HW_DECODING_OPTIONS,
)


def _scrollable(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(widget)
    area.setFrameShape(QScrollArea.NoFrame)
    return area


def _combo(items: list[str], current: str = "") -> QComboBox:
    cb = QComboBox()
    cb.addItems(items)
    if current:
        idx = cb.findText(current)
        if idx >= 0:
            cb.setCurrentIndex(idx)
    return cb


class AdvancedModePanel(QWidget):
    """Panel shown when Advanced encoding mode is selected."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._build_video_tab()
        self._build_audio_tab()
        self._build_picture_tab()
        self._build_filters_tab()
        self._build_subtitles_tab()
        self._build_container_tab()

    # ==================================================================
    #  VIDEO TAB
    # ==================================================================

    def _build_video_tab(self):
        w = QWidget()
        f = QFormLayout(w)

        self.v_encoder = _combo(ALL_ENCODERS, "nvenc_h265")
        f.addRow("Encoder:", self.v_encoder)

        self.v_rate_control = _combo(["quality", "bitrate"], "quality")
        f.addRow("Rate Control:", self.v_rate_control)

        self.v_quality = QDoubleSpinBox()
        self.v_quality.setRange(0, 51)
        self.v_quality.setDecimals(1)
        self.v_quality.setValue(22.0)
        f.addRow("Quality (CRF):", self.v_quality)

        self.v_vb = QSpinBox()
        self.v_vb.setRange(50, 100000)
        self.v_vb.setValue(1000)
        self.v_vb.setSuffix(" kbps")
        f.addRow("Video Bitrate:", self.v_vb)

        self.v_encoder_preset = QLineEdit()
        self.v_encoder_preset.setPlaceholderText("e.g. medium, slow, fast")
        f.addRow("Encoder Preset:", self.v_encoder_preset)

        self.v_encoder_tune = QLineEdit()
        self.v_encoder_tune.setPlaceholderText("e.g. film, animation, grain")
        f.addRow("Encoder Tune:", self.v_encoder_tune)

        self.v_encoder_profile = QLineEdit()
        self.v_encoder_profile.setPlaceholderText("e.g. main, high")
        f.addRow("Encoder Profile:", self.v_encoder_profile)

        self.v_encoder_level = QLineEdit()
        self.v_encoder_level.setPlaceholderText("e.g. 4.0, 5.1")
        f.addRow("Encoder Level:", self.v_encoder_level)

        self.v_multi_pass = QCheckBox("Enable multi-pass encoding")
        f.addRow("Multi-pass:", self.v_multi_pass)

        self.v_turbo = QCheckBox("Turbo first pass (x264/x265)")
        f.addRow("Turbo:", self.v_turbo)

        self.v_framerate = _combo(FRAMERATES, "Same as source")
        f.addRow("Framerate:", self.v_framerate)

        self.v_framerate_mode = _combo(["vfr", "cfr", "pfr"], "vfr")
        f.addRow("Framerate Mode:", self.v_framerate_mode)

        self.v_encopts = QLineEdit()
        self.v_encopts.setPlaceholderText("key=value:key=value")
        f.addRow("Extra Encoder Opts:", self.v_encopts)

        self.v_hw_decoding = _combo(HW_DECODING_OPTIONS, "Off")
        f.addRow("HW Decoding:", self.v_hw_decoding)

        self.v_hdr_metadata = _combo(HDR_METADATA_OPTIONS, "Off")
        f.addRow("HDR Metadata:", self.v_hdr_metadata)

        self.tabs.addTab(_scrollable(w), "Video")

        self.v_rate_control.currentTextChanged.connect(self._on_rate_control_changed)
        self._on_rate_control_changed()
        for widget in [self.v_encoder, self.v_rate_control, self.v_framerate,
                       self.v_framerate_mode, self.v_hw_decoding, self.v_hdr_metadata]:
            widget.currentIndexChanged.connect(self._emit_changed)
        for widget in [self.v_quality, self.v_vb]:
            widget.valueChanged.connect(self._emit_changed)
        for widget in [self.v_encoder_preset, self.v_encoder_tune,
                       self.v_encoder_profile, self.v_encoder_level, self.v_encopts]:
            widget.textChanged.connect(self._emit_changed)
        self.v_multi_pass.toggled.connect(self._emit_changed)
        self.v_turbo.toggled.connect(self._emit_changed)

    def _on_rate_control_changed(self):
        is_quality = self.v_rate_control.currentText() == "quality"
        self.v_quality.setEnabled(is_quality)
        self.v_vb.setEnabled(not is_quality)

    # ==================================================================
    #  AUDIO TAB
    # ==================================================================

    def _build_audio_tab(self):
        w = QWidget()
        f = QFormLayout(w)

        self.a_encoder = _combo(AUDIO_ENCODERS, "av_aac")
        f.addRow("Audio Encoder:", self.a_encoder)

        self.a_bitrate = QSpinBox()
        self.a_bitrate.setRange(16, 1536)
        self.a_bitrate.setValue(128)
        self.a_bitrate.setSuffix(" kbps")
        f.addRow("Audio Bitrate:", self.a_bitrate)

        self.a_quality = QDoubleSpinBox()
        self.a_quality.setRange(-1, 10)
        self.a_quality.setDecimals(1)
        self.a_quality.setValue(-1)
        self.a_quality.setSpecialValueText("Not set")
        f.addRow("Audio Quality:", self.a_quality)

        self.a_mixdown = _combo(MIXDOWNS, "stereo")
        f.addRow("Mixdown:", self.a_mixdown)

        self.a_samplerate = _combo(SAMPLE_RATES, "Auto")
        f.addRow("Sample Rate:", self.a_samplerate)

        self.a_drc = QDoubleSpinBox()
        self.a_drc.setRange(0, 4)
        self.a_drc.setDecimals(1)
        self.a_drc.setValue(0)
        f.addRow("DRC:", self.a_drc)

        self.a_gain = QDoubleSpinBox()
        self.a_gain.setRange(-20, 20)
        self.a_gain.setDecimals(1)
        self.a_gain.setValue(0)
        self.a_gain.setSuffix(" dB")
        f.addRow("Gain:", self.a_gain)

        self.a_tracks = QLineEdit("1")
        self.a_tracks.setPlaceholderText("e.g. 1 or 1,2,3")
        f.addRow("Audio Tracks:", self.a_tracks)

        self.a_lang_list = QLineEdit()
        self.a_lang_list.setPlaceholderText("e.g. eng,jpn")
        f.addRow("Language List:", self.a_lang_list)

        self.a_keep_names = QCheckBox("Preserve source audio track names")
        f.addRow("Keep Names:", self.a_keep_names)

        self.tabs.addTab(_scrollable(w), "Audio")

        for widget in [self.a_encoder, self.a_mixdown, self.a_samplerate]:
            widget.currentIndexChanged.connect(self._emit_changed)
        for widget in [self.a_bitrate]:
            widget.valueChanged.connect(self._emit_changed)
        for widget in [self.a_quality, self.a_drc, self.a_gain]:
            widget.valueChanged.connect(self._emit_changed)
        for widget in [self.a_tracks, self.a_lang_list]:
            widget.textChanged.connect(self._emit_changed)
        self.a_keep_names.toggled.connect(self._emit_changed)

    # ==================================================================
    #  PICTURE TAB
    # ==================================================================

    def _build_picture_tab(self):
        w = QWidget()
        f = QFormLayout(w)

        res_row = QWidget()
        res_layout = QHBoxLayout(res_row)
        res_layout.setContentsMargins(0, 0, 0, 0)
        self.p_width = QSpinBox()
        self.p_width.setRange(0, 15360)
        self.p_width.setValue(1280)
        self.p_height = QSpinBox()
        self.p_height.setRange(0, 8640)
        self.p_height.setValue(720)
        res_layout.addWidget(self.p_width)
        res_layout.addWidget(QLabel("x"))
        res_layout.addWidget(self.p_height)
        res_layout.addStretch()
        f.addRow("Width x Height:", res_row)

        max_row = QWidget()
        max_layout = QHBoxLayout(max_row)
        max_layout.setContentsMargins(0, 0, 0, 0)
        self.p_max_width = QSpinBox()
        self.p_max_width.setRange(0, 15360)
        self.p_max_width.setSpecialValueText("None")
        self.p_max_height = QSpinBox()
        self.p_max_height.setRange(0, 8640)
        self.p_max_height.setSpecialValueText("None")
        max_layout.addWidget(self.p_max_width)
        max_layout.addWidget(QLabel("x"))
        max_layout.addWidget(self.p_max_height)
        max_layout.addStretch()
        f.addRow("Max Width x Height:", max_row)

        self.p_anamorphic = _combo([m.lower() for m in ANAMORPHIC_MODES], "loose")
        f.addRow("Anamorphic:", self.p_anamorphic)

        self.p_modulus = QComboBox()
        for m in [2, 4, 8, 16]:
            self.p_modulus.addItem(str(m), m)
        f.addRow("Modulus:", self.p_modulus)

        self.p_crop_mode = _combo([c.lower() for c in CROP_MODES], "auto")
        f.addRow("Crop Mode:", self.p_crop_mode)

        self.p_crop = QLineEdit("0:0:0:0")
        self.p_crop.setPlaceholderText("top:bottom:left:right")
        f.addRow("Custom Crop:", self.p_crop)

        self.p_color_range = _combo([c.lower() for c in COLOR_RANGES], "auto")
        f.addRow("Color Range:", self.p_color_range)

        self.p_color_matrix = QComboBox()
        self.p_color_matrix.addItem("")
        for cm in COLOR_MATRICES:
            if cm != "Auto":
                self.p_color_matrix.addItem(cm)
        f.addRow("Color Matrix:", self.p_color_matrix)

        self.p_rotate = QComboBox()
        for r in [0, 90, 180, 270]:
            self.p_rotate.addItem(f"{r}\u00b0", r)
        f.addRow("Rotation:", self.p_rotate)

        self.p_hflip = QCheckBox("Horizontal flip")
        f.addRow("Flip:", self.p_hflip)

        self.tabs.addTab(_scrollable(w), "Picture")

        for widget in [self.p_anamorphic, self.p_modulus, self.p_crop_mode,
                       self.p_color_range, self.p_color_matrix, self.p_rotate]:
            widget.currentIndexChanged.connect(self._emit_changed)
        for widget in [self.p_width, self.p_height, self.p_max_width, self.p_max_height]:
            widget.valueChanged.connect(self._emit_changed)
        self.p_crop.textChanged.connect(self._emit_changed)
        self.p_hflip.toggled.connect(self._emit_changed)

    # ==================================================================
    #  FILTERS TAB
    # ==================================================================

    def _build_filters_tab(self):
        w = QWidget()
        f = QFormLayout(w)

        self.f_deinterlace = _combo([d.lower() for d in DEINTERLACE_TYPES], "off")
        f.addRow("Deinterlace:", self.f_deinterlace)

        self.f_deinterlace_preset = QLineEdit()
        self.f_deinterlace_preset.setPlaceholderText("e.g. bob, skip-spatial")
        f.addRow("Deinterlace Preset:", self.f_deinterlace_preset)

        self.f_comb_detect = _combo([c.lower() for c in COMB_DETECT_MODES], "off")
        f.addRow("Comb Detect:", self.f_comb_detect)

        self.f_detelecine = QCheckBox("Enable detelecine")
        f.addRow("Detelecine:", self.f_detelecine)

        self.f_denoise = _combo([d.lower() for d in DENOISE_TYPES], "off")
        f.addRow("Denoise:", self.f_denoise)

        self.f_denoise_strength = _combo([""] + DENOISE_STRENGTHS)
        f.addRow("Denoise Strength:", self.f_denoise_strength)

        self.f_denoise_tune = _combo([""] + NLMEANS_TUNES)
        f.addRow("Denoise Tune:", self.f_denoise_tune)

        self.f_chroma_smooth = _combo(["off"] + SHARPEN_STRENGTHS, "off")
        f.addRow("Chroma Smooth:", self.f_chroma_smooth)

        self.f_chroma_smooth_tune = QLineEdit()
        self.f_chroma_smooth_tune.setPlaceholderText("e.g. tiny, small, medium")
        f.addRow("Chroma Smooth Tune:", self.f_chroma_smooth_tune)

        self.f_sharpen = _combo([s.lower() for s in SHARPEN_TYPES], "off")
        f.addRow("Sharpen:", self.f_sharpen)

        self.f_sharpen_strength = _combo([""] + SHARPEN_STRENGTHS)
        f.addRow("Sharpen Strength:", self.f_sharpen_strength)

        self.f_sharpen_tune = QLineEdit()
        self.f_sharpen_tune.setPlaceholderText("e.g. film, grain, animation")
        f.addRow("Sharpen Tune:", self.f_sharpen_tune)

        self.f_deblock = _combo([d.lower() for d in DEBLOCK_STRENGTHS], "off")
        f.addRow("Deblock:", self.f_deblock)

        self.f_deblock_tune = _combo([""] + DEBLOCK_TUNES)
        f.addRow("Deblock Tune:", self.f_deblock_tune)

        self.f_grayscale = QCheckBox("Grayscale output")
        f.addRow("Grayscale:", self.f_grayscale)

        self.f_colorspace = _combo([c.lower() for c in COLORSPACE_PRESETS], "off")
        f.addRow("Colorspace:", self.f_colorspace)

        self.tabs.addTab(_scrollable(w), "Filters")

        for widget in [self.f_deinterlace, self.f_comb_detect, self.f_denoise,
                       self.f_denoise_strength, self.f_denoise_tune,
                       self.f_chroma_smooth, self.f_sharpen, self.f_sharpen_strength,
                       self.f_deblock, self.f_deblock_tune, self.f_colorspace]:
            widget.currentIndexChanged.connect(self._emit_changed)
        for widget in [self.f_deinterlace_preset, self.f_chroma_smooth_tune,
                       self.f_sharpen_tune]:
            widget.textChanged.connect(self._emit_changed)
        self.f_detelecine.toggled.connect(self._emit_changed)
        self.f_grayscale.toggled.connect(self._emit_changed)

    # ==================================================================
    #  SUBTITLES TAB
    # ==================================================================

    def _build_subtitles_tab(self):
        w = QWidget()
        f = QFormLayout(w)

        self.s_tracks = QLineEdit()
        self.s_tracks.setPlaceholderText('e.g. 1,2,3 or "none"')
        f.addRow("Subtitle Tracks:", self.s_tracks)

        self.s_lang_list = QLineEdit()
        self.s_lang_list.setPlaceholderText("e.g. eng,spa")
        f.addRow("Language List:", self.s_lang_list)

        self.s_all = QCheckBox("Select all subtitle tracks")
        f.addRow("All Subtitles:", self.s_all)

        self.s_first_only = QCheckBox("Select first matching track only")
        f.addRow("First Only:", self.s_first_only)

        self.s_burn = QLineEdit()
        self.s_burn.setPlaceholderText('Track number, "native", or empty')
        f.addRow("Burn-in:", self.s_burn)

        self.s_default = QSpinBox()
        self.s_default.setRange(-1, 99)
        self.s_default.setSpecialValueText("None")
        self.s_default.setValue(-1)
        f.addRow("Default Track:", self.s_default)

        self.s_forced = QLineEdit()
        self.s_forced.setPlaceholderText("e.g. 1,2")
        f.addRow("Forced:", self.s_forced)

        f.addRow(QLabel("--- SRT Import ---"))
        self.s_srt_file = QLineEdit()
        self.s_srt_file.setPlaceholderText("Path to .srt file")
        f.addRow("SRT File:", self.s_srt_file)

        self.s_srt_offset = QLineEdit()
        self.s_srt_offset.setPlaceholderText("Offset in ms")
        f.addRow("SRT Offset:", self.s_srt_offset)

        self.s_srt_lang = QLineEdit()
        self.s_srt_lang.setPlaceholderText("e.g. eng")
        f.addRow("SRT Language:", self.s_srt_lang)

        self.s_srt_codeset = QLineEdit()
        self.s_srt_codeset.setPlaceholderText("e.g. UTF-8, latin1")
        f.addRow("SRT Codeset:", self.s_srt_codeset)

        self.s_srt_burn = QCheckBox("Burn SRT into video")
        f.addRow("SRT Burn:", self.s_srt_burn)

        self.s_srt_default = QCheckBox("Set SRT as default")
        f.addRow("SRT Default:", self.s_srt_default)

        f.addRow(QLabel("--- SSA Import ---"))
        self.s_ssa_file = QLineEdit()
        self.s_ssa_file.setPlaceholderText("Path to .ssa/.ass file")
        f.addRow("SSA File:", self.s_ssa_file)

        self.s_ssa_offset = QLineEdit()
        self.s_ssa_offset.setPlaceholderText("Offset in ms")
        f.addRow("SSA Offset:", self.s_ssa_offset)

        self.s_ssa_lang = QLineEdit()
        self.s_ssa_lang.setPlaceholderText("e.g. eng")
        f.addRow("SSA Language:", self.s_ssa_lang)

        self.s_ssa_burn = QCheckBox("Burn SSA into video")
        f.addRow("SSA Burn:", self.s_ssa_burn)

        self.s_ssa_default = QCheckBox("Set SSA as default")
        f.addRow("SSA Default:", self.s_ssa_default)

        self.s_keep_names = QCheckBox("Preserve subtitle track names")
        f.addRow("Keep Names:", self.s_keep_names)

        self.tabs.addTab(_scrollable(w), "Subtitles")

        for widget in [self.s_tracks, self.s_lang_list, self.s_burn, self.s_forced,
                       self.s_srt_file, self.s_srt_offset, self.s_srt_lang,
                       self.s_srt_codeset, self.s_ssa_file, self.s_ssa_offset,
                       self.s_ssa_lang]:
            widget.textChanged.connect(self._emit_changed)
        for widget in [self.s_all, self.s_first_only, self.s_srt_burn,
                       self.s_srt_default, self.s_ssa_burn, self.s_ssa_default,
                       self.s_keep_names]:
            widget.toggled.connect(self._emit_changed)
        self.s_default.valueChanged.connect(self._emit_changed)

    # ==================================================================
    #  CONTAINER TAB
    # ==================================================================

    def _build_container_tab(self):
        w = QWidget()
        f = QFormLayout(w)

        self.c_format = _combo([c.lower() for c in CONTAINER_FORMATS], "auto")
        f.addRow("Container Format:", self.c_format)

        self.c_chapters = QCheckBox("Add chapter markers")
        self.c_chapters.setChecked(True)
        f.addRow("Chapters:", self.c_chapters)

        self.c_optimize = QCheckBox("Optimize for HTTP streaming (MP4 only)")
        f.addRow("Optimize:", self.c_optimize)

        self.c_ipod_atom = QCheckBox("iPod 5G compatibility (MP4 only)")
        f.addRow("iPod Atom:", self.c_ipod_atom)

        self.c_align_av = QCheckBox("Align audio/video start times")
        f.addRow("Align A/V:", self.c_align_av)

        self.c_keep_metadata = QCheckBox("Preserve source metadata")
        self.c_keep_metadata.setChecked(True)
        f.addRow("Keep Metadata:", self.c_keep_metadata)

        self.c_inline_params = QCheckBox("Inline parameter sets (adaptive streaming)")
        f.addRow("Inline Params:", self.c_inline_params)

        self.tabs.addTab(_scrollable(w), "Container")

        self.c_format.currentIndexChanged.connect(self._emit_changed)
        for widget in [self.c_chapters, self.c_optimize, self.c_ipod_atom,
                       self.c_align_av, self.c_keep_metadata, self.c_inline_params]:
            widget.toggled.connect(self._emit_changed)

    # ==================================================================
    #  CHANGE SIGNAL
    # ==================================================================

    def _emit_changed(self):
        self.changed.emit()

    # ==================================================================
    #  LOAD / SAVE
    # ==================================================================

    def load_from_config(self, cfg_section: dict):
        v = cfg_section.get("video", {})
        self._set_combo(self.v_encoder, v.get("encoder", "nvenc_h265"))
        self._set_combo(self.v_rate_control, v.get("rate_control", "quality"))
        self.v_quality.setValue(v.get("quality", 22.0))
        self.v_vb.setValue(v.get("vb", 1000))
        self.v_encoder_preset.setText(v.get("encoder_preset", ""))
        self.v_encoder_tune.setText(v.get("encoder_tune", ""))
        self.v_encoder_profile.setText(v.get("encoder_profile", ""))
        self.v_encoder_level.setText(v.get("encoder_level", ""))
        self.v_multi_pass.setChecked(v.get("multi_pass", False))
        self.v_turbo.setChecked(v.get("turbo", False))
        self._set_combo(self.v_framerate, v.get("framerate", "") or "Same as source")
        self._set_combo(self.v_framerate_mode, v.get("framerate_mode", "vfr"))
        self.v_encopts.setText(v.get("encopts", ""))
        self._set_combo(self.v_hw_decoding, v.get("hw_decoding", "") or "Off")
        self._set_combo(self.v_hdr_metadata, v.get("hdr_metadata", "") or "Off")

        a = cfg_section.get("audio", {})
        self._set_combo(self.a_encoder, a.get("encoder", "av_aac"))
        self.a_bitrate.setValue(a.get("bitrate", 128))
        aq = a.get("quality")
        self.a_quality.setValue(aq if aq is not None else -1)
        self._set_combo(self.a_mixdown, a.get("mixdown", "stereo"))
        self._set_combo(self.a_samplerate, a.get("samplerate", "auto") or "Auto")
        self.a_drc.setValue(a.get("drc", 0))
        self.a_gain.setValue(a.get("gain", 0))
        self.a_tracks.setText(a.get("tracks", "1"))
        self.a_lang_list.setText(a.get("lang_list", ""))
        self.a_keep_names.setChecked(a.get("keep_names", False))

        p = cfg_section.get("picture", {})
        self.p_width.setValue(p.get("width", 1280))
        self.p_height.setValue(p.get("height", 720))
        self.p_max_width.setValue(p.get("max_width") or 0)
        self.p_max_height.setValue(p.get("max_height") or 0)
        self._set_combo(self.p_anamorphic, p.get("anamorphic", "loose"))
        self._set_combo_data(self.p_modulus, p.get("modulus", 2))
        self._set_combo(self.p_crop_mode, p.get("crop_mode", "auto"))
        self.p_crop.setText(p.get("crop", "0:0:0:0"))
        self._set_combo(self.p_color_range, p.get("color_range", "auto"))
        self._set_combo(self.p_color_matrix, p.get("color_matrix", ""))
        self._set_combo_data(self.p_rotate, p.get("rotate", 0))
        self.p_hflip.setChecked(p.get("hflip", False))

        fl = cfg_section.get("filters", {})
        self._set_combo(self.f_deinterlace, fl.get("deinterlace", "off"))
        self.f_deinterlace_preset.setText(fl.get("deinterlace_preset", ""))
        self._set_combo(self.f_comb_detect, fl.get("comb_detect", "off"))
        self.f_detelecine.setChecked(fl.get("detelecine", False))
        self._set_combo(self.f_denoise, fl.get("denoise", "off"))
        self._set_combo(self.f_denoise_strength, fl.get("denoise_strength", ""))
        self._set_combo(self.f_denoise_tune, fl.get("denoise_tune", ""))
        self._set_combo(self.f_chroma_smooth, fl.get("chroma_smooth", "off"))
        self.f_chroma_smooth_tune.setText(fl.get("chroma_smooth_tune", ""))
        self._set_combo(self.f_sharpen, fl.get("sharpen", "off"))
        self._set_combo(self.f_sharpen_strength, fl.get("sharpen_strength", ""))
        self.f_sharpen_tune.setText(fl.get("sharpen_tune", ""))
        self._set_combo(self.f_deblock, fl.get("deblock", "off"))
        self._set_combo(self.f_deblock_tune, fl.get("deblock_tune", ""))
        self.f_grayscale.setChecked(fl.get("grayscale", False))
        self._set_combo(self.f_colorspace, fl.get("colorspace", "off") or "off")

        s = cfg_section.get("subtitles", {})
        self.s_tracks.setText(s.get("tracks", ""))
        self.s_lang_list.setText(s.get("lang_list", ""))
        self.s_all.setChecked(s.get("all", False))
        self.s_first_only.setChecked(s.get("first_only", False))
        self.s_burn.setText(s.get("burn", ""))
        self.s_default.setValue(s.get("default") if s.get("default") is not None else -1)
        self.s_forced.setText(s.get("forced", ""))
        self.s_srt_file.setText(s.get("srt_file", ""))
        self.s_srt_offset.setText(s.get("srt_offset", ""))
        self.s_srt_lang.setText(s.get("srt_lang", ""))
        self.s_srt_codeset.setText(s.get("srt_codeset", ""))
        self.s_srt_burn.setChecked(s.get("srt_burn", False))
        self.s_srt_default.setChecked(s.get("srt_default", False))
        self.s_ssa_file.setText(s.get("ssa_file", ""))
        self.s_ssa_offset.setText(s.get("ssa_offset", ""))
        self.s_ssa_lang.setText(s.get("ssa_lang", ""))
        self.s_ssa_burn.setChecked(s.get("ssa_burn", False))
        self.s_ssa_default.setChecked(s.get("ssa_default", False))
        self.s_keep_names.setChecked(s.get("keep_names", False))

        c = cfg_section.get("container", {})
        self._set_combo(self.c_format, c.get("format", "auto"))
        self.c_chapters.setChecked(c.get("chapters", True))
        self.c_optimize.setChecked(c.get("optimize", False))
        self.c_ipod_atom.setChecked(c.get("ipod_atom", False))
        self.c_align_av.setChecked(c.get("align_av", False))
        self.c_keep_metadata.setChecked(c.get("keep_metadata", True))
        self.c_inline_params.setChecked(c.get("inline_params", False))

    def save_to_config(self) -> dict:
        fr = self.v_framerate.currentText()
        hw = self.v_hw_decoding.currentText()
        hdr = self.v_hdr_metadata.currentText()
        aq = self.a_quality.value()
        sr = self.a_samplerate.currentText()
        sdef = self.s_default.value()

        return {
            "video": {
                "encoder": self.v_encoder.currentText(),
                "rate_control": self.v_rate_control.currentText(),
                "quality": self.v_quality.value(),
                "vb": self.v_vb.value(),
                "encoder_preset": self.v_encoder_preset.text(),
                "encoder_tune": self.v_encoder_tune.text(),
                "encoder_profile": self.v_encoder_profile.text(),
                "encoder_level": self.v_encoder_level.text(),
                "multi_pass": self.v_multi_pass.isChecked(),
                "turbo": self.v_turbo.isChecked(),
                "framerate": "" if fr == "Same as source" else fr,
                "framerate_mode": self.v_framerate_mode.currentText(),
                "encopts": self.v_encopts.text(),
                "hw_decoding": "" if hw == "Off" else hw,
                "hdr_metadata": "" if hdr == "Off" else hdr,
            },
            "audio": {
                "encoder": self.a_encoder.currentText(),
                "bitrate": self.a_bitrate.value(),
                "quality": aq if aq >= 0 else None,
                "mixdown": self.a_mixdown.currentText(),
                "samplerate": "auto" if sr == "Auto" else sr,
                "drc": self.a_drc.value(),
                "gain": self.a_gain.value(),
                "tracks": self.a_tracks.text(),
                "lang_list": self.a_lang_list.text(),
                "keep_names": self.a_keep_names.isChecked(),
            },
            "picture": {
                "width": self.p_width.value(),
                "height": self.p_height.value(),
                "max_width": self.p_max_width.value() or None,
                "max_height": self.p_max_height.value() or None,
                "anamorphic": self.p_anamorphic.currentText(),
                "modulus": self.p_modulus.currentData(),
                "crop_mode": self.p_crop_mode.currentText(),
                "crop": self.p_crop.text(),
                "color_range": self.p_color_range.currentText(),
                "color_matrix": self.p_color_matrix.currentText(),
                "rotate": self.p_rotate.currentData(),
                "hflip": self.p_hflip.isChecked(),
            },
            "filters": {
                "deinterlace": self.f_deinterlace.currentText(),
                "deinterlace_preset": self.f_deinterlace_preset.text(),
                "comb_detect": self.f_comb_detect.currentText(),
                "detelecine": self.f_detelecine.isChecked(),
                "denoise": self.f_denoise.currentText(),
                "denoise_strength": self.f_denoise_strength.currentText(),
                "denoise_tune": self.f_denoise_tune.currentText(),
                "chroma_smooth": self.f_chroma_smooth.currentText(),
                "chroma_smooth_tune": self.f_chroma_smooth_tune.text(),
                "sharpen": self.f_sharpen.currentText(),
                "sharpen_strength": self.f_sharpen_strength.currentText(),
                "sharpen_tune": self.f_sharpen_tune.text(),
                "deblock": self.f_deblock.currentText(),
                "deblock_tune": self.f_deblock_tune.currentText(),
                "grayscale": self.f_grayscale.isChecked(),
                "colorspace": self.f_colorspace.currentText(),
            },
            "subtitles": {
                "tracks": self.s_tracks.text(),
                "lang_list": self.s_lang_list.text(),
                "all": self.s_all.isChecked(),
                "first_only": self.s_first_only.isChecked(),
                "burn": self.s_burn.text(),
                "default": sdef if sdef >= 0 else None,
                "forced": self.s_forced.text(),
                "srt_file": self.s_srt_file.text(),
                "srt_offset": self.s_srt_offset.text(),
                "srt_lang": self.s_srt_lang.text(),
                "srt_codeset": self.s_srt_codeset.text(),
                "srt_burn": self.s_srt_burn.isChecked(),
                "srt_default": self.s_srt_default.isChecked(),
                "ssa_file": self.s_ssa_file.text(),
                "ssa_offset": self.s_ssa_offset.text(),
                "ssa_lang": self.s_ssa_lang.text(),
                "ssa_burn": self.s_ssa_burn.isChecked(),
                "ssa_default": self.s_ssa_default.isChecked(),
                "keep_names": self.s_keep_names.isChecked(),
            },
            "container": {
                "format": self.c_format.currentText(),
                "chapters": self.c_chapters.isChecked(),
                "optimize": self.c_optimize.isChecked(),
                "ipod_atom": self.c_ipod_atom.isChecked(),
                "align_av": self.c_align_av.isChecked(),
                "keep_metadata": self.c_keep_metadata.isChecked(),
                "inline_params": self.c_inline_params.isChecked(),
            },
        }

    @staticmethod
    def _set_combo(combo: QComboBox, text: str):
        idx = combo.findText(text)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    @staticmethod
    def _set_combo_data(combo: QComboBox, data):
        idx = combo.findData(data)
        if idx >= 0:
            combo.setCurrentIndex(idx)
