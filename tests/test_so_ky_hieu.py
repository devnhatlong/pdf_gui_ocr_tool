"""Số ký hiệu (cột Excel): python -m unittest tests.test_so_ky_hieu -v."""
import unittest

from core import metadata


def fields_of(text):
    meta = metadata.extract_metadata(text)
    meta["loai_van_ban"] = metadata.resolve_type(text, meta["so_ky_hieu"])
    return metadata.meta_to_fields(meta)


class ExtractTests(unittest.TestCase):
    def test_space_between_handwritten_number_and_slash(self):
        # số viết tay thường cách dấu / -> trước đây chỉ lấy được "2420"
        for line in ("Số:2420 /QĐ-CAT-PX01", "Số: 2420 / QĐ-CAT-PX01", "Số: 2420/QĐ-CAT-PX01"):
            with self.subTest(line=line):
                text = line + "\nLâm Đồng, ngày 28 tháng 8 năm 2025"
                self.assertEqual(metadata.extract_metadata(text)["so_ky_hieu"], "2420/QĐ-CAT-PX01")

    def test_does_not_swallow_following_words(self):
        self.assertEqual(metadata.extract_metadata("Số: 17\nDANH SÁCH CHẤM ĐIỂM")["so_ky_hieu"], "17")


class BuildTests(unittest.TestCase):
    def test_round_trip_keeps_original(self):
        for so in ("2420/QĐ-CAT-PX01", "1794/QĐ-XPHC", "53/BC-CNTT", "496/BCĐX-PV01-CNTT",
                   "1831/PV01-CNTT", "45/2026/NĐ-CP", "17"):
            with self.subTest(so=so):
                self.assertEqual(metadata.build_so_ky_hieu(fields_of(f"Số: {so}")), so)

    def test_edited_number_and_type_are_used(self):
        f = fields_of("Số: 24L0/QĐ-CAT-PX01")   # OCR đọc sai số viết tay
        f["so"] = "2420"
        self.assertEqual(metadata.build_so_ky_hieu(f), "2420/QĐ-CAT-PX01")
        f["loai"] = "TB"
        self.assertEqual(metadata.build_so_ky_hieu(f), "2420/TB-CAT-PX01")

    def test_cong_van_does_not_insert_type(self):
        f = fields_of("Số: 1831/PV01-CNTT")
        self.assertEqual(f["loai"], "CV")
        self.assertEqual(metadata.build_so_ky_hieu(f), "1831/PV01-CNTT")

    def test_missing_number_keeps_leading_slash(self):
        self.assertEqual(metadata.build_so_ky_hieu(fields_of("Số: /QĐ-CAT-PX01")), "/QĐ-CAT-PX01")

    def test_manual_value_wins(self):
        f = {**fields_of("Số: 24L0/QĐ-CAT-PXO1"), "sokyhieu": "2420/QĐ-CAT-PX01"}
        self.assertEqual(metadata.build_so_ky_hieu(f), "2420/QĐ-CAT-PX01")

    def test_custom_rule(self):
        f = {**fields_of("Số: 2420/QĐ-CAT-PX01"), "coquan": "CATLĐ"}
        self.assertEqual(metadata.build_so_ky_hieu(f, "{so}/{loai}-{coquan}"), "2420/QĐ-CATLĐ")

    def test_filename_is_not_affected(self):
        f = fields_of("Số: 2420/QĐ-CAT-PX01")
        self.assertEqual(metadata.build_filename(f, "{so}_{loai}", ext=""), "2420_QĐ")


if __name__ == "__main__":
    unittest.main()
