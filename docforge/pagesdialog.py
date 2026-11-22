"""Окно «Удалить страницы»: миниатюры всех страниц, выбор мышью или диапазоном («1-3, 5, 8-»)."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QDialog, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)

from .pdfsource import PdfSource
from .printing import options as opt

THUMB_W, THUMB_H = 132, 186
CHUNK = 6  # миниатюр за один такт: окно открывается сразу и не подвисает на больших файлах


class PagesDialog(QDialog):
    def __init__(self, parent, pdf: PdfSource, current: int):
        super().__init__(parent)
        self.setWindowTitle("Удалить страницы")
        self.resize(780, 620)
        self._pdf = pdf
        self._total = pdf.page_count
        self._next = 0
        self._syncing = False
        self.result_pages: list[int] = []  # номера с нуля

        root = QVBoxLayout(self)
        root.setSpacing(10)
        hint = QLabel("Отметьте страницы, которые нужно убрать (Ctrl и Shift — выбрать несколько). "
                      "Файл изменится только после «Сохранить», а до этого удаление можно отменить (Ctrl+Z).")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        root.addWidget(hint)

        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list.setIconSize(QSize(THUMB_W, THUMB_H))
        self.list.setGridSize(QSize(THUMB_W + 28, THUMB_H + 44))
        self.list.setSpacing(4)
        self.list.setUniformItemSizes(True)
        self.list.itemSelectionChanged.connect(self._selection_changed)
        root.addWidget(self.list, 1)

        row = QHBoxLayout()
        row.addWidget(QLabel("Или впишите номера:"))
        self.range_edit = QLineEdit()
        self.range_edit.setPlaceholderText("например: 1-3, 5, 8-")
        self.range_edit.textEdited.connect(self._range_edited)
        row.addWidget(self.range_edit, 1)
        root.addLayout(row)

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("muted")
        bottom.addWidget(self.status, 1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        self.delete_button = QPushButton("Удалить выбранные")
        self.delete_button.setObjectName("danger")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._accept)
        bottom.addWidget(cancel)
        bottom.addWidget(self.delete_button)
        root.addLayout(bottom)

        placeholder = self._placeholder()
        for i in range(self._total):
            item = QListWidgetItem(QIcon(placeholder), str(i + 1))
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.list.addItem(item)
        if 1 <= current <= self._total:
            self.list.item(current - 1).setSelected(True)
            self.list.scrollToItem(self.list.item(current - 1))
        self._selection_changed()
        QTimer.singleShot(0, self._fill_chunk)

    # ------------------------------------------------------------------ миниатюры

    def _placeholder(self) -> QPixmap:
        pm = QPixmap(THUMB_W, THUMB_H)
        pm.fill(QColor("#ffffff"))
        return pm

    def _thumb(self, index: int) -> QPixmap:
        image = self._pdf.render_image(index, THUMB_W * 2)
        canvas = QImage(THUMB_W, THUMB_H, QImage.Format.Format_RGB32)
        canvas.fill(QColor("#ffffff"))
        if image is not None:
            scaled = image.scaled(THUMB_W, THUMB_H, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter = QPainter(canvas)
            painter.drawImage((THUMB_W - scaled.width()) // 2, (THUMB_H - scaled.height()) // 2, scaled)
            painter.setPen(QColor("#c4c7d3"))
            painter.drawRect(0, 0, THUMB_W - 1, THUMB_H - 1)
            painter.end()
        return QPixmap.fromImage(canvas)

    def _fill_chunk(self) -> None:
        end = min(self._total, self._next + CHUNK)
        for i in range(self._next, end):
            try:
                self.list.item(i).setIcon(QIcon(self._thumb(i)))
            except Exception:  # noqa: BLE001 - одна плохая страница не должна ломать окно
                pass
        self._next = end
        if self._next < self._total and self.isVisible():
            QTimer.singleShot(0, self._fill_chunk)

    # ------------------------------------------------------------------ выбор

    def _selected(self) -> list[int]:
        return sorted(self.list.row(item) for item in self.list.selectedItems())

    def _selection_changed(self) -> None:
        picked = self._selected()
        if not self._syncing:
            self.range_edit.setText(_compact(picked))
        self.delete_button.setEnabled(bool(picked) and len(picked) < self._total)
        if len(picked) >= self._total and picked:
            self.status.setText("Нельзя удалить все страницы")
        else:
            self.status.setText(f"Выбрано страниц: {len(picked)} из {self._total}" if picked else f"Всего страниц: {self._total}")

    def _range_edited(self, text: str) -> None:
        pages = opt.parse_range(text, self._total) if text.strip() else []
        self._syncing = True
        self.list.blockSignals(True)
        self.list.clearSelection()
        if pages:
            for n in pages:
                self.list.item(n - 1).setSelected(True)
            self.list.scrollToItem(self.list.item(pages[0] - 1))
        self.list.blockSignals(False)
        self._syncing = False
        picked = self._selected()
        self.delete_button.setEnabled(bool(picked) and len(picked) < self._total)
        if text.strip() and pages is None:
            self.status.setText("Неверная запись. Пример: 1-3, 5, 8-")
        else:
            self.status.setText(f"Выбрано страниц: {len(picked)} из {self._total}" if picked else f"Всего страниц: {self._total}")

    def _accept(self) -> None:
        self.result_pages = self._selected()
        if self.result_pages and len(self.result_pages) < self._total:
            self.accept()


def _compact(rows: list[int]) -> str:
    """[0,1,2,4] -> «1-3, 5»."""
    out, i = [], 0
    while i < len(rows):
        j = i
        while j + 1 < len(rows) and rows[j + 1] == rows[j] + 1:
            j += 1
        out.append(str(rows[i] + 1) if i == j else f"{rows[i] + 1}-{rows[j] + 1}")
        i = j + 1
    return ", ".join(out)
