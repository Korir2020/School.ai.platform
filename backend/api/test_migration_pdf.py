import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from api.migration_check import UploadError, parse_table
from api.migration_rules import analyse_upload

STRUCT = [{"id": 1, "name": "Grade 7", "level_number": 7, "streams": [{"id": 11, "name": "East"}]}]
COLS = (50, 150, 250, 350)
HEAD = ["Admission No", "First name", "Surname", "Class"]
R1 = ["1001", "Amina", "Otieno", "Grade 7 East"]
R2 = ["1002", "Brian", "Kamau", "Grade 7 East"]


def make_pdf(pages, picture_on=()):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n, page in enumerate(pages, start=1):
        y = 780
        for row in page:
            for x, cell in zip(COLS, row):
                if cell is not None:
                    c.drawString(x, y, cell)
            y -= 20
        if n in picture_on:
            c.drawImage(ImageReader(Image.new("RGB", (40, 40), "white")), 50, 400, 100, 100)
        c.showPage()
    c.save()
    return SimpleUploadedFile("reg.pdf", buf.getvalue())


class PdfTests(SimpleTestCase):
    def test_typed_pdf_reads_rows(self):
        rows = parse_table(make_pdf([[HEAD, R1, R2]]))
        self.assertEqual(rows, [HEAD, R1, R2])

    def test_pages_markers_and_repeated_headers_removed(self):
        rows = parse_table(make_pdf([[HEAD, R1, ["Page 1 of 2"]], [HEAD, R2, ["Page 2 of 2"]]]))
        self.assertEqual(rows, [HEAD, R1, R2])

    def test_blank_page_ignored(self):
        rows = parse_table(make_pdf([[HEAD, R1], []]))
        self.assertEqual(rows, [HEAD, R1])

    def test_picture_only_page_refused_and_named(self):
        with self.assertRaises(UploadError) as ctx:
            parse_table(make_pdf([[HEAD, R1], []], picture_on=(2,)))
        self.assertIn("Page 2", str(ctx.exception))

    def test_empty_cell_refused_not_guessed(self):
        with self.assertRaises(UploadError) as ctx:
            parse_table(make_pdf([[HEAD, ["1004", "David", None, "Grade 7 East"]]]))
        self.assertIn("columns", str(ctx.exception))

    def test_not_a_pdf(self):
        with self.assertRaises(UploadError):
            parse_table(SimpleUploadedFile("a.pdf", b"hello"))

    def test_damaged_pdf(self):
        with self.assertRaises(UploadError):
            parse_table(SimpleUploadedFile("a.pdf", b"%PDF-1.4 garbage"))

    def test_pdf_through_the_rules(self):
        rows = parse_table(make_pdf([[HEAD, R1, R2]]))
        self.assertEqual(analyse_upload(rows, STRUCT)["summary"]["ready"], 2)
