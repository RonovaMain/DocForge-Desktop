"""Кодировщик PCL 5 (растровая графика) — язык, который понимают многие лазерные принтеры."""
from __future__ import annotations

import numpy as np

ESC = b"\x1b"


def job_begin(pjl: bool) -> bytes:
    out = b""
    if pjl:
        out += ESC + b"%-12345X@PJL\r\n@PJL ENTER LANGUAGE=PCL\r\n"
    return out + ESC + b"E"


def job_end(pjl: bool) -> bytes:
    out = ESC + b"E"
    if pjl:
        out += ESC + b"%-12345X"
    return out


def page(bits: np.ndarray, paper_code: int, dpi: int) -> bytes:
    """Одна страница: [bits] — упакованные строки (высота × ширина/8)."""
    height, row_bytes = bits.shape
    width = row_bytes * 8
    head = (
        ESC + f"&l{paper_code}A".encode() + ESC + b"&l0O"
        + ESC + b"*p0X" + ESC + b"*p0Y"
        + ESC + f"*t{dpi}R".encode() + ESC + b"*r0F"
        + ESC + f"*r{width}S".encode() + ESC + b"*r1A"
    )
    row_header = ESC + f"*b{row_bytes}W".encode()
    body = b"".join(row_header + bits[y].tobytes() for y in range(height))
    return head + body + ESC + b"*rB" + b"\x0c"
