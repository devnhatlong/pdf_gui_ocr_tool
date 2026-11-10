"""Sổ danh mục văn bản (Excel): python -m unittest tests.test_register -v."""
import os
import tempfile
import unittest

from openpyxl import load_workbook

from core import exporters, metadata


class SheetRangeTests(unittest.TestCase):
    def test_two_pages_per_sheet(self):
        self.assertEqual(metadata.sheet_range([1, 2], 2), "1")       # trang 1-2 = tờ 1
        self.assertEqual(metadata.sheet_range([1, 2, 3, 4], 2), "1-2")
        self.assertEqual(metadata.sheet_range([3, 4, 5], 2), "2-3")  # trang 3,4=tờ2; 5=tờ3
        self.assertEqual(metadata.sheet_range([6], 2), "3")
        self.assertEqual(metadata.sheet_range([1, 2, 5], 2), "1-3")  # span có trang trắng ở giữa

    def test_one_page_per_sheet(self):
        self.assertEqual(metadata.sheet_range([1, 2, 3], 1), "1-3")  # quét 1 mặt: tờ = trang

    def test_empty(self):
        self.assertEqual(metadata.sheet_range([], 2), "")


class RegisterExcelTests(unittest.TestCase):
    def build(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "dm.xlsx")
        exporters.export_register(rows, path)
        return load_workbook(path).active

    def test_headers_and_row(self):
        ws = self.build([{"so": "1792/QĐ-XPHC", "ngay": "12/08/2025", "coquan": "Công an tỉnh",
                          "trichyeu": "Quyết định xử phạt hành chính", "to_so": "1-3"}])
        self.assertEqual([c.value for c in ws[1]][:6], ["STT", "Số ký hiệu", "Ngày ban hành", "Cơ quan ban hành", "Trích yếu", "Tờ số"])
        self.assertEqual([ws.cell(2, c).value for c in range(1, 8)],
                         [1, "1792/QĐ-XPHC", "12/08/2025", "Công an tỉnh", "Quyết định xử phạt hành chính", "1-3", "Không mật"])
        self.assertIn(ws.cell(2, 8).value, (None, ""))   # Ghi chú để trống

    def test_stt_increments(self):
        ws = self.build([{"so": "1/BC-X"}, {"so": "2/BC-X"}, {"so": "3/BC-X"}])
        self.assertEqual([ws.cell(r, 1).value for r in (2, 3, 4)], [1, 2, 3])

    def test_do_mat_default_khong_mat(self):
        ws = self.build([{"so": "1/BC-X"}])
        self.assertEqual(ws.cell(2, 7).value, "Không mật")

    def test_do_mat_header_parenthesis_not_bold(self):
        from openpyxl.cell.rich_text import CellRichText
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "dm.xlsx")
        exporters.export_register([{"so": "1/BC-X"}], path)
        cell = load_workbook(path, rich_text=True).active.cell(1, 7)
        self.assertIsInstance(cell.value, CellRichText)
        bolds = [getattr(getattr(b, "font", None), "b", None) for b in cell.value]
        self.assertIn(True, bolds)    # "Độ mật" in đậm
        self.assertIn(False, bolds)   # "(Không mật/...)" không đậm
        self.assertIn("Không mật", str(cell.value))

    def test_font_times_new_roman_14_center_bold_header(self):
        ws = self.build([{"so": "1/BC-X", "trichyeu": "Thử"}])
        body = ws.cell(2, 5)
        self.assertEqual(body.font.name, "Times New Roman")
        self.assertEqual(body.font.size, 14)
        self.assertFalse(body.font.bold)
        self.assertEqual(body.alignment.horizontal, "center")
        self.assertEqual(body.alignment.vertical, "center")
        head = ws.cell(1, 1)
        self.assertTrue(head.font.bold)
        self.assertEqual(head.font.name, "Times New Roman")
        self.assertEqual(head.font.size, 14)


if __name__ == "__main__":
    unittest.main()
