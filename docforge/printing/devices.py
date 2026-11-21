"""Список принтеров системы и подсказки о модели (по ним работает автовыбор драйвера)."""
from __future__ import annotations

import os
import re
import subprocess
import urllib.parse
from dataclasses import dataclass


@dataclass
class PrinterInfo:
    name: str
    driver: str = ""
    port: str = ""
    uri: str = ""
    is_default: bool = False

    @property
    def model(self) -> str:
        """Лучшее, что известно о модели: драйвер в Windows, модель из адреса устройства в CUPS, иначе имя очереди."""
        if self.uri.startswith("usb://"):
            path = urllib.parse.unquote(urllib.parse.urlparse(self.uri).path.lstrip("/"))
            maker = urllib.parse.unquote(urllib.parse.urlparse(self.uri).netloc)
            if path:
                return f"{maker} {path}".strip()
        return self.driver or self.name

    @property
    def manufacturer(self) -> str:
        return self.model  # модель содержит производителя; правила каталога ищут его внутри строки


def list_printers() -> list[PrinterInfo]:
    try:
        return _list_windows() if os.name == "nt" else _list_cups()
    except Exception:
        return []


def _list_cups() -> list[PrinterInfo]:
    printers: dict[str, PrinterInfo] = {}
    out = subprocess.run(["lpstat", "-v"], capture_output=True, text=True, timeout=10).stdout
    for line in out.splitlines():
        m = re.match(r"device for (.+?): (.+)$", line.strip())
        if m:
            printers[m.group(1)] = PrinterInfo(name=m.group(1), uri=m.group(2).strip())
    default = ""
    out = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, timeout=10).stdout
    m = re.search(r":\s*(\S+)\s*$", out.strip())
    if m:
        default = m.group(1)
    if default in printers:
        printers[default].is_default = True
    return list(printers.values())


def _list_windows() -> list[PrinterInfo]:
    import ctypes
    from ctypes import wintypes

    class PRINTER_INFO_2W(ctypes.Structure):
        _fields_ = [
            ("pServerName", wintypes.LPWSTR), ("pPrinterName", wintypes.LPWSTR), ("pShareName", wintypes.LPWSTR),
            ("pPortName", wintypes.LPWSTR), ("pDriverName", wintypes.LPWSTR), ("pComment", wintypes.LPWSTR),
            ("pLocation", wintypes.LPWSTR), ("pDevMode", ctypes.c_void_p), ("pSepFile", wintypes.LPWSTR),
            ("pPrintProcessor", wintypes.LPWSTR), ("pDatatype", wintypes.LPWSTR), ("pParameters", wintypes.LPWSTR),
            ("pSecurityDescriptor", ctypes.c_void_p), ("Attributes", wintypes.DWORD), ("Priority", wintypes.DWORD),
            ("DefaultPriority", wintypes.DWORD), ("StartTime", wintypes.DWORD), ("UntilTime", wintypes.DWORD),
            ("Status", wintypes.DWORD), ("cJobs", wintypes.DWORD), ("AveragePages", wintypes.DWORD),
        ]

    w = ctypes.WinDLL("winspool.drv", use_last_error=True)
    w.EnumPrintersW.argtypes = [wintypes.DWORD, wintypes.LPWSTR, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    w.EnumPrintersW.restype = wintypes.BOOL
    flags = 0x2 | 0x4  # PRINTER_ENUM_LOCAL | PRINTER_ENUM_CONNECTIONS
    needed, returned = wintypes.DWORD(0), wintypes.DWORD(0)
    w.EnumPrintersW(flags, None, 2, None, 0, ctypes.byref(needed), ctypes.byref(returned))
    if needed.value == 0:
        return []
    buf = ctypes.create_string_buffer(needed.value)
    if not w.EnumPrintersW(flags, None, 2, buf, needed.value, ctypes.byref(needed), ctypes.byref(returned)):
        return []
    items = ctypes.cast(buf, ctypes.POINTER(PRINTER_INFO_2W))

    default = ctypes.create_unicode_buffer(260)
    size = wintypes.DWORD(260)
    w.GetDefaultPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    w.GetDefaultPrinterW(default, ctypes.byref(size))

    result = []
    for i in range(returned.value):
        it = items[i]
        result.append(PrinterInfo(
            name=it.pPrinterName or "", driver=it.pDriverName or "", port=it.pPortName or "",
            is_default=(it.pPrinterName == default.value),
        ))
    return result
