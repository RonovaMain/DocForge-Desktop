import base64
import os
import re
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from docforge.printing import catalog, options, pcl, pipeline
from docforge.printing.filters import FilterError, FilterProcess, pbm_header
from docforge.printing.halftone import to_bits
from docforge.printing.ieee1284 import Ieee1284
from docforge.printing.options import PAPERS, PrintOptions
from docforge.printing.postscript import PostScriptWriter

ID = "MFG:Hewlett-Packard;MDL:HP LaserJet 1018;CMD:ACL,PJL;CLS:PRINTER;DES:HP LaserJet 1018;"


def with_length(text, big=True):
    t = text.encode("latin-1")
    n = len(t) + 2
    return (n.to_bytes(2, "big" if big else "little")) + t


def top(mfg, model, cmds=()):
    return catalog.select(mfg, model, list(cmds))[0].spec.id


class Ieee1284Test(unittest.TestCase):
    def test_length_prefix_variants(self):
        for raw in (with_length(ID, True), with_length(ID, False), ID.encode()):
            i = Ieee1284.parse(raw)
            self.assertEqual(i.manufacturer, "Hewlett-Packard")
            self.assertEqual(i.model, "HP LaserJet 1018")
            self.assertEqual(i.commands, ["ACL", "PJL"])
        self.assertTrue(Ieee1284.parse(b"").is_empty())


class CatalogTest(unittest.TestCase):
    def test_old_hp(self):
        self.assertEqual(top("Hewlett-Packard", "HP LaserJet 1018", ["ACL"]), "foo2zjs")
        self.assertEqual(top("HP", "LaserJet 1020"), "foo2zjs")
        self.assertEqual(top("HP", "LaserJet Professional P1102"), "foo2zjs")
        self.assertEqual(top("HP", "LaserJet P1005"), "foo2xqx")
        self.assertEqual(top("HP", "LaserJet M1005 MFP"), "foo2xqx")

    def test_laserjet_1010_family_uses_builtin_pcl(self):
        for m in ("hp LaserJet 1010", "LaserJet 1012", "LaserJet 1015"):
            self.assertEqual(top("HP", m), "pcl5")
        self.assertEqual(top("X", "Y", ["DW-PCL"]), "pcl5")
        # из очереди печати: модель и производитель — одна строка
        self.assertEqual(top("HP HP LaserJet 1010", "HP HP LaserJet 1010"), "pcl5")

    def test_languages_decide_when_model_unknown(self):
        self.assertEqual(top("Brother", "HL-L2350DW", ["PCL6", "PDF"]), "pdf")
        self.assertEqual(top("X", "Y", ["POSTSCRIPT2", "PCL5E"]), "ps")
        self.assertEqual(top("X", "Y", ["PCL5E"]), "pcl5")
        self.assertEqual(top("", ""), "pcl5")

    def test_other_vendors_and_hints(self):
        self.assertEqual(top("Samsung", "ML-2010"), "foo2qpdl")
        self.assertEqual(top("Xerox", "Phaser 6110"), "foo2slx")
        self.assertEqual(catalog.unsupported_hint(["GDI"]), "GDI")
        self.assertIsNone(catalog.unsupported_hint(["PCL"]))

    def test_filter_args(self):
        self.assertEqual(catalog.BY_ID["foo2zjs"].filter_args(4960, 7016, 9, 2), ["-r600x600", "-g4960x7016", "-p9", "-n2"])


class OptionsTest(unittest.TestCase):
    def test_range(self):
        self.assertEqual(options.parse_range("1-3, 5, 8-", 9), [1, 2, 3, 5, 8, 9])
        self.assertIsNone(options.parse_range("0", 9))
        self.assertIsNone(options.parse_range("5-3", 9))
        self.assertIsNone(options.parse_range("abc", 9))
        self.assertIsNone(options.parse_range("10", 9))

    def test_duplex_passes(self):
        self.assertEqual(options.passes([1, 2, 3, 4, 5], options.DUPLEX_BATCH, False), [[1, 3, 5], [2, 4]])
        self.assertEqual(options.passes([1, 2, 3, 4, 5], options.DUPLEX_BATCH, True), [[1, 3, 5], [0, 4, 2]])
        self.assertEqual(options.passes([1, 2], options.DUPLEX_SHEET, False), [[1], [2]])
        self.assertEqual(options.passes([1], options.DUPLEX_BATCH, True), [[1]])

    def test_rotation(self):
        self.assertTrue(options.should_rotate(842, 595, options.ROTATE_LANDSCAPE_PAGES))
        self.assertFalse(options.should_rotate(595, 842, options.ROTATE_LANDSCAPE_PAGES))
        self.assertTrue(options.should_rotate(595, 842, options.ROTATE_ALL))


class EncoderTest(unittest.TestCase):
    def test_halftone_extremes(self):
        white = to_bits(np.full((16, 16), 255, np.uint8))
        black = to_bits(np.zeros((16, 16), np.uint8))
        self.assertEqual(int(white.sum()), 0)
        self.assertTrue(np.all(black == 255))
        mid = to_bits(np.full((64, 64), 128, np.uint8))
        density = np.unpackbits(mid).mean()
        self.assertTrue(0.35 < density < 0.65, density)

    def test_pcl_page_structure(self):
        bits = to_bits(np.zeros((4, 16), np.uint8))
        data = pcl.page(bits, 26, 300)
        self.assertTrue(data.startswith(b"\x1b&l26A\x1b&l0O"))
        self.assertEqual(data.count(b"\x1b*b2W"), 4)
        self.assertTrue(data.endswith(b"\x1b*rB\x0c"))
        self.assertEqual(pcl.job_begin(True), b"\x1b%-12345X@PJL\r\n@PJL ENTER LANGUAGE=PCL\r\n\x1bE")

    def test_postscript_data_roundtrip(self):
        rng = np.random.default_rng(1)
        gray = rng.integers(0, 256, (40, 64), dtype=np.uint8)
        gray[5:20] = 255
        chunks = []
        ps = PostScriptWriter(chunks.append, "Док №1")
        ps.page(gray, 595, 842)
        ps.finish()
        text = b"".join(chunks)
        self.assertTrue(text.startswith(b"%!PS-Adobe-3.0"))
        marker = b"/DataSource A >> image\n"
        start = text.index(marker) + len(marker)
        end = text.index(b"~>", start)
        decoded = base64.a85decode(text[start:end].replace(b"\n", b""))
        self.assertEqual(decoded, gray.tobytes())


def fake_render(index, w, h, margin, rotate):
    img = np.full((h, w), 255, np.uint8)
    img[margin:margin + 10, margin:margin + 10] = 0
    return img


class PipelineTest(unittest.TestCase):
    def run_pipeline(self, driver, pages=(1, 2), **kw):
        out = bytearray()
        opts = PrintOptions(copies=kw.get("copies", 1), pjl=kw.get("pjl", False))
        pipeline.run(catalog.BY_ID[driver], opts, list(pages), fake_render, out.extend,
                     filter_binary=kw.get("filter_binary"), pdf_bytes=kw.get("pdf_bytes"), all_pages=kw.get("all_pages"))
        return bytes(out)

    def test_pcl(self):
        data = self.run_pipeline("pcl5", pages=(1, 0, 2), copies=2, pjl=True)
        self.assertEqual(data.count(b"\x1b*rB\x0c"), 6)
        self.assertTrue(data.startswith(b"\x1b%-12345X@PJL"))
        self.assertTrue(data.endswith(b"\x1bE\x1b%-12345X"))

    def test_postscript(self):
        data = self.run_pipeline("ps")
        self.assertEqual(data.count(b"showpage"), 2)
        self.assertIn(b"%%Pages: 2", data)

    def test_pdf_direct_whole_document_only(self):
        pdf = b"%PDF-1.4 test"
        self.assertEqual(self.run_pipeline("pdf", pdf_bytes=pdf, all_pages=2, copies=2), pdf * 2)
        with self.assertRaises(ValueError):
            self.run_pipeline("pdf", pages=(2,), pdf_bytes=pdf, all_pages=2)

    @unittest.skipUnless(os.path.exists("/bin/cat") or os.path.exists("/usr/bin/cat"), "нужен cat")
    def test_filter_gets_pbm_pages(self):
        cat = "/usr/bin/cat" if os.path.exists("/usr/bin/cat") else "/bin/cat"
        spec = catalog.DriverSpec("t", "t", catalog.FILTER, "cat", 100, "", False)
        out = bytearray()
        pipeline.run(spec, PrintOptions(), [1, 2], fake_render, out.extend, filter_binary=cat)
        self.assertEqual(len(re.findall(rb"P4\n\d+ \d+\n", bytes(out))), 2)

    @unittest.skipUnless(os.path.exists("/bin/sh"), "нужен sh")
    def test_filter_failure_reports_stderr(self):
        spec = catalog.DriverSpec("t", "t", catalog.FILTER, "sh", 100, "-c exit_with_error", False)
        with self.assertRaises(FilterError) as cm:
            pipeline.run(spec, PrintOptions(), [1], fake_render, lambda b: None, filter_binary="/bin/sh")
        self.assertIn("кодом", str(cm.exception))

    def test_cancel(self):
        calls = []
        with self.assertRaises(pipeline.Cancelled):
            pipeline.run(catalog.BY_ID["pcl5"], PrintOptions(), [1, 2], fake_render, calls.append, cancelled=lambda: len(calls) > 1)


if __name__ == "__main__":
    unittest.main()
