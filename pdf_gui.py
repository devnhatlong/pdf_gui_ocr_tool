# === pdf_gui.py ===
import tkinter as tk
from tkinter import ttk, filedialog, Text
from utils.file_ops import list_pdfs_in_folder
from utils.pdf_utils import pdf_to_images
from utils.ocr_engine import extract_text_from_image
from PIL import Image, ImageTk
import os
import unicodedata
import re


class PDFGuiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Xử lý File số hóa")
        self.root.geometry("1200x700")
        self.selected_folder = None
        self.tk_image = None
        self.current_file_path = None
        self.setup_ui()

    # ==================================================
    # UI
    # ==================================================
    def setup_ui(self):
        left_frame = tk.Frame(self.root)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)

        tk.Label(left_frame, text="Thông tin File PDF",
                 font=("Arial", 12, "bold"), pady=10).pack()

        self.entries = {}
        for label in ["Cơ quan ban hành", "Số ký hiệu", "Ngày ban hành", "Mô tả"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label + ":", width=15, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=("Arial", 12), width=50)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            if label == "Cơ quan ban hành":
                entry.insert(0, "CAT")
            entry.bind("<KeyRelease>", lambda e: self.generate_new_filename())
            self.entries[label] = entry

        frame_lv = tk.Frame(left_frame)
        frame_lv.pack(fill=tk.X, pady=2)
        tk.Label(frame_lv, text="Loại văn bản:", width=15).pack(side=tk.LEFT)
        self.loai_vb = ttk.Combobox(
            frame_lv,
            values=["BC", "CV", "KH", "KL", "QĐ", "NQ", "TTr", "TB", "PA", "CTr"],
        )
        self.loai_vb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.loai_vb.bind("<<ComboboxSelected>>", lambda e: self.generate_new_filename())

        for label in ["Tên file hiện tại:", "Tên file mới:"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=15, anchor="w").pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=("Arial", 12), width=50)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.entries[label] = entry

        tk.Button(left_frame, text="Chọn Thư Mục PDF",
                  command=self.select_folder, bg="orange").pack(fill=tk.X, pady=10)
        tk.Button(left_frame, text="🔁 Tạo tên file mới",
                  command=self.generate_new_filename, bg="lightblue").pack(fill=tk.X)
        tk.Button(left_frame, text="💾 Đổi tên file",
                  command=self.rename_file, bg="lightgreen").pack(fill=tk.X, pady=5)

        # ===== RIGHT =====
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        tk.Label(right_frame, text="File PDF trong thư mục").pack(anchor="w", padx=5)

        list_frame = tk.Frame(right_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.Y)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(
            list_frame, width=40, yscrollcommand=scrollbar.set
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)
        scrollbar.config(command=self.file_listbox.yview)

        preview_frame = tk.Frame(right_frame)
        preview_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        header = tk.Frame(preview_frame)
        header.pack(fill=tk.X)
        tk.Label(header, text="Trang đầu PDF (ảnh)", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        tk.Label(header, text=" | ").pack(side=tk.LEFT)
        tk.Label(header, text="OCR text", font=("Arial", 10, "bold")).pack(side=tk.LEFT)

        body = tk.Frame(preview_frame)
        body.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(body, width=600, bg="gray")
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ocr_frame = tk.Frame(body)
        ocr_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ocr_scroll = tk.Scrollbar(ocr_frame)
        ocr_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.ocr_text = Text(
            ocr_frame, wrap="word", font=("Arial", 10),
            yscrollcommand=ocr_scroll.set
        )
        self.ocr_text.pack(fill=tk.BOTH, expand=True)
        ocr_scroll.config(command=self.ocr_text.yview)

    # ==================================================
    # FILE HANDLING
    # ==================================================
    def select_folder(self):
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.selected_folder = folder
        self.file_listbox.delete(0, tk.END)
        for f in list_pdfs_in_folder(folder):
            self.file_listbox.insert(tk.END, f)

    def on_file_select(self, event=None):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        filename = self.file_listbox.get(sel[0])
        self.load_pdf(filename)

    def load_pdf(self, filename):
        self.current_file_path = os.path.join(self.selected_folder, filename)
        self.entries["Tên file hiện tại:"].delete(0, tk.END)
        self.entries["Tên file hiện tại:"].insert(0, filename)

        self.ocr_text.delete(1.0, tk.END)
        self.ocr_text.insert(tk.END, "Đang xử lý OCR...")

        images = pdf_to_images(self.current_file_path, max_pages=1)
        if not images:
            return

        img = Image.open(images[0]).resize((600, 800), Image.Resampling.LANCZOS)
        self.tk_image = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_image)

        text = extract_text_from_image(images[0])
        self.ocr_text.delete(1.0, tk.END)
        self.ocr_text.insert(tk.END, text)

        meta = self.extract_metadata_from_ocr(text)
        if meta["so_ky_hieu"]:
            self.entries["Số ký hiệu"].delete(0, tk.END)
            self.entries["Số ký hiệu"].insert(0, meta["so_ky_hieu"])
        if meta["ngay_ban_hanh"]:
            self.entries["Ngày ban hành"].delete(0, tk.END)
            self.entries["Ngày ban hành"].insert(0, meta["ngay_ban_hanh"])

        self.generate_new_filename()

    # ==================================================
    # OCR METADATA
    # ==================================================
    def remove_accents(self, s):
        s = unicodedata.normalize("NFKD", s)
        return "".join(c for c in s if not unicodedata.combining(c)).lower()

    def extract_metadata_from_ocr(self, text):
        result = {"so_ky_hieu": "", "ngay_ban_hanh": ""}
        if not text:
            return result

        lines = text.splitlines()[:15]
        t = self.remove_accents(" ".join(lines))
        t = re.sub(r"\s+", " ", t)

        # === SỐ KÝ HIỆU ===
        for p in [
            r"\bso[:\-\s]+([a-z0-9\/\-\.]+)",
            r"\bs0[:\-\s]+([a-z0-9\/\-\.]+)",
        ]:
            m = re.search(p, t)
            if m:
                result["so_ky_hieu"] = m.group(1).upper()
                break

        # === NGÀY BAN HÀNH ===
        m = re.search(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})", t)
        if m:
            d, mth, y = m.groups()
            result["ngay_ban_hanh"] = f"{d.zfill(2)}/{mth.zfill(2)}/{y}"
            return result

        m = re.search(r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b", t)
        if m:
            d, mth, y = m.groups()
            result["ngay_ban_hanh"] = f"{d.zfill(2)}/{mth.zfill(2)}/{y}"

        return result

    # ==================================================
    # RENAME
    # ==================================================
    def generate_new_filename(self):
        loai = self.loai_vb.get().strip()
        cq = self.entries["Cơ quan ban hành"].get().strip()
        so = self.entries["Số ký hiệu"].get().strip()
        ngay = self.entries["Ngày ban hành"].get().replace("/", "-")
        mota = self.remove_accents(self.entries["Mô tả"].get()).replace(" ", "")

        parts = [loai, cq, so, ngay, mota]
        parts = [re.sub(r'[\\/:*?"<>|]', "", p) for p in parts if p]
        name = "_".join(parts) + ".pdf"

        self.entries["Tên file mới:"].delete(0, tk.END)
        self.entries["Tên file mới:"].insert(0, name)

    def rename_file(self):
        if not self.current_file_path:
            return
        new_name = self.entries["Tên file mới:"].get()
        if not new_name:
            return
        new_path = os.path.join(self.selected_folder, new_name)
        os.rename(self.current_file_path, new_path)
        self.select_folder()


if __name__ == "__main__":
    root = tk.Tk()
    PDFGuiApp(root)
    root.mainloop()
