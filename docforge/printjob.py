"""Печать документа: подготовка PDF, проходы двусторонней печати и фоновая работа (системная или встроенная)."""
from __future__ import annotations

import os
import tempfile
import time

from PyQt6.QtCore import QMarginsF, QObject, QRectF, QThread, pyqtSignal
from PyQt6.QtGui import QPageLayout, QPageSize, QPainter
from PyQt6.QtPrintSupport import QPrinter
from PyQt6.QtWidgets import QMessageBox, QProgressDialog

from .document import LoadedDoc
from .paths import filter_binary
from .pdfsource import PdfSource
from .printdialog import PrintRequest
from .printing import options as opt
from .printing import pipeline
from .printing.catalog import PDF
from .printing.filters import FilterError
from .printing.rawsend import SendError, make_sender

_SIZES = {
    "A4": QPageSize.PageSizeId.A4, "A5": QPageSize.PageSizeId.A5,
    "LETTER": QPageSize.PageSizeId.Letter, "LEGAL": QPageSize.PageSizeId.Legal,
}
FIRMWARE_WAIT_S = 4.0  # время на запуск прошивки подобрано с запасом и не проверялось на конкретных моделях


class PrintWorker(QThread):
    progress = pyqtSignal(int, int)
    finishedWith = pyqtSignal(str)  # "" — успех, "cancelled" — отмена, иначе текст ошибки

    def __init__(self, request: PrintRequest, pdf_path: str, pages: list[int], send_firmware: bool, parent=None):
        super().__init__(parent)
        self.request = request
        self.pdf_path = pdf_path
        self.pages = pages
        self.send_firmware = send_firmware
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        source = None
        try:
            source = PdfSource(self.pdf_path)  # свой экземпляр: QtPdf не потокобезопасен
            if self.request.mode == "system":
                self._print_system(source)
            else:
                self._print_builtin(source)
            self.finishedWith.emit("")
        except pipeline.Cancelled:
            self.finishedWith.emit("cancelled")
        except (FilterError, SendError, ValueError, OSError, RuntimeError) as e:
            self.finishedWith.emit(str(e) or e.__class__.__name__)
        except Exception as e:  # не роняем программу из-за потока печати
            self.finishedWith.emit(f"Неожиданная ошибка печати: {e}")
        finally:
            if source is not None:
                source.close()

    # ------------------------------------------------------------------ встроенная печать

    def _print_builtin(self, source: PdfSource) -> None:
        req = self.request
        spec = req.spec
        if self.send_firmware and req.firmware and spec is not None and spec.needs_firmware:
            with open(req.firmware, "rb") as f:
                data = f.read()
            fw = make_sender(req.printer, "DocForge firmware")
            try:
                fw.write(data)
                fw.close()
            except Exception:
                fw.abort()
                raise
            time.sleep(FIRMWARE_WAIT_S)
        binary = None
        if spec.binary:
            found = filter_binary(spec.binary)
            binary = str(found) if found else None
        pdf_bytes = None
        if spec.kind == PDF:
            with open(self.pdf_path, "rb") as f:
                pdf_bytes = f.read()
        sender = make_sender(req.printer, "DocForge")
        try:
            pipeline.run(
                spec, req.options, self.pages, source.render_gray, sender.write,
                progress=lambda done, total: self.progress.emit(done, total),
                cancelled=lambda: self._cancel, filter_binary=binary, pdf_bytes=pdf_bytes, all_pages=source.page_count,
            )
            sender.close()
        except BaseException:
            sender.abort()
            raise

    # ------------------------------------------------------------------ системная печать

    def _print_system(self, source: PdfSource) -> None:
        o = self.request.options
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if self.request.printer is not None:
            printer.setPrinterName(self.request.printer.name)
        printer.setPageSize(QPageSize(_SIZES[o.paper.key]))
        printer.setPageOrientation(QPageLayout.Orientation.Portrait)
        printer.setFullPage(True)
        printer.setCopyCount(o.copies)
        printer.setCollateCopies(True)
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("Не удалось начать печать: принтер недоступен или не принял задание")
        try:
            rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            px = lambda mm: int(mm / 25.4 * o.dpi + 0.5)
            w, h = px(o.paper.mm_width), px(o.paper.mm_height)
            margin = px(o.margin_mils / 1000 * 25.4)
            rotate = o.rotate_mode()
            total = len(self.pages)
            for i, number in enumerate(self.pages):
                if self._cancel:
                    raise pipeline.Cancelled("Печать отменена")
                if i > 0:
                    printer.newPage()
                if number:
                    image = source.render_page(number - 1, w, h, margin, rotate, gray=False)
                    painter.drawImage(QRectF(0, 0, rect.width(), rect.height()), image)
                self.progress.emit(i + 1, total)
        finally:
            painter.end()


class PrintController(QObject):
    """Ведёт печать от окна до последнего прохода. Живёт, пока идёт печать."""

    finished = pyqtSignal()

    def __init__(self, window, view, doc: LoadedDoc, request: PrintRequest, current_page: int, restore_night):
        super().__init__(window)
        self._window, self._view, self._doc, self._req = window, view, doc, request
        self._current = max(1, current_page)
        self._restore_night = restore_night
        self._tmp = tempfile.mkdtemp(prefix="docforge-print-")
        self._pdf = ""
        self._passes: list[list[int]] = []
        self._pass_index = 0
        self._dialog: QProgressDialog | None = None
        self._worker: PrintWorker | None = None
        self._firmware_pending = request.mode == "builtin" and request.firmware is not None

    def start(self) -> None:
        if self._doc.kind == "pdf":
            self._pdf = self._doc.work
            self._pdf_ready()
            return
        o = self._req.options
        orientation = QPageLayout.Orientation.Landscape if o.orientation == opt.LANDSCAPE else QPageLayout.Orientation.Portrait
        m = o.margin_mils * 25.4 / 1000
        layout = QPageLayout(QPageSize(_SIZES[o.paper.key]), orientation, QMarginsF(m, m, m, m), QPageLayout.Unit.Millimeter)
        self._pdf = os.path.join(self._tmp, "doc.pdf")
        page = self._view.page()
        page.pdfPrintingFinished.connect(self._on_pdf_printed)
        self._view.set_night(False)  # печатаем всегда светлую страницу
        page.printToPdf(self._pdf, layout)

    def _on_pdf_printed(self, path: str, ok: bool) -> None:
        self._view.page().pdfPrintingFinished.disconnect(self._on_pdf_printed)
        self._restore_night()
        if not ok or not os.path.isfile(self._pdf):
            self._fail("Не удалось подготовить страницы документа к печати.")
            return
        self._pdf_ready()

    def _pdf_ready(self) -> None:
        try:
            probe = PdfSource(self._pdf)
            total = probe.page_count
            probe.close()
        except Exception as e:
            self._fail(f"Не удалось прочитать подготовленные страницы: {e}")
            return
        req = self._req
        if req.pages_choice == opt.PAGES_ALL:
            pages = list(range(1, total + 1))
        elif req.pages_choice == opt.PAGES_CURRENT:
            pages = [min(self._current, total)]
        else:
            pages = opt.parse_range(req.range_text, total)
            if pages is None:
                self._fail(f"Неверный диапазон страниц. В документе {total} стр. Пример: 1-3, 5, 8-.")
                return
        self._passes = opt.passes(pages, req.options.duplex, req.options.reverse_backs)
        self._pass_index = 0
        self._run_pass()

    def _run_pass(self) -> None:
        pages = self._passes[self._pass_index]
        label = "Печать…" if len(self._passes) == 1 else f"Проход {self._pass_index + 1} из {len(self._passes)}…"
        dialog = QProgressDialog(label, "Отмена", 0, max(1, len(pages)), self._window)
        dialog.setWindowTitle("Печать")
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self._dialog = dialog
        worker = PrintWorker(self._req, self._pdf, pages, self._firmware_pending and self._pass_index == 0, self)
        self._worker = worker
        worker.progress.connect(lambda done, total: dialog.setValue(min(done, dialog.maximum())))
        worker.finishedWith.connect(self._on_pass_done)
        dialog.canceled.connect(worker.cancel)
        worker.start()

    def _on_pass_done(self, result: str) -> None:
        if self._dialog is not None:
            self._dialog.close()
        if result == "cancelled":
            self._cleanup()
            return
        if result:
            self._fail(result)
            return
        self._firmware_pending = False
        self._pass_index += 1
        if self._pass_index < len(self._passes):
            mode = self._req.options.duplex
            text = ("Переверните напечатанную стопку и положите её обратно в лоток, затем нажмите «Продолжить»."
                    if mode == opt.DUPLEX_BATCH else
                    "Переверните лист и положите его обратно в лоток, затем нажмите «Продолжить».")
            box = QMessageBox(QMessageBox.Icon.Question, "Двусторонняя печать", text, parent=self._window)
            go = box.addButton("Продолжить", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is not go:
                self._cleanup()
                return
            self._run_pass()
            return
        self._cleanup()

    def _fail(self, message: str) -> None:
        QMessageBox.critical(self._window, "Печать", message)
        self._cleanup()

    def _cleanup(self) -> None:
        import shutil

        shutil.rmtree(self._tmp, ignore_errors=True)
        self.finished.emit()
        self.deleteLater()
