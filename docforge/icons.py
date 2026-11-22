"""Значки интерфейса: векторные (SVG прямо в коде), окрашиваются под текущую тему. Никаких системных картинок Windows."""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_PATHS = {
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "save": '<path d="M5 3h11l4 4v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8V3"/><path d="M7 21v-7h10v7"/>',
    "print": '<path d="M6 9V3h12v6"/><rect x="3" y="9" width="18" height="8" rx="2"/><path d="M7 14h10v7H7z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    "edit": '<path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/><path d="M10 11v6M14 11v6"/>',
    "undo": '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 0 1 0 12h-3"/>',
    "redo": '<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 0 0 0 12h3"/>',
    "cursor": '<path d="M5 3l14 8-6 2-2 6z"/>',
    "highlight": '<path d="M14 4l6 6-8 8H6v-6z"/><path d="M4 21h16"/>',
    "marker": '<path d="M18 3l3 3-9 9-3-3z"/><path d="M9 12c-2.5 0-4 1.6-4 3.5 0 1.3-.8 2.6-2 3.5 4.5 1.2 9-.2 9-4"/>',
    "pen": '<path d="M12 19l7-7-4-4-7 7z"/><path d="M8 15l-4 5 5-4"/><path d="M15 8l1.5-1.5a2 2 0 0 1 3 3L18 11"/>',
    "cover": '<rect x="4" y="6" width="16" height="12" rx="2" fill="currentColor"/>',
    "eraser": '<path d="M16 4l5 5-9 9H7l-4-4a2 2 0 0 1 0-3z"/><path d="M9 11l4 4"/>',
    "zoom-in": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5M8 11h6M11 8v6"/>',
    "zoom-out": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5M8 11h6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "fit-width": '<path d="M3 5v14M21 5v14"/><path d="M7 12h10M7 12l3-3M7 12l3 3M17 12l-3-3M17 12l-3 3"/>',
    "fit-page": '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6"/>',
    "up": '<path d="M6 15l6-6 6 6"/>',
    "down": '<path d="M6 9l6 6 6-6"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "pages": '<rect x="4" y="3" width="12" height="16" rx="2"/><path d="M8 21h10a2 2 0 0 0 2-2V8"/>',
    "palette": '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="11" r="1" fill="currentColor"/><circle cx="12" cy="7.5" r="1" fill="currentColor"/><circle cx="16" cy="11" r="1" fill="currentColor"/>',
}

_cache: dict[tuple, QPixmap] = {}


def _pixmap(name: str, color: str, size: int) -> QPixmap:
    key = (name, color, size)
    pm = _cache.get(key)
    if pm is not None:
        return pm
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        + _PATHS[name]
        + "</svg>"
    ).replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    _cache[key] = pm
    return pm


def make_icon(name: str, normal: str, disabled: str, checked: str | None = None) -> QIcon:
    """Значок трёх состояний: обычный, недоступный и (для переключателей) включённый."""
    icon = QIcon()
    for size in (20, 24, 32, 48, 64):
        icon.addPixmap(_pixmap(name, normal, size), QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap(_pixmap(name, normal, size), QIcon.Mode.Active, QIcon.State.Off)
        icon.addPixmap(_pixmap(name, disabled, size), QIcon.Mode.Disabled, QIcon.State.Off)
        if checked:
            icon.addPixmap(_pixmap(name, checked, size), QIcon.Mode.Normal, QIcon.State.On)
            icon.addPixmap(_pixmap(name, checked, size), QIcon.Mode.Active, QIcon.State.On)
            icon.addPixmap(_pixmap(name, disabled, size), QIcon.Mode.Disabled, QIcon.State.On)
    return icon


def names() -> list[str]:
    return list(_PATHS)
