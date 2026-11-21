#!/usr/bin/env python3
"""Собирает движок документов: engine/src (Java) -> build/engine/engine.jar и урезанную JRE build/engine/runtime.

Нужен JDK 17+ (javac и jlink). Подойдёт JDK из Android Studio (папка jbr) — укажите её в JAVA_HOME.
Без jlink собирается только engine.jar: для разработки хватит обычной Java из PATH."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "engine" / "src"
OUT = ROOT / "build" / "engine"
MAIN_CLASS = "dev.ronova.docforge.server.EngineServer"
MODULES = "java.base,java.xml"  # всё, что нужно движкам: java.util, java.io, javax.xml, org.w3c


def tool(name: str) -> str | None:
    exe = name + (".exe" if os.name == "nt" else "")
    home = os.environ.get("JAVA_HOME")
    if home and (Path(home) / "bin" / exe).exists():
        return str(Path(home) / "bin" / exe)
    return shutil.which(name)


def run(cmd: list[str]) -> None:
    print("  $", " ".join(cmd))
    subprocess.run(cmd, check=True)


def compile_sources(classes: Path) -> None:
    sources = sorted(str(p) for p in SRC.rglob("*.java"))
    argfile = OUT / "sources.txt"
    argfile.write_text("\n".join(s.replace("\\", "/") for s in sources), encoding="utf-8")
    javac = tool("javac")
    if javac:
        run([javac, "-encoding", "UTF-8", "--release", "17", "-nowarn", "-d", str(classes), f"@{argfile}"])
        return
    java = tool("java")
    if not java:
        sys.exit("Не найдена Java. Установите JDK 17+ и/или задайте JAVA_HOME.")
    # запасной путь: компилятор из модуля jdk.compiler (есть в JDK, но не в простой JRE)
    run([java, "-m", "jdk.compiler/com.sun.tools.javac.Main", "-encoding", "UTF-8", "-nowarn", "-d", str(classes), f"@{argfile}"])


def make_jar(classes: Path, jar: Path) -> None:
    with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("META-INF/MANIFEST.MF", f"Manifest-Version: 1.0\nMain-Class: {MAIN_CLASS}\n")
        for path in sorted(classes.rglob("*.class")):
            z.write(path, path.relative_to(classes).as_posix())


def make_runtime(runtime: Path) -> bool:
    jlink = tool("jlink")
    if not jlink:
        print("jlink не найден — собран только engine.jar (запуск на системной Java)")
        return False
    if runtime.exists():
        shutil.rmtree(runtime)
    base = [jlink, "--add-modules", MODULES, "--output", str(runtime), "--strip-debug", "--no-header-files", "--no-man-pages"]
    try:
        run(base + ["--compress=zip-6"])
    except subprocess.CalledProcessError:
        if runtime.exists():
            shutil.rmtree(runtime)
        run(base + ["--compress=2"])  # JDK 17
    return True


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    classes = OUT / "classes"
    classes.mkdir()
    print("Компиляция движка…")
    compile_sources(classes)
    make_jar(classes, OUT / "engine.jar")
    print("Урезанная JRE…")
    make_runtime(OUT / "runtime")
    print("Готово:", OUT)


if __name__ == "__main__":
    main()
