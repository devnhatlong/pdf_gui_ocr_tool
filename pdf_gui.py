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


def create_entry_with_placeholder(parent, placeholder_text, width=20, font=("Arial", 10)):
    """Tạo Entry với placeholder text"""
    entry = tk.Entry(parent, font=font, width=width, fg="grey")
    entry.insert(0, placeholder_text)
    
    def on_focus_in(event):
        if entry.get() == placeholder_text:
            entry.delete(0, tk.END)
            entry.config(fg="black")
    
    def on_focus_out(event):
        if entry.get() == "":
            entry.insert(0, placeholder_text)
            entry.config(fg="grey")
    
    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)
    
    # Kiểm tra khi có text được nhập
    def on_key_release(event):
        if entry.get() != placeholder_text:
            entry.config(fg="black")
    
    entry.bind("<KeyRelease>", on_key_release)
    
    return entry


class PDFGuiApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Phần mềm số hóa")
        self.root.geometry("1200x700")
        
        # Set icon cho cửa sổ (sử dụng logo.ico)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "assets", "logo.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except:
                pass  # Bỏ qua nếu không set được icon
        
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

        # Loại văn bản (đưa lên đầu) - Combobox có thể tự nhập
        frame_lv = tk.Frame(left_frame)
        frame_lv.pack(fill=tk.X, pady=2)
        tk.Label(frame_lv, text="Loại văn bản:", width=16, font=("Arial", 9), anchor="w").pack(side=tk.LEFT)
        self.loai_vb = ttk.Combobox(
            frame_lv,
            values=["BC", "CV", "KH", "KL", "QĐ", "NQ", "TTr", "TB", "PA", "CTr"],
            font=("Arial", 10),
            state="normal"  # Cho phép tự nhập
        )
        self.loai_vb.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.loai_vb.bind("<<ComboboxSelected>>", lambda e: self.generate_new_filename())
        self.loai_vb.bind("<KeyRelease>", lambda e: self.generate_new_filename())  # Cập nhật khi gõ

        self.entries = {}
        self.placeholders = {
            "Cơ quan ban hành": "CAT, CAX, UBND...",
            "Số ký hiệu": "123/BC-CAX",
            "Ngày ban hành": "01/01/2024",
            "Trích yếu": "V/v thông báo..."
        }
        for label in ["Cơ quan ban hành", "Số ký hiệu", "Ngày ban hành", "Trích yếu"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label + ":", width=16, anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
            entry = create_entry_with_placeholder(frame, self.placeholders[label], width=20, font=("Arial", 10))
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            
            # Custom key release để xử lý placeholder
            def make_key_handler(entry_widget, placeholder):
                def handler(event):
                    current = entry_widget.get()
                    if current and current != placeholder:
                        self.generate_new_filename()
                return handler
            
            entry.bind("<KeyRelease>", make_key_handler(entry, self.placeholders[label]))
            self.entries[label] = entry

        for label in ["Tên file hiện tại:", "Tên file mới:"]:
            frame = tk.Frame(left_frame)
            frame.pack(fill=tk.X, pady=2)
            tk.Label(frame, text=label, width=16, anchor="w", font=("Arial", 9)).pack(side=tk.LEFT)
            entry = tk.Entry(frame, font=("Arial", 9), width=20)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.entries[label] = entry

        tk.Button(left_frame, text="Chọn Thư Mục PDF",
                  command=self.select_folder, bg="orange", font=("Arial", 9)).pack(fill=tk.X, pady=8)
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
            entry = self.entries["Số ký hiệu"]
            entry.delete(0, tk.END)
            entry.insert(0, meta["so_ky_hieu"])
            entry.config(fg="black")
        if meta["ngay_ban_hanh"]:
            entry = self.entries["Ngày ban hành"]
            entry.delete(0, tk.END)
            entry.insert(0, meta["ngay_ban_hanh"])
            entry.config(fg="black")
        if meta["trich_yeu"]:
            entry = self.entries["Trích yếu"]
            entry.delete(0, tk.END)
            entry.insert(0, meta["trich_yeu"])
            entry.config(fg="black")

        self.generate_new_filename()

    # ==================================================
    # OCR METADATA
    # ==================================================
    def remove_accents(self, s):
        s = unicodedata.normalize("NFKD", s)
        return "".join(c for c in s if not unicodedata.combining(c)).lower()

    def extract_metadata_from_ocr(self, text):
        result = {"so_ky_hieu": "", "ngay_ban_hanh": "", "trich_yeu": ""}
        if not text:
            return result

        lines = text.splitlines()[:20]  # Tăng lên 20 dòng để lấy được trích yếu
        original_lines = lines  # Giữ nguyên để lấy text gốc (có dấu)
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
        else:
            m = re.search(r"\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b", t)
            if m:
                d, mth, y = m.groups()
                result["ngay_ban_hanh"] = f"{d.zfill(2)}/{mth.zfill(2)}/{y}"

        # === TRÍCH YẾU ===
        # Tìm pattern "V/v" hoặc "Về việc" trong text gốc (có dấu)
        original_text = "\n".join(original_lines)
        
        # Tìm dòng chứa "V/v" hoặc "Về việc"
        vv_line_idx = None
        vv_prefix = ""
        for idx, line in enumerate(original_lines):
            line_clean = line.strip()
            if re.search(r"^[\s]*(V/v|Về việc)[\s:]", line_clean, re.IGNORECASE):
                vv_line_idx = idx
                # Tìm prefix "V/v" hoặc "Về việc"
                match = re.search(r"^[\s]*((?:V/v|Về việc)[\s:]*)", line_clean, re.IGNORECASE)
                if match:
                    vv_prefix = match.group(1).strip()
                break
        
        if vv_line_idx is not None:
            # Lấy các dòng liên tiếp sau "V/v" cho đến khi gặp dòng dừng (trước "Kính gửi")
            trich_yeu_lines = []
            stop_keywords = ["kính gửi", "về", "cơ quan"]
            
            for i in range(vv_line_idx, min(vv_line_idx + 5, len(original_lines))):  # Tối đa 5 dòng
                line = original_lines[i].strip()
                if not line:
                    continue
                
                # Kiểm tra xem có phải dòng dừng không (đặc biệt là "Kính gửi")
                line_lower = line.lower()
                if any(kw in line_lower for kw in stop_keywords):
                    break
                
                # Nếu là dòng đầu tiên (chứa V/v), lấy toàn bộ dòng
                if i == vv_line_idx:
                    trich_yeu_lines.append(line)
                else:
                    # Nếu dòng quá ngắn (< 5 ký tự) có thể là ký tự lẻ, bỏ qua
                    if len(line) < 5:
                        continue
                    # Kiểm tra xem có phải là số hoặc ngày không (thường là thông tin khác)
                    if re.match(r"^[\s]*(?:Số|Ngày)[\s:]", line, re.IGNORECASE):
                        break
                    trich_yeu_lines.append(line)
            
            if trich_yeu_lines:
                trich_yeu = " ".join(trich_yeu_lines)
                # Loại bỏ khoảng trắng thừa
                trich_yeu = re.sub(r"\s+", " ", trich_yeu).strip()
                # Giới hạn độ dài (tối đa 250 ký tự)
                if len(trich_yeu) > 250:
                    trich_yeu = trich_yeu[:247] + "..."
                if trich_yeu and len(trich_yeu) >= 5:
                    result["trich_yeu"] = trich_yeu
        
        # Nếu không tìm thấy "V/v", tìm dòng có nội dung ngắn sau ngày tháng
        if not result["trich_yeu"]:
            # Tìm dòng đầu tiên sau ngày tháng mà không phải là "Kính gửi" hoặc "Cơ quan"
            for i, line in enumerate(original_lines):
                line_clean = line.strip()
                if not line_clean or len(line_clean) < 15:
                    continue
                # Bỏ qua các dòng thông tin cơ bản
                skip_keywords = ["kính gửi", "cơ quan", "số:", "ngày", "độc lập", "tự do", "hạnh phúc"]
                if any(x in line_clean.lower() for x in skip_keywords):
                    continue
                # Lấy dòng có độ dài hợp lý (15-200 ký tự)
                if 15 <= len(line_clean) <= 200:
                    result["trich_yeu"] = line_clean
                    break

        return result

    # ==================================================
    # RENAME
    # ==================================================
    def get_entry_value(self, label):
        """Lấy giá trị từ entry, bỏ qua nếu là placeholder"""
        entry = self.entries[label]
        placeholder = self.placeholders.get(label, "")
        value = entry.get().strip()
        if value == placeholder:
            return ""
        return value

    def generate_new_filename(self):
        loai = self.loai_vb.get().strip()
        cq = self.get_entry_value("Cơ quan ban hành")
        so = self.get_entry_value("Số ký hiệu")
        ngay_raw = self.get_entry_value("Ngày ban hành")
        ngay = ngay_raw.replace("/", "-")
        
        # Xử lý trích yếu: bỏ dấu, viết hoa chữ cái đầu mỗi từ, sau đó bỏ khoảng trắng
        trich_yeu = self.get_entry_value("Trích yếu")
        if trich_yeu:
            # Bỏ dấu
            trich_yeu = self.remove_accents(trich_yeu)
            # Viết hoa chữ cái đầu mỗi từ
            trich_yeu = trich_yeu.title()
            # Bỏ khoảng trắng
            mota = trich_yeu.replace(" ", "")
        else:
            mota = ""

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
