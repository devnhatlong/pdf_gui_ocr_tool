# Hướng dẫn thêm Tesseract OCR vào project

Để ứng dụng chạy offline mà không cần cài đặt Tesseract trên máy đích, bạn cần copy thư mục Tesseract vào project.

## Các bước:

1. **Copy thư mục Tesseract từ máy đã cài đặt:**
   - Mở thư mục: `C:\Program Files\Tesseract-OCR\`
   - Copy toàn bộ thư mục này vào thư mục project với tên: `tesseract-ocr`

2. **Cấu trúc thư mục sau khi copy:**
   ```
   pdf_gui_ocr_tool/
   ├── tesseract-ocr/
   │   ├── tesseract.exe
   │   ├── các file DLL (.dll)
   │   └── tessdata/
   │       ├── vie.traineddata  (bắt buộc - tiếng Việt)
   │       ├── eng.traineddata  (bắt buộc - tiếng Anh)
   │       └── các file .traineddata khác (nếu cần)
   ├── poppler-24.08.0/
   ├── pdf_gui.py
   ├── config.py
   └── ...
   ```

3. **Kiểm tra:**
   - File `config.py` đã được cấu hình để tự động tìm Tesseract trong thư mục `tesseract-ocr`
   - Nếu không tìm thấy, sẽ dùng path mặc định `C:\Program Files\Tesseract-OCR\tesseract.exe`
   - Biến môi trường `TESSDATA_PREFIX` sẽ được tự động thiết lập

4. **Lưu ý quan trọng:**
   - Phải có ít nhất 2 file ngôn ngữ: `vie.traineddata` và `eng.traineddata` trong thư mục `tessdata`
   - Tổng kích thước thư mục Tesseract khoảng 70-100MB (bao gồm cả ngôn ngữ)
   - Nếu chưa có file `vie.traineddata`, có thể tải tại: https://github.com/tesseract-ocr/tessdata

## Build với PyInstaller:

File `pdf_gui.spec` đã được cấu hình để include thư mục `tesseract-ocr` vào build.
Chạy: `pyinstaller pdf_gui.spec`

Sau khi build, file exe sẽ chứa cả Poppler và Tesseract, có thể chạy trên máy không cài đặt các thư viện này.

