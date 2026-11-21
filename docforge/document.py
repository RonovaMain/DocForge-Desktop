"""Открытый документ: HTML для просмотра, рабочая копия для правки, картинки пакета, PDF."""
from __future__ import annotations

import os
import shutil
import tempfile
import zipfile

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
        self._tmp = tempfile.mkdtemp(prefix="docforge-")
        ext = os.path.splitext(self.name)[1] or "." + self.format.lower()
        self.work = os.path.join(self._tmp, "work" + ext)
        shutil.copyfile(path, self.work)
        try:
            if self.kind == "pdf":
                from .pdfsource import PdfSource

                self.pdf = PdfSource(self.work)
                self.html = engine.pdf_pages(self.pdf.page_sizes())
            else:
                self.html = engine.render(self.work, self.name)
        except Exception:
            self.close()
            raise

    # ------------------------------------------------------------------ свойства

    @property
    def editable(self) -> bool:
        return self.kind != "pdf"

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

    def close(self) -> None:
        if self.pdf is not None:
            self.pdf.close()
            self.pdf = None
        shutil.rmtree(self._tmp, ignore_errors=True)
