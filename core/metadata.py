# === metadata.py ===
# Trích xuất thông tin văn bản hành chính từ kết quả OCR: số ký hiệu, ngày ban hành, trích yếu,
# loại văn bản, cơ quan ban hành; và tạo tên file theo quy tắc đặt tên.

import re
import unicodedata


AUTHORITY_TITLES = ("giam doc", "tong giam doc", "pho giam doc", "chu tich", "pho chu tich", "uy ban nhan dan",
                    "hoi dong nhan dan", "bo truong", "thu truong", "cuc truong", "hieu truong", "truong phong",
                    "truong ban", "bi thu")


class _Extractor:
    def strip_marks(self, s):
        """Bỏ dấu thanh, dấu mũ và viết thường; giữ chữ đ (Unicode không tách được dấu của đ)."""
        s = unicodedata.normalize("NFKD", s)
        return "".join(c for c in s if not unicodedata.combining(c)).lower()

    def remove_accents(self, s):
        return self.strip_marks(s).replace("đ", "d")

    @staticmethod
    def starts_new_sentence(line):
        """Dòng bắt đầu bằng chữ hoa nhưng không viết hoa toàn bộ -> câu mới của phần nội dung.
        (Trích yếu nhiều dòng thì dòng sau viết thường, hoặc viết hoa toàn bộ nếu là tiêu đề.)"""
        letters = [c for c in line if c.isalpha()]
        return bool(letters) and letters[0].isupper() and not all(c.isupper() for c in letters)

    def ends_summary(self, line, summary_lines):
        """Dòng này không còn thuộc trích yếu: câu mới, hoặc dòng thẩm quyền ban hành viết hoa
        (VD: "GIÁM ĐỐC CÔNG AN TỈNH") nằm ngay dưới trích yếu của quyết định."""
        if self.starts_new_sentence(line):
            return True
        letters = [c for c in line if c.isalpha()]
        if not letters or not all(c.isupper() for c in letters):
            return False
        summary_letters = [c for c in "".join(summary_lines) if c.isalpha()]
        if not all(c.isupper() for c in summary_letters):
            return True
        return self.remove_accents(line).startswith(AUTHORITY_TITLES)

    def extract_metadata_from_ocr(self, text):
        result = {"so_ky_hieu": "", "ngay_ban_hanh": "", "trich_yeu": "", "loai_van_ban": ""}
        if not text:
            return result
        
        # Mapping từ khóa tiêu đề sang loại văn bản
        keyword_to_loai = {
            "báo cáo": "BC",
            "công văn": "CV",
            "kế hoạch": "KH",
            "kết luận": "KL",
            "quyết định": "QĐ",
            "nghị quyết": "NQ",
            "tờ trình": "TTr",
            "thông báo": "TB",
            "phương án": "PA",
            "chương trình": "CTr",
            "giấy mời": "GM",
            "danh sách": "DS"
        }

        lines = text.splitlines()[:20]  # Tăng lên 20 dòng để lấy được trích yếu
        original_lines = lines  # Giữ nguyên để lấy text gốc (có dấu)
        t = self.remove_accents(" ".join(lines))
        t = re.sub(r"\s+", " ", t)

        # === SỐ KÝ HIỆU === (giữ chữ Đ: QĐ, NĐ-CP...)
        t_so = re.sub(r"\s+", " ", self.strip_marks(" ".join(lines)))
        for p in [
            r"\bso[:\-\s]+([a-z0-9đ\/\-\.]+)",
            r"\bs0[:\-\s]+([a-z0-9đ\/\-\.]+)",
        ]:
            m = re.search(p, t_so)
            if m:
                result["so_ky_hieu"] = m.group(1).upper()
                break

        # === NGÀY BAN HÀNH ===
        m = re.search(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})", t)
        if m:
            d, mth, y = m.groups()
            result["ngay_ban_hanh"] = f"{d.zfill(2)}/{mth.zfill(2)}/{y}"
        else:
            m = re.search(r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b", t)
            if m:
                d, mth, y = m.groups()
                result["ngay_ban_hanh"] = f"{d.zfill(2)}/{mth.zfill(2)}/{y}"

        # === TRÍCH YẾU ===
        # Tìm pattern "V/v" hoặc "Về việc" trong text gốc (có dấu)
        original_text = "\n".join(original_lines)
        
        # Danh sách từ khóa cần loại bỏ khỏi trích yếu (tiêu đề, đầu thư, v.v.)
        exclude_keywords = ["kính gửi", "giấy mời", "kế hoạch", "thông báo", "quyết định", "báo cáo", "nghị quyết"]

        # Tìm dòng chứa "V/v" hoặc "Về việc"
        vv_line_idx = None
        vv_prefix = ""
        for idx, line in enumerate(original_lines):
            line_clean = line.strip()
            if re.search(r"^[\s]*(V/v|Về việc)[\s:]", line_clean, re.IGNORECASE):
                vv_line_idx = idx
                # Tìm prefix "V/v" hoặc "Về việc"
                match = re.search(r"^[\s]*((?:V/v|Về việc)[\s:]*)", line_clean, re.IGNORECASE)
                if match:
                    vv_prefix = match.group(1).strip()
                break
        
        if vv_line_idx is not None:
            # Lấy các dòng liên tiếp sau "V/v" cho đến khi gặp dòng dừng
            trich_yeu_lines = []
            # Chỉ dừng khi gặp các từ khóa này ở đầu dòng (tiêu đề riêng, không phải trong nội dung V/v)
            # Đặc biệt chú ý "kính gửi" - luôn dừng trước đó
            stop_keywords = ["kính gửi", "giấy mời", "kế hoạch", "quyết định", "báo cáo", "nghị quyết", "cơ quan"]
            stop_keywords_no_accents = [self.remove_accents(kw) for kw in stop_keywords]
            
            for i in range(vv_line_idx, min(vv_line_idx + 5, len(original_lines))):  # Tối đa 5 dòng
                line = original_lines[i].strip()
                if not line:
                    continue
                
                # Bỏ dấu để so sánh (xử lý lỗi OCR)
                line_no_accents = self.remove_accents(line)
                
                # Kiểm tra xem có phải dòng dừng không - chỉ kiểm tra các từ khóa ở ĐẦU dòng
                # Đây là các tiêu đề riêng biệt, không phải nội dung trong V/v
                is_stop_line = False
                for kw_no_accents in stop_keywords_no_accents:
                    # Kiểm tra nếu dòng bắt đầu bằng từ khóa (có thể có khoảng trắng đầu)
                    if re.match(r"^[\s]*" + re.escape(kw_no_accents), line_no_accents):
                        is_stop_line = True
                        break
                
                if is_stop_line:
                    # Gặp dòng dừng (như "Kính gửi"), break ngay lập tức
                    break
                
                # Kiểm tra xem có phải là số hoặc ngày không (thường là thông tin khác, dừng lại)
                if re.match(r"^[\s]*(?:so|ngay)[\s:]", line_no_accents):
                    break

                # Dòng tiếp theo bắt đầu một câu mới (viết hoa chữ đầu) là phần nội dung, không phải trích yếu
                if trich_yeu_lines and self.ends_summary(line, trich_yeu_lines):
                    break

                # Lấy dòng này vào trích yếu (bao gồm cả dòng V/v và các dòng tiếp theo)
                trich_yeu_lines.append(line)
            
            if trich_yeu_lines:
                trich_yeu = " ".join(trich_yeu_lines)
                # Loại bỏ khoảng trắng thừa
                trich_yeu = re.sub(r"\s+", " ", trich_yeu).strip()
                # Giới hạn độ dài (tối đa 250 ký tự)
                if len(trich_yeu) > 250:
                    trich_yeu = trich_yeu[:247] + "..."
                if trich_yeu and len(trich_yeu) >= 5:
                    result["trich_yeu"] = trich_yeu

            # Có "V/v": loại văn bản lấy từ dòng tiêu đề đứng riêng (VD: "BÁO CÁO", "KẾ HOẠCH")
            for line in original_lines[:vv_line_idx]:
                title = re.sub(r"[^a-z ]", "", self.remove_accents(line)).strip()
                for kw, loai in keyword_to_loai.items():
                    if title == self.remove_accents(kw):
                        result["loai_van_ban"] = loai
                        break

        # Nếu không tìm thấy "V/v", tìm các từ khóa tiêu đề (thường viết hoa và in đậm)
        if not result["trich_yeu"]:
            # Danh sách từ khóa tiêu đề (so sánh không dấu để xử lý lỗi OCR)
            title_keywords_original = [
                "kính gửi", "giấy mời", "kế hoạch", "thông báo", "quyết định", 
                "báo cáo", "nghị quyết", "phương án", "công văn", "kết luận", 
                "tờ trình", "chương trình", "danh sách"
            ]
            # Tạo danh sách từ khóa không dấu để so sánh
            title_keywords_no_accents = [self.remove_accents(kw) for kw in title_keywords_original]
            
            # Tìm dòng chứa từ khóa tiêu đề (có thể viết hoa hoàn toàn hoặc viết hoa chữ cái đầu)
            title_line_idx = None
            matched_keyword_idx = None  # Lưu index của từ khóa đã match
            for idx, line in enumerate(original_lines):
                line_clean = line.strip()
                if not line_clean:
                    continue
                
                # Bỏ dấu của dòng để so sánh (xử lý lỗi OCR)
                line_no_accents = self.remove_accents(line_clean)
                
                # Kiểm tra xem dòng này có bắt đầu bằng một trong các từ khóa tiêu đề không
                for kw_idx, kw_no_accents in enumerate(title_keywords_no_accents):
                    # Kiểm tra nếu dòng bắt đầu bằng từ khóa (có thể có khoảng trắng đầu)
                    kw_pattern = r"^[\s]*" + re.escape(kw_no_accents) + r"[\s:]+(.+)"
                    match_kw = re.match(kw_pattern, line_no_accents)
                    if match_kw:
                        # Trường hợp: từ khóa + nội dung (ví dụ: "THÔNG BÁO: về việc...")
                        # Tìm vị trí từ khóa trong dòng gốc để lấy phần sau
                        kw_original = title_keywords_original[kw_idx]
                        # Thử match với từ khóa gốc trước (có dấu đúng)
                        match_original = re.search(r"^[\s]*" + re.escape(kw_original) + r"[\s:]+(.+)", line_clean, re.IGNORECASE)
                        if match_original:
                            result["trich_yeu"] = match_original.group(1).strip()
                        else:
                            # Nếu không match (do OCR sai dấu), tìm vị trí bằng cách so sánh không dấu
                            # Tìm vị trí từ khóa trong dòng gốc bằng cách so sánh từng đoạn không dấu
                            line_no_accents_lower = line_no_accents.lower()
                            kw_start_pos = line_no_accents_lower.find(kw_no_accents)
                            if kw_start_pos >= 0:
                                # Tìm vị trí tương ứng trong dòng gốc
                                # Đếm số ký tự không dấu từ đầu đến vị trí từ khóa
                                char_count = 0
                                original_pos = 0
                                for i, char in enumerate(line_clean):
                                    if char_count >= kw_start_pos:
                                        original_pos = i
                                        break
                                    # Đếm ký tự (không tính dấu kết hợp)
                                    if not unicodedata.combining(char):
                                        char_count += 1
                                
                                # Tìm vị trí kết thúc từ khóa (sau dấu cách hoặc dấu :)
                                content_start = original_pos + len(kw_original)  # Ước lượng
                                # Tìm chính xác hơn bằng cách tìm dấu cách/dấu : sau từ khóa
                                for i in range(original_pos, min(original_pos + len(kw_original) + 5, len(line_clean))):
                                    if line_clean[i] in [':', ' ', '\t']:
                                        # Tìm vị trí bắt đầu nội dung (sau các dấu cách/dấu :)
                                        content_start = i + 1
                                        while content_start < len(line_clean) and line_clean[content_start] in [' ', ':', '\t']:
                                            content_start += 1
                                        break
                                
                                if content_start < len(line_clean):
                                    result["trich_yeu"] = line_clean[content_start:].strip()
                                else:
                                    # Fallback: lấy phần sau từ khóa từ dòng không dấu
                                    result["trich_yeu"] = match_kw.group(1).strip()
                            else:
                                # Fallback: lấy phần sau từ khóa từ dòng không dấu
                                result["trich_yeu"] = match_kw.group(1).strip()
                        if result["trich_yeu"]:
                            # Tìm loại văn bản từ mapping
                            kw_original = title_keywords_original[kw_idx]
                            # "Quyết định bổ nhiệm..." là tên văn bản: giữ nguyên cả dòng.
                            # "THÔNG BÁO: ...", "Thông báo về việc ...": chỉ lấy phần nội dung.
                            rest = self.remove_accents(result["trich_yeu"])
                            if (kw_original != "kính gửi" and not rest.startswith(("ve viec", "v/v"))
                                    and not re.match(re.escape(kw_no_accents) + r"\s*:", line_no_accents.strip())):
                                result["trich_yeu"] = line_clean
                            if kw_original in keyword_to_loai:
                                result["loai_van_ban"] = keyword_to_loai[kw_original]
                            return result
                    
                    # Kiểm tra nếu dòng chỉ chứa từ khóa (tiêu đề riêng, không có nội dung sau)
                    match_title_only = re.match(r"^[\s]*" + re.escape(kw_no_accents) + r"[\s:]*$", line_no_accents)
                    if match_title_only:
                        # Trường hợp: chỉ có từ khóa (ví dụ: "DANH SACH")
                        # Đánh dấu dòng này là tiêu đề, sẽ lấy các dòng sau làm trích yếu
                        title_line_idx = idx
                        matched_keyword_idx = kw_idx
                        break
                
                if title_line_idx is not None:
                    break
            
            # Nếu tìm thấy từ khóa tiêu đề, set loại văn bản
            if matched_keyword_idx is not None:
                kw_original = title_keywords_original[matched_keyword_idx]
                if kw_original in keyword_to_loai:
                    result["loai_van_ban"] = keyword_to_loai[kw_original]
            
            # Nếu tìm thấy dòng tiêu đề, lấy các dòng sau nó làm trích yếu
            if title_line_idx is not None:
                trich_yeu_lines = []
                stop_keywords = ["kính gửi", "cơ quan", "số", "ngày"]
                stop_keywords_no_accents = [self.remove_accents(kw) for kw in stop_keywords]
                
                # Lấy các dòng sau tiêu đề (bắt đầu từ dòng tiếp theo)
                for i in range(title_line_idx + 1, min(title_line_idx + 5, len(original_lines))):
                    line = original_lines[i].strip()
                    if not line:
                        continue
                    
                    # Bỏ dấu để so sánh (xử lý lỗi OCR)
                    line_no_accents = self.remove_accents(line)
                    
                    # Kiểm tra xem có phải dòng dừng không
                    is_stop_line = False
                    for kw_no_accents in stop_keywords_no_accents:
                        if re.match(r"^[\s]*" + re.escape(kw_no_accents), line_no_accents):
                            is_stop_line = True
                            break
                    
                    if is_stop_line:
                        break
                    
                    # Kiểm tra xem có phải là số hoặc ngày không (so sánh không dấu)
                    if re.match(r"^[\s]*(?:so|ngay)[\s:]", line_no_accents):
                        break

                    if trich_yeu_lines and self.ends_summary(line, trich_yeu_lines):
                        break

                    # Lấy dòng này vào trích yếu
                    trich_yeu_lines.append(line)
                
                if trich_yeu_lines:
                    trich_yeu = " ".join(trich_yeu_lines)
                    # Loại bỏ khoảng trắng thừa
                    trich_yeu = re.sub(r"\s+", " ", trich_yeu).strip()
                    # Giới hạn độ dài (tối đa 250 ký tự)
                    if len(trich_yeu) > 250:
                        trich_yeu = trich_yeu[:247] + "..."
                    if trich_yeu and len(trich_yeu) >= 5:
                        result["trich_yeu"] = trich_yeu

        return result


DOC_TYPES = [
    ("BC", "Báo cáo"), ("CV", "Công văn"), ("KH", "Kế hoạch"), ("KL", "Kết luận"),
    ("QĐ", "Quyết định"), ("NQ", "Nghị quyết"), ("TTr", "Tờ trình"), ("TB", "Thông báo"),
    ("PA", "Phương án"), ("CTr", "Chương trình"), ("GM", "Giấy mời"), ("DS", "Danh sách"),
]
_TYPE_CODES = {code.upper(): code for code, _ in DOC_TYPES} | {"QD": "QĐ"}

# Tên cơ quan (không dấu, viết thường) -> viết tắt dùng trong tên file
_AGENCY_ABBR = [
    (r"^(uy ban nhan dan|ubnd)\b", "UBND"),
    (r"^cong an (tinh|thanh pho)\b", "CAT"),
    (r"^cong an (huyen|quan|thi xa)\b", "CAH"),
    (r"^cong an (xa|phuong|thi tran)\b", "CAX"),
    (r"^(hoi dong nhan dan|hdnd)\b", "HĐND"),
    (r"^(dang uy|dang bo|tinh uy|huyen uy|thanh uy)\b", "ĐU"),
    (r"^so\s", "SỞ"),
    (r"^bo\s", "BỘ"),
]
_extractor = _Extractor()
remove_accents = _extractor.remove_accents


def detect_agency(text):
    """Cơ quan ban hành: dòng viết hoa đầu tiên ở góc trên (bỏ quốc hiệu). Trả về (tên đầy đủ, viết tắt)."""
    for raw in text.splitlines()[:6]:
        line = raw.split("   ")[0].strip()          # cột trái của hàng (quốc hiệu nằm cột phải)
        plain = remove_accents(line)
        if not line or "cong hoa" in plain or "doc lap" in plain or plain.startswith(("so", "s0")) and ":" in line:
            continue
        letters = [c for c in line if c.isalpha()]
        if len(letters) < 4 or not all(c.isupper() for c in letters):
            continue
        for pattern, abbr in _AGENCY_ABBR:
            if re.search(pattern, plain):
                return line, abbr
        words = [w for w in re.split(r"\s+", line) if w]
        return line, "".join(w[0] for w in words[:4]).upper()
    return "", ""


def extract_metadata(text):
    """Thông tin văn bản từ văn bản OCR (theo thứ tự đọc)."""
    meta = _extractor.extract_metadata_from_ocr(text)
    if not meta["loai_van_ban"] and meta["so_ky_hieu"]:
        # Số ký hiệu dạng 45/CV-UBND -> loại văn bản CV
        m = re.search(r"/([A-ZĐ]+[a-z]*)-", meta["so_ky_hieu"])
        if m and m.group(1).upper() in _TYPE_CODES:
            meta["loai_van_ban"] = _TYPE_CODES[m.group(1).upper()]
    meta["co_quan"], meta["co_quan_viet_tat"] = detect_agency(text)
    return meta


def _summary_part(trich_yeu):
    """Trích yếu: giữ dấu và khoảng trắng, viết hoa chữ đầu (dòng viết hoa toàn bộ đưa về chữ thường trước)."""
    text = unicodedata.normalize("NFC", trich_yeu)
    if text.isupper():
        text = text.lower()
    text = re.sub(r"^v\s*/\s*v\b[.:]?\s*", "Về việc ", text, flags=re.I)
    return text[:1].upper() + text[1:]


def to_ascii(text):
    """Bỏ dấu tiếng Việt, giữ chữ hoa / thường: Quyết Định -> Quyet Dinh."""
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in text if not unicodedata.combining(c))


def _joined(text):
    """Viết liền, hoa chữ đầu mỗi từ: Về việc bổ nhiệm -> VeViecBoNhiem (giữ dấu / để thay sau)."""
    return "".join(w[:1].upper() + w[1:] for w in re.findall(r"[A-Za-z0-9/\-]+", text))


def build_filename(fields, rule="{so}_{ngay}_{trichyeu}", ext=".pdf", slash="-", ascii_name=False):
    """fields: loai, coquan, so, ngay (dd/mm/yyyy), trichyeu. Phần rỗng được bỏ cùng dấu nối.
    slash: chuỗi người dùng chọn thay cho dấu / (không dùng được trong tên file): 56/BC-CAT -> 56-BC-CAT.
    ascii_name: tên file không dấu, trích yếu viết liền (VeViecBoNhiem)."""
    values = {
        "loai": (fields.get("loai") or "").strip(),
        "coquan": (fields.get("coquan") or "").strip(),
        "so": (fields.get("so") or "").strip(),
        "ngay": (fields.get("ngay") or "").strip(),
        "trichyeu": _summary_part(re.sub(r"\s+", " ", fields.get("trichyeu") or "").strip()),
    }
    if ascii_name:
        values = {k: to_ascii(v) for k, v in values.items()}
        values["trichyeu"] = _joined(values["trichyeu"])
        rule = to_ascii(rule)
    # Giữ chỗ bằng \0 để bước gộp dấu nối bên dưới không làm đổi chuỗi người dùng chọn (VD: "--")
    values = {k: re.sub(r'[\\:*?"<>|\r\n\t]', "", v.replace("/", "\0")) for k, v in values.items()}
    name = rule
    for key, value in values.items():
        name = name.replace("{" + key + "}", value)
    name = re.sub(r"[_\-\s]{2,}", lambda m: m.group(0)[0], name).strip("_- ")
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", name)
    name = name.replace("\0", re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", slash))
    return (name[:180] + ext) if name else ""


def meta_to_fields(meta):
    return {"loai": meta.get("loai_van_ban", ""), "coquan": meta.get("co_quan_viet_tat", ""),
            "so": meta.get("so_ky_hieu", ""), "ngay": meta.get("ngay_ban_hanh", ""),
            "trichyeu": meta.get("trich_yeu", "")}
