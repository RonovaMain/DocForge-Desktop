"""Запуск внешнего фильтра печати (foo2zjs и др.): страницы PBM — в stdin, вывод фильтра — прямо в принтер."""
from __future__ import annotations

import os
import subprocess
import threading
from typing import Callable


class FilterError(Exception):
    pass


def pbm_header(width: int, height: int) -> bytes:
    return f"P4\n{width} {height}\n".encode("ascii")


class FilterProcess:
    def __init__(self, command: list[str], sink: Callable[[bytes], None]):
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        try:
            self._proc = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags
            )
        except OSError as e:
            raise FilterError(f"Не удалось запустить драйвер {command[0]}: {e}") from e
        self._sink = sink
        self._sink_error: BaseException | None = None
        self._err = bytearray()
        self._pump = threading.Thread(target=self._pump_stdout, daemon=True)
        self._errs = threading.Thread(target=self._read_stderr, daemon=True)
        self._pump.start()
        self._errs.start()

    @property
    def stdin(self):
        return self._proc.stdin

    def _pump_stdout(self) -> None:
        try:
            while True:
                data = self._proc.stdout.read(16384)
                if not data:
                    break
                self._sink(data)
        except BaseException as e:  # ошибка записи в принтер: останавливаем фильтр и сообщаем наверх
            self._sink_error = e
            self._proc.kill()

    def _read_stderr(self) -> None:
        while True:
            data = self._proc.stderr.read(1024)
            if not data:
                break
            if len(self._err) < 4096:
                self._err += data[: 4096 - len(self._err)]

    def finish(self) -> None:
        """Закрывает ввод, ждёт конца вывода и проверяет код возврата."""
        try:
            self._proc.stdin.close()
        except OSError:
            pass  # фильтр мог завершиться раньше — причина будет в коде возврата
        self._pump.join()
        code = self._proc.wait()
        self._errs.join(0.5)
        for pipe in (self._proc.stdout, self._proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        if self._sink_error is not None:
            raise self._sink_error
        if code != 0:
            tail = bytes(self._err).decode("utf-8", "replace").strip()
            raise FilterError(f"Фильтр печати завершился с кодом {code}" + (f": {tail}" if tail else ""))

    def abort(self) -> None:
        try:
            self._proc.kill()
            self._proc.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for pipe in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
