"""Панель пометок для PDF: курсор, выделение текста, маркер, ручка, закраска, ластик; цвет и толщина; отмена; страницы."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor
from PyQt6.QtWidgets import QButtonGroup, QColorDialog, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QSlider, QToolBar, QWidget

from . import pdfedit
from .icons import make_icon

CURSOR, ERASER = "none", "eraser"

# (название, значок, подсказка)
TOOLS = [
    (CURSOR, "Курсор", "cursor", "Просто читать и прокручивать"),
    (pdfedit.TOOL_HIGHLIGHT, "Текст", "highlight", "Выделить текст цветом: проведите по строкам. Работает там, где в PDF есть текст"),
    (pdfedit.TOOL_MARKER, "Маркер", "marker", "Широкий полупрозрачный мазок от руки — подходит и для сканов"),
    (pdfedit.TOOL_PEN, "Ручка", "pen", "Тонкая линия от руки"),
    (pdfedit.TOOL_COVER, "Закраска", "cover", "Залить прямоугольник сплошным цветом"),
    (ERASER, "Ластик", "eraser", "Стереть пометку, которую вы ещё не сохранили"),
]

COLORS = ["#ffeb3b", "#ffb74d", "#ff80ab", "#f44336", "#66bb6a", "#42a5f5", "#ab47bc", "#111111", "#ffffff"]

DEFAULT_COLOR = {
    pdfedit.TOOL_HIGHLIGHT: "#ffeb3b", pdfedit.TOOL_MARKER: "#66bb6a", pdfedit.TOOL_PEN: "#f44336",
    pdfedit.TOOL_COVER: "#111111",
}
DEFAULT_WIDTH = {pdfedit.TOOL_MARKER: 14, pdfedit.TOOL_PEN: 2}
WIDTH_RANGE = {pdfedit.TOOL_MARKER: (4, 40), pdfedit.TOOL_PEN: (1, 12)}


class MarkupBar(QToolBar):
    toolChanged = pyqtSignal(str, str, float)   # инструмент, цвет, толщина в пунктах
    undoRequested = pyqtSignal()
    redoRequested = pyqtSignal()
    deletePagesRequested = pyqtSignal()
    closeRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Пометки", parent)
        self.setObjectName("markupbar")
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(20, 20))
        self.tool = CURSOR
        self.colors = dict(DEFAULT_COLOR)
        self.widths = dict(DEFAULT_WIDTH)
        self._icon_names: list[tuple[QAction, str]] = []

        group = QActionGroup(self)
        group.setExclusive(True)
        self.tool_actions: dict[str, QAction] = {}
        for key, title, icon, tip in TOOLS:
            a = QAction(title, self)
            a.setCheckable(True)
            a.setToolTip(f"{title} — {tip}")
            a.triggered.connect(lambda checked, k=key: self.set_tool(k))
            group.addAction(a)
            self.addAction(a)
            self.tool_actions[key] = a
            self._icon_names.append((a, icon))
        self.tool_actions[CURSOR].setChecked(True)
        self.addSeparator()

        # цвета
        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(4, 0, 4, 0)
        lay.setSpacing(5)
        self.swatches = QButtonGroup(self)
        self.swatches.setExclusive(True)
        self._swatch_buttons: dict[str, QPushButton] = {}
        for color in COLORS:
            b = self._make_swatch(color)
            lay.addWidget(b)
            self.swatches.addButton(b)
            self._swatch_buttons[color] = b
        more = QPushButton("…")
        more.setObjectName("swatch")
        more.setStyleSheet("QPushButton#swatch{background:transparent;}")
        more.setToolTip("Другой цвет…")
        more.clicked.connect(self._pick_custom)
        lay.addWidget(more)
        self._colors_widget = self.addWidget(holder)

        # толщина
        self.width_label = QLabel("Толщина")
        self.width_label.setObjectName("muted")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setFixedWidth(110)
        self.slider.valueChanged.connect(self._width_changed)
        self._width_label_action = self.addWidget(self.width_label)
        self._slider_action = self.addWidget(self.slider)
        self.addSeparator()

        self.a_undo = QAction("Отменить", self)
        self.a_undo.setToolTip("Отменить последнее действие (Ctrl+Z)")
        self.a_undo.triggered.connect(lambda: self.undoRequested.emit())
        self.a_redo = QAction("Повторить", self)
        self.a_redo.setToolTip("Вернуть отменённое (Ctrl+Y)")
        self.a_redo.triggered.connect(lambda: self.redoRequested.emit())
        self.a_pages = QAction("Удалить страницы…", self)
        self.a_pages.setToolTip("Выбрать ненужные страницы и убрать их из документа")
        self.a_pages.triggered.connect(lambda: self.deletePagesRequested.emit())
        for a, icon in ((self.a_undo, "undo"), (self.a_redo, "redo"), (self.a_pages, "trash")):
            self.addAction(a)
            self._icon_names.append((a, icon))
        self.a_undo.setEnabled(False)
        self.a_redo.setEnabled(False)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.addWidget(spacer)
        self.a_close = QAction("Закрыть панель", self)
        self.a_close.triggered.connect(lambda: self.closeRequested.emit())
        self.addAction(self.a_close)
        self._icon_names.append((self.a_close, "close"))
        self._refresh_options()

    # ------------------------------------------------------------------ значки под тему

    def apply_icons(self, theme: dict) -> None:
        for action, name in self._icon_names:
            action.setIcon(make_icon(name, theme["text"], theme["faint"], theme["accent"]))

    # ------------------------------------------------------------------ цвет и толщина

    def _make_swatch(self, color: str) -> QPushButton:
        b = QPushButton()
        b.setObjectName("swatch")
        b.setCheckable(True)
        b.setToolTip(color)
        border = "#9aa0b4" if color.lower() in ("#ffffff", "#fafafa") else color
        b.setStyleSheet(f"QPushButton#swatch{{background:{color};}} QPushButton#swatch:!checked{{border:2px solid {border};}}")
        b.clicked.connect(lambda checked, c=color: self._set_color(c))
        return b

    def _set_color(self, color: str) -> None:
        if self.tool in self.colors:
            self.colors[self.tool] = color
        self._emit()

    def _pick_custom(self) -> None:
        start = QColor(self.colors.get(self.tool, "#ffeb3b"))
        color = QColorDialog.getColor(start, self, "Цвет")
        if color.isValid():
            self._set_color(color.name())
            for b in self._swatch_buttons.values():
                b.setChecked(False)

    def _width_changed(self, value: int) -> None:
        if self.tool in self.widths:
            self.widths[self.tool] = value
        self._emit()

    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self.tool_actions[tool].setChecked(True)
        self._refresh_options()
        self._emit()

    def _refresh_options(self) -> None:
        has_color = self.tool in self.colors
        for b in self._swatch_buttons.values():
            b.setEnabled(has_color)
        current = self.colors.get(self.tool, "").lower()
        for color, b in self._swatch_buttons.items():
            b.setChecked(has_color and color.lower() == current)
        has_width = self.tool in WIDTH_RANGE
        self._width_label_action.setVisible(has_width)
        self._slider_action.setVisible(has_width)
        if has_width:
            lo, hi = WIDTH_RANGE[self.tool]
            self.slider.blockSignals(True)
            self.slider.setRange(lo, hi)
            self.slider.setValue(self.widths[self.tool])
            self.slider.blockSignals(False)

    def _emit(self) -> None:
        color = self.colors.get(self.tool, "#000000")
        width = float(self.widths.get(self.tool, 2))
        self.toolChanged.emit(self.tool, color, width)
        self._refresh_swatches_only()

    def _refresh_swatches_only(self) -> None:
        current = self.colors.get(self.tool, "").lower()
        for color, b in self._swatch_buttons.items():
            b.blockSignals(True)
            b.setChecked(color.lower() == current)
            b.blockSignals(False)

    def current(self) -> tuple[str, str, float]:
        return self.tool, self.colors.get(self.tool, "#000000"), float(self.widths.get(self.tool, 2))

    def set_history(self, can_undo: bool, can_redo: bool) -> None:
        self.a_undo.setEnabled(can_undo)
        self.a_redo.setEnabled(can_redo)
