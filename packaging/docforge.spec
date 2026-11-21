# -*- mode: python ; coding: utf-8 -*-
# Сборка: pyinstaller packaging/docforge.spec --noconfirm   (перед этим: python tools/build_engine.py)
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
build = root / "build"
datas = [(str(root / "docforge" / "resources"), "docforge/resources")]
binaries = []
hiddenimports = []

for pkg in (
    "PyQt6.QtPdf",
    "PyQt6.QtWebEngineCore",
    "PyQt6.QtWebEngineWidgets",
    "PyQt6.QtWebChannel",
    "PyQt6.QtPrintSupport",
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

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
