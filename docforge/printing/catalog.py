"""Каталог способов печати и автовыбор по модели принтера и его языкам (CMD из IEEE 1284 Device ID).

Таблица моделей составлена по документации foo2zjs и openprinting.org. Ошибка в ней не опасна:
выбранный способ всегда можно сменить вручную."""
from __future__ import annotations

import re
from dataclasses import dataclass

PCL5, POSTSCRIPT, PDF, FILTER = "pcl5", "postscript", "pdf", "filter"
_ARGS = "-r{dpi}x{dpi} -g{w}x{h} -p{paper} -n{copies}"


@dataclass(frozen=True)
class DriverSpec:
    id: str
    title: str
    kind: str
    binary: str | None = None   # для FILTER: имя программы
    dpi: int = 0                # для FILTER и PostScript: разрешение растра
    args: str = ""              # для FILTER: шаблон аргументов {dpi} {w} {h} {paper} {copies}
    needs_firmware: bool = False
    note: str = ""

    def filter_args(self, width_px: int, height_px: int, paper_code: int, copies: int) -> list[str]:
        out = []
        for part in self.args.split():
            out.append(
                part.replace("{dpi}", str(self.dpi)).replace("{w}", str(width_px)).replace("{h}", str(height_px))
                .replace("{paper}", str(paper_code)).replace("{copies}", str(copies))
            )
        return out


ALL: list[DriverSpec] = [
    DriverSpec("pcl5", "PCL 5 (встроенный, чёрно-белый)", PCL5, dpi=300,
               note="Многие лазерные принтеры HP, Brother, Kyocera, Lexmark, OKI, Ricoh"),
    DriverSpec("ps", "PostScript (встроенный, оттенки серого)", POSTSCRIPT, dpi=200, note="Принтеры с PostScript 2/3"),
    DriverSpec("pdf", "PDF напрямую (документ целиком)", PDF, note="Принтеры, которые сами читают PDF"),
    DriverSpec("foo2zjs", "foo2zjs (ZjStream: HP LaserJet 1000/1005/1018/1020/1022, P1102/P1566/P1606, CP1025, P2035, Minolta)",
               FILTER, "foo2zjs", 600, _ARGS, True, "Нужен файл прошивки .dl, загружается в принтер после включения"),
    DriverSpec("foo2xqx", "foo2xqx (XQX: HP LaserJet P1005–P1008, P1505, P2014, M1005/M1120/M1212)",
               FILTER, "foo2xqx", 600, _ARGS, True, "Для части моделей нужен файл прошивки .dl"),
    DriverSpec("foo2qpdl", "foo2qpdl (QPDL/SPL: Samsung ML/CLP/SCX, Xerox Phaser 31xx)", FILTER, "foo2qpdl", 600, _ARGS),
    DriverSpec("foo2slx", "foo2slx (SLX: Xerox Phaser 6110)", FILTER, "foo2slx", 600, _ARGS),
    DriverSpec("foo2lava", "foo2lava (LAVA: Kyocera FS-1016MFP / FS-1118MFP)", FILTER, "foo2lava", 600, _ARGS),
]
BY_ID = {d.id: d for d in ALL}

_HP = r"(hp|hewlett)"
_RULES: list[tuple[str, re.Pattern, re.Pattern]] = [
    (d, re.compile(m, re.I), re.compile(n, re.I))
    for d, m, n in [
        # LaserJet 1010/1012/1015 — не foo2zjs: они понимают урезанный растровый PCL, его печатает встроенный PCL 5
        ("pcl5", _HP, r"laserjet\s+(1010|1012|1015)\b"),
        ("foo2zjs", _HP, r"laserjet\s+(1000|1005|1018|1020|1022)\b"),
        ("foo2zjs", _HP, r"\b(p1102w?|p1566|p1606|p2035|cp1025|m1319)"),
        ("foo2zjs", r"(minolta|konica|qms)", r"magicolor\s+(2200|2300)\s*dl"),
        ("foo2xqx", _HP, r"\b(p100[5-8]|p1505|p2014|m1005|m1120|m1212)"),
        ("foo2qpdl", r"(samsung|xerox)",
         r"\b(clp-?3\d\d|ml-?(1610|1640|1660|1665|1860|2010|2240|2250|2510|2570|2571|2850|2851)|scx-?4[23]\d\d|phaser\s+31(17|22|24|25|30|40|55|60))"),
        ("foo2slx", r"xerox", r"phaser\s+6110"),
        ("foo2lava", r"kyocera", r"fs-?1(016|118)\s*mfp"),
    ]
]


@dataclass(frozen=True)
class Match:
    spec: DriverSpec
    score: int
    reason: str


def select(manufacturer: str, model: str, commands: list[str] | None = None) -> list[Match]:
    """Подходящие способы печати по убыванию уверенности. Список не пуст: в конце всегда есть запасные варианты."""
    best: dict[str, Match] = {}

    def offer(driver_id: str, score: int, reason: str) -> None:
        old = best.get(driver_id)
        if old is None or old.score < score:
            best[driver_id] = Match(BY_ID[driver_id], score, reason)

    mfg, mdl = manufacturer or "", model or ""
    for driver_id, mfg_re, model_re in _RULES:
        if mfg_re.search(mfg) and model_re.search(mdl):
            offer(driver_id, 100, f"модель {(mfg + ' ' + mdl).strip()} есть в таблице")
    for cmd in commands or []:
        c = cmd.upper()
        if c in ("ZJS", "ZJSTREAM"):
            offer("foo2zjs", 90, f"принтер заявляет язык {c}")
        elif c == "XQX":
            offer("foo2xqx", 90, "принтер заявляет язык XQX")
        elif c.startswith("QPDL") or c in ("SPL", "SPLC"):
            offer("foo2qpdl", 60, f"принтер заявляет язык {c}")
        elif c == "PDF":
            offer("pdf", 75, "принтер заявляет чтение PDF")
        elif c.startswith("POSTSCRIPT") or c in ("PS", "PS2", "PS3"):
            offer("ps", 70, "принтер заявляет PostScript")
        elif c == "DW-PCL" or "FASTRASTER" in c:
            offer("pcl5", 65, f"принтер заявляет растровый PCL ({c}) — так устроены HP LaserJet 1010/1012/1015")
        elif c in ("PCL", "PCL3") or c.startswith("PCL5"):
            offer("pcl5", 60, "принтер заявляет PCL")
        elif c.startswith("PCL6") or c in ("PCLXL", "PCL XL"):
            offer("pcl5", 35, "заявлен только PCL 6 — большинство таких принтеров понимают и PCL 5")
    offer("pcl5", 10, "запасной вариант")
    offer("ps", 8, "запасной вариант")
    return sorted(best.values(), key=lambda m: -m.score)


def unsupported_hint(commands: list[str]) -> str | None:
    """Если принтер говорит только на языках без встроенных драйверов — название такого языка, иначе None."""
    host = None
    for cmd in commands:
        c = cmd.upper()
        if c.startswith(("PCL", "POSTSCRIPT", "PS")) or c in ("PDF", "ZJS", "XQX") or c.startswith("QPDL"):
            return None
        if c in ("GDI", "SPL", "SPLC", "ACL", "HBPL", "PPA") or c.startswith("CAPT"):
            host = c
    return host
