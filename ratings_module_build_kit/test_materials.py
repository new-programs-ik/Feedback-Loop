"""
test_materials.py — the materials-by-link agent (URL parsing, link splitting, sniffing, and the
service wiring). Network is never touched — fetch is mocked. Run: python -m unittest test_materials -v
"""
import unittest
from unittest.mock import patch

import materials_fetch as MF
import service


class TestClassify(unittest.TestCase):
    def test_drive_file_forms(self):
        for url in [
            "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view?usp=sharing",
            "https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345",
            "https://drive.google.com/uc?id=1AbCdEfGhIjKlMnOpQrStUvWxYz012345&export=download",
        ]:
            kind, gid = MF.classify(url)
            self.assertEqual(kind, "drive_file")
            self.assertEqual(gid, "1AbCdEfGhIjKlMnOpQrStUvWxYz012345")

    def test_docs_slides_sheets(self):
        self.assertEqual(MF.classify("https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit")[0], "doc")
        self.assertEqual(MF.classify("https://docs.google.com/presentation/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit")[0], "slides")
        self.assertEqual(MF.classify("https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/edit")[0], "sheet")

    def test_folder_and_generic(self):
        self.assertEqual(MF.classify("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345")[0], "drive_folder")
        self.assertEqual(MF.classify("https://materials.myteam.vercel.app/decks/trees.pdf")[0], "generic")


class TestHelpers(unittest.TestCase):
    def test_split_links(self):
        txt = "https://a.com/x.pdf  https://b.com/y\nhttps://c.com/z, not-a-link"
        self.assertEqual(MF.split_links(txt), ["https://a.com/x.pdf", "https://b.com/y", "https://c.com/z"])

    def test_split_links_empty(self):
        self.assertEqual(MF.split_links("  "), [])

    def test_sniff_ext(self):
        self.assertEqual(MF._sniff_ext(b"%PDF-1.7 ..."), ".pdf")
        self.assertEqual(MF._sniff_ext(b"PK\x03\x04word/document.xml"), ".docx")
        self.assertEqual(MF._sniff_ext(b"PK\x03\x04ppt/slides"), ".pptx")
        self.assertEqual(MF._sniff_ext(b"just text"), ".txt")

    def test_folder_link_is_rejected(self):
        with self.assertRaises(MF.MaterialsFetchError):
            MF._fetch_one("https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz012345")


class TestServiceWiring(unittest.TestCase):
    def test_materials_url_is_fetched_and_extracted(self):
        req = service.AnalyzeRequest(transcript="1\n00:00:01,000 --> 00:00:03,000\nHi.\n",
                                     materials_url="https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz012345/view")
        with patch.object(MF, "fetch_all", return_value=[("slides.txt", b"Planned: trees, gini, ensembles")]):
            out = service.gather_materials(req)
        self.assertIn("trees, gini, ensembles", out)
        self.assertIn("from link", out)

    def test_materials_url_error_becomes_422(self):
        from fastapi import HTTPException
        req = service.AnalyzeRequest(transcript="1\n00:00:01,000 --> 00:00:03,000\nHi.\n",
                                     materials_url="https://drive.google.com/file/d/badbadbadbadbadbadbad/view")
        with patch.object(MF, "fetch_all", side_effect=MF.MaterialsFetchError("access denied (403)")):
            with self.assertRaises(HTTPException) as cm:
                service.gather_materials(req)
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("access denied", cm.exception.detail)


if __name__ == "__main__":
    unittest.main()
