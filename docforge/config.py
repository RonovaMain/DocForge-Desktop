"""Настройки и список недавних файлов — один JSON в каталоге настроек пользователя."""
from __future__ import annotations

import json
from pathlib import Path

from .paths import config_dir

DEFAULTS = {
    "theme": "system",       # system | light | dark — оформление окна
    "night_documents": False,  # тёмная тема документов
    "text_scale": 100,         # размер текста документов, %
    "pdf_zoom_mode": "width",  # width | page | custom — как показывать страницы PDF
    "pdf_zoom": 100,           # масштаб PDF в %, если режим custom
    "print_mode": "system",    # system | builtin
    "recent": [],
    "print": {},               # последние параметры печати
}
MAX_RECENT = 12


class Settings:
    def __init__(self, path: Path | None = None):
        self._path = path or (config_dir() / "settings.json")
        self.data = dict(DEFAULTS)
        try:
            loaded = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                self.data.update(loaded)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._path)
        except OSError:
            pass

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value) -> None:
        self.data[key] = value
        self.save()

    def add_recent(self, path: str) -> None:
        items = [p for p in self.data.get("recent", []) if p != path]
        items.insert(0, path)
        self.data["recent"] = items[:MAX_RECENT]
        self.save()

    def recent(self) -> list[str]:
        from os.path import exists
        return [p for p in self.data.get("recent", []) if exists(p)]

    def clear_recent(self) -> None:
        self.data["recent"] = []
        self.save()
