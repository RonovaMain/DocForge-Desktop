"""Оформление окна: своя светлая и тёмная палитры и таблица стилей на стиле Fusion.

Системные цвета Windows не используются: именно из-за них в режиме «как в системе» всё выходило серо-бежевым и сливалось.
«Как в системе» теперь значит только «светлая или тёмная — как выбрано в ОС», а цвета везде наши.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QPalette
from PyQt6.QtWidgets import QApplication

LIGHT = {
    "scheme": "light",
    "bg": "#f3f4f8", "surface": "#ffffff", "raised": "#f7f8fb", "text": "#1c1e26", "muted": "#6a6f80",
    "faint": "#a3a7b5", "border": "#dcdee6", "hover": "#eceef5", "pressed": "#e1e4ee",
    "accent": "#6a5ae0", "accent_hover": "#5849cf", "accent_soft": "#e9e6fd", "on_accent": "#ffffff",
    "danger": "#d93a49", "scroll": "#c4c7d3", "scroll_hover": "#a9adbd", "page": "#d9dbe1",
}
DARK = {
    "scheme": "dark",
    "bg": "#1b1c21", "surface": "#25262c", "raised": "#2c2d34", "text": "#e9eaf0", "muted": "#9a9eb0",
    "faint": "#5f6374", "border": "#383a44", "hover": "#31323b", "pressed": "#3a3b46",
    "accent": "#9a8cff", "accent_hover": "#b0a5ff", "accent_soft": "#35305f", "on_accent": "#14122b",
    "danger": "#ff6b78", "scroll": "#454757", "scroll_hover": "#5d6074", "page": "#232429",
}

_current = dict(LIGHT)


def current() -> dict:
    return _current


def system_scheme(app: QApplication) -> str:
    """Тема ОС: «light» или «dark»."""
    try:
        scheme = app.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        if scheme == Qt.ColorScheme.Light:
            return "light"
    except AttributeError:  # Qt старше 6.5
        pass
    return "dark" if app.palette().color(QPalette.ColorRole.Window).lightness() < 128 else "light"


def resolve(mode: str, app: QApplication) -> str:
    if mode in ("light", "dark"):
        return mode
    return system_scheme(app)


def _palette(t: dict) -> QPalette:
    p = QPalette()
    c = QColor
    p.setColor(QPalette.ColorRole.Window, c(t["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, c(t["text"]))
    p.setColor(QPalette.ColorRole.Base, c(t["surface"]))
    p.setColor(QPalette.ColorRole.AlternateBase, c(t["raised"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, c(t["raised"]))
    p.setColor(QPalette.ColorRole.ToolTipText, c(t["text"]))
    p.setColor(QPalette.ColorRole.Text, c(t["text"]))
    p.setColor(QPalette.ColorRole.Button, c(t["raised"]))
    p.setColor(QPalette.ColorRole.ButtonText, c(t["text"]))
    p.setColor(QPalette.ColorRole.BrightText, c(t["danger"]))
    p.setColor(QPalette.ColorRole.Link, c(t["accent"]))
    p.setColor(QPalette.ColorRole.Highlight, c(t["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, c(t["on_accent"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, c(t["faint"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c(t["faint"]))
    return p


def _qss(t: dict) -> str:
    return """
QMainWindow, QDialog { background: %(bg)s; }
QWidget { color: %(text)s; }
QLabel { background: transparent; }
QMenuBar { background: %(bg)s; border-bottom: 1px solid %(border)s; padding: 2px 6px; }
QMenuBar::item { background: transparent; padding: 6px 11px; border-radius: 6px; }
QMenuBar::item:selected { background: %(hover)s; }
QMenu { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; padding: 6px; }
QMenu::item { padding: 7px 30px 7px 14px; border-radius: 6px; margin: 1px 0; }
QMenu::item:selected { background: %(accent_soft)s; color: %(text)s; }
QMenu::item:disabled { color: %(faint)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 6px 8px; }
QToolBar { background: %(surface)s; border: none; border-bottom: 1px solid %(border)s; padding: 6px 10px; spacing: 3px; }
QToolBar::separator { width: 1px; background: %(border)s; margin: 5px 8px; }
QToolButton { background: transparent; border: none; border-radius: 8px; padding: 6px 10px; color: %(text)s; }
QToolButton:hover { background: %(hover)s; }
QToolButton:pressed { background: %(pressed)s; }
QToolButton:checked { background: %(accent_soft)s; color: %(accent)s; }
QToolButton:disabled { color: %(faint)s; }
QToolButton::menu-indicator { image: none; }
QPushButton { background: %(raised)s; border: 1px solid %(border)s; border-radius: 8px; padding: 7px 18px; }
QPushButton:hover { border-color: %(accent)s; }
QPushButton:pressed { background: %(pressed)s; }
QPushButton:disabled { color: %(faint)s; }
QPushButton:flat { background: transparent; border: none; }
QPushButton#primary { background: %(accent)s; color: %(on_accent)s; border: none; font-weight: 600; padding: 10px 26px; }
QPushButton#primary:hover { background: %(accent_hover)s; }
QPushButton#danger { background: %(danger)s; color: #ffffff; border: none; font-weight: 600; }
QPushButton#danger:disabled { background: %(border)s; color: %(faint)s; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background: %(surface)s; border: 1px solid %(border)s; border-radius: 8px; padding: 6px 10px;
    selection-background-color: %(accent)s; selection-color: %(on_accent)s; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: %(accent)s; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView { background: %(surface)s; border: 1px solid %(border)s; selection-background-color: %(accent_soft)s;
    selection-color: %(text)s; outline: 0; padding: 4px; }
QStatusBar { background: %(bg)s; border-top: 1px solid %(border)s; color: %(muted)s; }
QStatusBar::item { border: none; }
QStatusBar QToolButton { padding: 3px 7px; border-radius: 6px; }
QStatusBar QLabel { color: %(muted)s; }
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: %(scroll)s; border-radius: 4px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: %(scroll_hover)s; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(scroll)s; border-radius: 4px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: %(scroll_hover)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QListWidget { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; padding: 4px; outline: 0; }
QListWidget::item { padding: 8px 10px; border-radius: 8px; }
QListWidget::item:hover { background: %(hover)s; }
QListWidget::item:selected { background: %(accent_soft)s; color: %(text)s; }
QToolTip { background: %(raised)s; color: %(text)s; border: 1px solid %(border)s; border-radius: 6px; padding: 5px 8px; }
QGroupBox { border: 1px solid %(border)s; border-radius: 10px; margin-top: 12px; padding: 12px 10px 8px 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: %(muted)s; }
QSlider::groove:horizontal { height: 4px; background: %(border)s; border-radius: 2px; }
QSlider::sub-page:horizontal { background: %(accent)s; border-radius: 2px; }
QSlider::handle:horizontal { background: %(accent)s; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }
QProgressBar { background: %(border)s; border: none; border-radius: 4px; height: 8px; text-align: center; }
QProgressBar::chunk { background: %(accent)s; border-radius: 4px; }
QFrame#card { background: %(surface)s; border: 1px dashed %(border)s; border-radius: 14px; }
QToolBar#markupbar { background: %(raised)s; }
QWidget#searchbar { background: %(surface)s; border-bottom: 1px solid %(border)s; }
QPushButton#swatch { border-radius: 11px; border: 2px solid transparent; padding: 0; min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; }
QPushButton#swatch:checked { border: 2px solid %(accent)s; }
QPushButton#swatch:hover { border: 2px solid %(muted)s; }
QLabel#muted { color: %(muted)s; }
QLabel#title { font-size: 26px; font-weight: 700; }
""" % t


def apply(app: QApplication, mode: str) -> dict:
    """Применяет тему окна («system», «light», «dark») и возвращает её цвета."""
    global _current
    try:  # Qt 6.8+: «как в системе» — снова следовать ОС, иначе системную тему уже не узнать
        if mode == "system":
            app.styleHints().unsetColorScheme()
    except AttributeError:
        pass
    scheme = resolve(mode, app)
    t = DARK if scheme == "dark" else LIGHT
    _current = dict(t)
    app.setStyle("Fusion")
    app.setPalette(_palette(t))
    app.setStyleSheet(_qss(t))
    try:  # Qt 6.8+: заголовок окна в Windows тоже светлый или тёмный
        if mode != "system":
            app.styleHints().setColorScheme(Qt.ColorScheme.Dark if scheme == "dark" else Qt.ColorScheme.Light)
    except AttributeError:
        pass
    return _current


def setup_font(app: QApplication) -> None:
    import os

    if os.name == "nt":
        font = QFont("Segoe UI", 10)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        app.setFont(font)
    else:
        font = app.font()
        font.setPointSizeF(max(10.0, font.pointSizeF()))
        app.setFont(font)
