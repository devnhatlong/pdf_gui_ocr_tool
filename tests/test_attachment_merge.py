"""Gộp danh sách kèm theo vào văn bản chính: python -m unittest tests.test_attachment_merge -v."""
import unittest
from types import SimpleNamespace

from core import splitter

H = 1000
HEADER = ["CÔNG AN TỈNH LÂM ĐỒNG", "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "Độc lập - Tự do - Hạnh phúc"]


def ocr(lines):
    """lines: chuỗi (mỗi dòng một hàng) hoặc danh sách ô (cùng hàng)."""
    out = []
    for i, line in enumerate(lines):
        y = 30 + i * 40
        for j, text in enumerate([line] if isinstance(line, str) else line):
            out.append({"text": text, "box": [50 + j * 200, y, 240 + j * 200, y + 24]})
    return {"size": [1000, H], "lines": out}


def letter(number="123/BC-DONVI", extra=()):
    return ocr(HEADER + [f"Số: {number}", "DONVI, ngày 18 tháng 6 năm 2026", "BÁO CÁO", "Về việc thi đua", *extra])


def make_doc(*pages):
    items = [SimpleNamespace(uid=f"p{i}", blank=False, codes=[]) for i in range(len(pages))]
    data = {p.uid: o for p, o in zip(items, pages)}
    return SimpleNamespace(pages=items, ocr=data, groups=[],
                           page_text=lambda uid: "\n".join(ln["text"] for ln in data[uid]["lines"]))


def sizes(doc, **settings):
    groups = splitter.analyze(doc, {"keep_annex": True, "naming_rule": "{so}", **settings})
    return [len(g["uids"]) for g in groups]


LIST_PAGE = ocr(HEADER + ["DANH SÁCH", "Cán bộ đề nghị khen thưởng", "Nơi nhận"])
TABLE_PAGE = ocr(HEADER + [[f"{i}", "Nguyễn Văn A", "Thiếu tá", "HTTNV"] for i in range(1, 8)])
MENTION = ["(có Danh sách kèm theo)"]


class AttachmentMergeTests(unittest.TestCase):
    def test_detects_mention_phrases(self):
        for text in ("(có Danh sách kèm theo)", "có Phụ lục chi tiết kèm theo", "kèm theo Danh sách", "theo Bảng tổng hợp kèm theo"):
            self.assertTrue(splitter.mentions_attachment(ocr([text])), text)

    def test_ignores_unrelated_text(self):
        for text in ("Danh sách cán bộ tháng 9", "Kèm theo Quyết định này", "Báo cáo tình hình công tác"):
            self.assertFalse(splitter.mentions_attachment(ocr([text])), text)

    def test_list_after_mention_merges(self):
        self.assertEqual(sizes(make_doc(letter(extra=MENTION), LIST_PAGE)), [2])

    def test_table_after_mention_merges(self):
        self.assertEqual(sizes(make_doc(letter(extra=MENTION), TABLE_PAGE)), [2])

    def test_mention_on_later_page_counts(self):
        body = ocr(["tiếp tục nội dung báo cáo", "(có Danh sách kèm theo)"])
        self.assertEqual(sizes(make_doc(letter(), body, LIST_PAGE)), [3])

    def test_list_without_mention_stays_separate(self):
        self.assertEqual(sizes(make_doc(letter(), LIST_PAGE)), [1, 1])

    def test_document_with_own_number_stays_separate(self):
        self.assertEqual(sizes(make_doc(letter(extra=MENTION), letter("54/BC-CNTT"))), [1, 1])

    def test_mention_does_not_carry_past_next_document(self):
        doc = make_doc(letter(extra=MENTION), letter("54/BC-CNTT"), LIST_PAGE)
        self.assertEqual(sizes(doc), [1, 1, 1])

    def test_keep_annex_off_keeps_pages_separate(self):
        self.assertEqual(sizes(make_doc(letter(extra=MENTION), LIST_PAGE), keep_annex=False), [1, 1])

    def test_reason_is_shown_on_merged_page(self):
        doc = make_doc(letter(extra=MENTION), LIST_PAGE)
        sizes(doc)
        self.assertIn("Tài liệu kèm theo văn bản trước - gộp chung", doc.pages[1].split_score["reasons"])


if __name__ == "__main__":
    unittest.main()
