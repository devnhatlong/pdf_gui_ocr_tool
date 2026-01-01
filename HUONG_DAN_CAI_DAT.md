# Hướng dẫn Cài đặt và Sử dụng

## Yêu cầu khi copy sang máy khác

Khi bạn đã build thành công file `.exe`, để sử dụng trên máy khác, bạn cần:

### Cách 1: Copy toàn bộ thư mục (Khuyến nghị)

Copy toàn bộ các thư mục và file sau:

```
OCR_PDF.exe
poppler-24.08.0/
tesseract-ocr/
assets/
```

**Cấu trúc thư mục khi copy:**
```
📁 Thư mục phần mềm/
  ├── OCR_PDF.exe
  ├── 📁 poppler-24.08.0/
  │   └── Library/bin/...
  ├── 📁 tesseract-ocr/
  │   ├── tesseract.exe
  │   └── tessdata/
  └── 📁 assets/
      ├── logo.ico
      └── logo.png
```

### Cách 2: Chỉ copy file .exe (nếu build với --onefile)

Nếu file `.exe` được build với chế độ `--onefile`, PyInstaller sẽ đóng gói tất cả dependencies vào trong file .exe. Tuy nhiên, vẫn cần kiểm tra:

1. **Kiểm tra kích thước file .exe:**
   - Nếu file `.exe` có kích thước lớn (100-200MB), có thể đã bao gồm các thư viện cần thiết
   - Nếu file nhỏ (< 50MB), có thể cần copy thêm các thư mục

2. **Test trên máy khác:**
   - Copy file `OCR_PDF.exe` sang máy khác
   - Chạy thử xem có lỗi không
   - Nếu có lỗi về Poppler hoặc Tesseract, copy thêm các thư mục tương ứng

### Các lỗi thường gặp và cách khắc phục

1. **Lỗi: "Unable to find poppler"**
   - **Giải pháp:** Copy thư mục `poppler-24.08.0/` cùng với file .exe

2. **Lỗi: "Tesseract not found"**
   - **Giải pháp:** Copy thư mục `tesseract-ocr/` cùng với file .exe

3. **Lỗi: "Icon not found"**
   - **Giải pháp:** Copy thư mục `assets/` cùng với file .exe (không bắt buộc, chỉ ảnh hưởng icon)

### Hướng dẫn sử dụng

1. **Chạy ứng dụng:**
   - Double-click vào file `OCR_PDF.exe`
   - Ứng dụng sẽ mở ra giao diện

2. **Sử dụng:**
   - Click "Chọn Thư Mục PDF" để chọn thư mục chứa file PDF
   - Click vào file PDF trong danh sách bên phải
   - Ứng dụng sẽ tự động:
     - Hiển thị ảnh trang đầu PDF
     - Thực hiện OCR để trích xuất text
     - Tự động điền thông tin: Số ký hiệu, Ngày ban hành, Trích yếu
   - Chỉnh sửa thông tin nếu cần
   - Click "💾 Đổi tên file" để đổi tên file PDF

3. **Lưu ý:**
   - Ứng dụng chỉ xử lý trang đầu của file PDF
   - OCR có thể mất vài giây tùy thuộc vào kích thước file
   - Đảm bảo file PDF không bị khóa (locked) khi đổi tên

### Tối ưu kích thước (Tùy chọn)

Nếu muốn giảm kích thước khi copy, bạn có thể:

1. **Nén các thư mục:**
   - Nén `poppler-24.08.0/`, `tesseract-ocr/`, `assets/` thành file .zip
   - Hướng dẫn người dùng giải nén trước khi chạy

2. **Tạo file cài đặt:**
   - Sử dụng Inno Setup hoặc NSIS để tạo file installer
   - Tự động giải nén và cấu hình khi cài đặt


