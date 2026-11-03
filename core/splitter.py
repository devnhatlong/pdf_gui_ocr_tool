# === splitter.py ===
# AI tách văn bản: phân tích một tập PDF scan chứa nhiều văn bản hành chính, chấm điểm từng trang
# xem có phải trang bắt đầu văn bản mới không, nhóm các trang và đặt tên theo thông tin OCR.
#
# Dấu hiệu trang đầu: quốc hiệu, "Số: .../...", ngày tháng, tiêu đề loại văn bản, tên cơ quan.
# Dấu hiệu kết thúc ở trang trước: "Nơi nhận", khối chữ ký, trang trắng, mã QR/barcode phân cách.
# Dấu hiệu trang tiếp nối: số trang (- 2 -), phụ lục, dòng đầu viết thường.

import math
import re

from core import metadata

TITLE_WORDS = ["bao cao", "cong van", "ke hoach", "ket luan", "quyet dinh", "nghi quyet", "to trinh",
               "thong bao", "phuong an", "chuong trinh", "giay moi", "danh sach", "bien ban", "huong dan",
               "chi thi", "quy dinh", "quy che", "giay de nghi", "don", "hop dong", "giay xac nhan"]
SIGN_WORDS = ["tm.", "kt.", "tl.", "giam doc", "chu tich", "truong phong", "thu truong", "pho truong",
              "nguoi ky", "truong ban", "bi thu", "chi huy truong", "nguoi lap"]


def _plain(s):
    return metadata.remove_accents(s).lower()


def _region(ocr, top=None, bottom=None):
    """Các dòng trong vùng theo tỉ lệ chiều cao trang (0..1)."""
    h = (ocr.get("size") or [0, 0])[1] or 1
    out = []
    for ln in ocr.get("lines", []):
        y = (ln["box"][1] + ln["box"][3]) / 2 / h
        if (top is None or y <= top) and (bottom is None or y >= bottom):
            out.append(ln["text"])
    return out


def score_page(ocr, prev_ocr, page, prev_page, settings):
    """Điểm khả năng trang là trang đầu văn bản mới + lý do."""
    score, reasons = 0.0, []
    if not ocr:
        return 0.0, ["Chưa có OCR"]
    top_lines = _region(ocr, top=0.42)
    top = _plain(" ".join(top_lines))
    first = _plain(" ".join(_region(ocr, top=0.10)))
    all_lines = [ln["text"] for ln in ocr.get("lines", [])]

    def add(points, why):
        nonlocal score
        score += points
        reasons.append(why)

    if "cong hoa xa hoi chu nghia" in top:
        add(3.0, "Có quốc hiệu")
    if "doc lap" in top and "hanh phuc" in top:
        add(1.0, "Có tiêu ngữ")
    if re.search(r"\bs[o0]\s*[:.]\s*[\w.\-]*\d+\s*/", top):
        add(2.0, "Có số/ký hiệu")
    if re.search(r"ngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4}", top):
        add(1.0, "Có ngày ban hành")
    for line in top_lines:
        t = re.sub(r"[^a-z ]", "", _plain(line)).strip()
        if any(t == w or t.startswith(w + " ") and len(t) <= len(w) + 25 for w in TITLE_WORDS):
            if any(c.isalpha() and c.isupper() for c in line[:3]):
                add(2.0, f"Tiêu đề \"{line.strip()[:30]}\"")
                break
    agency, _abbr = metadata.detect_agency("\n".join(top_lines[:4]))
    if agency:
        add(1.0, "Có tên cơ quan ban hành")
    if "kinh gui" in top:
        add(0.5, "Có \"Kính gửi\"")

    if re.search(r"\bphu luc\b", first) or (top_lines and _plain(top_lines[0]).startswith("phu luc")):
        if settings.get("keep_annex", True):
            add(-4.0, "Phụ lục - gộp với văn bản trước")
        else:
            add(3.0, "Phụ lục")
    edge = _region(ocr, top=0.07) + _region(ocr, bottom=0.93)
    for t in edge:
        m = re.fullmatch(r"[\s\-–-]*(\d{1,3})[\s\-–-]*", t)
        if m and int(m.group(1)) >= 2:
            add(-2.5, f"Có số trang {m.group(1)}")
            break
    if all_lines:
        letters = [c for c in all_lines[0] if c.isalpha()]
        if letters and letters[0].islower():
            add(-1.5, "Dòng đầu viết thường (tiếp nối)")

    if prev_ocr:
        prev_bottom = _plain(" ".join(_region(prev_ocr, bottom=0.45)))
        if "noi nhan" in prev_bottom:
            add(1.5, "Trang trước có \"Nơi nhận\"")
        if any(w in prev_bottom for w in SIGN_WORDS):
            add(0.8, "Trang trước có khối chữ ký")
    if prev_page is not None:
        if prev_page.blank:
            add(3.0 if settings.get("blank_as_separator") else 1.5, "Sau trang trắng")
        if prev_page.codes:
            add(4.0, "Sau trang mã QR/barcode phân cách")
    return score, reasons


def probability(score):
    return 1 / (1 + math.exp(-(score - 2.5) * 1.2))


def analyze(doc, settings):
    """Đề xuất điểm tách. Kết quả lưu vào doc.groups và trả về danh sách nhóm."""
    pages = doc.pages
    starts = {}
    prev_content = None
    for i, p in enumerate(pages):
        if p.blank or p.codes:
            continue
        ocr = doc.ocr.get(p.uid)
        prev_ocr = doc.ocr.get(prev_content.uid) if prev_content else None
        prev_page = pages[i - 1] if i > 0 else None
        sc, reasons = score_page(ocr, prev_ocr, p, prev_page, settings)
        prob = probability(sc)
        if prev_content is None:
            starts[p.uid] = {"prob": max(prob, 0.5), "reasons": reasons or ["Trang đầu tập"]}
        elif prob >= 0.5:
            starts[p.uid] = {"prob": prob, "reasons": reasons}
        p.split_score = {"prob": prob, "reasons": reasons}
        prev_content = p
    doc.groups = build_groups(doc, starts, settings)
    return doc.groups


def build_groups(doc, starts, settings, names=None):
    """starts: uid trang bắt đầu -> {prob, reasons}. Trang trắng / trang phân cách bị bỏ nếu cài đặt."""
    names = names or {}
    groups, cur = [], None
    drop_blank = settings.get("remove_blank_pages", True)
    for p in doc.pages:
        separator = bool(p.codes)
        if (p.blank and drop_blank) or separator:
            continue
        if p.uid in starts or cur is None:
            info = starts.get(p.uid, {"prob": 0.5, "reasons": ["Bắt đầu thủ công"]})
            cur = {"start_uid": p.uid, "uids": [], "confidence": round(info["prob"] * 100),
                   "reasons": info["reasons"]}
            groups.append(cur)
        cur["uids"].append(p.uid)
    rule = settings.get("naming_rule")
    for i, g in enumerate(groups):
        text = doc.page_text(g["uids"][0])
        meta = metadata.extract_metadata(text)
        g["meta"] = meta
        auto = metadata.build_filename(metadata.meta_to_fields(meta), rule, ext="")
        g["auto_name"] = auto or f"Van_ban_{i + 1:02d}"
        g["name"] = names.get(g["start_uid"]) or g["auto_name"]
        g["type"] = meta.get("loai_van_ban") or "Khác"
        g["agency"] = meta.get("co_quan_viet_tat") or "Khác"
        g["title"] = meta.get("trich_yeu") or ""
        g["low"] = g["confidence"] < settings.get("split_threshold", 70)
    return groups


def set_boundaries(doc, start_uids, settings, names=None):
    """Áp dụng điểm tách do người dùng chỉnh (giữ độ tin cậy AI cho các điểm còn lại)."""
    old = {g["start_uid"]: g for g in doc.groups}
    starts = {}
    for uid in start_uids:
        if uid in old:
            starts[uid] = {"prob": old[uid]["confidence"] / 100, "reasons": old[uid]["reasons"]}
        else:
            starts[uid] = {"prob": 1.0, "reasons": ["Điểm tách thủ công"]}
    doc.groups = build_groups(doc, starts, settings, names)
    return doc.groups
