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
REGISTRY_KEY = r"SOFTWARE\PDF_GUI_OCR"  # Registry key để lưu trial data
REGISTRY_VALUE = "TrialData"  # Tên value trong registry


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


def _get_registry_key(mode=None):
    """Lấy registry key, tạo nếu chưa có (khi mode = KEY_WRITE)"""
    if not HAS_WINREG:
        return None
    if mode is None:
        mode = winreg.KEY_READ
    try:
        # Mở/Create key trong HKEY_CURRENT_USER
        if mode == winreg.KEY_WRITE:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY)
        else:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_KEY, 0, mode)
        return key
    except Exception:
        return None


def _save_trial_to_registry(first_run_timestamp, machine_id):
    """Lưu trial data vào Registry với signature"""
    if not HAS_WINREG:
        return False
    
    try:
        # Tạo payload: machine_id|first_run
        payload = f"{machine_id}|{first_run_timestamp}"
        sig = sign(payload)
        # Lưu: payload|signature
        trial_data = f"{payload}|{sig}"
        
        key = _get_registry_key(winreg.KEY_WRITE)
        if key:
            winreg.SetValueEx(key, REGISTRY_VALUE, 0, winreg.REG_SZ, trial_data)
            winreg.CloseKey(key)
            return True
    except Exception:
        pass
    return False


def _load_trial_from_registry(machine_id):
    """Đọc trial data từ Registry và validate"""
    if not HAS_WINREG:
        return None
    
    try:
        key = _get_registry_key(winreg.KEY_READ)
        if not key:
            return None
        
        try:
            trial_data, _ = winreg.QueryValueEx(key, REGISTRY_VALUE)
            winreg.CloseKey(key)
        except FileNotFoundError:
            winreg.CloseKey(key)
            return None
        
        # Parse: payload|signature
        parts = trial_data.split("|")
        if len(parts) != 3:
            return None
        
        stored_machine_id, first_run_str, sig = parts
        
        # Kiểm tra Machine ID phải khớp
        if stored_machine_id != machine_id:
            return None
        
        # Validate signature
        payload = f"{stored_machine_id}|{first_run_str}"
        expected_sig = sign(payload)
        if sig != expected_sig:
            return None  # Signature không hợp lệ, có thể bị giả mạo
        
        first_run = int(first_run_str)
        return first_run
    except Exception:
        pass
    return None


def _get_fallback_trial_path():
    """Lấy đường dẫn file ẩn cho trial data (fallback cho non-Windows)"""
    try:
        # Windows: AppData\Local (ẩn, không phải trong thư mục app)
        # Linux/Mac: ~/.config hoặc ~/.local/share
        if os.name == 'nt':  # Windows
            appdata = os.getenv('LOCALAPPDATA', os.getenv('APPDATA', os.path.expanduser('~')))
            trial_dir = os.path.join(appdata, 'PDF_GUI_OCR')
            os.makedirs(trial_dir, exist_ok=True)
            return os.path.join(trial_dir, '.trial.dat')  # File ẩn với dấu chấm
        else:  # Linux/Mac
            config_dir = os.path.join(os.path.expanduser('~'), '.config', 'pdf_gui_ocr')
            os.makedirs(config_dir, exist_ok=True)
            return os.path.join(config_dir, '.trial.dat')
    except Exception:
        return None


def _save_trial_fallback(first_run_timestamp, machine_id):
    """Lưu trial data vào file ẩn (fallback cho non-Windows hoặc khi Registry không hoạt động)"""
    trial_path = _get_fallback_trial_path()
    if not trial_path:
        return False
    
    try:
        payload = f"{machine_id}|{first_run_timestamp}"
        sig = sign(payload)
        trial_data = f"{payload}|{sig}"
        
        with open(trial_path, "w", encoding="utf-8") as f:
            f.write(trial_data)
        
        # Trên Windows, set file attribute ẩn
        if os.name == 'nt':
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(trial_path, 2)  # FILE_ATTRIBUTE_HIDDEN
            except:
                pass
        return True
    except Exception:
        return False


def _load_trial_fallback(machine_id):
    """Đọc trial data từ file ẩn và validate (fallback)"""
    trial_path = _get_fallback_trial_path()
    if not trial_path or not os.path.exists(trial_path):
        return None
    
    try:
        with open(trial_path, "r", encoding="utf-8") as f:
            trial_data = f.read().strip()
        
        # Parse: payload|signature
        parts = trial_data.split("|")
        if len(parts) != 3:
            return None
        
        stored_machine_id, first_run_str, sig = parts
        
        # Kiểm tra Machine ID phải khớp
        if stored_machine_id != machine_id:
            return None
        
        # Validate signature
        payload = f"{stored_machine_id}|{first_run_str}"
        expected_sig = sign(payload)
        if sig != expected_sig:
            return None  # Signature không hợp lệ
        
        first_run = int(first_run_str)
        return first_run
    except Exception:
        pass
    return None


def check_trial():
    """Kiểm tra xem còn trong thời gian dùng thử không"""
    machine_id = get_machine_id()
    current_time = int(time.time())
    
    # Đọc từ Registry (Windows) hoặc file ẩn (non-Windows)
    first_run = _load_trial_from_registry(machine_id)
    
    # Fallback: nếu không có trong Registry, thử đọc từ file ẩn
    if first_run is None:
        first_run = _load_trial_fallback(machine_id)
    
    # Nếu vẫn không có, đây là lần đầu chạy - tạo trial mới
    if first_run is None:
        first_run = current_time
        # Lưu vào Registry (ưu tiên, Windows)
        if not _save_trial_to_registry(first_run, machine_id):
            # Fallback về file ẩn nếu không lưu được Registry (non-Windows hoặc lỗi)
            _save_trial_fallback(first_run, machine_id)
    
    # Tính toán thời gian còn lại
    days_used = (current_time - first_run) / 86400  # 86400 = số giây trong 1 ngày
    remaining_days = TRIAL_DAYS - days_used
    
    return remaining_days > 0


def get_trial_info():
    """Lấy thông tin trial (số ngày còn lại)"""
    machine_id = get_machine_id()
    current_time = time.time()
    
    # Đọc từ Registry (Windows) hoặc file ẩn (non-Windows)
    first_run = _load_trial_from_registry(machine_id)
    
    # Fallback: nếu không có trong Registry, thử đọc từ file ẩn
    if first_run is None:
        first_run = _load_trial_fallback(machine_id)
    
    # Nếu vẫn không có, đây là lần đầu chạy
    if first_run is None:
        return {"remaining_days": TRIAL_DAYS, "is_trial": True}
    
    # Tính toán thời gian còn lại
    days_used = (current_time - first_run) / 86400
    remaining_days = max(0, TRIAL_DAYS - days_used)
    
    # Làm tròn lên để tránh trường hợp 0.998264 thành 0
    # Nếu còn > 0 thì tính là ít nhất 1 ngày
    remaining_days_int = int(remaining_days) if remaining_days >= 1.0 else (1 if remaining_days > 0 else 0)
    
    return {
        "remaining_days": remaining_days_int,
        "is_trial": remaining_days > 0
    }


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
    if date.today() > expiry_date:
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
            remaining_days = (expiry_date - date.today()).days
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

