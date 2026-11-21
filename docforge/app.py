"""Точка входа: настройка Qt, оформление, открытие файла из командной строки."""
from __future__ import annotations

import sys

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from . import APP_NAME, AUTHOR, __version__


_default_style = ""


def apply_theme(app: QApplication, mode: str) -> None:
    """system — как в ОС; light/dark — своя палитра на стиле Fusion."""
    global _default_style
    if not _default_style:
        _default_style = app.style().objectName()
    if mode == "system":
        app.setStyle(_default_style)
        app.setPalette(app.style().standardPalette())
        return
    app.setStyle("Fusion")
    if mode == "light":
        app.setPalette(app.style().standardPalette())
        return
    p = QPalette()
    base, text = QColor(32, 33, 36), QColor(232, 234, 237)
    p.setColor(QPalette.ColorRole.Window, QColor(45, 46, 50))
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 46, 50))
    p.setColor(QPalette.ColorRole.ToolTipBase, base)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor(53, 54, 58))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.ColorRole.Link, QColor(138, 180, 248))
    p.setColor(QPalette.ColorRole.Highlight, QColor(66, 99, 190))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    gray = QColor(128, 128, 128)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, gray)
    app.setPalette(p)


def main() -> int:
    from .viewer import register_scheme

    register_scheme()  # до создания QApplication
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(AUTHOR)
    app.setApplicationVersion(__version__)

    from .config import Settings
    from .engine import EngineClient
    from .mainwindow import MainWindow

    settings = Settings()
    global _default_style
    _default_style = app.style().objectName()  # стиль ОС: к нему возвращает режим «как в системе»
    apply_theme(app, settings["theme"])
    window = MainWindow(EngineClient(), settings)
    window.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]  # путь к документу (из «Открыть с помощью»)
    if args:
        window.open_path(args[0], confirmed=True)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
