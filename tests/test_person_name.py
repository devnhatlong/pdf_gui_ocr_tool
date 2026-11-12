"""Tên người trong Quyết định nối vào cuối trích yếu: python -m unittest tests.test_person_name -v."""
import unittest

from core import metadata

HEADER = ("CÔNG AN TỈNH LÂM ĐỒNG\nCỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\n"
          "Số: 3400/QĐ-CAT-PX01\nLâm Đồng, ngày 12 tháng 9 năm 2025\n"
          "QUYẾT ĐỊNH\nVề việc bổ nhiệm chức danh Trinh sát viên sơ cấp\n"
          "GIÁM ĐỐC CÔNG AN TỈNH LÂM ĐỒNG\nCăn cứ Thông tư số 09/2025/TT-BCA;\nQUYẾT ĐỊNH:\n")


def summary(body, header=HEADER):
    return metadata.meta_to_fields(metadata.extract_metadata(header + body))["trichyeu"]


class PersonNameTests(unittest.TestCase):
    def test_single_person_is_appended(self):
        body = ("Điều 1. Bổ nhiệm chức danh Trinh sát viên sơ cấp đối với đồng chí Bùi Mạnh Cường, "
                "sinh năm 1995, cấp bậc Thượng úy.\nĐiều 2. Quyết định có hiệu lực kể từ ngày ký.")
        self.assertEqual(summary(body), "Về việc bổ nhiệm chức danh Trinh sát viên sơ cấp Bùi Mạnh Cường")

    def test_name_wrapped_over_lines_and_rank_before_name(self):
        body = "Điều 1. Bổ nhiệm đồng chí Thượng úy\nNguyễn Hồng Sơn, cán bộ Phòng PX01.\nĐiều 2. Thi hành."
        self.assertEqual(summary(body), "Về việc bổ nhiệm chức danh Trinh sát viên sơ cấp Nguyễn Hồng Sơn")

    def test_all_caps_name(self):
        body = "Điều 1. Bổ nhiệm ông TRẦN VĂN BÌNH, sinh ngày 01/01/1990.\nĐiều 2. Thi hành."
        self.assertTrue(summary(body).endswith(" Trần Văn Bình"))

    def test_several_people_adds_nothing(self):
        body = ("Điều 1. Bổ nhiệm đồng chí Bùi Mạnh Cường và đồng chí Nguyễn Hồng Sơn giữ chức danh ...\n"
                "Điều 2. Thi hành.")
        self.assertEqual(summary(body), "Về việc bổ nhiệm chức danh Trinh sát viên sơ cấp")

    def test_list_attached_adds_nothing(self):
        body = "Điều 1. Bổ nhiệm các đồng chí có tên trong danh sách kèm theo.\nĐiều 2. Thi hành."
        self.assertEqual(summary(body), "Về việc bổ nhiệm chức danh Trinh sát viên sơ cấp")

    def test_title_word_is_not_a_name(self):
        body = "Điều 1. Giao đồng chí Trưởng phòng Tổ chức cán bộ thực hiện.\nĐiều 2. Thi hành."
        self.assertEqual(summary(body), "Về việc bổ nhiệm chức danh Trinh sát viên sơ cấp")

    def test_only_for_decisions(self):
        header = HEADER.replace("Số: 3400/QĐ-CAT-PX01", "Số: 53/BC-CNTT").replace("QUYẾT ĐỊNH", "BÁO CÁO")
        body = "Điều 1. Đồng chí Bùi Mạnh Cường báo cáo.\nĐiều 2. Thi hành."
        self.assertNotIn("Bùi Mạnh Cường", summary(body, header))

    def test_signer_outside_dieu_1_is_ignored(self):
        body = "Điều 1. Bổ nhiệm chức danh cho cán bộ đủ điều kiện.\nĐiều 2. Thi hành.\nGIÁM ĐỐC\nĐại tá Lê Văn Tùng"
        self.assertEqual(summary(body), "Về việc bổ nhiệm chức danh Trinh sát viên sơ cấp")

    def test_filename_appends_name_without_accents(self):
        fields = metadata.meta_to_fields(metadata.extract_metadata(
            HEADER + "Điều 1. Bổ nhiệm đồng chí Bùi Mạnh Cường, sinh năm 1995.\nĐiều 2. Thi hành."))
        name = metadata.build_filename(fields, "{loai}_{so}_{trichyeu}", ext="", ascii_name=True)
        self.assertEqual(name, "QĐ_3400_VeViecBoNhiemChucDanhTrinhSatVienSoCapBuiManhCuong")


if __name__ == "__main__":
    unittest.main()
