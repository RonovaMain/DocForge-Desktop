import io
import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docforge.engine import DocError, EngineClient
from docforge.paths import engine_command

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def minimal_docx(paragraphs):
    body = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paragraphs)
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
                   f'<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="{W}"><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


def engine_available():
    try:
        engine_command()
        return True
    except FileNotFoundError:
        return False


@unittest.skipUnless(engine_available(), "движок не собран: python tools/build_engine.py")
class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = EngineClient()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.path = os.path.join(cls.tmp.name, "t.docx")
        with open(cls.path, "wb") as f:
            f.write(minimal_docx(["Первый абзац", "Второй абзац"]))

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()
        cls.tmp.cleanup()

    def test_ping_and_detect(self):
        self.assertTrue(self.engine.ping())
        self.assertEqual(self.engine.detect(self.path, "t.docx"), "DOCX")

    def test_render_edit_roundtrip(self):
        html = self.engine.render(self.path, "t.docx")
        self.assertIn("Первый абзац", html)
        ids = re.findall(r'data-id="([^"]+)"', html)
        self.assertGreaterEqual(len(ids), 2)
        self.assertEqual(self.engine.text_at(self.path, "t.docx", ids[1]), "Второй абзац")
        out = os.path.join(self.tmp.name, "edited.docx")
        self.engine.edit_text(self.path, "t.docx", ids[1], "Новый текст & <b>", out)
        self.assertEqual(self.engine.text_at(out, "edited.docx", ids[1]), "Новый текст & <b>")
        self.assertEqual(self.engine.text_at(self.path, "t.docx", ids[1]), "Второй абзац")  # исходник не тронут

    def test_errors_are_readable(self):
        bad = os.path.join(self.tmp.name, "x.txt")
        with open(bad, "w") as f:
            f.write("hello")
        with self.assertRaises(DocError) as cm:
            self.engine.render(bad, "x.txt")
        self.assertIn("Неподдерживаемый", str(cm.exception))

    def test_pdf_wrapper(self):
        html = self.engine.pdf_pages([(595, 842), (612, 792)])
        self.assertEqual(html.count('class="pdfpage"'), 2)
        self.assertIn("docforge.local/pdf/1", html)


if __name__ == "__main__":
    unittest.main()
