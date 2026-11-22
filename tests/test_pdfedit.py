import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docforge import pdfedit, pdfpage
from docforge.engine import DocError

try:
    import pikepdf
except ImportError:  # pragma: no cover
    pikepdf = None


def make_pdf(path, pages=3, rotate=0, crop=None):
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page(page_size=(400, 600))
    for page in pdf.pages:
        if rotate:
            page.obj["/Rotate"] = rotate
        if crop:
            page.obj["/CropBox"] = pikepdf.Array(crop)
    pdf.save(path)
    pdf.close()


def contents_text(page) -> str:
    c = page.obj["/Contents"]
    parts = [c[i] for i in range(len(c))] if isinstance(c, pikepdf.Array) else [c]
    return "\n".join(p.read_bytes().decode("latin-1") for p in parts)


class CleanOpTest(unittest.TestCase):
    def test_rejects_garbage(self):
        for bad in (None, {}, {"tool": "x"}, {"tool": "pen", "points": []}, {"tool": "highlight", "rects": []},
                    {"tool": "cover", "rect": [0.1, 0.1, 0.1, 0.1]}, {"tool": "pen", "points": [["a", 1]]}):
            self.assertIsNone(pdfedit.clean_op(bad), bad)

    def test_normalizes(self):
        op = pdfedit.clean_op({"tool": "cover", "color": "zzz", "rect": [0.5, 0.6, 0.1, 0.2]})
        self.assertEqual(op["rect"], [0.1, 0.2, 0.5, 0.6])
        self.assertEqual(op["color"], "#ffeb3b")  # неверный цвет заменяется
        self.assertEqual(pdfedit.clean_op({"tool": "cover", "color": "ABCDEF", "rect": [0, 0, 1, 1]})["color"], "#abcdef")
        op = pdfedit.clean_op({"tool": "pen", "color": "#112233", "width": 5, "points": [[2, -1]]})
        self.assertEqual(op["points"], [(1.0, 0.0)])
        self.assertLessEqual(op["width"], 0.2)

    def test_remap_after_delete(self):
        self.assertEqual(pdfedit.remap_after_delete({0: ["a"], 1: ["b"], 3: ["c"], 4: ["d"]}, [1, 3]), {0: ["a"], 2: ["d"]})


@unittest.skipIf(pikepdf is None, "нет pikepdf")
class PdfFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = os.path.join(self.tmp.name, "a.pdf")

    def tearDown(self):
        self.tmp.cleanup()

    def test_marks_are_baked_into_contents(self):
        make_pdf(self.src)
        out = os.path.join(self.tmp.name, "o.pdf")
        ops = [
            pdfedit.clean_op({"tool": "highlight", "color": "#ffeb3b", "rects": [[0.1, 0.1, 0.5, 0.15]]}),
            pdfedit.clean_op({"tool": "pen", "color": "#ff0000", "width": 0.005, "points": [[0.1, 0.5], [0.4, 0.6]]}),
            pdfedit.clean_op({"tool": "cover", "color": "#000000", "rect": [0.2, 0.7, 0.4, 0.8]}),
        ]
        pdfedit.write_with_ops(self.src, out, {0: ops})
        with pikepdf.open(out) as pdf:
            text = contents_text(pdf.pages[0])
            self.assertIn("Multiply", str(pdf.pages[0].obj["/Resources"]["/ExtGState"]))
            self.assertIn(" re", text)
            self.assertIn(" S Q", text)
            self.assertNotIn(" re", contents_text(pdf.pages[1]))  # соседняя страница не тронута
        with pikepdf.open(self.src) as pdf:  # исходник не изменился
            self.assertEqual(len(pdf.pages), 3)

    def test_geometry_matrix_per_rotation(self):
        expected = {0: "1 0 0 -1 0 600", 90: "0 1 1 0 0 0", 180: "-1 0 0 1 400 0", 270: "0 -1 -1 0 400 600"}
        for rot, matrix in expected.items():
            make_pdf(self.src, pages=1, rotate=rot)
            out = os.path.join(self.tmp.name, f"o{rot}.pdf")
            pdfedit.write_with_ops(self.src, out, {0: [pdfedit.clean_op({"tool": "cover", "color": "#ff0000", "rect": [0.1, 0.1, 0.3, 0.2]})]})
            with pikepdf.open(out) as pdf:
                self.assertIn(matrix + " cm", contents_text(pdf.pages[0]), rot)

    def test_cropbox_offset(self):
        make_pdf(self.src, pages=1, crop=[20, 30, 380, 560])
        out = os.path.join(self.tmp.name, "o.pdf")
        pdfedit.write_with_ops(self.src, out, {0: [pdfedit.clean_op({"tool": "cover", "color": "#ff0000", "rect": [0.1, 0.1, 0.3, 0.2]})]})
        with pikepdf.open(out) as pdf:
            self.assertIn("1 0 0 -1 20 560 cm", contents_text(pdf.pages[0]))

    def test_inherited_resources_are_kept(self):
        make_pdf(self.src, pages=2)
        with pikepdf.open(self.src) as pdf:
            pdf.Root.Pages["/Resources"] = pikepdf.Dictionary(Font=pikepdf.Dictionary())
            for page in pdf.pages:
                if "/Resources" in page.obj:
                    del page.obj["/Resources"]
            pdf.save(os.path.join(self.tmp.name, "i.pdf"))
        out = os.path.join(self.tmp.name, "o.pdf")
        pdfedit.write_with_ops(os.path.join(self.tmp.name, "i.pdf"), out, {0: [pdfedit.clean_op({"tool": "cover", "rect": [0.1, 0.1, 0.3, 0.2]})]})
        with pikepdf.open(out) as pdf:
            self.assertIn("/Font", pdf.pages[0].obj["/Resources"])
            self.assertIn("/ExtGState", pdf.pages[0].obj["/Resources"])

    def test_delete_pages(self):
        make_pdf(self.src, pages=5)
        out = os.path.join(self.tmp.name, "d.pdf")
        self.assertEqual(pdfedit.write_without_pages(self.src, out, [0, 2, 2]), 3)
        with pikepdf.open(out) as pdf:
            self.assertEqual(len(pdf.pages), 3)
        with self.assertRaises(DocError):
            pdfedit.write_without_pages(self.src, out, list(range(5)))
        with self.assertRaises(DocError):
            pdfedit.write_without_pages(self.src, out, [])
        with self.assertRaises(DocError):
            pdfedit.write_without_pages(self.src, out, [99])


class PdfPageHtmlTest(unittest.TestCase):
    def test_html(self):
        html = pdfpage.build_html([(595.0, 842.0), (612.0, 792.0)], "page", 150)
        self.assertIn("[[595.0, 842.0], [612.0, 792.0]]", html)
        self.assertIn("var mode = 'page'", html)
        self.assertNotIn("__SIZES__", html)
        self.assertNotIn("__MODE__", html)
        self.assertIn("script-src 'nonce-", html)

    def test_bad_mode_falls_back(self):
        self.assertIn("var mode = 'width'", pdfpage.build_html([(100.0, 100.0)], "x'; alert(1); '", 100))


if __name__ == "__main__":
    unittest.main()
