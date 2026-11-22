"""Самопроверка собранной программы без окна: `DocForge --selftest результат.txt`.
Проверяет, что модули Qt загружаются, движок документов (своя JRE + engine.jar) запускается и читает и правит DOCX. Нужна для проверки сборок в CI."""
from __future__ import annotations

import io
import os
import re
import tempfile
import zipfile

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _minimal_docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml",
                   f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{_W}"><w:body>'
                   '<w:p><w:r><w:t>Проверка движка</w:t></w:r></w:p></w:body></w:document>')
    return buf.getvalue()


QT_MODULES = ("QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtPrintSupport",
              "QtPdf", "QtSvg", "QtWebChannel", "QtWebEngineCore", "QtWebEngineWidgets")


def check_qt() -> None:
    """Импорт всех модулей Qt без создания окна: ловит модули, не попавшие в сборку."""
    import importlib

    failed = []
    for name in QT_MODULES:
        try:
            importlib.import_module("PyQt6." + name)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{name}: {e}")
    if failed:
        raise RuntimeError("Qt не загрузился: " + "; ".join(failed))


def check_pdf_edit() -> None:
    """Правка PDF: создаём файл, вшиваем пометку, удаляем страницу. Ловит pikepdf, не попавший в сборку."""
    import pikepdf

    from . import pdfedit

    with tempfile.TemporaryDirectory() as tmp:
        src, marked, cut = (os.path.join(tmp, n) for n in ("a.pdf", "b.pdf", "c.pdf"))
        pdf = pikepdf.new()
        pdf.add_blank_page(page_size=(200, 300))
        pdf.add_blank_page(page_size=(200, 300))
        pdf.save(src)
        pdf.close()
        op = pdfedit.clean_op({"tool": "cover", "color": "#ff0000", "rect": [0.1, 0.1, 0.4, 0.3]})
        pdfedit.write_with_ops(src, marked, {0: [op]})
        if pdfedit.write_without_pages(marked, cut, [1]) != 1:
            raise RuntimeError("удаление страницы PDF не сработало")


def run(result_path: str | None) -> int:
    from .engine import EngineClient
    from .paths import engine_command

    message, code = "OK", 0
    engine = None
    try:
        check_qt()
        check_pdf_edit()
        engine = EngineClient()
        if not engine.ping():
            raise RuntimeError("движок не ответил на ping")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.docx")
            with open(path, "wb") as f:
                f.write(_minimal_docx())
            html = engine.render(path, "t.docx")
            ids = re.findall(r'data-id="([^"]+)"', html)
            if "Проверка движка" not in html or not ids:
                raise RuntimeError("DOCX отрисован неверно")
            out = os.path.join(tmp, "e.docx")
            engine.edit_text(path, "t.docx", ids[0], "Правка", out)
            if engine.text_at(out, "e.docx", ids[0]) != "Правка":
                raise RuntimeError("правка текста не сработала")
        message = "OK: движок документов работает (" + " ".join(engine_command()[:1]) + ")"
    except Exception as e:
        message, code = f"ОШИБКА: {e}", 1
    finally:
        if engine is not None:
            engine.close()
    if result_path:
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(message + "\n")
    else:
        print(message)
    return code
