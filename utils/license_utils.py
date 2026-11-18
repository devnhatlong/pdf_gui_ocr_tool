# === license_utils.py ===
# License Key do tool D:\Project\DesktopApp\license_tool cấp (chọn sản phẩm "OfflineOCR Studio"):
#   base64url(OFFLINEOCR|machine_id|YYYY-MM-DD) . base64url(chữ ký Ed25519)
# App chỉ giữ PUBLIC KEY nên kiểm tra được key nhưng không tạo được key.
# Cách tính Machine ID phải giống hàm get_machine_id() trong license_tool.
import uuid
import hashlib
import hmac
import base64
import json
import os
import time
from datetime import datetime, date

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

# Windows Registry (chỉ trên Windows)
try:
    import winreg
    HAS_WINREG = True
except ImportError:
    HAS_WINREG = False

# Cấu hình
PRODUCT = "OFFLINEOCR"
PUBLIC_KEY_HEX = "e81ceff45266f3941c0205463f203c467faa84ec05b5b76ef3ce6c2858179d61"  # keygen.py --show trong license_tool
SECRET_KEY = b"CAT_LAMDONG_PRIVATE_KEY_2026"  # Chỉ dùng ký dữ liệu dùng thử, không liên quan License Key
TRIAL_DAYS = 1  # Số ngày dùng thử
import config
LICENSE_FILE = config.LICENSE_FILE   # %LOCALAPPDATA%\OfflineOCR Studio\data\license.dat (khi đã cài đặt)
_LEGACY_LICENSE_FILES = [os.path.join(config.APP_DIR, "license.dat"), "license.dat"]   # vị trí của bản cũ


def _license_path():
    """File license đang có (ưu tiên vị trí mới), hoặc vị trí mới nếu chưa có."""
    for path in [LICENSE_FILE] + _LEGACY_LICENSE_FILES:
        if os.path.exists(path):
            return path
    return LICENSE_FILE


def get_machine_id():
    """Tạo Machine ID dựa trên MAC address (ổn định, không đổi)"""
    try:
        raw = str(uuid.getnode())  # MAC address
        return hashlib.sha256(raw.encode()).hexdigest()[:32].upper()  # 32 ký tự
    except:
        # Fallback nếu không lấy được MAC
        return hashlib.sha256("fallback_machine".encode()).hexdigest()[:32].upper()


def sign(data: str):
    """Ký dữ liệu bằng SECRET_KEY"""
    return hmac.new(SECRET_KEY, data.encode(), hashlib.sha256).hexdigest()


# === Dữ liệu dùng thử ===
# Một bản ghi "machine_id|lần_chạy_đầu|lần_chạy_muộn_nhất|chữ_ký" lưu ở NHIỀU nơi (registry + 2 file ẩn ở 2 thư mục
# khác nhau). Mỗi lần kiểm tra: gộp mọi bản còn đọc được (lần chạy đầu SỚM nhất, lần chạy muộn nhất MUỘN nhất)
# rồi ghi lại đủ mọi nơi -> xóa một chỗ thì chỗ khác khôi phục lại.
# "Lần chạy muộn nhất" chống lùi đồng hồ: thời điểm tính hạn = max(giờ máy, lần chạy muộn nhất).
# Bản cũ chỉ có "machine_id|lần_chạy_đầu|chữ_ký" (registry TrialData, file .trial.dat) -> vẫn đọc được.
REGISTRY_KEY = r"SOFTWARE\PDF_GUI_OCR"
REGISTRY_VALUE = "TrialData"


class _RegistryStore:
    def read(self):
        if not HAS_WINREG:
            return None
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, winreg.KEY_READ) as key:
                return winreg.QueryValueEx(key, REGISTRY_VALUE)[0]
        except OSError:
            return None

    def write(self, data):
        if not HAS_WINREG:
            return False
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY) as key:
                winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, data)
            return True
        except OSError:
            return False


class _FileStore:
    def __init__(self, path):
        self.path = path

    def read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return None

    def write(self, data):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            if os.path.exists(self.path):
                # Windows không cho mở file ẩn ở chế độ "w" -> ghi đè tại chỗ
                with open(self.path, "r+", encoding="utf-8") as f:
                    f.write(data)
                    f.truncate()
            else:
                with open(self.path, "w", encoding="utf-8") as f:
                    f.write(data)
                if os.name == "nt":
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(self.path, 2)  # FILE_ATTRIBUTE_HIDDEN
            return True
        except Exception:
            return False


def _stores():
    """Các nơi lưu dữ liệu dùng thử."""
    home = os.path.expanduser("~")
    if os.name == "nt":
        local = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or home
        shared = os.getenv("PROGRAMDATA") or os.getenv("ALLUSERSPROFILE") or home
        files = [os.path.join(local, "PDF_GUI_OCR", ".trial.dat"),
                 os.path.join(shared, "PDF_GUI_OCR", ".trial.dat")]
    else:
        files = [os.path.join(home, ".config", "pdf_gui_ocr", ".trial.dat"),
                 os.path.join(home, ".local", "share", "pdf_gui_ocr", ".trial.dat")]
    return [_RegistryStore()] + [_FileStore(p) for p in files]


def _parse_trial(data, machine_id):
    """(lần chạy đầu, lần chạy muộn nhất) nếu bản ghi hợp lệ và đúng máy, ngược lại None."""
    parts = (data or "").strip().split("|")
    if len(parts) not in (3, 4) or parts[0] != machine_id:
        return None
    if not hmac.compare_digest(parts[-1], sign("|".join(parts[:-1]))):
        return None
    try:
        first = int(parts[1])
        last = int(parts[2]) if len(parts) == 4 else first
    except ValueError:
        return None
    return first, max(first, last)


def _sync_state():
    """Gộp + ghi lại dữ liệu dùng thử ở mọi nơi. Trả về (lần chạy đầu, thời điểm hiện tại đã chống lùi giờ)."""
    machine_id = get_machine_id()
    now = int(time.time())
    stores = _stores()
    records = [r for r in (_parse_trial(s.read(), machine_id) for s in stores) if r]
    first = min((r[0] for r in records), default=now)
    last = max([now] + [r[1] for r in records])
    payload = f"{machine_id}|{first}|{last}"
    data = f"{payload}|{sign(payload)}"
    for s in stores:
        if (s.read() or "").strip() != data:
            s.write(data)
    return first, last


def _today():
    """Ngày hiện tại dùng để tính hạn: không lùi được bằng cách chỉnh đồng hồ máy."""
    return date.fromtimestamp(_sync_state()[1])


def _trial_remaining_days():
    first, now = _sync_state()
    return TRIAL_DAYS - (now - first) / 86400


def check_trial():
    """Kiểm tra xem còn trong thời gian dùng thử không"""
    return _trial_remaining_days() > 0


def get_trial_info():
    """Lấy thông tin trial (số ngày còn lại)"""
    remaining_days = max(0.0, _trial_remaining_days())
    # Còn > 0 thì tính là ít nhất 1 ngày (tránh 0.99 thành 0)
    remaining_days_int = int(remaining_days) if remaining_days >= 1.0 else (1 if remaining_days > 0 else 0)
    return {"remaining_days": remaining_days_int, "is_trial": remaining_days > 0}


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _decode_license(license_key: str):
    """Kiểm tra chữ ký rồi tách thành [product, machine_id, expiry_str].
    Trả về None nếu sai định dạng, False nếu chữ ký không hợp lệ."""
    try:
        payload_b64, sig_b64 = license_key.strip().split(".")
        payload, sig = _b64d(payload_b64), _b64d(sig_b64)
    except Exception:
        return None
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX)).verify(sig, payload)
    except (InvalidSignature, ValueError):
        return False
    parts = payload.decode(errors="replace").split("|")
    return parts if len(parts) == 3 else None


def verify_license_key(license_key: str):
    """Xác thực license key"""
    # Bỏ khoảng trắng / xuống dòng lẫn vào khi khách copy key qua Zalo, email...
    license_key = "".join((license_key or "").split())
    if license_key and "." not in license_key:
        # Key HMAC của bản cũ không có dấu "." -> không còn được chấp nhận
        return False, "License Key thuộc phiên bản cũ. Vui lòng gửi Code cho nhà cung cấp để nhận key mới"

    parts = _decode_license(license_key)
    if parts is None:
        return False, "License Key không đúng định dạng"
    if parts is False:
        return False, "License Key không hợp lệ"

    product, machine_id, expiry_str = parts
    if product != PRODUCT:
        return False, "License Key không hợp lệ"
    if machine_id != get_machine_id():
        return False, "License Key không đúng với Code của máy này"

    # Kiểm tra ngày hết hạn
    try:
        expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
    except ValueError:
        return False, "License Key không hợp lệ (ngày hết hạn sai)"
    if _today() > expiry_date:
        return False, f"License Key đã hết hạn ngày {expiry_date.strftime('%d/%m/%Y')}"

    return True, "License Key hợp lệ"


def check_license():
    """Kiểm tra xem có license hợp lệ không"""
    path = _license_path()
    if not os.path.exists(path):
        return False
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            license_key = f.read().strip()
        
        if not license_key:
            return False
        
        is_valid, message = verify_license_key(license_key)
        return is_valid
    except:
        return False


def save_license(license_key: str):
    """Lưu license key vào file"""
    try:
        os.makedirs(os.path.dirname(LICENSE_FILE), exist_ok=True)
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(license_key.strip())
        return True
    except:
        return False


def get_license_info():
    """Lấy thông tin license (nếu có)"""
    path = _license_path()
    if not os.path.exists(path):
        return None
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            license_key = f.read().strip()
        
        if not license_key:
            return None
        
        parts = _decode_license(license_key)
        if not parts:
            return None

        _, machine_id, expiry_str = parts

        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            remaining_days = (expiry_date - _today()).days
        except:
            remaining_days = None
        
        return {
            "machine_id": machine_id,
            "expiry_date": expiry_str,
            "remaining_days": remaining_days
        }
    except:
        return None


if __name__ == "__main__":
    # Test các hàm
    print("Machine ID:", get_machine_id())
    print("Trial:", check_trial())
    print("Trial info:", get_trial_info())
    print("License:", check_license())

