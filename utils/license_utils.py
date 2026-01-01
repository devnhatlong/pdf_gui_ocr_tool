# === license_utils.py ===
import uuid
import hashlib
import hmac
import base64
import json
import os
import time
from datetime import datetime, date

# Cấu hình
SECRET_KEY = b"CAT_LAMDONG_PRIVATE_KEY_2026"
TRIAL_DAYS = 0  # Số ngày dùng thử
TRIAL_FILE = "trial.dat"
LICENSE_FILE = "license.dat"


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


def check_trial():
    """Kiểm tra xem còn trong thời gian dùng thử không"""
    if not os.path.exists(TRIAL_FILE):
        # Lần đầu chạy, tạo file trial
        try:
            data = {"first_run": int(time.time())}
            with open(TRIAL_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return True
        except:
            return False

    try:
        with open(TRIAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "first_run" not in data:
            return False

        days_used = (time.time() - data["first_run"]) / 86400  # 86400 = số giây trong 1 ngày
        remaining_days = TRIAL_DAYS - days_used
        
        return remaining_days > 0
    except:
        return False


def get_trial_info():
    """Lấy thông tin trial (số ngày còn lại)"""
    if not os.path.exists(TRIAL_FILE):
        return {"remaining_days": TRIAL_DAYS, "is_trial": True}
    
    try:
        with open(TRIAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "first_run" not in data:
            return {"remaining_days": 0, "is_trial": False}
        
        days_used = (time.time() - data["first_run"]) / 86400
        remaining_days = max(0, TRIAL_DAYS - days_used)
        
        return {
            "remaining_days": int(remaining_days),
            "is_trial": remaining_days > 0
        }
    except:
        return {"remaining_days": 0, "is_trial": False}


def verify_license_key(license_key: str):
    """Xác thực license key"""
    try:
        # Decode base64
        raw = base64.b64decode(license_key.encode()).decode()
        parts = raw.split("|")
        
        if len(parts) != 3:
            return False, "License key không hợp lệ"
        
        machine_id, expiry_str, sig = parts
        
        # Kiểm tra Machine ID
        current_machine_id = get_machine_id()
        if machine_id != current_machine_id:
            return False, f"License key không khớp với máy này. Mã máy: {current_machine_id}"
        
        # Kiểm tra chữ ký
        payload = f"{machine_id}|{expiry_str}"
        expected_sig = sign(payload)
        if sig != expected_sig:
            return False, "License key không hợp lệ (chữ ký sai)"
        
        # Kiểm tra ngày hết hạn
        try:
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()
            if date.today() > expiry_date:
                return False, f"License key đã hết hạn (hết hạn: {expiry_str})"
        except:
            return False, "License key không hợp lệ (ngày hết hạn sai)"
        
        return True, "License key hợp lệ"
    except Exception as e:
        return False, f"Lỗi kiểm tra license: {str(e)}"


def check_license():
    """Kiểm tra xem có license hợp lệ không"""
    if not os.path.exists(LICENSE_FILE):
        return False
    
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
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
        with open(LICENSE_FILE, "w", encoding="utf-8") as f:
            f.write(license_key.strip())
        return True
    except:
        return False


def get_license_info():
    """Lấy thông tin license (nếu có)"""
    if not os.path.exists(LICENSE_FILE):
        return None
    
    try:
        with open(LICENSE_FILE, "r", encoding="utf-8") as f:
            license_key = f.read().strip()
        
        if not license_key:
            return None
        
        raw = base64.b64decode(license_key.encode()).decode()
        parts = raw.split("|")
        
        if len(parts) != 3:
            return None
        
        machine_id, expiry_str, sig = parts
        
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


# ========================================
# ADMIN TOOL - Generate License Key
# ========================================
def generate_license_key(machine_id: str, expiry_date: str = "2099-12-31"):
    """
    Tạo license key cho một máy cụ thể
    
    Args:
        machine_id: Machine ID của máy người dùng
        expiry_date: Ngày hết hạn (format: YYYY-MM-DD)
    
    Returns:
        License key (base64 encoded string)
    """
    payload = f"{machine_id}|{expiry_date}"
    sig = sign(payload)
    license_raw = f"{payload}|{sig}"
    return base64.b64encode(license_raw.encode()).decode()


if __name__ == "__main__":
    # Test các hàm
    print("Machine ID:", get_machine_id())
    print("Trial:", check_trial())
    print("Trial info:", get_trial_info())
    print("License:", check_license())

