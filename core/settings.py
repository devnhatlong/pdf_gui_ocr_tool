# === settings.py ===
# Cấu hình người dùng (lưu JSON trong data/settings.json), có sao lưu / khôi phục.

import json
import os
import threading

import config

DEFAULTS = {
    "output_dir": config.DEFAULT_OUTPUT_DIR,
    "export_format": "pdf",            # pdf | searchable_pdf | docx | xlsx | txt
    "keep_original": True,
    "folder_by_date": True,
    "naming_rule": "{loai}_{coquan}_{so}_{ngay}_{trichyeu}",
    "overwrite": False,                # False: tự thêm (1), (2)... khi trùng tên
    "dpi": 200,
    "device": "auto",                  # auto | cpu
    "quality": "fast",                 # fast | auto | accurate
    "engine": "auto",                  # auto | fast | structure | vl
    "auto_rotate": True,
    "deskew": True,
    "denoise": False,
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
