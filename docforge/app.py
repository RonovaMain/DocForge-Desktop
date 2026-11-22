"""Точка входа: настройка Qt, оформление, открытие файла из командной строки."""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from . import APP_NAME, AUTHOR, __version__


def main() -> int:
    from .viewer import register_scheme

    register_scheme()  # до создания QApplication
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(AUTHOR)
    app.setApplicationVersion(__version__)

    from . import theme
    from .config import Settings
    from .engine import EngineClient
    from .mainwindow import MainWindow

    settings = Settings()
    theme.setup_font(app)
    theme.apply(app, settings["theme"])
    window = MainWindow(EngineClient(), settings)
    try:  # тема ОС сменилась, пока программа открыта (Qt 6.5+)
        app.styleHints().colorSchemeChanged.connect(lambda *_: window.on_system_scheme_changed())
    except AttributeError:
        pass
    window.show()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]  # путь к документу (из «Открыть с помощью»)
    if args:
        window.open_path(args[0], confirmed=True)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
