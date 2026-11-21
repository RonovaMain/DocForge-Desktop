"""Клиент сервера движков: DOCX/XLSX/PPTX/ODF -> HTML и правка текста. Один долгоживущий процесс Java."""
from __future__ import annotations

import os
import subprocess
import threading
import urllib.parse

from .paths import engine_command


class DocError(Exception):
    """Ошибка с понятным пользователю текстом (повреждённый файл, неподдерживаемый формат...)."""


def _enc(s: str) -> str:
    return urllib.parse.quote(s, safe="")


class EngineClient:
    def __init__(self, command: list[str] | None = None):
        self._command = command
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ процесс

    def _start(self) -> subprocess.Popen:
        command = self._command or engine_command()
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        return subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=flags
        )

    def close(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc is not None:
            try:
                proc.stdin.close()
                proc.wait(timeout=2)
            except Exception:
                proc.kill()

    # ------------------------------------------------------------------ запросы

    def call(self, *parts: str) -> bytes:
        line = ("\t".join([parts[0]] + [_enc(p) for p in parts[1:]]) + "\n").encode("ascii")
        with self._lock:
            for attempt in (0, 1):
                if self._proc is None or self._proc.poll() is not None:
                    self._proc = self._start()
                proc = self._proc
                try:
                    proc.stdin.write(line)
                    proc.stdin.flush()
                    header = proc.stdout.readline().decode("ascii", "replace").split()
                    if len(header) != 2:
                        raise BrokenPipeError("пустой ответ движка")
                    size = int(header[1])
                    body = proc.stdout.read(size) if size else b""
                    if len(body) != size:
                        raise BrokenPipeError("ответ движка оборван")
                except (BrokenPipeError, OSError, ValueError):
                    self._proc = None
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    if attempt == 1:
                        raise DocError("Движок документов не отвечает")
                    continue
                if header[0] == "OK":
                    return body
                raise DocError(body.decode("utf-8", "replace"))
        raise DocError("Движок документов не отвечает")

    def ping(self) -> bool:
        return self.call("ping") == b"pong"

    def detect(self, path: str, name: str) -> str:
        return self.call("detect", path, name).decode("utf-8")

    def render(self, path: str, name: str) -> str:
        return self.call("render", path, name).decode("utf-8")

    def text_at(self, path: str, name: str, element_id: str) -> str:
        return self.call("text", path, name, element_id).decode("utf-8")

    def display_at(self, path: str, name: str, element_id: str) -> str:
        return self.call("display", path, name, element_id).decode("utf-8")

    def edit_text(self, path: str, name: str, element_id: str, text: str, out_path: str) -> None:
        self.call("edit", path, name, element_id, text, out_path)

    def pdf_pages(self, sizes: list[tuple[int, int]]) -> str:
        return self.call("pdfpages", ",".join(f"{w}x{h}" for w, h in sizes)).decode("utf-8")
