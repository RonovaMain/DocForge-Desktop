"""Отправка готовых данных в принтер «как есть» (RAW), минуя драйвер печати.

Windows: через диспетчер очереди печати (RAW-задание в очередь принтера). Linux: через CUPS (`lp -o raw`).
Очередь может быть с любым драйвером — например «Generic / Text Only»: наши данные драйвер не трогает."""
from __future__ import annotations

import os
import subprocess

from .devices import PrinterInfo


class SendError(Exception):
    pass


class RawSender:
    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def abort(self) -> None:
        pass


class WindowsSpooler(RawSender):
    CHUNK = 64 * 1024

    def __init__(self, printer_name: str, doc_name: str = "DocForge"):
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        w = ctypes.WinDLL("winspool.drv", use_last_error=True)
        self._w = w

        class DOC_INFO_1(ctypes.Structure):
            _fields_ = [("pDocName", wintypes.LPWSTR), ("pOutputFile", wintypes.LPWSTR), ("pDatatype", wintypes.LPWSTR)]

        w.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
        w.OpenPrinterW.restype = wintypes.BOOL
        w.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DOC_INFO_1)]
        w.StartDocPrinterW.restype = wintypes.DWORD
        w.StartPagePrinter.argtypes = [wintypes.HANDLE]
        w.StartPagePrinter.restype = wintypes.BOOL
        w.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        w.WritePrinter.restype = wintypes.BOOL
        for fn in ("EndPagePrinter", "EndDocPrinter", "ClosePrinter", "AbortPrinter"):
            getattr(w, fn).argtypes = [wintypes.HANDLE]
            getattr(w, fn).restype = wintypes.BOOL

        self._handle = wintypes.HANDLE()
        if not w.OpenPrinterW(printer_name, ctypes.byref(self._handle), None):
            raise SendError(f"Не удалось открыть принтер «{printer_name}»: {ctypes.WinError(ctypes.get_last_error())}")
        info = DOC_INFO_1(doc_name, None, "RAW")
        self._info = info  # держим ссылку на время задания
        if not w.StartDocPrinterW(self._handle, 1, ctypes.byref(info)):
            err = ctypes.get_last_error()
            w.ClosePrinter(self._handle)
            hint = " У очереди принтера драйвер не принимает RAW — выберите очередь с драйвером «Generic / Text Only»." if err == 1804 else ""
            raise SendError(f"Принтер не принял задание: {ctypes.WinError(err)}.{hint}")
        w.StartPagePrinter(self._handle)
        self._open = True

    def write(self, data: bytes) -> None:
        from ctypes import wintypes

        ct, w = self._ct, self._w
        view = memoryview(data)
        for i in range(0, len(data), self.CHUNK):
            chunk = bytes(view[i:i + self.CHUNK])
            written = wintypes.DWORD(0)
            buf = ct.create_string_buffer(chunk, len(chunk))
            if not w.WritePrinter(self._handle, buf, len(chunk), ct.byref(written)) or written.value != len(chunk):
                raise SendError(f"Ошибка записи в принтер: {ct.WinError(ct.get_last_error())}")

    def close(self) -> None:
        if self._open:
            self._open = False
            self._w.EndPagePrinter(self._handle)
            self._w.EndDocPrinter(self._handle)
            self._w.ClosePrinter(self._handle)

    def abort(self) -> None:
        if self._open:
            self._open = False
            self._w.AbortPrinter(self._handle)
            self._w.ClosePrinter(self._handle)


class CupsRaw(RawSender):
    def __init__(self, queue: str, title: str = "DocForge"):
        try:
            self._proc = subprocess.Popen(
                ["lp", "-d", queue, "-o", "raw", "-t", title, "-"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except OSError as e:
            raise SendError(f"Не удалось запустить lp (CUPS): {e}") from e

    def write(self, data: bytes) -> None:
        try:
            self._proc.stdin.write(data)
        except (BrokenPipeError, OSError) as e:
            raise SendError(f"CUPS не принимает данные: {self._stderr() or e}") from e

    def _stderr(self) -> str:
        try:
            return self._proc.stderr.read().decode("utf-8", "replace").strip()
        except Exception:
            return ""

    def close(self) -> None:
        try:
            self._proc.stdin.close()
        except OSError:
            pass
        code = self._proc.wait()
        if code != 0:
            raise SendError(f"lp завершился с кодом {code}: {self._stderr()}")

    def abort(self) -> None:
        self._proc.kill()


def make_sender(printer: PrinterInfo, title: str = "DocForge") -> RawSender:
    if os.name == "nt":
        return WindowsSpooler(printer.name, title)
    return CupsRaw(printer.name, title)
