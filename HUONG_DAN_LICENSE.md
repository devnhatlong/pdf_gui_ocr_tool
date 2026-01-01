# HƯỚNG DẪN SỬ DỤNG HỆ THỐNG LICENSE

## Cho Người Dùng

### 1. Lấy Machine ID

Có 2 cách để lấy Machine ID:

**Cách 1: Chạy tool riêng (Khuyên dùng)**
```bash
python get_machine_id.py
```
- Cửa sổ sẽ hiển thị Machine ID
- Click nút "📋 Copy Machine ID" để copy vào clipboard
- Gửi Machine ID này cho người quản trị

**Cách 2: Từ dialog License trong app**
- Khi app yêu cầu nhập License Key, dialog sẽ hiển thị Machine ID
- Click nút "📋 Copy" bên cạnh Machine ID để copy
- Gửi Machine ID này cho người quản trị

### 2. Nhận và kích hoạt License Key

1. Gửi Machine ID cho người quản trị
2. Nhận License Key từ người quản trị
3. Mở app, dialog sẽ tự động hiển thị nếu cần
4. Dán License Key vào ô "Nhập License Key"
5. Click nút "Kích hoạt"

### 3. Thời gian dùng thử

- Lần đầu chạy app: Tự động bắt đầu dùng thử **30 ngày**
- Trong thời gian dùng thử: App hoạt động bình thường
- Gần hết thời gian dùng thử: Có thông báo số ngày còn lại
- Hết thời gian dùng thử: Phải nhập License Key để tiếp tục sử dụng

---

## Cho Người Quản Trị

### 1. Tạo License Key

```bash
python generate_license.py
```

**Các bước:**
1. Yêu cầu người dùng gửi Machine ID (họ chạy `get_machine_id.py`)
2. Chạy `generate_license.py`
3. Nhập Machine ID từ người dùng (32 ký tự, chữ hoa)
4. Nhập ngày hết hạn (format: YYYY-MM-DD, ví dụ: 2025-12-31)
   - Hoặc nhấn Enter để dùng mặc định (2099-12-31 = vĩnh viễn)
5. Copy License Key được tạo
6. Gửi License Key cho người dùng

**Ví dụ:**
```
Nhập Machine ID từ người dùng: A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6
Nhập ngày hết hạn (YYYY-MM-DD, mặc định: 2099-12-31): 2025-12-31
```

### 2. Lưu ý

- Mỗi License Key chỉ hoạt động trên 1 máy cụ thể (dựa trên Machine ID)
- License Key không thể copy sang máy khác
- Nên lưu lại thông tin: Machine ID, License Key, ngày hết hạn để quản lý

### 3. Kiểm tra License

Để kiểm tra xem License Key có hợp lệ không, bạn có thể:
- Yêu cầu người dùng thử kích hoạt
- Nếu báo lỗi, kiểm tra lại Machine ID và ngày hết hạn

---

## Cấu trúc File

```
pdf_gui_ocr_tool/
├── get_machine_id.py          # Tool cho người dùng lấy Machine ID
├── generate_license.py         # Tool cho admin tạo License Key
├── utils/
│   └── license_utils.py       # Module xử lý license
├── license.dat                 # File chứa License Key (tự động tạo)
└── trial.dat                   # File thông tin trial (tự động tạo)
```

---

## Xử lý sự cố

**Lỗi: "License key không khớp với máy này"**
- Kiểm tra Machine ID đã đúng chưa
- Mỗi máy có Machine ID riêng, không thể dùng chung

**Lỗi: "License key đã hết hạn"**
- Tạo License Key mới với ngày hết hạn mới hơn

**App không chạy sau khi nhập License Key**
- Kiểm tra file `license.dat` đã được tạo chưa
- Xóa file `license.dat` và thử lại

**Muốn reset trial**
- Xóa file `trial.dat` (lưu ý: chỉ có thể dùng 1 lần)

