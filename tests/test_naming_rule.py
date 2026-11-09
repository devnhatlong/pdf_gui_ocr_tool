"""File naming rule checks: python -m unittest tests.test_naming_rule -v."""
import json
import os
import tempfile
import unittest

from core import metadata
from core.settings import DEFAULTS, OLD_NAMING_RULE, Settings

FIELDS = {"loai": "QĐ", "coquan": "UBND", "so": "123/QĐ-UBND", "ngay": "05/11/2026",
          "trichyeu": "Về việc phê duyệt kế hoạch"}


class AsciiNameTests(unittest.TestCase):
    def build(self, fields, rule="{so}_{ngay}_{trichyeu}", **kw):
        return metadata.build_filename(fields, rule, ext="", ascii_name=True, **kw)

    def test_on_by_default(self):
        self.assertIs(DEFAULTS["filename_ascii"], True)

    def test_summary_joined_without_accents(self):
        fields = {"so": "56/BC-CAT", "ngay": "19/10/2026", "trichyeu": "Quyết định bổ nhiệm kỹ thuật viên sơ cấp"}
        self.assertEqual(self.build(fields, "{so}_{ngay}_{trichyeu}"), "56_19-10-2026_QuyetDinhBoNhiemKyThuatVienSoCap")

    def test_d_letter_and_punctuation(self):
        fields = {"so": "496/BCĐX-PV01", "trichyeu": "V/v đề nghị kiểm tra, sửa chữa (đợt 2) tháng 9/2026"}
        self.assertEqual(self.build(fields, "{so}_{trichyeu}"), "496_VeViecDeNghiKiemTraSuaChuaDot2Thang9-2026")

    def test_other_fields_lose_accents(self):
        self.assertEqual(self.build(FIELDS, "{loai}_{coquan}_{so}"), "QD_UBND_123")

    def test_off_keeps_vietnamese(self):
        fields = {"so": "56/BC-CAT", "trichyeu": "Quyết định bổ nhiệm"}
        self.assertEqual(metadata.build_filename(fields, "{so}_{trichyeu}", ext=""), "56_Quyết định bổ nhiệm")

    def test_number_only_before_slash(self):
        for raw, num in (("1794/QĐ-XPHC", "1794"), ("496/BCĐX-PV01-CNTT", "496"), ("53/BC-CNTT", "53"), ("88", "88")):
            self.assertEqual(self.build({"so": raw}, "{so}"), num)

    def test_api_uses_setting(self):
        from types import SimpleNamespace
        from core.api import Api
        values = {"naming_rule": "{so}_{loai}_{trichyeu}", "slash_replacement": "-", "filename_ascii": True}
        api = SimpleNamespace(_settings=SimpleNamespace(get=values.get))
        fields = {"so": "1794/QĐ-XPHC", "loai": "QĐ", "trichyeu": "Về việc thi đua"}
        self.assertEqual(Api._file_name(api, fields), "1794_QD_VeViecThiDua.pdf")
        values["filename_ascii"] = False
        self.assertEqual(Api._file_name(api, fields), "1794_QĐ_Về việc thi đua.pdf")


class NamingRuleTests(unittest.TestCase):
    def load(self, saved):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(saved, f)
            return Settings(path).get("naming_rule")

    def test_default_rule_is_number_type_agency_date_summary(self):
        self.assertEqual(DEFAULTS["naming_rule"], "{so}-{loai}-{coquan}_{ngay}_{trichyeu}")
        self.assertEqual(metadata.build_filename(FIELDS, DEFAULTS["naming_rule"]),
                         "123-QĐ-UBND_05-11-2026_Về việc phê duyệt kế hoạch.pdf")

    def test_user_example(self):
        fields = {"loai": "BC", "coquan": "CAT", "so": "56/BC-CAT", "ngay": "19/10/2026",
                  "trichyeu": "Quyết định bổ nhiệm kỹ thuật viên sơ cấp"}
        self.assertEqual(metadata.build_filename(fields, DEFAULTS["naming_rule"], ext=""),
                         "56-BC-CAT_19-10-2026_Quyết định bổ nhiệm kỹ thuật viên sơ cấp")

    def test_summary_all_caps_and_illegal_characters(self):
        self.assertEqual(metadata.build_filename({"trichyeu": "VỀ VIỆC PHÊ DUYỆT"}), "Về việc phê duyệt.pdf")
        self.assertEqual(metadata.build_filename({"trichyeu": "về Nghị định 12/2024: \"sửa đổi\"?"}),
                         "Về Nghị định 12-2024 sửa đổi.pdf")

    def test_summary_expands_vv(self):
        for summary in ("V/v tổ chức tập huấn", "V/V: tổ chức tập huấn", "v / v tổ chức tập huấn"):
            self.assertEqual(metadata.build_filename({"trichyeu": summary}), "Về việc tổ chức tập huấn.pdf")

    def test_summary_follows_the_document(self):
        header = ("CÔNG AN TỈNH LÂM ĐỒNG\nCỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc\n"
                  "Số: 56/QĐ-CAT\nLâm Đồng, ngày 19 tháng 10 năm 2026\n")
        footer = "\nGIÁM ĐỐC CÔNG AN TỈNH\nCăn cứ Luật Công an nhân dân"
        cases = {
            "Quyết định bổ nhiệm kỹ thuật viên sơ cấp": "Quyết định bổ nhiệm kỹ thuật viên sơ cấp",
            "QUYẾT ĐỊNH BỔ NHIỆM KỸ THUẬT VIÊN SƠ CẤP": "Quyết định bổ nhiệm kỹ thuật viên sơ cấp",
            "QUYẾT ĐỊNH\nVề việc bổ nhiệm kỹ thuật viên": "Về việc bổ nhiệm kỹ thuật viên",
            "QUYẾT ĐỊNH\nVỀ VIỆC BỔ NHIỆM KỸ THUẬT VIÊN": "Về việc bổ nhiệm kỹ thuật viên",
            "QUYẾT ĐỊNH\nVỀ VIỆC BỔ NHIỆM\nKỸ THUẬT VIÊN SƠ CẤP": "Về việc bổ nhiệm kỹ thuật viên sơ cấp",
            "Về việc bổ nhiệm kỹ thuật viên": "Về việc bổ nhiệm kỹ thuật viên",
            "Quyết định về việc bổ nhiệm cán bộ": "Về việc bổ nhiệm cán bộ",
            "THÔNG BÁO: Lịch họp giao ban tháng 11": "Lịch họp giao ban tháng 11",
            "BÁO CÁO\nKết quả công tác quý III": "Kết quả công tác quý III",
        }
        for body, expected in cases.items():
            with self.subTest(body=body):
                fields = metadata.meta_to_fields(metadata.extract_metadata(header + body + footer))
                self.assertEqual(metadata.build_filename(fields, "{trichyeu}", ext=""), expected)

    def test_slash_replacement_is_configurable(self):
        cases = {"-": "123_05-11-2026", ".": "123_05.11.2026", "_": "123_05_11_2026",
                 "--": "123_05--11--2026", " ": "123_05 11 2026", "": "123_05112026", "~": "123_05~11~2026"}
        for slash, expected in cases.items():
            with self.subTest(slash=slash):
                self.assertEqual(metadata.build_filename(FIELDS, "{so}_{ngay}", ext="", slash=slash), expected)

    def test_slash_replacement_cannot_add_windows_forbidden_characters(self):
        name = metadata.build_filename(FIELDS, "{ngay}", ext="", slash='\\/:*?"<>|\x01.')
        self.assertEqual(name, "05.11.2026")

    def test_slash_replacement_default_and_saved_value(self):
        self.assertEqual(DEFAULTS["slash_replacement"], "-")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "settings.json")
            Settings(path).update({"slash_replacement": "."})
            self.assertEqual(Settings(path).get("slash_replacement"), ".")

    def test_missing_part_drops_its_separator(self):
        self.assertEqual(metadata.build_filename({**FIELDS, "ngay": ""}, "{so}-{loai}-{coquan}_{ngay}_{trichyeu}"),
                         "123-QĐ-UBND_Về việc phê duyệt kế hoạch.pdf")

    def test_number_keeps_letter_d_with_stroke(self):
        for number in ("1/QĐ-UBND", "45/2026/NĐ-CP", "88/KH-ĐU", "15/ĐA-UBND", "12/TB-VP"):
            self.assertEqual(metadata.extract_metadata(f"Số: {number}")["so_ky_hieu"], number)

    def test_type_is_derived_from_number_with_d(self):
        self.assertEqual(metadata.extract_metadata("Số: 1/QĐ-UBND")["loai_van_ban"], "QĐ")

    def test_summary_has_no_d_with_stroke(self):
        self.assertEqual(metadata.remove_accents("Quyết định Đà Nẵng"), "quyet dinh da nang")

    def test_saved_old_default_moves_to_new_rule(self):
        self.assertEqual(self.load({"naming_rule": OLD_NAMING_RULE}), DEFAULTS["naming_rule"])

    def test_saved_custom_rule_is_kept(self):
        self.assertEqual(self.load({"naming_rule": "{ngay}_{so}"}), "{ngay}_{so}")

    def test_old_number_date_summary_default_moves_to_new_rule(self):
        self.assertEqual(self.load({"naming_rule": "{so}_{ngay}_{trichyeu}"}), DEFAULTS["naming_rule"])


if __name__ == "__main__":
    unittest.main()
