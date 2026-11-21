#!/usr/bin/env python3
"""Копирует движки документов из Android-репозитория DocForge в engine/src, чтобы обе версии работали одинаково.

    python tools/sync_engine.py путь/к/DocForge-main
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

PACKAGES = ["core", "html", "odf", "ooxml", "xml", "zip"]  # print/ и android/ — только для Android


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    android = Path(sys.argv[1]) / "app" / "src" / "main" / "java" / "dev" / "ronova" / "docforge"
    if not android.is_dir():
        sys.exit(f"Не найдена папка движков: {android}")
    target = Path(__file__).resolve().parent.parent / "engine" / "src" / "dev" / "ronova" / "docforge"
    for name in PACKAGES:
        dest = target / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(android / name, dest)
        print("обновлено:", name)
    print("Серверный класс engine/src/dev/ronova/docforge/server/EngineServer.java не затронут.")


if __name__ == "__main__":
    main()
