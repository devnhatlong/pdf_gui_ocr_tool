"""Trích loại / cơ quan theo bảng viết tắt cấu hình: python -m unittest tests.test_metadata_maps -v."""
import unittest

from core import metadata

# Hai cột: cơ quan bên trái, quốc hiệu bên phải (cách nhau >= 3 dấu cách như bản scan hai cột)
HDR_PHONG = ("CÔNG AN TỈNH LÂM ĐỒNG              CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
             "PHÒNG THAM MƯU                     Độc lập - Tự do - Hạnh phúc\n"
             "Số: 496/BCĐX-PV01-CNTT\n")
HDR_DOI = ("PHÒNG THAM MƯU                     CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
           "ĐỘI CÔNG NGHỆ THÔNG TIN            Độc lập - Tự do - Hạnh phúc\n"
           "Số: 53/BC-CNTT\n")
HDR_ONE = ("ỦY BAN NHÂN DÂN TỈNH LÂM ĐỒNG      CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
           "Số: 17/QĐ-UBND\n")


class ResolveTypeTests(unittest.TestCase):
    def test_code_after_slash_known(self):
        self.assertEqual(metadata.resolve_type("", "1794/QĐ-XPHC"), "QĐ")

    def test_code_after_slash_unknown_is_kept(self):
        self.assertEqual(metadata.resolve_type("", "496/BCĐX-PV01-CNTT"), "BCĐX")

    def test_ocr_d_without_stroke_maps_to_canonical(self):
        self.assertEqual(metadata.resolve_type("", "1/QD-UBND"), "QĐ")

    def test_unit_code_after_slash_is_cong_van(self):
        self.assertEqual(metadata.resolve_type("", "1831/PV01-CNTT"), "CV")

    def test_year_in_number_is_skipped(self):
        self.assertEqual(metadata.resolve_type("", "45/2026/NĐ-CP"), "NĐ")

    def test_title_fallback_when_no_code(self):
        self.assertEqual(metadata.resolve_type("DANH SÁCH\nCán bộ đề nghị khen thưởng", ""), "DS")

    def test_custom_type_code(self):
        tmap = [{"ten": "Lệnh", "tat": "L"}]
        self.assertEqual(metadata.resolve_type("", "9/L-CA", tmap), "L")


class DetectAgencyTests(unittest.TestCase):
    def test_takes_issuing_body_above_so(self):
        self.assertEqual(metadata.detect_agency(HDR_PHONG), ("PHÒNG THAM MƯU", "PV01"))

    def test_lowest_unit_before_so(self):
        self.assertEqual(metadata.detect_agency(HDR_DOI)[1], "CNTT")

    def test_single_line_header(self):
        self.assertEqual(metadata.detect_agency(HDR_ONE), ("ỦY BAN NHÂN DÂN TỈNH LÂM ĐỒNG", "UBND"))

    def test_default_has_cong_an_units(self):
        self.assertEqual(metadata.detect_agency("PHÒNG CẢNH SÁT GIAO THÔNG\nSố: 10/KH-PC08\n")[1], "PC08")

    def test_trai_giam_number_not_confused_with_so_line(self):
        self.assertEqual(metadata.detect_agency("TRẠI GIAM SỐ 02\nSố: 5/QĐ-TTG02\n"), ("TRẠI GIAM SỐ 02", "TTG02"))

    def test_longest_matching_unit_wins(self):
        text = "PHÒNG CẢNH SÁT ĐIỀU TRA TỘI PHẠM VỀ MA TÚY\nSố: 9/BC-PC04\n"
        self.assertEqual(metadata.detect_agency(text)[1], "PC04")

    def test_doi_units_under_phong_tham_muu(self):
        for name, code in (("ĐỘI THAM MƯU TỔNG HỢP", "TMTH"), ("ĐỘI VIỄN THÔNG CƠ YẾU", "VTCY"),
                           ("TRUNG TÂM THÔNG TIN CHỈ HUY", "TTTTCH")):
            self.assertEqual(metadata.detect_agency(f"{name}\nSố: 1/BC-{code}\n")[1], code)

    def test_custom_agency_abbreviation(self):
        amap = [{"ten": "Phòng Cảnh sát giao thông", "tat": "PC08"}]
        text = "PHÒNG CẢNH SÁT GIAO THÔNG\nSố: 10/KH-PC08\n"
        self.assertEqual(metadata.detect_agency(text, amap), ("PHÒNG CẢNH SÁT GIAO THÔNG", "PC08"))

    def test_unknown_agency_falls_back_to_initials(self):
        text = "BAN CHỈ HUY QUÂN SỰ\nSố: 5/BC-X\n"
        self.assertEqual(metadata.detect_agency(text, [])[1], "BCHQ")


class SecrecyTests(unittest.TestCase):
    def ocr(self, lines):
        return {"size": [1000, 1000], "lines": [{"text": t, "box": [100, int(y * 1000) - 8, 300, int(y * 1000) + 8]} for t, y in lines]}

    def test_base_levels_and_ocr_variants(self):
        for text, label in (("TUYỆT MẬT", "Tuyệt mật"), ("TUYẾT MẬT", "Tuyệt mật"), ("TỐI MẬT", "Tối mật"),
                            ("MẬT", "Mật"), ("MẶT", "Mật"), ("MẬT]", "Mật")):
            self.assertEqual(metadata.detect_secrecy(self.ocr([(text, 0.2)])), label, text)

    def test_no_stamp(self):
        self.assertEqual(metadata.detect_secrecy(self.ocr([("QUYẾT ĐỊNH", 0.2)])), "Không mật")
        self.assertEqual(metadata.detect_secrecy(None), "Không mật")

    def test_mat_in_content_not_detected(self):
        self.assertEqual(metadata.detect_secrecy(self.ocr([("mật độ xây dựng 40%", 0.6)])), "Không mật")
        self.assertEqual(metadata.detect_secrecy(self.ocr([("Về việc bảo vệ bí mật", 0.2)])), "Không mật")

    def test_adjustment_and_declassify(self):
        self.assertEqual(metadata.detect_secrecy(self.ocr([("GIẢM XUỐNG TỐI MẬT", 0.2)])), "Tối mật")
        self.assertEqual(metadata.detect_secrecy(self.ocr([("TĂNG LÊN TUYỆT MẬT", 0.2)])), "Tuyệt mật")
        self.assertEqual(metadata.detect_secrecy(self.ocr([("GIẢM XUỐNG MẬT", 0.2)])), "Mật")
        self.assertEqual(metadata.detect_secrecy(self.ocr([("GIẢI MẬT", 0.2)])), "Không mật")


class EndToEndTests(unittest.TestCase):
    def test_phong_tham_muu_document(self):
        meta = metadata.extract_metadata(HDR_PHONG)
        self.assertEqual(meta["loai_van_ban"], "BCĐX")
        self.assertEqual(meta["co_quan_viet_tat"], "PV01")

    def test_filename_uses_number_type_agency(self):
        meta = metadata.extract_metadata(HDR_DOI)
        fields = metadata.meta_to_fields(meta)
        name = metadata.build_filename(fields, "{so}-{loai}-{coquan}", ext="")
        self.assertEqual(name, "53-BC-CNTT")

    def test_so_field_is_number_only(self):
        for raw, num in (("53/BC-CNTT", "53"), ("1831/PV01-CNTT", "1831"), ("45/2026/NĐ-CP", "45"), ("618/QĐ-CAT", "618")):
            self.assertEqual(metadata.so_number(raw), num)
        self.assertEqual(metadata.meta_to_fields(metadata.extract_metadata(HDR_DOI))["so"], "53")

    def test_empty_maps_disable_abbreviation(self):
        # Bảng rỗng: cơ quan dùng chữ cái đầu, loại giữ mã thô
        meta = metadata.extract_metadata(HDR_PHONG, type_map=[], agency_map=[])
        self.assertEqual(meta["loai_van_ban"], "BCĐX")
        self.assertEqual(meta["co_quan_viet_tat"], "PTM")


if __name__ == "__main__":
    unittest.main()
