"""Constants, preset data, and shared resources for the UI."""

ABR_PRESETS = {
    "480p":   {"width": 854,  "height": 480,  "vb": 400},
    "720p":   {"width": 1280, "height": 720,  "vb": 1000},
    "1080p":  {"width": 1920, "height": 1080, "vb": 2000},
    "1440p":  {"width": 2560, "height": 1440, "vb": 4000},
    "4K UHD": {"width": 3840, "height": 2160, "vb": 8000},
    "8K":     {"width": 7680, "height": 4320, "vb": 30000},
}

CRF_PRESETS = {
    "18 - Visually Lossless": 18,
    "20 - High Quality":      20,
    "22 - Good Quality":      22,
    "24 - Balanced":          24,
    "26 - Smaller Files":     26,
    "28 - Low Quality":       28,
}

SIMPLE_ENCODERS = [
    ("NVENC H.265 (GPU)",         "nvenc_h265"),
    ("x265 (CPU - Best Quality)", "x265"),
    ("x264 (CPU - Fast)",         "x264"),
]

ALL_ENCODERS = [
    "svt_av1", "svt_av1_10bit", "ffv1",
    "x264", "x264_10bit", "vce_h264", "nvenc_h264",
    "x265", "x265_10bit", "x265_12bit",
    "vce_h265", "vce_h265_10bit", "nvenc_h265", "nvenc_h265_10bit",
    "mpeg4", "mpeg2", "VP8", "VP9", "VP9_10bit", "theora",
]

AUDIO_ENCODERS = [
    "av_aac", "copy:aac", "ac3", "copy:ac3", "eac3", "copy:eac3",
    "truehd", "copy:truehd", "copy:dts", "copy:dtshd",
    "mp3", "copy:mp3", "opus", "copy:opus", "vorbis", "copy:vorbis",
    "flac16", "flac24", "copy:flac", "alac16", "alac24", "copy:alac",
    "copy", "none",
]

MIXDOWNS = [
    "mono", "left_only", "right_only", "stereo",
    "dpl1", "dpl2", "5point1", "6point1", "7point1", "5_2_lfe",
]

SAMPLE_RATES = [
    "Auto", "8", "11.025", "12", "16", "22.05", "24",
    "32", "44.1", "48", "88.2", "96", "176.4", "192",
]

FRAMERATES = [
    "Same as source",
    "5", "10", "12", "15", "23.976", "24", "25",
    "29.97", "30", "48", "50", "59.94", "60", "72",
    "75", "90", "100", "120",
]

ANAMORPHIC_MODES = ["None", "Auto", "Loose", "Custom"]

CROP_MODES = ["Auto", "Conservative", "None", "Custom"]

COLOR_RANGES = ["Auto", "Limited", "Full"]

COLOR_MATRICES = ["Auto", "BT.2020", "BT.709", "BT.601", "PAL"]

DENOISE_TYPES = ["Off", "hqdn3d", "NLMeans"]

DENOISE_STRENGTHS = ["ultralight", "light", "medium", "strong"]

NLMEANS_TUNES = ["none", "film", "grain", "highmotion", "animation", "tape", "sprite"]

SHARPEN_TYPES = ["Off", "Unsharp", "Lapsharp"]

SHARPEN_STRENGTHS = ["ultralight", "light", "medium", "strong", "stronger", "verystrong"]

DEBLOCK_STRENGTHS = ["Off", "ultralight", "light", "medium", "strong", "stronger", "verystrong"]

DEBLOCK_TUNES = ["small", "medium", "large"]

DEINTERLACE_TYPES = ["Off", "Yadif", "Bwdif", "Decomb"]

COMB_DETECT_MODES = ["Off", "Default", "Permissive", "Fast"]

COLORSPACE_PRESETS = ["Off", "BT.2020", "BT.709", "BT.601-525", "BT.601-625"]

CONTAINER_FORMATS = ["Auto", "av_mkv", "av_mp4", "av_webm"]

HDR_METADATA_OPTIONS = ["Off", "hdr10plus", "dolbyvision", "all"]

HW_DECODING_OPTIONS = ["Off", "nvdec", "qsv"]

VIDEO_EXTENSIONS = [
    ".mkv", ".mp4", ".avi", ".mov", ".wmv",
    ".m4v", ".ts", ".flv", ".mpg", ".mpeg",
]

APP_NAME = "Auto Video Encoder"
APP_VERSION = "2.0.0"
DEFAULT_AUDIO_BITRATE = 128

def get_icon_path() -> str:
    """Return the absolute path to icon_r.ico, works both dev and PyInstaller."""
    import sys
    from pathlib import Path
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent
    return str(base / "icon_r.ico")
