# Hướng dẫn Build File .exe

## Yêu cầu

1. **Python 3.7+** đã được cài đặt
2. **PyInstaller** đã được cài đặt
3. Các thư mục cần thiết:
   - `poppler-24.08.0/` - Poppler binaries
   - `tesseract-ocr/` - Tesseract OCR binaries  
   - `assets/` - Chứa logo.ico và logo.png

## Các bước Build

### Bước 1: Cài đặt PyInstaller (nếu chưa có)

```bash
pip install pyinstaller
```

### Bước 2: Kiểm tra cấu trúc thư mục

Đảm bảo các thư mục sau tồn tại trong thư mục dự án:
- `poppler-24.08.0/`
- `tesseract-ocr/`
- `assets/` (chứa `logo.ico`)

### Bước 3: Build file .exe

Chạy lệnh sau trong thư mục dự án:

```bash
pyinstaller pdf_gui.spec
```

Hoặc nếu muốn build từ đầu (tự động tạo spec file):

```bash
pyinstaller --onefile --windowed --icon=assets/logo.ico --add-data "poppler-24.08.0;poppler-24.08.0" --add-data "tesseract-ocr;tesseract-ocr" --add-data "assets;assets" pdf_gui.py
```

### Bước 4: Tìm file .exe

Sau khi build xong, file `.exe` sẽ nằm trong thư mục:
- `dist/OCR_PDF.exe`

### Bước 5: Kiểm tra file .exe

1. Chạy thử file `dist/OCR_PDF.exe`
2. Kiểm tra xem ứng dụng có mở được không
3. Test chức năng OCR và đổi tên file

## Lưu ý

- File `.exe` sẽ có kích thước lớn (khoảng 100-200MB) vì đã bao gồm:
  - Python runtime
  - Tất cả dependencies (PIL, pytesseract, pdf2image, etc.)
  - Poppler binaries
  - Tesseract OCR binaries và data files
  - Assets (logo, icon)

- Nếu gặp lỗi khi chạy `.exe`, kiểm tra:
  - Tất cả thư mục `poppler-24.08.0` và `tesseract-ocr` đã được include
  - File `logo.ico` tồn tại trong `assets/`
  - Chạy với `--debug=all` để xem chi tiết lỗi

## Build với debug (nếu cần)

Nếu muốn xem console output để debug:

```bash
pyinstaller pdf_gui.spec --debug=all
```

Hoặc sửa file `pdf_gui.spec`, đổi `console=False` thành `console=True`.

