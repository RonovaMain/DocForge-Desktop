"""Потоковый вывод страниц-растров в PostScript уровня 2 (оттенки серого, 8 бит, ASCII85)."""
from __future__ import annotations

import base64
import re
from typing import Callable

import numpy as np


class PostScriptWriter:
    def __init__(self, write: Callable[[bytes], None], title: str = "DocForge"):
        self._write = write
        self._page = 0
        safe = re.sub(r"[^A-Za-z0-9 ._-]", "_", title)
        write(
            f"%!PS-Adobe-3.0\n%%Creator: DocForge\n%%Title: {safe}\n%%LanguageLevel: 2\n%%Pages: (atend)\n%%EndComments\n".encode("latin-1")
        )

    def page(self, gray: np.ndarray, width_pt: int, height_pt: int) -> None:
        """Растр [gray] (высота × ширина, 255 — белый) на лист размером [width_pt]×[height_pt] пунктов."""
        h, w = gray.shape
        self._page += 1
        self._write(
            (
                f"%%Page: {self._page} {self._page}\n"
                f"<< /PageSize [{width_pt} {height_pt}] >> setpagedevice\n"
                "gsave\n"
                f"{width_pt} {height_pt} scale\n"
                "/DeviceGray setcolorspace\n"
                "/A currentfile /ASCII85Decode filter def\n"
                f"<< /ImageType 1 /Width {w} /Height {h} /BitsPerComponent 8 /Decode [0 1]\n"
                f"/ImageMatrix [{w} 0 0 -{h} 0 {h}] /DataSource A >> image\n"
            ).encode("latin-1")
        )
        data = np.ascontiguousarray(gray).tobytes()
        step = 4 * 16384  # кратно 4 — группы ASCII85 не рвутся между порциями
        for i in range(0, len(data), step):
            chunk = data[i:i + step]
            self._write(base64.a85encode(chunk, wrapcol=72) + b"\n")
        self._write(b"~>\nA status { A flushfile } if\ngrestore\nshowpage\n")

    def finish(self) -> None:
        self._write(f"%%Trailer\n%%Pages: {self._page}\n%%EOF\n".encode("latin-1"))
