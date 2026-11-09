# === settings.py ===
# Cấu hình người dùng (lưu JSON trong data/settings.json), có sao lưu / khôi phục.

import json
import os
import threading

import config
from core import metadata

DEFAULTS = {
    "output_dir": config.DEFAULT_OUTPUT_DIR,
    "export_format": "pdf",            # pdf | searchable_pdf | docx | xlsx | txt
    "keep_original": True,
    "folder_by_date": True,
    "naming_rule": "{coquan}_{loai}_{so}_{ngay}_{trichyeu}",
    "slash_replacement": "-",          # chuỗi thay cho dấu / trong tên file
    "filename_ascii": True,            # tên file không dấu, trích yếu viết liền (VeViecBoNhiem)
    "doc_type_map": list(metadata.DEFAULT_TYPE_MAP),     # bảng viết tắt loại văn bản (sửa trong Cài đặt)
    "agency_map": list(metadata.DEFAULT_AGENCY_MAP),     # bảng viết tắt cơ quan ban hành
    "overwrite": False,                # False: tự thêm (1), (2)... khi trùng tên
    "dpi": 200,
    "device": "auto",                  # auto | cpu
    "quality": "fast",                 # fast | auto | accurate
    "engine": "auto",                  # auto | fast | structure | vl
    "auto_rotate": True,
    "deskew": True,
    "denoise": False,
    "ink_boost": "off",                # off | light | strong - tăng độ đậm chữ trước khi OCR
    "color_mode": "keep",              # keep | gray | vivid | bw - đổi màu ảnh trước khi OCR
    "ocr_threshold": 80,               # % - dòng dưới ngưỡng được đánh dấu cần kiểm tra
    "split_threshold": 70,             # % - điểm tách dưới ngưỡng được đánh dấu nghi vấn
    "keep_annex": True,                # giữ phụ lục cùng văn bản chính
    "blank_as_separator": False,       # ưu tiên trang trắng làm ranh giới
    "remove_blank_pages": True,
    "history_days": 90,
    "clean_temp": True,
    "no_ocr_log": True,
    "theme": "light",
}


OLD_NAMING_RULE = "{loai}_{coquan}_{so}_{ngay}_{trichyeu}"   # mặc định cũ, tự đổi sang quy tắc mới
# Các quy tắc là mặc định của bản cũ (khi {so} còn gồm cả loại/cơ quan) -> tự nâng lên quy tắc mới
SUPERSEDED_RULES = {OLD_NAMING_RULE, "{so}_{ngay}_{trichyeu}"}


class Settings:
    def __init__(self, path=config.SETTINGS_FILE):
        self.path = path
        self._lock = threading.Lock()
        self.data = dict(DEFAULTS)
        try:
            with open(path, encoding="utf-8") as f:
                self.data.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        if self.data["naming_rule"] in SUPERSEDED_RULES:
            self.data["naming_rule"] = DEFAULTS["naming_rule"]

    def get(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def all(self):
        return dict(self.data)

    def update(self, values):
        with self._lock:
            for k, v in values.items():
                if k in DEFAULTS:
                    self.data[k] = type(DEFAULTS[k])(v) if DEFAULTS[k] is not None else v
            self.save()
        return self.all()

    def save(self, path=None):
        path = path or self.path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def restore(self, path):
        with open(path, encoding="utf-8") as f:
            values = json.load(f)
        return self.update(values)

    def reset(self):
        with self._lock:
            self.data = dict(DEFAULTS)
            self.save()
        return self.all()
