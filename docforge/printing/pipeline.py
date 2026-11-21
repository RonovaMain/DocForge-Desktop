"""Печать встроенными способами: страницы рисуются растром, кодируются (PCL 5 / PostScript / PBM для фильтра) и уходят в принтер."""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np

from . import pcl
from .catalog import FILTER, PCL5, PDF, POSTSCRIPT, DriverSpec
from .filters import FilterError, FilterProcess, pbm_header
from .halftone import to_bits
from .options import PrintOptions

# render(индекс страницы с нуля, ширина, высота, поле в пикселях, режим поворота) -> серый растр uint8 (высота × ширина), 255 — белый
Render = Callable[[int, int, int, int, str], np.ndarray]


class Cancelled(Exception):
    pass


def _px(mm: float, dpi: int) -> int:
    return int(mm / 25.4 * dpi + 0.5)


def run(
    spec: DriverSpec,
    options: PrintOptions,
    pages: Sequence[int],
    render: Render,
    write: Callable[[bytes], None],
    progress: Callable[[int, int], None] = lambda done, total: None,
    cancelled: Callable[[], bool] = lambda: False,
    filter_binary: str | None = None,
    pdf_bytes: bytes | None = None,
    all_pages: int | None = None,
) -> None:
    """Печатает [pages] (номера с 1; 0 — пустая страница) [options.copies] раз выбранным способом."""
    rotate = options.rotate_mode()
    copies = max(1, options.copies)

    def check() -> None:
        if cancelled():
            raise Cancelled("Печать отменена")

    def page_gray(number: int, w: int, h: int, margin: int) -> np.ndarray:
        if number == 0:
            return np.full((h, w), 255, dtype=np.uint8)
        return render(number - 1, w, h, margin, rotate)

    if spec.kind == PDF:
        if pdf_bytes is None or list(pages) != list(range(1, (all_pages or len(pages)) + 1)):
            raise ValueError("«PDF напрямую» печатает документ целиком: выберите все страницы и односторонний режим")
        for c in range(copies):
            check()
            if options.pjl:
                write(b"\x1b%-12345X@PJL ENTER LANGUAGE=PDF\r\n")
            write(pdf_bytes)
            if options.pjl:
                write(b"\x1b%-12345X")
            progress(c + 1, copies)
        return

    total = len(pages) * (copies if spec.kind != FILTER else 1)
    done = 0

    if spec.kind == PCL5:
        dpi = options.dpi
        paper_w, paper_h = _px(options.paper.mm_width, dpi), _px(options.paper.mm_height, dpi)
        # принтеры не печатают у самого края листа (около 4 мм) — растр занимает только печатаемую область
        inset = int(dpi * 0.17 + 0.5)
        raster_w, raster_h = (paper_w - 2 * inset) // 8 * 8, paper_h - 2 * inset
        margin = max(0, _px(options.margin_mils / 1000 * 25.4, dpi) - inset)
        write(pcl.job_begin(options.pjl))
        for _ in range(copies):
            for number in pages:
                check()
                gray = page_gray(number, raster_w, raster_h, margin)
                write(pcl.page(to_bits(gray), options.paper.pcl_code, dpi))
                done += 1
                progress(done, total)
        write(pcl.job_end(options.pjl))
        return

    if spec.kind == POSTSCRIPT:
        from .postscript import PostScriptWriter

        dpi = spec.dpi or 200
        w, h = _px(options.paper.mm_width, dpi), _px(options.paper.mm_height, dpi)
        margin = _px(options.margin_mils / 1000 * 25.4, dpi)
        pt_w, pt_h = _px(options.paper.mm_width, 72), _px(options.paper.mm_height, 72)
        if options.pjl:
            write(b"\x1b%-12345X@PJL ENTER LANGUAGE=POSTSCRIPT\r\n")
        ps = PostScriptWriter(write)
        for _ in range(copies):
            for number in pages:
                check()
                ps.page(page_gray(number, w, h, margin), pt_w, pt_h)
                done += 1
                progress(done, total)
        ps.finish()
        if options.pjl:
            write(b"\x1b%-12345X")
        return

    if spec.kind == FILTER:
        if not filter_binary:
            raise FilterError(f"Драйвера {spec.binary} нет в этой сборке программы")
        dpi = spec.dpi
        paper_w, paper_h = _px(options.paper.mm_width, dpi), _px(options.paper.mm_height, dpi)
        raster_w = (paper_w + 7) // 8 * 8
        margin = _px(options.margin_mils / 1000 * 25.4, dpi)
        command = [filter_binary] + spec.filter_args(raster_w, paper_h, options.paper.dmpaper, copies)
        proc = FilterProcess(command, write)
        try:
            for number in pages:
                check()
                gray = page_gray(number, raster_w, paper_h, margin)
                proc.stdin.write(pbm_header(raster_w, paper_h))
                proc.stdin.write(to_bits(gray).tobytes())
                done += 1
                progress(done, total)
        except (OSError, ValueError) as e:  # чаще всего фильтр завершился сам: его сообщение полезнее, чем «Broken pipe»
            try:
                proc.finish()
            except FilterError as inner:
                raise inner
            raise FilterError(f"Не удалось передать страницу драйверу: {e}") from e
        except BaseException:
            proc.abort()
            raise
        proc.finish()
        return

    raise ValueError(f"Неизвестный способ печати: {spec.kind}")
