"""Самопроверка собранной программы без окна: `DocForge --selftest результат.txt`.
Проверяет, что движок документов (своя JRE + engine.jar) запускается и читает и правит DOCX. Нужна для проверки сборок в CI."""
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


def run(result_path: str | None) -> int:
    from .engine import EngineClient
    from .paths import engine_command

    message, code = "OK", 0
    engine = None
    try:
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
