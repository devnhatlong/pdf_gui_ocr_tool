# Thử DeepSeek-OCR 2 trong môi trường dev

Môi trường thử nằm riêng trong `experiments/deepseek`, không thay đổi engine mặc định hay thư viện của app. Không tạo bộ cài.

- Model: `deepseek-ai/DeepSeek-OCR-2`.
- Revision: `aaa02f3811945a91062062994c5c4a3f4c0af2b0`.
- SHA256 trọng số: `d8ff67a424ba6f4dd077885eb9d6a05d2537e76fe5491f0e2a9b712f8c8870fa`.
- BF16, không lượng tử hóa; CUDA 12.4 / PyTorch 2.6.0 / Transformers 4.46.3.
- Decoder dùng eager attention để chạy Windows không cần FlashAttention. Phần visual encoder dùng SDPA theo code upstream.
- Tối đa 4 GiB cho trọng số nằm thường trực trên GPU; phần còn lại offload qua RAM. Bộ nhớ thực tế khi suy luận cao hơn giới hạn trọng số này.
- Ưu tiên giữ encoder ảnh và lớp xuất từ vựng trên GPU để giảm việc chuyển tham số ở mỗi bước. Hai embedding query được giữ trên GPU vì code upstream truy cập trực tiếp `.weight`, không gọi hook `forward` của Accelerate.
- Ảnh được xử lý hoàn toàn tại máy, Transformers chạy chế độ offline.

Chạy trong thư mục này:

```powershell
.\run_trial.ps1 -ImagePath 'D:\duong-dan\trang-bao-cao.png' -Case page
```

`date`, `header`, `both` dùng tọa độ tỷ lệ cố định dành riêng cho trang báo cáo đang so sánh. Với tài liệu khác, dùng `-Case page` để OCR cả ảnh; không dùng hai vùng cố định này như bộ phát hiện ngày tổng quát.

Để lặp lại phép thử hai vùng trên đúng trang báo cáo mẫu: dùng `-Case both`. Model được chạy greedy, không gợi ý đáp án và không hậu xử lý sửa số.

Kết quả nằm trong `results/manual-YYYYMMDD-HHMMSS`: ảnh đầu vào từng vùng, văn bản và `results.json` chứa thời gian nạp, thời gian OCR, VRAM, RAM và hash ảnh nguồn. Prompt là `<image>\nFree OCR.`, không gợi ý đáp án ngày.

Nguồn: https://github.com/deepseek-ai/DeepSeek-OCR-2 và https://huggingface.co/deepseek-ai/DeepSeek-OCR-2 . Các bản tải qua mirror chỉ được chấp nhận khi SHA256 khớp nguồn chính thức.
