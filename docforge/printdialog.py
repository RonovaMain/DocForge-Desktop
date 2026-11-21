"""Окно печати: два способа — системная печать (драйвер Windows / CUPS) и встроенная печать DocForge (PCL, PostScript, foo2zjs…)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from .config import Settings
from .paths import config_dir, filter_binary
from .printing import catalog, options as opt
from .printing.devices import PrinterInfo, list_printers

MARGINS = [("Без полей", 0), ("5 мм", 200), ("10 мм", 400), ("20 мм", 800)]
QUALITY = [("Черновик, 150 dpi", 150), ("Обычное, 300 dpi", 300), ("Высокое, 600 dpi", 600)]
ORIENTATIONS = [("Авто (по странице)", opt.AUTO), ("Книжная", opt.PORTRAIT), ("Альбомная", opt.LANDSCAPE)]
DUPLEXES = [
    ("Односторонняя", opt.DUPLEX_OFF),
    ("Вручную, пачкой (сначала лицевые, потом обратные)", opt.DUPLEX_BATCH),
    ("Вручную, лист за листом", opt.DUPLEX_SHEET),
]


@dataclass
class PrintRequest:
    options: opt.PrintOptions
    mode: str                      # "system" | "builtin"
    printer: PrinterInfo | None
    spec: catalog.DriverSpec | None
    firmware: str | None
    pages_choice: str
    range_text: str


def firmware_path(printer_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", printer_name) or "printer"
    return str(config_dir() / "firmware" / f"{safe}.dl")


def driver_available(spec: catalog.DriverSpec) -> bool:
    return spec.kind != catalog.FILTER or (spec.binary is not None and filter_binary(spec.binary) is not None)


class PrintDialog(QDialog):
    def __init__(self, parent, settings: Settings, can_current: bool, doc_is_pdf: bool):
        super().__init__(parent)
        self.setWindowTitle("Печать")
        self.setMinimumWidth(560)
        self._settings = settings
        self._saved = dict(settings["print"] or {})
        self._doc_is_pdf = doc_is_pdf
        self.request: PrintRequest | None = None
        self._printers = list_printers()

        root = QVBoxLayout(self)

        # --- способ печати
        mode_box = QGroupBox("Способ печати")
        mode_layout = QVBoxLayout(mode_box)
        self.mode_system = QRadioButton("Системная — драйвер принтера Windows / CUPS (как в других программах)")
        self.mode_builtin = QRadioButton("Встроенная — DocForge сам готовит данные: PCL, PostScript, foo2zjs и др.")
        group = QButtonGroup(self)
        group.addButton(self.mode_system)
        group.addButton(self.mode_builtin)
        mode_layout.addWidget(self.mode_system)
        mode_layout.addWidget(self.mode_builtin)
        root.addWidget(mode_box)

        # --- принтер
        form = QFormLayout()
        self.printer_combo = QComboBox()
        for p in self._printers:
            self.printer_combo.addItem(p.name + ("  (по умолчанию)" if p.is_default else ""), p)
        if not self._printers:
            self.printer_combo.addItem("Принтеры не найдены")
            self.printer_combo.setEnabled(False)
        default_index = next((i for i, p in enumerate(self._printers) if p.is_default), 0)
        saved_name = self._saved.get("printer")
        saved_index = next((i for i, p in enumerate(self._printers) if p.name == saved_name), default_index)
        self.printer_combo.setCurrentIndex(saved_index)
        form.addRow("Принтер:", self.printer_combo)
        root.addLayout(form)

        # --- встроенная печать
        self.builtin_box = QGroupBox("Встроенная печать")
        bl = QFormLayout(self.builtin_box)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bl.addRow(self.info)
        self.driver_combo = QComboBox()
        bl.addRow("Драйвер:", self.driver_combo)
        fw_row = QWidget()
        fw_layout = QHBoxLayout(fw_row)
        fw_layout.setContentsMargins(0, 0, 0, 0)
        self.fw_label = QLabel()
        self.fw_label.setWordWrap(True)
        self.fw_button = QPushButton("Выбрать .dl…")
        fw_layout.addWidget(self.fw_label, 1)
        fw_layout.addWidget(self.fw_button)
        self.fw_row = fw_row
        bl.addRow("Прошивка:", fw_row)
        self.quality = QComboBox()
        for label, dpi in QUALITY:
            self.quality.addItem(label, dpi)
        self.quality.setCurrentIndex(max(0, self.quality.findData(self._saved.get("dpi", 300))))
        bl.addRow("Качество (PCL):", self.quality)
        self.pjl = QCheckBox("Отправлять PJL-заголовок")
        self.pjl.setChecked(bool(self._saved.get("pjl", False)))
        bl.addRow(self.pjl)
        if os.name == "nt":
            note = QLabel("В Windows данные уходят в очередь принтера как RAW. Если очередь не принимает RAW, добавьте принтер "
                          "на его порт (например USB001) с драйвером «Generic / Text Only».")
            note.setWordWrap(True)
            note.setStyleSheet("color: gray;")
            bl.addRow(note)
        root.addWidget(self.builtin_box)

        # --- страницы и бумага
        common = QFormLayout()
        pages_row = QWidget()
        pl = QHBoxLayout(pages_row)
        pl.setContentsMargins(0, 0, 0, 0)
        self.pages_all = QRadioButton("Все")
        self.pages_current = QRadioButton("Текущая")
        self.pages_range = QRadioButton("Диапазон:")
        self.range_edit = QLineEdit(self._saved.get("range", ""))
        self.range_edit.setPlaceholderText("1-3, 5, 8-")
        pg = QButtonGroup(self)
        for b in (self.pages_all, self.pages_current, self.pages_range):
            pg.addButton(b)
            pl.addWidget(b)
        pl.addWidget(self.range_edit, 1)
        self.pages_current.setEnabled(can_current)
        self.pages_all.setChecked(True)
        self.range_edit.textChanged.connect(lambda t: self.pages_range.setChecked(True) if t.strip() else None)
        common.addRow("Страницы:", pages_row)

        self.paper = QComboBox()
        for p in opt.PAPERS.values():
            self.paper.addItem(p.label, p.key)
        self.paper.setCurrentIndex(max(0, self.paper.findData(self._saved.get("paper", "A4"))))
        common.addRow("Бумага:", self.paper)
        self.orientation = QComboBox()
        for label, key in ORIENTATIONS:
            self.orientation.addItem(label, key)
        self.orientation.setCurrentIndex(max(0, self.orientation.findData(self._saved.get("orientation", opt.AUTO))))
        common.addRow("Ориентация:", self.orientation)
        self.margins = QComboBox()
        for label, mils in MARGINS:
            self.margins.addItem(label, mils)
        self.margins.setCurrentIndex(max(0, self.margins.findData(self._saved.get("margin", 400))))
        common.addRow("Поля:", self.margins)
        self.copies = QSpinBox()
        self.copies.setRange(1, 99)
        self.copies.setValue(1)
        common.addRow("Копии:", self.copies)
        self.duplex = QComboBox()
        for label, key in DUPLEXES:
            self.duplex.addItem(label, key)
        self.duplex.setCurrentIndex(max(0, self.duplex.findData(self._saved.get("duplex", opt.DUPLEX_OFF))))
        common.addRow("Двусторонняя:", self.duplex)
        self.reverse = QCheckBox("Обратные стороны в обратном порядке (если принтер выдаёт листы лицом вверх)")
        self.reverse.setChecked(bool(self._saved.get("reverse", False)))
        common.addRow(self.reverse)
        root.addLayout(common)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Печать")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        (self.mode_builtin if self._saved.get("mode", settings["print_mode"]) == "builtin" else self.mode_system).setChecked(True)
        self.mode_system.toggled.connect(self._refresh)
        self.printer_combo.currentIndexChanged.connect(self._detect)
        self.driver_combo.currentIndexChanged.connect(self._refresh_firmware)
        self.fw_button.clicked.connect(self._pick_firmware)
        self._detect()
        self._refresh()

    # ------------------------------------------------------------------ состояние

    def _printer(self) -> PrinterInfo | None:
        data = self.printer_combo.currentData()
        return data if isinstance(data, PrinterInfo) else None

    def _spec(self) -> catalog.DriverSpec | None:
        data = self.driver_combo.currentData()
        return data if isinstance(data, catalog.DriverSpec) else None

    def _refresh(self) -> None:
        self.builtin_box.setVisible(self.mode_builtin.isChecked())
        self.adjustSize()

    def _detect(self) -> None:
        """Автоопределение: по модели принтера подбирается способ печати и ставится первым в списке."""
        printer = self._printer()
        self.driver_combo.blockSignals(True)
        self.driver_combo.clear()
        matches = catalog.select(printer.manufacturer, printer.model, []) if printer else catalog.select("", "", [])
        ordered = [m.spec for m in matches] + [s for s in catalog.ALL if s.id not in {m.spec.id for m in matches}]
        pick = next((m for m in matches if driver_available(m.spec)), None)
        for spec in ordered:
            label = spec.title + ("" if driver_available(spec) else "  (нет в этой сборке)")
            self.driver_combo.addItem(label, spec)
        self.driver_combo.setCurrentIndex(ordered.index(pick.spec) if pick else 0)
        self.driver_combo.blockSignals(False)
        text = f"Принтер: {printer.model}" if printer else "Принтер не выбран"
        if pick:
            text += f"\nВыбран способ печати: {pick.spec.title}\n({pick.reason})"
        self.info.setText(text)
        self._refresh_firmware()

    def _refresh_firmware(self) -> None:
        spec, printer = self._spec(), self._printer()
        visible = bool(spec and spec.needs_firmware and printer)
        self.fw_row.setVisible(visible)
        form = self.builtin_box.layout()
        label = form.labelForField(self.fw_row)
        if label is not None:
            label.setVisible(visible)
        if visible:
            have = os.path.isfile(firmware_path(printer.name))
            self.fw_label.setText("Выбрана, будет загружена в принтер перед печатью" if have else "Не выбрана (нужна для этой модели)")

    def _pick_firmware(self) -> None:
        printer = self._printer()
        if printer is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Файл прошивки принтера", "", "Прошивка (*.dl);;Все файлы (*)")
        if not path:
            return
        size = os.path.getsize(path)
        if not 0 < size <= 4 * 1024 * 1024:
            QMessageBox.warning(self, "Прошивка", "Файл не похож на прошивку принтера (ожидается .dl размером до 4 МБ).")
            return
        dest = firmware_path(printer.name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(path, "rb") as src, open(dest, "wb") as dst:
            dst.write(src.read())
        self._refresh_firmware()

    # ------------------------------------------------------------------ результат

    def _accept(self) -> None:
        builtin = self.mode_builtin.isChecked()
        printer = self._printer()
        if printer is None:
            QMessageBox.warning(self, "Печать", "Не найден ни один принтер. Установите принтер в системе и повторите.")
            return
        spec = self._spec() if builtin else None
        if builtin and spec is not None and not driver_available(spec):
            QMessageBox.warning(self, "Печать", "Этого драйвера нет в данной сборке программы. Выберите другой или используйте системную печать.")
            return
        choice = opt.PAGES_RANGE if self.pages_range.isChecked() else opt.PAGES_CURRENT if self.pages_current.isChecked() else opt.PAGES_ALL
        if choice == opt.PAGES_RANGE and not self.range_edit.text().strip():
            QMessageBox.warning(self, "Печать", "Укажите диапазон страниц, например 1-3, 5, 8-.")
            return
        options = opt.PrintOptions(
            paper=opt.PAPERS[self.paper.currentData()],
            orientation=self.orientation.currentData(),
            margin_mils=self.margins.currentData(),
            copies=self.copies.value(),
            duplex=self.duplex.currentData(),
            reverse_backs=self.reverse.isChecked(),
            dpi=self.quality.currentData() if builtin else 300,
            pjl=self.pjl.isChecked(),
            pages=choice,
            range_text=self.range_edit.text(),
        )
        fw = None
        if builtin and spec is not None and spec.needs_firmware and os.path.isfile(firmware_path(printer.name)):
            fw = firmware_path(printer.name)
        self.request = PrintRequest(options, "builtin" if builtin else "system", printer, spec, fw, choice, options.range_text)
        self._settings["print"] = {
            "mode": self.request.mode, "printer": printer.name, "paper": self.paper.currentData(),
            "orientation": options.orientation, "margin": options.margin_mils, "duplex": options.duplex,
            "reverse": options.reverse_backs, "dpi": self.quality.currentData(), "pjl": options.pjl,
            "range": options.range_text,
        }
        self._settings["print_mode"] = self.request.mode
        self.accept()
