"""Параметры печати и чистая логика: какие страницы и в каком порядке печатать."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Paper:
    key: str
    label: str
    mm_width: int
    mm_height: int
    pcl_code: int
    dmpaper: int  # код бумаги Windows, им пользуются фильтры foo2*


PAPERS = {
    "A4": Paper("A4", "A4", 210, 297, 26, 9),
    "A5": Paper("A5", "A5", 148, 210, 25, 11),
    "LETTER": Paper("LETTER", "Letter", 216, 279, 2, 1),
    "LEGAL": Paper("LEGAL", "Legal", 216, 356, 3, 5),
}

AUTO, PORTRAIT, LANDSCAPE = "auto", "portrait", "landscape"
PAGES_ALL, PAGES_CURRENT, PAGES_RANGE = "all", "current", "range"
# OFF — односторонняя; BATCH — сначала все лицевые, потом обратные (как в Word); SHEET — лист за листом с паузой на переворот
DUPLEX_OFF, DUPLEX_BATCH, DUPLEX_SHEET = "off", "batch", "sheet"
ROTATE_NONE, ROTATE_LANDSCAPE_PAGES, ROTATE_ALL = "none", "landscape_pages", "all"


@dataclass
class PrintOptions:
    paper: Paper = field(default_factory=lambda: PAPERS["A4"])
    orientation: str = AUTO
    margin_mils: int = 400   # тысячные доли дюйма (200 ≈ 5 мм)
    pages: str = PAGES_ALL
    range_text: str = ""
    copies: int = 1
    duplex: str = DUPLEX_OFF
    reverse_backs: bool = False
    dpi: int = 300
    pjl: bool = False

    def rotate_mode(self) -> str:
        return {AUTO: ROTATE_LANDSCAPE_PAGES, PORTRAIT: ROTATE_NONE, LANDSCAPE: ROTATE_ALL}[self.orientation]


def parse_range(text: str, total: int) -> list[int] | None:
    """«1-3, 5, 8-» -> [1, 2, 3, 5, 8, …]. None — если запись неверна или страницы вне документа."""
    result: list[int] = []
    for part in text.replace(";", ",").split(","):
        t = part.strip()
        if not t:
            continue
        if "-" not in t:
            if not t.isdigit():
                return None
            n = int(t)
            if n < 1 or n > total:
                return None
            result.append(n)
        else:
            a, b = (x.strip() for x in t.split("-", 1))
            if (a and not a.isdigit()) or (b and not b.isdigit()):
                return None
            start = int(a) if a else 1
            end = int(b) if b else total
            if start < 1 or end > total or start > end:
                return None
            result.extend(range(start, end + 1))
    return result or None


def passes(pages: list[int], mode: str, reverse_backs: bool) -> list[list[int]]:
    """Проходы печати. 0 в списке — пустая страница (держит порядок листов при обратной раскладке)."""
    if mode == DUPLEX_OFF:
        return [pages]
    if mode == DUPLEX_SHEET:
        return [[p] for p in pages]
    fronts = pages[0::2]
    backs = pages[1::2]
    if not backs:
        return [fronts]
    if reverse_backs:
        backs = backs[::-1]
        if len(pages) % 2 == 1:  # у последнего листа обратная сторона пустая, в обратном порядке он идёт первым
            backs = [0] + backs
    return [fronts, backs]


def should_rotate(page_w: float, page_h: float, mode: str) -> bool:
    """Бумага всегда подаётся книжной; повернуть ли страницу на 90°."""
    if mode == ROTATE_ALL:
        return True
    if mode == ROTATE_LANDSCAPE_PAGES:
        return page_w > page_h
    return False


def fit(page_w: float, page_h: float, avail_w: float, avail_h: float) -> tuple[float, float, float]:
    """Масштаб и смещение, чтобы страница целиком поместилась в область и стояла по центру."""
    scale = min(avail_w / page_w, avail_h / page_h)
    return scale, (avail_w - page_w * scale) / 2.0, (avail_h - page_h * scale) / 2.0
