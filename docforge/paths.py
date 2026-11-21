"""Где лежат ресурсы и движок документов — в исходниках и в собранной программе (PyInstaller)."""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """Корень данных: в собранной программе — каталог распаковки, в исходниках — корень репозитория."""
    if frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def resource(name: str) -> Path:
    return Path(__file__).resolve().parent / "resources" / name


def _ensure_executable(path: Path) -> None:
    """Упаковщики не всегда сохраняют бит исполнения: на Linux выставляем его сами."""
    if os.name != "nt" and path.is_file() and not os.access(path, os.X_OK):
        try:
            path.chmod(0o755)
        except OSError:
            pass


def engine_command() -> list[str]:
    """Команда запуска сервера движков. Движок — те же классы Java, что в Android-версии, со своей урезанной JRE."""
    env_dir = os.environ.get("DOCFORGE_ENGINE_DIR")
    candidates = [Path(env_dir)] if env_dir else []
    candidates += [base_dir() / "engine", base_dir() / "build" / "engine"]
    exe = "java.exe" if os.name == "nt" else "java"
    for d in candidates:
        jar = d / "engine.jar"
        java = d / "runtime" / "bin" / exe
        if jar.is_file() and java.is_file():
            _ensure_executable(java)
            return [str(java), "-Xshare:auto", "-XX:TieredStopAtLevel=1", "-Xss4m", "-cp", str(jar), "dev.ronova.docforge.server.EngineServer"]
        if jar.is_file():  # разработка: системная Java
            system_java = shutil.which("java")
            if system_java:
                return [system_java, "-XX:TieredStopAtLevel=1", "-Xss4m", "-cp", str(jar), "dev.ronova.docforge.server.EngineServer"]
        classes = d / "classes"
        if classes.is_dir() and shutil.which("java"):
            return [shutil.which("java"), "-cp", str(classes), "dev.ronova.docforge.server.EngineServer"]
    raise FileNotFoundError(
        "Не найден движок документов (engine.jar). Соберите его: python tools/build_engine.py"
    )


def config_dir() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    path = root / "DocForge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def filter_binary(name: str) -> Path | None:
    """Фильтры печати foo2* (foo2zjs и др.), собранные вместе с программой. None — в этой сборке их нет."""
    exe = f"{name}.exe" if os.name == "nt" else name
    for d in (base_dir() / "filters", base_dir() / "build" / "filters"):
        p = d / exe
        if p.is_file():
            _ensure_executable(p)
            return p
    return None
