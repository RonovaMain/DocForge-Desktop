# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller packaging/docforge.spec --noconfirm   (перед этим: python tools/build_engine.py)
import os
from pathlib import Path
import PyQt6

root = Path(SPECPATH).parent
build = root / "build"
datas = [(str(root / "docforge" / "resources"), "docforge/resources")]
binaries = []

# Все модули Qt, которые импортирует программа. Явный список: PyInstaller подхватит их DLL, плагины и
# ресурсы WebEngine своими хуками, а если модуля нет в установленном PyQt6 — сборка остановится здесь,
# а не выдаст exe, который падает при запуске с «No module named 'PyQt6.QtPdf'».
QT_MODULES = [
    "QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtPrintSupport",
    "QtPdf", "QtWebChannel", "QtWebEngineCore", "QtWebEngineWidgets",
]
qt_dir = Path(PyQt6.__file__).parent
missing = [m for m in QT_MODULES
           if not any(f.suffix in (".pyd", ".so") for f in qt_dir.glob(m + ".*"))]
if missing:
    raise SystemExit(
        "В установленном PyQt6 нет модулей: " + ", ".join(missing)
        + f"\nПапка: {qt_dir}\nQtPdf ставится отдельным пакетом PyQt6-Pdf; переустановите: pip install --force-reinstall -r requirements.txt"
    )
hiddenimports = ["PyQt6." + m for m in QT_MODULES]

engine = build / "engine"
if not (engine / "engine.jar").is_file():
    raise SystemExit("Нет build/engine/engine.jar — сначала запустите python tools/build_engine.py")
datas.append((str(engine / "engine.jar"), "engine"))
if (engine / "runtime").is_dir():
    datas.append((str(engine / "runtime"), "engine/runtime"))

filters = build / "filters"
if filters.is_dir() and any(filters.iterdir()):
    datas.append((str(filters), "filters"))

icon = str(root / "docforge" / "resources" / ("icon.ico" if os.name == "nt" else "icon.png"))

a = Analysis(
    [str(root / "packaging" / "entry.py")],
    pathex=[str(root)],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "PIL"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="DocForge",
    console=False,
    icon=icon,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="DocForge", upx=False)
