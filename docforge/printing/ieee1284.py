"""Разбор строки IEEE 1284 Device ID: «MFG:Hewlett-Packard;MDL:HP LaserJet 1018;CMD:ACL,PJL;…»."""
from __future__ import annotations


class Ieee1284:
    def __init__(self, fields: dict[str, str] | None = None):
        self.fields = fields or {}

    @classmethod
    def parse_string(cls, text: str | None) -> "Ieee1284":
        fields: dict[str, str] = {}
        for part in (text or "").split(";"):
            key, sep, value = part.partition(":")
            key = key.strip().upper()
            if sep and key and key not in fields:
                fields[key] = value.strip().replace("\0", "")
        return cls(fields)

    @classmethod
    def parse(cls, raw: bytes) -> "Ieee1284":
        """Сырой ответ принтера: первые два байта — длина (big-endian, у части принтеров little-endian)."""
        if not raw:
            return cls()
        start, end = 0, len(raw)
        if len(raw) >= 2:
            first, second = raw[0], raw[1]
            looks_like_text = 0x41 <= first < 0x7F and 0x20 <= second < 0x7F
            if not looks_like_text:
                big = (first << 8) | second
                little = (second << 8) | first
                if 2 <= big <= len(raw):
                    declared = big
                elif 2 <= little <= len(raw):
                    declared = little
                else:
                    declared = len(raw)
                start, end = 2, min(len(raw), declared)
        return cls.parse_string(raw[start:end].decode("latin-1"))

    def _first(self, *keys: str) -> str:
        for k in keys:
            v = self.fields.get(k)
            if v:
                return v
        return ""

    def is_empty(self) -> bool:
        return not self.fields

    @property
    def manufacturer(self) -> str:
        return self._first("MFG", "MANUFACTURER")

    @property
    def model(self) -> str:
        return self._first("MDL", "MODEL")

    @property
    def description(self) -> str:
        return self._first("DES", "DESCRIPTION")

    @property
    def commands(self) -> list[str]:
        raw = self._first("CMD", "COMMAND SET", "COMMANDSET")
        out: list[str] = []
        for s in raw.split(","):
            t = s.strip().upper()
            if t and t not in out:
                out.append(t)
        return out
