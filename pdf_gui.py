# === pdf_gui.py ===
import tkinter as tk
from tkinter import ttk, filedialog, Text
from utils.file_ops import list_pdfs_in_folder
from utils.pdf_utils import pdf_to_images
from PIL import Image, ImageTk
import webbrowser
import subprocess  # ✅ bổ sung
import os
import tempfile

class PDFGuiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Xử lý File số hóa")
        self.root.geometry("1200x700")
        self.last_opened_path = None
        self.setup_ui()

    def setup_ui(self):
        left_frame = tk.Frame(self.root)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        tk.Label(left_frame, text="Thông tin File PDF", font=("Arial", 12, "bold"), pady=10).pack()

        self.entries = {}
        for label in ["Cơ quan ban hành", "Số ký hiệu", "Ngày ban hành", "Mô tả"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label+":", width=15, anchor='w').pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=("Arial", 12), width=50)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            if label == "Cơ quan ban hành":
                entry.insert(0, "CAT")
            entry.bind("<KeyRelease>", lambda e: self.generate_new_filename())
            self.entries[label] = entry

        frame_lv = tk.Frame(left_frame)
        frame_lv.pack(fill=tk.X, pady=2)
        tk.Label(frame_lv, text="Loại văn bản:", width=15).pack(side=tk.LEFT)
        self.loai_vb = ttk.Combobox(frame_lv, values=["BC", "CV", "KH", "KL", "QĐ", "NQ", "TTr", "TB", "PA", "CTr"])
        self.loai_vb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.loai_vb.bind("<<ComboboxSelected>>", lambda e: self.generate_new_filename())

        for label in ["Tên file hiện tại:", "Tên file mới:"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=15, anchor='w').pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=("Arial", 12), width=50)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.entries[label] = entry

        tk.Button(left_frame, text="Chọn Thư Mục PDF", command=self.select_folder, bg="orange").pack(fill=tk.X, padx=5, pady=10)

        tk.Button(left_frame, text="🔁 Tạo tên file mới", command=self.generate_new_filename, bg="lightblue").pack(fill=tk.X, padx=5, pady=5)
        tk.Button(left_frame, text="💾 Đổi tên file", command=self.rename_file, bg="lightgreen").pack(fill=tk.X, padx=5, pady=5)

        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        tk.Label(right_frame, text="File PDF trong thư mục").pack(anchor='w', padx=5)

        list_frame = tk.Frame(right_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Thêm scrollbar Y và listbox thay cho combobox
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(list_frame, width=40, yscrollcommand=scrollbar.set)
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)

        scrollbar.config(command=self.file_listbox.yview)

        tk.Button(list_frame, text="🔍 Mở PDF trong Chrome", command=self.open_pdf_in_browser).pack(pady=5)

        preview_frame = tk.Frame(right_frame)
        preview_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(preview_frame, text="Trang đầu PDF (ảnh)").pack(anchor='w')

        image_text_frame = tk.Frame(preview_frame)
        image_text_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(image_text_frame, bg='gray', width=600)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.ocr_text = Text(image_text_frame, wrap='word', width=50)
        self.ocr_text.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.selected_folder = None
        self.tk_image = None
        self.current_file_path = None

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.selected_folder = folder
            files = list_pdfs_in_folder(folder)
            self.file_listbox.delete(0, tk.END)
            for f in files:
                self.file_listbox.insert(tk.END, f)
            if files:
                self.file_listbox.select_set(0)
                self.on_file_select()

    def on_file_select(self, event=None):
        self.display_pdf_image(event)
        self.open_pdf_in_browser()
    def display_pdf_image(self, event):
        for key in self.entries:
            self.entries[key].delete(0, tk.END)
        self.entries["Cơ quan ban hành"].insert(0, "CAT")
        self.loai_vb.set('')
        if not self.selected_folder:
            return
        selection = self.file_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        filename = self.file_listbox.get(index)
        if filename:
            full_path = os.path.join(self.selected_folder, filename)
            self.current_file_path = full_path

            for key in self.entries:
                self.entries[key].delete(0, tk.END)
            self.entries["Cơ quan ban hành"].insert(0, "CAT")
            self.loai_vb.set('')
            self.entries["Tên file hiện tại:"].insert(0, filename)

            try:
                image_paths = pdf_to_images(full_path, max_pages=1, save_to_disk=False)
                if image_paths:
                    image = Image.open(image_paths[0])
                    image = image.resize((600, 800), Image.Resampling.LANCZOS)
                    self.tk_image = ImageTk.PhotoImage(image)
                    self.canvas.delete("all")
                    self.canvas.create_image(0, 0, anchor='nw', image=self.tk_image)
                    self.ocr_text.delete(1.0, tk.END)
                    self.ocr_text.insert(tk.END, "(Bạn có thể thêm tính năng OCR để tự trích xuất nội dung từ ảnh tại đây)")
            except Exception as e:
                self.canvas.delete("all")
                self.canvas.create_text(10, 10, anchor='nw', text=f"Không thể hiển thị ảnh: {e}")

    def generate_new_filename(self):
        import re
        loai = self.loai_vb.get().strip()
        co_quan = self.entries["Cơ quan ban hành"].get().strip()
        so_ky_hieu = self.entries["Số ký hiệu"].get().strip()
        ngay_ban_hanh = self.entries["Ngày ban hành"].get().strip().replace("/", "-")
        mo_ta = self.entries["Mô tả"].get().strip()

        parts = [loai, co_quan, so_ky_hieu, ngay_ban_hanh, mo_ta]
        # Loại bỏ các ký tự không hợp lệ trong tên file Windows
        parts = [re.sub(r'[\\\\/:*?"<>|\n]', '', p) for p in parts if p.strip()]
        new_name = "_".join(parts) + ".pdf"

        self.entries["Tên file mới:"].delete(0, tk.END)
        self.entries["Tên file mới:"].insert(0, new_name)

    def rename_file(self):
        if self.current_file_path and self.selected_folder:
            new_name = self.entries["Tên file mới:"].get().strip()
            if new_name:
                new_path = os.path.join(self.selected_folder, new_name)
                try:
                    os.rename(self.current_file_path, new_path)
                    self.select_folder()  # refresh list
                    self.current_file_path = new_path
                except Exception as e:
                    print("Lỗi đổi tên:", e)

    def open_pdf_in_browser(self):
        if self.current_file_path and os.path.exists(self.current_file_path):
            # 🔒 Nếu file đã mở rồi, không mở lại nữa
            if self.last_opened_path == self.current_file_path:
                return
            self.last_opened_path = self.current_file_path

            chrome_paths = [
                r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
            ]
            chrome_path = next((p for p in chrome_paths if os.path.exists(p)), None)
            if chrome_path:
                subprocess.Popen([chrome_path, self.current_file_path], shell=True)
            else:
                webbrowser.open(self.current_file_path)

if __name__ == '__main__':
    root = tk.Tk()
    app = PDFGuiApp(root)
    root.mainloop()
