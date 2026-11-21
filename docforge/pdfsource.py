"""PDF средствами Qt (QtPdf): страницы для просмотра и растр для печати. Без сторонних библиотек."""
from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QBuffer, QIODevice, QSize, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtPdf import QPdfDocument

from .engine import DocError
from .printing.options import fit, should_rotate

MAX_PIXELS = 12_000_000

_ERRORS = {
    "IncorrectPassword": "PDF защищён паролем — такие файлы пока не поддерживаются.",
    "UnsupportedSecurityScheme": "PDF зашифрован неподдерживаемым способом.",
    "InvalidFileFormat": "Файл повреждён или не является PDF.",
    "FileNotFound": "Файл не найден.",
}


class PdfSource:
    """Один документ QtPdf. Объект не потокобезопасен: для печати в другом потоке создавайте свой экземпляр."""

    def __init__(self, path: str):
        self.path = path
        self.doc = QPdfDocument(None)
        error = self.doc.load(path)
        if error != QPdfDocument.Error.None_:
            raise DocError(_ERRORS.get(error.name, f"Не удалось открыть PDF ({error.name})."))

    @property
    def page_count(self) -> int:
        return self.doc.pageCount()

    def page_sizes(self) -> list[tuple[int, int]]:
        out = []
        for i in range(self.doc.pageCount()):
            s = self.doc.pagePointSize(i)
            out.append((max(1, round(s.width())), max(1, round(s.height()))))
        return out

    def _render(self, index: int, width: int, height: int) -> QImage:
        image = self.doc.render(index, QSize(width, height))
        canvas = QImage(image.size(), QImage.Format.Format_RGB32)
        canvas.fill(Qt.GlobalColor.white)
        painter = QPainter(canvas)
        painter.drawImage(0, 0, image)
        painter.end()
        return canvas

    def render_image(self, index: int, width: int) -> QImage | None:
        """Страница шириной [width] пикселей (ограничено по числу пикселей, чтобы не исчерпать память)."""
        if index < 0 or index >= self.doc.pageCount():
            return None
        size = self.doc.pagePointSize(index)
        height = max(1, int(size.height() * width / max(1.0, size.width())))
        if width * height > MAX_PIXELS:
            k = (MAX_PIXELS / (width * height)) ** 0.5
            width, height = max(1, int(width * k)), max(1, int(height * k))
        return self._render(index, width, height)

    def render_jpeg(self, index: int, width: int) -> bytes | None:
        image = self.render_image(index, width)
        if image is None:
            return None
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        image.save(buf, "JPEG", 90)
        return bytes(buf.data())

    def render_page(self, index: int, w: int, h: int, margin: int, rotate_mode: str, gray: bool = True) -> QImage:
        """Страница, вписанная в лист [w]×[h] пикселей с полем [margin]; при необходимости повёрнута на 90°. Фон белый."""
        size = self.doc.pagePointSize(index)
        pw, ph = size.width(), size.height()
        rotated = should_rotate(pw, ph, rotate_mode)
        if rotated:
            pw, ph = ph, pw
        scale, ox, oy = fit(pw, ph, max(1, w - 2 * margin), max(1, h - 2 * margin))
        tw, th = max(1, int(pw * scale)), max(1, int(ph * scale))
        page_image = self._render(index, th, tw) if rotated else self._render(index, tw, th)
        canvas = QImage(w, h, QImage.Format.Format_Grayscale8 if gray else QImage.Format.Format_RGB32)
        canvas.fill(Qt.GlobalColor.white)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if rotated:
            painter.translate(margin + ox + tw, margin + oy)
            painter.rotate(90)
            painter.drawImage(0, 0, page_image)
        else:
            painter.drawImage(int(margin + ox), int(margin + oy), page_image)
        painter.end()
        return canvas

    def render_gray(self, index: int, w: int, h: int, margin: int, rotate_mode: str) -> np.ndarray:
        """То же, что render_page, но как серый массив numpy (высота × ширина) — для кодировщиков PCL/PostScript/PBM."""
        image = self.render_page(index, w, h, margin, rotate_mode, gray=True)
        ptr = image.constBits()
        ptr.setsize(image.sizeInBytes())
        stride = image.bytesPerLine()
        return np.frombuffer(ptr, dtype=np.uint8).reshape(image.height(), stride)[:, :image.width()].copy()

    def close(self) -> None:
        self.doc.close()
