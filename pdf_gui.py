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
        # PanedWindow để có thể kéo thay đổi kích thước
        main_paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        left_frame = tk.Frame(main_paned, width=320)
        main_paned.add(left_frame, minsize=250, width=320)

        tk.Label(left_frame, text="Thông tin File PDF",
                 font=("Arial", 11, "bold"), pady=8).pack()

        self.entries = {}
        for label in ["Cơ quan ban hành", "Số ký hiệu", "Ngày ban hành", "Trích yếu"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label + ":", width=12, anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=("Arial", 10), width=20)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            if label == "Cơ quan ban hành":
                entry.insert(0, "CAT")
            entry.bind("<KeyRelease>", lambda e: self.generate_new_filename())
            self.entries[label] = entry

        frame_lv = tk.Frame(left_frame)
        frame_lv.pack(fill=tk.X, pady=2)
        tk.Label(frame_lv, text="Loại văn bản:", width=12, font=("Arial", 9)).pack(side=tk.LEFT)
        self.loai_vb = ttk.Combobox(
            frame_lv,
            values=["BC", "CV", "KH", "KL", "QĐ", "NQ", "TTr", "TB", "PA", "CTr"],
            font=("Arial", 10),
        )
        self.loai_vb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.loai_vb.bind("<<ComboboxSelected>>", lambda e: self.generate_new_filename())

        for label in ["Tên file hiện tại:", "Tên file mới:"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=12, anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=("Arial", 9), width=20)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.entries[label] = entry

        tk.Button(left_frame, text="Chọn Thư Mục PDF",
                  command=self.select_folder, bg="orange", font=("Arial", 9)).pack(fill=tk.X, pady=8)
        tk.Button(left_frame, text="🔁 Tạo tên file mới",
                  command=self.generate_new_filename, bg="lightblue", font=("Arial", 9)).pack(fill=tk.X, pady=2)
        tk.Button(left_frame, text="💾 Đổi tên file",
                  command=self.rename_file, bg="lightgreen", font=("Arial", 9)).pack(fill=tk.X, pady=2)

        # ===== RIGHT =====
        right_frame = tk.Frame(main_paned)
        main_paned.add(right_frame, minsize=400)

        # PanedWindow cho phần bên phải (list và preview)
        right_paned = tk.PanedWindow(right_frame, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5)
        right_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        list_frame = tk.Frame(right_paned, width=200)
        right_paned.add(list_frame, minsize=150, width=200)
        
        tk.Label(list_frame, text="File PDF trong thư mục", font=("Arial", 9, "bold")).pack(anchor="w", padx=2, pady=2)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.file_listbox = tk.Listbox(
            list_frame, yscrollcommand=scrollbar.set, font=("Arial", 9)
        )
        self.file_listbox.pack(fill=tk.BOTH, expand=True)
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)
        scrollbar.config(command=self.file_listbox.yview)

        preview_frame = tk.Frame(right_paned)
        right_paned.add(preview_frame, minsize=400)

        header = tk.Frame(preview_frame)
        header.pack(fill=tk.X)
        tk.Label(header, text="Trang đầu PDF (ảnh)", font=("Arial", 10, "bold")).pack(side=tk.LEFT)
        tk.Label(header, text=" | ").pack(side=tk.LEFT)
        tk.Label(header, text="OCR text", font=("Arial", 10, "bold")).pack(side=tk.LEFT)

        # PanedWindow cho preview (ảnh và OCR text)
        preview_paned = tk.PanedWindow(preview_frame, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5)
        preview_paned.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        canvas_frame = tk.Frame(preview_paned)
        preview_paned.add(canvas_frame, minsize=300, width=500)
        self.canvas = tk.Canvas(canvas_frame, bg="gray")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        ocr_frame = tk.Frame(preview_paned)
        preview_paned.add(ocr_frame, minsize=200, width=300)

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
        mota = self.remove_accents(self.entries["Trích yếu"].get()).replace(" ", "")

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
