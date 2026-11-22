"""Открытый документ: HTML для просмотра, рабочая копия для правки, картинки пакета, PDF."""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
import zipfile

from . import pdfedit, pdfpage
from .engine import DocError, EngineClient

KINDS = {"DOCX": "text", "ODT": "text", "XLSX": "sheet", "ODS": "sheet", "PPTX": "slides", "ODP": "slides", "PDF": "pdf"}
TITLES = {
    "DOCX": "Word", "XLSX": "Excel", "PPTX": "PowerPoint", "ODT": "LibreOffice Writer",
    "ODS": "LibreOffice Calc", "ODP": "LibreOffice Impress", "PDF": "PDF",
}
IMAGE_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".jpe": "image/jpeg", ".gif": "image/gif",
    ".bmp": "image/bmp", ".webp": "image/webp", ".svg": "image/svg+xml",
}
OPEN_FILTER = (
    "Документы (*.docx *.xlsx *.pptx *.odt *.ods *.odp *.pdf *.docm *.xlsm *.pptm *.ppsx *.dotx *.xltx *.potx *.ott *.ots *.otp);;"
    "Все файлы (*)"
)


def image_mime(part_name: str) -> str | None:
    return IMAGE_MIME.get(os.path.splitext(part_name.lower())[1])


class LoadedDoc:
    def __init__(self, engine: EngineClient, path: str):
        self.engine = engine
        self.source_path = path
        self.name = os.path.basename(path)
        self.format = engine.detect(path, self.name)
        self.kind = KINDS[self.format]
        self.dirty = False
        self.pdf = None
        self.marks: dict[int, list[dict]] = {}  # пометки PDF, ещё не вшитые в файл: страница (с нуля) -> список
        self._undo: list[tuple] = []
        self._redo: list[tuple] = []
        self._backups = 0
        self.zoom_mode, self.zoom_pct = "width", 100
        self._tmp = tempfile.mkdtemp(prefix="docforge-")
        ext = os.path.splitext(self.name)[1] or "." + self.format.lower()
        self.work = os.path.join(self._tmp, "work" + ext)
        shutil.copyfile(path, self.work)
        try:
            if self.kind == "pdf":
                from .pdfsource import PdfSource

                self.pdf = PdfSource(self.work)
                self.html = self.pdf_html()
            else:
                self.html = engine.render(self.work, self.name)
        except Exception:
            self.close()
            raise

    # ------------------------------------------------------------------ свойства

    @property
    def editable(self) -> bool:
        """Можно ли править текст (у PDF вместо этого — пометки и удаление страниц)."""
        return self.kind != "pdf"

    @property
    def is_pdf(self) -> bool:
        return self.kind == "pdf"

    @property
    def title(self) -> str:
        return TITLES.get(self.format, self.format)

    @property
    def has_pages(self) -> bool:
        return self.kind in ("slides", "pdf")

    # ------------------------------------------------------------------ картинки пакета

    def media(self, part_name: str) -> bytes | None:
        if self.kind == "pdf" or image_mime(part_name) is None:
            return None
        try:
            with zipfile.ZipFile(self.work) as z:
                return z.read(part_name)
        except (KeyError, OSError, zipfile.BadZipFile):
            return None

    def image_parts(self) -> list[str]:
        """Все картинки документа: из папок media (Office) и Pictures (ODF)."""
        if self.kind == "pdf":
            return []
        try:
            with zipfile.ZipFile(self.work) as z:
                names = z.namelist()
        except (OSError, zipfile.BadZipFile):
            return []
        out = []
        for n in names:
            low = n.lower()
            if image_mime(low) and ("/media/" in low or low.startswith("pictures/")):
                out.append(n)
        return sorted(out)

    # ------------------------------------------------------------------ правка

    def text_at(self, element_id: str) -> str:
        return self.engine.text_at(self.work, self.name, element_id)

    def display_at(self, element_id: str) -> str:
        return self.engine.display_at(self.work, self.name, element_id)

    def edit(self, element_id: str, text: str) -> None:
        out = os.path.join(self._tmp, "edit.tmp")
        self.engine.edit_text(self.work, self.name, element_id, text, out)
        os.replace(out, self.work)
        self.dirty = True

    def save(self, target: str | None = None) -> str:
        """Пишет рабочую копию в [target] (по умолчанию — в исходный файл). Запись через временный файл: при сбое исходник цел."""
        dest = target or self.source_path
        tmp = dest + ".docforge-tmp"
        try:
            shutil.copyfile(self.work, tmp)
            os.replace(tmp, dest)
        except OSError as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise DocError(f"Не удалось сохранить файл: {e.strerror or e}") from e
        self.source_path = dest
        self.name = os.path.basename(dest)
        self.dirty = False
        return dest

    # ------------------------------------------------------------------ PDF: пометки и страницы

    def pdf_html(self) -> str:
        return pdfpage.build_html(self.pdf.page_sizes_f(), self.zoom_mode, self.zoom_pct)

    @property
    def has_marks(self) -> bool:
        return any(self.marks.values())

    def marks_of(self, page: int) -> list[dict]:
        return self.marks.get(page, [])

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def add_mark(self, page: int, op: dict) -> None:
        self.marks.setdefault(page, []).append(op)
        self._undo.append(("add", page))
        self._redo.clear()
        self.dirty = True

    def erase_mark(self, page: int, index: int) -> bool:
        items = self.marks.get(page, [])
        if not 0 <= index < len(items):
            return False
        op = items.pop(index)
        self._undo.append(("erase", page, index, op))
        self._redo.clear()
        self.dirty = True
        return True

    def undo(self) -> tuple[str, int]:
        """Отменяет последнее действие. Возвращает («page», номер страницы) или («all», -1), если изменился сам файл; («», -1) — нечего отменять."""
        if not self._undo:
            return "", -1
        entry = self._undo.pop()
        kind = entry[0]
        if kind == "add":
            op = self.marks[entry[1]].pop()
            self._redo.append(("add", entry[1], op))
            return "page", entry[1]
        if kind == "erase":
            _, page, index, op = entry
            self.marks.setdefault(page, []).insert(index, op)
            self._redo.append(("erase", page, index))
            return "page", page
        # удаление страниц: возвращаем прежний файл и прежние пометки
        _, backup, marks, undo, redo = entry
        self._swap_pdf_file(backup)
        self.marks, self._undo, self._redo = marks, undo, redo
        return "all", -1

    def redo(self) -> tuple[str, int]:
        if not self._redo:
            return "", -1
        entry = self._redo.pop()
        if entry[0] == "add":
            self.marks.setdefault(entry[1], []).append(entry[2])
            self._undo.append(("add", entry[1]))
            return "page", entry[1]
        _, page, index = entry
        items = self.marks.get(page, [])
        if 0 <= index < len(items):
            op = items.pop(index)
            self._undo.append(("erase", page, index, op))
        return "page", page

    def _new_tmp(self, tag: str) -> str:
        self._backups += 1
        return os.path.join(self._tmp, f"{tag}{self._backups}.pdf")

    def _swap_pdf_file(self, path: str) -> None:
        """Делает [path] рабочим файлом PDF и заново открывает его для просмотра и печати."""
        from .pdfsource import PdfSource

        new_work = self._new_tmp("work")
        shutil.copyfile(path, new_work)
        old_pdf, old_work = self.pdf, self.work
        self.pdf = PdfSource(new_work)
        if old_pdf is not None:
            old_pdf.close()
        self.work = new_work
        try:
            os.remove(old_work)
        except OSError:
            pass
        self.html = self.pdf_html()

    def commit_marks(self) -> bool:
        """Вшивает пометки в рабочий файл. True — что-то изменилось (страницы надо перерисовать)."""
        if not self.has_marks:
            self.marks.clear()
            return False
        out = self._new_tmp("marked")
        pdfedit.write_with_ops(self.work, out, self.marks)
        self._swap_pdf_file(out)
        os.remove(out)
        self.marks = {}
        self._drop_history()
        return True

    def _drop_history(self) -> None:
        for entry in self._undo + self._redo:
            if entry and entry[0] == "pages" and len(entry) > 1 and isinstance(entry[1], str):
                try:
                    os.remove(entry[1])
                except OSError:
                    pass
        self._undo, self._redo = [], []

    def delete_pages(self, pages: list[int]) -> int:
        """Удаляет страницы (номера с нуля) из рабочей копии. Возвращает число оставшихся. Отменяется через undo()."""
        if self.pdf is None:
            raise DocError("Это не PDF.")
        backup = self._new_tmp("backup")
        shutil.copyfile(self.work, backup)
        marks_before = copy.deepcopy(self.marks)
        undo_before, redo_before = list(self._undo), list(self._redo)
        # пометки сначала вшиваем: после удаления номера страниц сдвигаются
        src = self.work
        if self.has_marks:
            marked = self._new_tmp("marked")
            pdfedit.write_with_ops(self.work, marked, self.marks)
            src = marked
        out = self._new_tmp("cut")
        try:
            left = pdfedit.write_without_pages(src, out, pages)
        finally:
            if src != self.work and os.path.exists(src):
                os.remove(src)
        self._swap_pdf_file(out)
        os.remove(out)
        self.marks = {}
        self._undo = [("pages", backup, marks_before, undo_before, redo_before)]
        self._redo = []
        self.dirty = True
        return left

    def printable_pdf(self) -> str:
        """Путь к PDF для печати: рабочий файл, а если есть несохранённые пометки — его копия с ними."""
        if not self.has_marks:
            return self.work
        out = os.path.join(self._tmp, "print.pdf")
        pdfedit.write_with_ops(self.work, out, self.marks)
        return out

    def close(self) -> None:
        if self.pdf is not None:
            self.pdf.close()
            self.pdf = None
        shutil.rmtree(self._tmp, ignore_errors=True)
