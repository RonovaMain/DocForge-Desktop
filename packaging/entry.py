"""Точка входа для PyInstaller (внутри пакета относительные импорты, поэтому запуск через docforge.*)."""
import sys

if "--selftest" in sys.argv:  # проверка сборки без окна и без Qt: DocForge --selftest результат.txt
    from docforge.selftest import run

    i = sys.argv.index("--selftest")
    raise SystemExit(run(sys.argv[i + 1] if i + 1 < len(sys.argv) else None))

from docforge.app import main

raise SystemExit(main())
