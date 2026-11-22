"""Правка PDF: пометки (выделение текста, маркер, ручка, закраска) вшиваются прямо в содержимое страниц, страницы удаляются.

Пометки хранятся как простые словари с координатами в долях страницы (0..1, начало — левый верхний угол видимой страницы),
поэтому не зависят от масштаба, поворота и размеров листа. Перед записью они переводятся в команды рисования PDF.

Вшитое нельзя стереть в другой программе: это обычное содержимое страницы. Пока файл не сохранён, любую пометку можно отменить.
Закраска скрывает вид страницы, но не удаляет текст и картинки под ней — для секретных данных этого недостаточно.
"""
from __future__ import annotations

import os
import re

from .engine import DocError

TOOL_HIGHLIGHT = "highlight"   # подсветка выделенного текста (по словам)
TOOL_MARKER = "marker"         # широкий полупрозрачный мазок от руки
TOOL_PEN = "pen"               # тонкая линия от руки
TOOL_COVER = "cover"           # закраска прямоугольника сплошным цветом
TOOLS = (TOOL_HIGHLIGHT, TOOL_MARKER, TOOL_PEN, TOOL_COVER)

_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")


def _pikepdf():
    try:
        import pikepdf
    except ImportError as e:  # pragma: no cover - зависит от сборки
        raise DocError("В этой сборке нет библиотеки pikepdf, правка PDF недоступна.") from e
    return pikepdf


def parse_color(value: str, default=(1.0, 0.92, 0.0)) -> tuple[float, float, float]:
    if not isinstance(value, str) or not _HEX.match(value):
        return default
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _num(x: float) -> str:
    s = f"{float(x):.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def clean_op(raw: dict) -> dict | None:
    """Проверяет и приводит к единому виду пометку, пришедшую от страницы. None — пометка непригодна."""
    if not isinstance(raw, dict):
        return None
    tool = raw.get("tool")
    if tool not in TOOLS:
        return None
    color = raw.get("color") if isinstance(raw.get("color"), str) and _HEX.match(raw.get("color")) else "#ffeb3b"
    color = "#" + color.lstrip("#").lower()

    def clamp(v):
        return max(0.0, min(1.0, float(v)))

    try:
        if tool == TOOL_HIGHLIGHT:
            rects = []
            for r in raw.get("rects", [])[:5000]:
                x0, y0, x1, y1 = (clamp(v) for v in r[:4])
                if x1 > x0 and y1 > y0:
                    rects.append([x0, y0, x1, y1])
            if not rects:
                return None
            return {"tool": tool, "color": color, "rects": rects}
        if tool == TOOL_COVER:
            x0, y0, x1, y1 = (clamp(v) for v in raw["rect"][:4])
            x0, x1 = sorted((x0, x1))
            y0, y1 = sorted((y0, y1))
            if x1 - x0 < 0.001 or y1 - y0 < 0.001:
                return None
            return {"tool": tool, "color": color, "rect": [x0, y0, x1, y1]}
        points = [(clamp(p[0]), clamp(p[1])) for p in raw.get("points", [])[:20000]]
        if not points:
            return None
        width = max(0.0005, min(0.2, float(raw.get("width", 0.004))))  # в долях ширины страницы
        return {"tool": tool, "color": color, "width": width, "points": points}
    except (KeyError, TypeError, ValueError, IndexError):
        return None


# ---------------------------------------------------------------------- геометрия страницы


class PageGeometry:
    """Видимая область страницы: куда на листе попадает точка (x, y) видимой страницы (в пунктах, от левого верхнего угла)."""

    def __init__(self, page):
        box = page.get("/CropBox", None)
        if box is None:
            box = page.get("/MediaBox", None)
        if box is None:
            box = [0, 0, 612, 792]
        vals = [float(v) for v in box]
        self.llx, self.lly = min(vals[0], vals[2]), min(vals[1], vals[3])
        self.urx, self.ury = max(vals[0], vals[2]), max(vals[1], vals[3])
        rot = page.get("/Rotate", None)
        try:
            self.rotate = int(rot) % 360 if rot is not None else 0
        except (TypeError, ValueError):
            self.rotate = 0
        if self.rotate not in (0, 90, 180, 270):
            self.rotate = 0
        w, h = self.urx - self.llx, self.ury - self.lly
        self.width, self.height = (h, w) if self.rotate in (90, 270) else (w, h)

    def matrix(self) -> tuple[float, float, float, float, float, float]:
        """Матрица (a b c d e f): видимая система «вниз и вправо, в пунктах» -> пространство страницы PDF."""
        if self.rotate == 90:
            return 0, 1, 1, 0, self.llx, self.lly
        if self.rotate == 180:
            return -1, 0, 0, 1, self.urx, self.lly
        if self.rotate == 270:
            return 0, -1, -1, 0, self.urx, self.ury
        return 1, 0, 0, -1, self.llx, self.ury


# ---------------------------------------------------------------------- запись пометок


def _ops_to_stream(ops: list[dict], geo: PageGeometry, gs_names: dict) -> bytes:
    W, H = geo.width, geo.height
    out = ["q", " ".join(_num(v) for v in geo.matrix()) + " cm"]
    for op in ops:
        r, g, b = parse_color(op["color"])
        color = f"{_num(r)} {_num(g)} {_num(b)}"
        tool = op["tool"]
        if tool == TOOL_HIGHLIGHT:
            out.append(f"q /{gs_names['mul']} gs {color} rg")
            for x0, y0, x1, y1 in op["rects"]:
                out.append(f"{_num(x0 * W)} {_num(y0 * H)} {_num((x1 - x0) * W)} {_num((y1 - y0) * H)} re")
            out.append("f Q")
        elif tool == TOOL_COVER:
            x0, y0, x1, y1 = op["rect"]
            out.append(f"q {color} rg {_num(x0 * W)} {_num(y0 * H)} {_num((x1 - x0) * W)} {_num((y1 - y0) * H)} re f Q")
        else:  # от руки: маркер и ручка
            pts = [(x * W, y * H) for x, y in op["points"]]
            lw = op["width"] * W
            gs = gs_names["mul"] if tool == TOOL_MARKER else None
            head = f"q /{gs} gs " if gs else "q "
            if len(pts) == 1:  # точка: кружок нужной толщины
                x, y = pts[0]
                rad = lw / 2
                k = 0.5523 * rad
                out.append(
                    f"{head}{color} rg {_num(x + rad)} {_num(y)} m "
                    f"{_num(x + rad)} {_num(y + k)} {_num(x + k)} {_num(y + rad)} {_num(x)} {_num(y + rad)} c "
                    f"{_num(x - k)} {_num(y + rad)} {_num(x - rad)} {_num(y + k)} {_num(x - rad)} {_num(y)} c "
                    f"{_num(x - rad)} {_num(y - k)} {_num(x - k)} {_num(y - rad)} {_num(x)} {_num(y - rad)} c "
                    f"{_num(x + k)} {_num(y - rad)} {_num(x + rad)} {_num(y - k)} {_num(x + rad)} {_num(y)} c f Q"
                )
                continue
            cmds = [f"{_num(pts[0][0])} {_num(pts[0][1])} m"] + [f"{_num(x)} {_num(y)} l" for x, y in pts[1:]]
            out.append(f"{head}{color} RG {_num(lw)} w 1 J 1 j " + " ".join(cmds) + " S Q")
    out.append("Q")
    return ("\n".join(out) + "\n").encode("ascii")


def _own_resources(pikepdf, page):
    """Ресурсы страницы, которые можно менять. Унаследованные от родителя копируются на страницу, чтобы не задеть остальные."""
    res = page.get("/Resources", None)
    if res is not None:
        return res
    node = page.get("/Parent", None)
    inherited = None
    for _ in range(64):  # защита от цикла в повреждённом файле
        if node is None:
            break
        inherited = node.get("/Resources", None)
        if inherited is not None:
            break
        node = node.get("/Parent", None)
    fresh = pikepdf.Dictionary()
    if inherited is not None:
        for key in inherited.keys():
            fresh[key] = inherited[key]
        ext = inherited.get("/ExtGState", None)
        if ext is not None:  # словарь графических состояний тоже копируем: он будет изменён
            copy = pikepdf.Dictionary()
            for key in ext.keys():
                copy[key] = ext[key]
            fresh["/ExtGState"] = copy
    page["/Resources"] = fresh
    return fresh


def _wrap_contents(pdf, page) -> list:
    pikepdf = _pikepdf()
    existing = page.get("/Contents", None)
    if existing is None:
        return []
    if isinstance(existing, pikepdf.Array):
        return [existing[i] for i in range(len(existing))]
    return [existing]


def apply_ops(pdf, ops_by_page: dict[int, list[dict]]) -> None:
    """Вшивает пометки в открытый pikepdf-документ. Ключ — номер страницы с нуля."""
    pikepdf = _pikepdf()
    for index, ops in ops_by_page.items():
        if not ops or index < 0 or index >= len(pdf.pages):
            continue
        page = pdf.pages[index].obj
        geo = PageGeometry(page)
        if geo.width <= 0 or geo.height <= 0:
            continue
        # свои «графические состояния»: умножение цвета на страницу (маркер не закрывает текст)
        resources = _own_resources(pikepdf, page)
        ext = resources.get("/ExtGState", None)
        if ext is None:
            ext = pikepdf.Dictionary()
            resources["/ExtGState"] = ext
        name = "DFmul"
        n = 0
        while f"/{name}" in ext:
            n += 1
            name = f"DFmul{n}"
        marker_alpha = 0.45
        ext[f"/{name}"] = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, BM=pikepdf.Name.Multiply, ca=1.0, CA=1.0)
        name_marker = name + "m"
        ext[f"/{name_marker}"] = pikepdf.Dictionary(Type=pikepdf.Name.ExtGState, BM=pikepdf.Name.Multiply,
                                                    ca=marker_alpha, CA=marker_alpha)
        highlight = [o for o in ops if o["tool"] == TOOL_HIGHLIGHT]
        others = [o for o in ops if o["tool"] != TOOL_HIGHLIGHT]
        parts = []
        if highlight:
            parts.append(_ops_to_stream(highlight, geo, {"mul": name}))
        if others:
            parts.append(_ops_to_stream(others, geo, {"mul": name_marker}))
        old = _wrap_contents(pdf, page)
        streams = [pdf.make_stream(b"q\n")] + old + [pdf.make_stream(b"\nQ\n")] + [pdf.make_stream(p) for p in parts]
        page["/Contents"] = pikepdf.Array(streams)


def open_pdf(path: str):
    pikepdf = _pikepdf()
    try:
        return pikepdf.open(path)
    except pikepdf.PasswordError as e:
        raise DocError("PDF защищён паролем — такие файлы пока не поддерживаются.") from e
    except (pikepdf.PdfError, OSError) as e:
        raise DocError(f"Не удалось прочитать PDF для правки: {e}") from e


def _save(pdf, target: str) -> None:
    tmp = target + ".docforge-tmp"
    try:
        pdf.save(tmp)
        os.replace(tmp, target)
    except Exception as e:  # noqa: BLE001
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise DocError(f"Не удалось записать PDF: {e}") from e


def write_with_ops(src: str, dest: str, ops_by_page: dict[int, list[dict]]) -> None:
    """Копия [src] в [dest] с вшитыми пометками."""
    pdf = open_pdf(src)
    try:
        apply_ops(pdf, ops_by_page)
        _save(pdf, dest)
    except DocError:
        raise
    except Exception as e:  # noqa: BLE001
        raise DocError(f"Не удалось применить пометки: {e}") from e
    finally:
        pdf.close()


def write_without_pages(src: str, dest: str, remove: list[int]) -> int:
    """Копия [src] в [dest] без страниц [remove] (номера с нуля). Возвращает число оставшихся страниц."""
    pdf = open_pdf(src)
    try:
        total = len(pdf.pages)
        drop = sorted({i for i in remove if 0 <= i < total}, reverse=True)
        if not drop:
            raise DocError("Не выбрано ни одной страницы.")
        if len(drop) >= total:
            raise DocError("Нельзя удалить все страницы документа.")
        for i in drop:
            del pdf.pages[i]
        _save(pdf, dest)
        return total - len(drop)
    except DocError:
        raise
    except Exception as e:  # noqa: BLE001
        raise DocError(f"Не удалось удалить страницы: {e}") from e
    finally:
        pdf.close()


def remap_after_delete(ops_by_page: dict[int, list[dict]], removed: list[int]) -> dict[int, list[dict]]:
    """Пометки удалённых страниц пропадают, у остальных меняется номер страницы."""
    gone = set(removed)
    out: dict[int, list[dict]] = {}
    for index, ops in ops_by_page.items():
        if index in gone:
            continue
        shift = sum(1 for r in gone if r < index)
        out[index - shift] = ops
    return out
