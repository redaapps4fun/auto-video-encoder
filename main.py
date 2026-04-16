"""Auto Video Encoder - HandBrake Watch Encoder.

Cross-platform GUI (PySide6) and headless daemon for automated video encoding
using HandBrakeCLI + ffprobe. Supports ABR, CRF, and Advanced encoding modes.
"""

import sys
import argparse
import signal


def run_gui(auto_start: bool = False):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QIcon
    from PySide6.QtCore import QTimer
    from ui.main_window import MainWindow
    from ui.resources import get_icon_path
    from config import ConfigManager

    app = QApplication(sys.argv)
    app.setApplicationName("Auto Video Encoder")
    app.setOrganizationName("Compresor")
    app.setWindowIcon(QIcon(get_icon_path()))

    config = ConfigManager()
    window = MainWindow(config)
    window.show()

    should_auto_start = auto_start or config.get("auto_start_watcher", False)
    if should_auto_start:
        QTimer.singleShot(1000, window.start_encoder)

    sys.exit(app.exec())


def run_headless():
    import logging
    from PySide6.QtCore import QCoreApplication, QTimer
    from config import ConfigManager
    from encoder_engine import EncoderEngine

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("compresor")

    app = QCoreApplication(sys.argv)

    config = ConfigManager()
    engine = EncoderEngine(config)
    engine.log_message.connect(lambda msg: log.info(msg))
    engine.stats_updated.connect(
        lambda s: log.info(
            f"Processed: {s['total']}  Encoded: {s['encoded']}  "
            f"Copied: {s['copied']}  Skipped: {s['skipped']}  "
            f"Queued: {s['queued']}"
        )
    )

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())

    QTimer.singleShot(0, engine.start)
    sys.exit(app.exec())


def main():
    parser = argparse.ArgumentParser(
        description="Auto Video Encoder - HandBrake Watch Encoder"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without GUI as a background daemon",
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Automatically start the watcher on launch (GUI mode)",
    )
    args = parser.parse_args()

    if args.headless:
        run_headless()
    else:
        run_gui(auto_start=args.auto_start)


if __name__ == "__main__":
    main()
