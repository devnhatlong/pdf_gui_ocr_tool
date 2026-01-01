# === generate_license.py ===
# Tool dành cho Admin để tạo License Key
# Cách dùng: python generate_license.py

import sys
from utils.license_utils import generate_license_key

def main():
    print("=" * 60)
    print("CÔNG CỤ TẠO LICENSE KEY")
    print("=" * 60)
    print()
    print("HƯỚNG DẪN:")
    print("1. Yêu cầu người dùng chạy: python get_machine_id.py")
    print("2. Người dùng sẽ copy Machine ID và gửi cho bạn")
    print("3. Nhập Machine ID vào đây để tạo License Key")
    print()
    print("=" * 60)
    print()
    
    # Nhận Machine ID từ người dùng
    machine_id = input("Nhập Machine ID từ người dùng: ").strip().upper()
    
    if not machine_id or len(machine_id) != 32:
        print("❌ Machine ID không hợp lệ (phải có 32 ký tự)")
        return
    
    # Nhận ngày hết hạn
    expiry_default = "2099-12-31"
    expiry_input = input(f"Nhập ngày hết hạn (YYYY-MM-DD, mặc định: {expiry_default}): ").strip()
    
    if not expiry_input:
        expiry_date = expiry_default
    else:
        expiry_date = expiry_input
    
    # Validate ngày
    try:
        from datetime import datetime
        datetime.strptime(expiry_date, "%Y-%m-%d")
    except:
        print("❌ Ngày hết hạn không hợp lệ (format: YYYY-MM-DD)")
        return
    
    # Tạo license key
    license_key = generate_license_key(machine_id, expiry_date)
    
    print()
    print("=" * 60)
    print("LICENSE KEY ĐÃ TẠO:")
    print("=" * 60)
    print(license_key)
    print("=" * 60)
    print()
    print("✅ Gửi license key này cho người dùng để họ nhập vào app")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nĐã hủy.")
    except Exception as e:
        print(f"\n❌ Lỗi: {e}")

