"""Чёрно-белый растр из оттенков серого: упорядоченное растрирование матрицей Байера (как в Android-версии)."""
from __future__ import annotations

import numpy as np

BAYER = np.array(
    [
        [0, 32, 8, 40, 2, 34, 10, 42],
        [48, 16, 56, 24, 50, 18, 58, 26],
        [12, 44, 4, 36, 14, 46, 6, 38],
        [60, 28, 52, 20, 62, 30, 54, 22],
        [3, 35, 11, 43, 1, 33, 9, 41],
        [51, 19, 59, 27, 49, 17, 57, 25],
        [15, 47, 7, 39, 13, 45, 5, 37],
        [63, 31, 55, 23, 61, 29, 53, 21],
    ],
    dtype=np.int32,
)


def to_bits(gray: np.ndarray, top: int = 0) -> np.ndarray:
    """Серый растр (высота × ширина, ширина кратна 8; 255 — белый) -> биты (1 = чёрный), упакованные по строкам."""
    h, w = gray.shape
    if w % 8:
        raise ValueError("ширина растра должна быть кратна 8")
    # чуть усиливаем контраст: светло-серый становится белым, тёмный — чёрным
    boosted = np.clip(((gray.astype(np.int32) - 24) * 255) // 207, 0, 255)
    rows = (np.arange(h) + top) & 7
    cols = np.arange(w) & 7
    threshold = BAYER[rows][:, cols] * 4 + 2
    return np.packbits(boosted < threshold, axis=1)
