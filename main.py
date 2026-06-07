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


def run_headless(
    web_host: str = "127.0.0.1",
    web_port: int = 7332,
    web_ui: bool = True,
):
    import logging
    from PySide6.QtCore import QCoreApplication, QTimer
    from config import ConfigManager
    from encoder_engine import EncoderEngine
    from web.bridge import HeadlessBridge
    from web.server import start_web_server

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log = logging.getLogger("compresor")

    app = QCoreApplication(sys.argv)

    config = ConfigManager()
    bridge = HeadlessBridge(config)

    if web_ui:
        start_web_server(bridge, web_host, web_port)
        log.info(f"Web UI available at http://{web_host}:{web_port}")

        if config.get("auto_start_watcher", False):
            QTimer.singleShot(0, bridge.start_engine)
    else:
        engine = EncoderEngine(config)
        engine.log_message.connect(lambda msg: log.info(msg))
        engine.stats_updated.connect(
            lambda s: log.info(
                f"Processed: {s['total']}  Encoded: {s['encoded']}  "
                f"Copied: {s['copied']}  Skipped: {s['skipped']}  "
                f"Already done: {s.get('registry_skipped', 0)}  "
                f"Queued: {s['queued']}"
            )
        )
        QTimer.singleShot(0, engine.start)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())

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
    parser.add_argument(
        "--web-port",
        type=int,
        default=7332,
        help="Web UI port in headless mode (default: 7332)",
    )
    parser.add_argument(
        "--web-host",
        default="127.0.0.1",
        help="Web UI bind address in headless mode (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--no-web-ui",
        action="store_true",
        help="Disable web UI in headless mode (console-only daemon)",
    )
    args = parser.parse_args()

    if args.headless:
        run_headless(
            web_host=args.web_host,
            web_port=args.web_port,
            web_ui=not args.no_web_ui,
        )
    else:
        run_gui(auto_start=args.auto_start)


if __name__ == "__main__":
    main()
