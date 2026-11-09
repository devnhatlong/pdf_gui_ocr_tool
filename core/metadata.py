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

# Bảng viết tắt mặc định - người dùng sửa / thêm / xóa trong Cài đặt (settings: doc_type_map, agency_map)
DEFAULT_TYPE_MAP = [
    {"ten": "Báo cáo đề xuất", "tat": "BCĐX"},
    {"ten": "Báo cáo", "tat": "BC"},
    {"ten": "Công văn", "tat": "CV"},
    {"ten": "Kế hoạch", "tat": "KH"},
    {"ten": "Kết luận", "tat": "KL"},
    {"ten": "Quyết định", "tat": "QĐ"},
    {"ten": "Nghị quyết", "tat": "NQ"},
    {"ten": "Tờ trình", "tat": "TTr"},
    {"ten": "Thông báo", "tat": "TB"},
    {"ten": "Phương án", "tat": "PA"},
    {"ten": "Chương trình", "tat": "CTr"},
    {"ten": "Giấy mời", "tat": "GM"},
    {"ten": "Danh sách", "tat": "DS"},
    {"ten": "Chỉ thị", "tat": "CT"},
    {"ten": "Hướng dẫn", "tat": "HD"},
]
DEFAULT_AGENCY_MAP = [
    {"ten": "Ủy ban nhân dân", "tat": "UBND"},
    {"ten": "Hội đồng nhân dân", "tat": "HĐND"},
    {"ten": "Công an tỉnh", "tat": "CAT"},
    {"ten": "Công an thành phố", "tat": "CATP"},
    {"ten": "Công an huyện", "tat": "CAH"},
    {"ten": "Công an xã", "tat": "CAX"},
    # Các phòng / đơn vị Công an tỉnh (số ký hiệu dùng mã này)
    {"ten": "Phòng Tham mưu", "tat": "PV01"},
    {"ten": "Phòng Hồ sơ", "tat": "PV06"},
    {"ten": "Phòng Tổ chức cán bộ", "tat": "PX01"},
    {"ten": "Phòng Công tác đảng và công tác chính trị", "tat": "PX03"},
    {"ten": "Thanh tra Công an tỉnh", "tat": "PX05"},
    {"ten": "Cơ quan Ủy ban kiểm tra Đảng ủy Công an tỉnh", "tat": "PX06"},
    {"ten": "Phòng Hậu cần", "tat": "PH10"},
    {"ten": "Phòng An ninh đối ngoại", "tat": "PA01"},
    {"ten": "Phòng An ninh đối nội", "tat": "PA02"},
    {"ten": "Phòng An ninh chính trị nội bộ", "tat": "PA03"},
    {"ten": "Phòng An ninh kinh tế", "tat": "PA04"},
    {"ten": "Phòng ANM & PCTP sử dụng CNC", "tat": "PA05"},
    {"ten": "Phòng Kỹ thuật nghiệp vụ", "tat": "PA06"},
    {"ten": "Phòng Quản lý xuất nhập cảnh", "tat": "PA08"},
    {"ten": "Phòng An ninh điều tra", "tat": "PA09"},
    {"ten": "Văn phòng cơ quan Cảnh sát điều tra", "tat": "PC01"},
    {"ten": "Phòng Cảnh sát điều tra tội phạm về trật tự xã hội", "tat": "PC02"},
    {"ten": "Phòng Cảnh sát điều tra tội phạm về tham nhũng, kinh tế, buôn lậu", "tat": "PC03"},
    {"ten": "Phòng Cảnh sát điều tra tội phạm về ma túy", "tat": "PC04"},
    {"ten": "Phòng Cảnh sát quản lý hành chính về trật tự xã hội", "tat": "PC06"},
    {"ten": "Phòng Cảnh sát phòng cháy, chữa cháy và cứu nạn, cứu hộ", "tat": "PC07"},
    {"ten": "Phòng Cảnh sát giao thông", "tat": "PC08"},
    {"ten": "Phòng Kỹ thuật hình sự", "tat": "PC09"},
    {"ten": "Phòng Cảnh sát thi hành án hình sự và hỗ trợ tư pháp", "tat": "PC10"},
    {"ten": "Trại Giam số 01", "tat": "TTG01"},
    {"ten": "Trại Giam số 02", "tat": "TTG02"},
    {"ten": "Trại Giam số 03", "tat": "TTG03"},
    {"ten": "Phòng Cảnh sát cơ động/Cảnh sát bảo vệ", "tat": "PK02"},
    # Các đội / đơn vị thuộc Phòng Tham mưu
    {"ten": "Đội Tham mưu Tổng hợp", "tat": "TMTH"},
    {"ten": "Đội Tham mưu An ninh", "tat": "TMAN"},
    {"ten": "Đội Tham mưu Cảnh sát", "tat": "TMCS"},
    {"ten": "Đội Công nghệ thông tin", "tat": "CNTT"},
    {"ten": "Đội CNTT", "tat": "CNTT"},
    {"ten": "Đội Viễn thông Cơ yếu", "tat": "VTCY"},
    {"ten": "Đội Pháp chế và Quản lý khoa học", "tat": "PC"},
    {"ten": "Trung tâm thông tin chỉ huy", "tat": "TTTTCH"},
    {"ten": "Xây dựng phong trào", "tat": "PT"},
    {"ten": "Đảng ủy", "tat": "ĐU"},
    {"ten": "Sở", "tat": "SỞ"},
    {"ten": "Bộ", "tat": "BỘ"},
]
_extractor = _Extractor()
remove_accents = _extractor.remove_accents


def _as_pairs(mapping, default):
    """Chuẩn hóa bảng viết tắt về [(tên, viết_tắt)]. mapping None -> dùng mặc định; rỗng -> rỗng (tôn trọng người dùng)."""
    if mapping is None:
        mapping = default
    pairs = []
    for item in mapping:
        if isinstance(item, dict):
            ten, tat = item.get("ten", ""), item.get("tat", "")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            ten, tat = item
        else:
            continue
        ten, tat = str(ten).strip(), str(tat).strip()
        if ten and tat:
            pairs.append((ten, tat))
    return pairs


def _match_type_code(code, pairs):
    """Đổi mã loại về chữ viết tắt chuẩn trong bảng (QD -> QĐ); mã lạ giữ nguyên (BCĐX)."""
    for _ten, tat in pairs:
        if remove_accents(tat).upper() == remove_accents(code).upper():
            return tat
    return code.upper()


def resolve_type(text, so_ky_hieu, type_map=None):
    """Loại văn bản: ưu tiên mã chữ ngay sau dấu / của số ký hiệu (1794/QĐ-XPHC -> QĐ).
    Số dạng số/ĐƠNVỊ (1831/PV01-CNTT, mã đơn vị có số) là công văn -> CV.
    Không có / thì tra theo chữ tiêu đề OCR (DANH SÁCH, BÁO CÁO...). Mã lạ vẫn giữ (496/BCĐX -> BCĐX)."""
    pairs = _as_pairs(type_map, DEFAULT_TYPE_MAP)
    m = re.search(r"/\s*([A-Za-z0-9Đđ]+)", so_ky_hieu or "")
    if m:
        first = m.group(1)
        if re.fullmatch(r"\d{4}", first):   # 45/2026/NĐ-CP: bỏ năm, lấy mã sau dấu / kế tiếp
            m2 = re.search(r"/\s*\d{4}\s*/\s*([A-Za-zĐđ]+)", so_ky_hieu)
            first = m2.group(1) if m2 else first
        if re.search(r"[A-Za-zĐđ]", first) and not re.search(r"\d", first):
            return _match_type_code(first, pairs)
        # mã sau / có chữ số (PV01...) = mã đơn vị, số không ghi loại -> công văn
        for ten, tat in pairs:
            if remove_accents(ten).strip() == "cong van":
                return tat
        return "CV"
    lines = [ln for ln in (remove_accents(x).strip() for x in text.splitlines()[:12]) if ln]
    best = None
    for ten, tat in pairs:
        key = remove_accents(ten).strip()
        if key and any(ln == key or ln.startswith(key + " ") for ln in lines):
            if best is None or len(key) > best[0]:
                best = (len(key), tat)
    return best[1] if best else ""


# Dòng tiêu đề văn bản (không dấu): gặp thì dừng gom cơ quan (dùng khi trang không có dòng "Số:")
_HEADING_STOPS = ("bao cao", "cong van", "ke hoach", "ket luan", "quyet dinh", "nghi quyet",
                  "to trinh", "thong bao", "phuong an", "chuong trinh", "giay moi", "danh sach",
                  "chi thi", "huong dan", "bien ban", "phu luc", "kinh gui", "bang ", "bieu ")


def detect_agency(text, agency_map=None):
    """Cơ quan ban hành = dòng viết hoa ngay trên 'Số:' (1 dòng thì lấy chính dòng đó).
    Trả về (tên đầy đủ, viết tắt theo bảng cấu hình)."""
    pairs = _as_pairs(agency_map, DEFAULT_AGENCY_MAP)
    header = []
    for raw in text.splitlines()[:8]:
        line = raw.split("   ")[0].strip()          # cột trái của hàng (quốc hiệu nằm cột phải)
        plain = remove_accents(line)
        if not line:
            continue
        if re.search(r"\bs[o0]\s*[:.]", plain) or re.search(r"\d\s*/\s*[a-zđ]", plain):   # tới dòng "Số: 123/..." thì dừng ("Trại giam số 02" không tính)
            break
        if plain.startswith(_HEADING_STOPS):   # tới tiêu đề (DANH SÁCH, BÁO CÁO...) thì dừng
            break
        if "cong hoa" in plain or "doc lap" in plain or "hanh phuc" in plain:
            continue
        letters = [c for c in line if c.isalpha()]
        if len(letters) < 3 or not all(c.isupper() for c in letters):
            continue
        header.append(line)
    if not header:
        return "", ""
    name = header[-1]
    return name, _abbr_for_agency(name, pairs)


def _abbr_for_agency(name, pairs):
    plain = remove_accents(name).strip()
    best = None
    for ten, tat in pairs:
        key = remove_accents(ten).strip()
        if key and (plain == key or re.search(r"\b" + re.escape(key) + r"\b", plain)):
            if best is None or len(key) > best[0]:
                best = (len(key), tat)
    if best:
        return best[1]
    words = [w for w in re.split(r"\s+", name) if w]
    return "".join(w[0] for w in words[:4]).upper()


def extract_metadata(text, type_map=None, agency_map=None):
    """Thông tin văn bản từ văn bản OCR (theo thứ tự đọc). type_map / agency_map: bảng viết tắt từ Cài đặt."""
    meta = _extractor.extract_metadata_from_ocr(text)
    loai = resolve_type(text, meta["so_ky_hieu"], type_map)
    if loai:
        meta["loai_van_ban"] = loai
    meta["co_quan"], meta["co_quan_viet_tat"] = detect_agency(text, agency_map)
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
    slash: chuỗi người dùng chọn thay cho dấu / (không dùng được trong tên file): 123/BC-CAT -> 123-BC-CAT.
    ascii_name: tên file không dấu, trích yếu viết liền (VeViecBoNhiem)."""
    so_raw = (fields.get("so") or "").strip()
    so_match = re.match(r"\s*(\d+[A-Za-zĐđ]?)", so_raw)   # {so} chỉ lấy số thứ tự trước dấu / (1794/QĐ-XPHC -> 1794)
    values = {
        "loai": (fields.get("loai") or "").strip(),
        "coquan": (fields.get("coquan") or "").strip(),
        "so": so_match.group(1) if so_match else so_raw,
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
