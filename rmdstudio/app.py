"""Application entry point."""
from __future__ import annotations

import argparse
import ctypes
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, APP_ORG, __version__, icons, paths, theme
from .main_window import MainWindow


def _set_windows_app_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RmdStudio.Local.1")
    except Exception:
        pass


def _enable_dark_titlebar(window) -> None:
    """Use the Windows immersive dark title bar when available."""
    try:
        import ctypes

        value = ctypes.c_int(1)
        hwnd = int(window.winId())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def _install_exception_hook() -> None:
    log_file = paths.log_path()

    def hook(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open(log_file, "a", encoding="utf-8") as handle:
                handle.write(text + "\n\n")
        except Exception:
            pass
        try:
            QMessageBox.critical(
                None,
                APP_NAME,
                "Something unexpected happened.\n\n"
                f"{exc_value}\n\nA log was written to:\n{log_file}",
            )
        except Exception:
            pass

    sys.excepthook = hook


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_NAME, add_help=True)
    parser.add_argument("file", nargs="?", help="R Markdown file to open")
    parser.add_argument("--version", action="store_true", help="show the version and exit")
    parser.add_argument("--demo", action="store_true", help="open the bundled sample")
    parser.add_argument("--selftest", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--screenshot", metavar="PNG", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args, qt_args = parser.parse_known_args(argv)
    if args.version:
        print(f"{APP_NAME} {__version__}")
        return 0

    _set_windows_app_id()
    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(icons.app_icon())
    theme.apply_theme(app)
    _install_exception_hook()

    window = MainWindow()
    window.show()
    _enable_dark_titlebar(window)

    if args.selftest:
        def run_selftest():
            ok = window.selftest()
            print("SELFTEST OK" if ok else "SELFTEST FAILED")
            window._saved_generation = window._generation  # avoid close prompt
            window.close()
            app.exit(0 if ok else 1)

        QTimer.singleShot(250, run_selftest)
        return app.exec()

    if args.screenshot:
        out_path = Path(args.screenshot).resolve()
        window.resize(1440, 940)

        def capture():
            if args.demo:
                window.open_demo()
            elif args.file:
                window.open_path(Path(args.file))
            QTimer.singleShot(1800, lambda: _save_screenshot(window, out_path, app))

        QTimer.singleShot(250, capture)
        return app.exec()

    if args.demo:
        QTimer.singleShot(100, window.open_demo)
    elif args.file:
        QTimer.singleShot(100, lambda: window.open_path(Path(args.file)))
    return app.exec()


def _save_screenshot(window: MainWindow, out_path: Path, app: QApplication) -> None:
    try:
        window.grab().save(str(out_path), "PNG")
        print(f"SCREENSHOT {out_path}")
    finally:
        window._saved_generation = window._generation
        window.close()
        app.quit()
