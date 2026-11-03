# === pdf_gui.py ===
import os
import queue
import re
import sys
import threading
import tkinter as tk
import unicodedata
from datetime import datetime
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

from utils import ui_kit as ui
from utils.file_ops import list_pdfs_in_folder
from utils.license_utils import (
    get_machine_id, check_license, check_trial, get_trial_info,
    verify_license_key, save_license, get_license_info
)
from utils.ocr_engine import OcrService, DEFAULT_MODE
from utils.pdf_utils import pdf_to_images

APP_NAME = "Phần mềm số hóa"
APP_SUBTITLE = "Nhận dạng văn bản PDF (OCR) và đặt tên file tự động"
APP_VERSION = "2.0"
AUTHOR_LINES = [
    ("Phát triển bởi", "Nguyễn Nhật Long"),
    ("Đơn vị", "Đội CNTT - Phòng Tham mưu"),
    ("Liên hệ", "0365 756 687"),
]
PERMANENT = "2099-12-31"

DOC_TYPES = [
    ("BC", "Báo cáo"), ("CV", "Công văn"), ("KH", "Kế hoạch"), ("KL", "Kết luận"),
    ("QĐ", "Quyết định"), ("NQ", "Nghị quyết"), ("TTr", "Tờ trình"), ("TB", "Thông báo"),
    ("PA", "Phương án"), ("CTr", "Chương trình"), ("GM", "Giấy mời"), ("DS", "Danh sách"),
]

# Màu riêng của màn hình chính
CANVAS_BG = "#E2E8F0"      # nền vùng xem trước / thanh kéo
WARNING = "#B45309"
SPINNER = "◐◓◑◒"


def section_title(parent, text, bg=ui.BG):
    return tk.Label(parent, text=text, bg=bg, fg=ui.INK, font=(ui.FONT_TITLE, 11), anchor="w")


def caption(parent, text="", bg=ui.BG, fg=ui.INK_FAINT, size=9, **kw):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=(ui.FONT, size), anchor="w", justify="left", **kw)


def slim_scrollbar(parent):
    return ttk.Scrollbar(parent, orient=tk.VERTICAL, style="Slim.Vertical.TScrollbar")


def setup_styles(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Slim.Vertical.TScrollbar", gripcount=0, borderwidth=0, relief="flat",
                    background="#CBD5E1", troughcolor=ui.BG, bordercolor=ui.BG,
                    lightcolor="#CBD5E1", darkcolor="#CBD5E1", arrowsize=ui.S(12),
                    arrowcolor=ui.INK_FAINT)
    style.map("Slim.Vertical.TScrollbar", background=[("active", ui.BORDER_HOVER)])


class PDFGuiApp:
    def __init__(self, root):
        self.root = root
        self.root.withdraw()  # Ẩn cửa sổ chính trong lúc kiểm tra bản quyền

        self.selected_folder = None
        self.current_file_path = None
        self.all_files = []        # Toàn bộ file PDF trong thư mục
        self.visible_files = []    # File đang hiển thị (sau khi lọc)
        self.renamed = set()       # File đã đổi tên trong phiên làm việc
        self.preview_image = None  # Ảnh PIL gốc của trang đầu
        self.tk_image = None
        self.preview_state = "empty"  # empty | loading | image | error
        self.is_licensed = False
        self.trial_remaining = 0

        self._token = 0
        self._requests = queue.Queue()
        self._results = queue.Queue()
        self._busy = False
        self._spin = 0
        self._resize_job = None
        self.ocr = OcrService()
        self.ready = False

        # Kiểm tra license/trial trước khi khởi động
        if not self.check_license_and_trial():
            return

        self.setup_ui()
        threading.Thread(target=self._ocr_worker, daemon=True).start()
        self.root.after(100, self._poll_results)
        self.ready = True
        self.root.deiconify()
        try:
            self.root.state("zoomed")
        except tk.TclError:
            pass

    # ==================================================
    # UI
    # ==================================================
    def setup_ui(self):
        root = self.root
        ui.setup_window(root, APP_NAME, 1360, 820, resizable=True)
        root.minsize(ui.S(1080), ui.S(640))
        setup_styles(root)

        self._build_header()
        self._build_footer()

        main = tk.PanedWindow(root, orient=tk.HORIZONTAL, bg=CANVAS_BG, bd=0,
                              sashwidth=ui.S(5), sashrelief=tk.FLAT, opaqueresize=True)
        main.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(main, bg=ui.BG)
        center = tk.Frame(main, bg=ui.BG)
        right = tk.Frame(main, bg=ui.BG)
        main.add(left, minsize=ui.S(220), width=ui.S(290), stretch="never")
        main.add(center, minsize=ui.S(420), stretch="always")
        main.add(right, minsize=ui.S(340), width=ui.S(410), stretch="never")

        self._build_file_panel(left)
        self._build_preview_panel(center)
        self._build_form_panel(right)
        self._bind_shortcuts()
        self._update_license_badge()

        if not self.is_licensed:
            self.status.show(
                f"Bạn đang dùng bản dùng thử — còn {self.trial_remaining} ngày. "
                "Bấm \"Kích hoạt bản quyền\" trên thanh tiêu đề để sử dụng lâu dài.", "info")

    def _build_header(self):
        header = ui.HeaderBar(self.root, APP_NAME, APP_SUBTITLE, icon="doc", height=72)
        header.pack(fill=tk.X)
        actions = tk.Frame(header, bg=ui.HEADER_MID)
        actions.place(relx=1.0, rely=0.5, x=-ui.S(24), anchor="e")

        self.btn_about = ui.RoundedButton(actions, "Giới thiệu", command=self.show_about,
                                          variant="header", height=36, font_size=9, bold=False,
                                          bg=ui.HEADER_MID)
        self.btn_about.pack(side=tk.RIGHT)
        self.btn_activate = ui.RoundedButton(actions, "Kích hoạt bản quyền", command=self.open_activation,
                                             variant="header", height=36, font_size=9, bold=False,
                                             bg=ui.HEADER_MID)
        if not self.is_licensed:
            self.btn_activate.pack(side=tk.RIGHT, padx=(0, ui.S(8)))
        ui.RoundedButton(actions, "Mở thư mục PDF", command=self.select_folder,
                         variant="header-accent", height=36, font_size=10,
                         bg=ui.HEADER_MID).pack(side=tk.RIGHT, padx=(0, ui.S(8)))

    def _build_footer(self):
        footer = tk.Frame(self.root, bg=ui.SURFACE_SOFT)
        footer.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(footer, bg=ui.BORDER, height=1).pack(side=tk.TOP, fill=tk.X)
        inner = tk.Frame(footer, bg=ui.SURFACE_SOFT, padx=ui.S(16), pady=ui.S(5))
        inner.pack(fill=tk.X)

        self.status_label = caption(inner, "Sẵn sàng — bấm \"Mở thư mục PDF\" (Ctrl+O) để bắt đầu",
                                    bg=ui.SURFACE_SOFT, fg=ui.INK_SOFT)
        self.status_label.pack(side=tk.LEFT)

        caption(inner, "  ·  ".join(v for _, v in AUTHOR_LINES), bg=ui.SURFACE_SOFT,
                size=8).pack(side=tk.RIGHT)
        self.license_badge = caption(inner, "", bg=ui.SURFACE_SOFT, size=9)
        self.license_badge.pack(side=tk.RIGHT, padx=(0, ui.S(18)))

    def _build_file_panel(self, parent):
        pad = ui.S(16)
        top = tk.Frame(parent, bg=ui.BG, padx=pad, pady=ui.S(14))
        top.pack(fill=tk.X)
        title_row = tk.Frame(top, bg=ui.BG)
        title_row.pack(fill=tk.X)
        section_title(title_row, "Tài liệu").pack(side=tk.LEFT)
        self.count_label = tk.Label(title_row, text="0", bg=ui.ACCENT_SOFT, fg=ui.ACCENT_HOVER,
                                    font=(ui.FONT, 8, "bold"), padx=ui.S(7))
        self.count_label.pack(side=tk.LEFT, padx=(ui.S(8), 0))
        self.folder_label = caption(top, "Chưa chọn thư mục", size=8)
        self.folder_label.pack(fill=tk.X, pady=(ui.S(2), ui.S(10)))
        self.folder_label.bind("<Configure>", lambda e: self.folder_label.configure(wraplength=e.width))

        self.search_field = ui.OutlinedField(top, "Tìm file (Ctrl+F)", font_size=10)
        self.search_field.pack(fill=tk.X)
        self.search_field.input.bind("<KeyRelease>", lambda e: self.refresh_file_list())
        self.search_field.input.bind("<Escape>", lambda e: (self.search_field.set(""), self.refresh_file_list()))

        list_box = tk.Frame(parent, bg=ui.BG, padx=ui.S(8))
        list_box.pack(fill=tk.BOTH, expand=True, pady=(0, ui.S(8)))
        scroll = slim_scrollbar(list_box)
        self.file_listbox = tk.Listbox(
            list_box, font=(ui.FONT, 10), bd=0, relief=tk.FLAT, highlightthickness=0,
            bg=ui.BG, fg=ui.INK, activestyle="none", selectbackground=ui.ACCENT_SOFT,
            selectforeground=ui.ACCENT_HOVER, exportselection=False, yscrollcommand=scroll.set,
        )
        scroll.configure(command=self.file_listbox.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.file_listbox.pack(fill=tk.BOTH, expand=True, padx=(ui.S(8), 0))
        self.file_listbox.bind("<<ListboxSelect>>", self.on_file_select)

        # Trạng thái rỗng (chưa mở thư mục / không có file)
        self.empty_state = tk.Frame(list_box, bg=ui.BG)
        self.empty_title = tk.Label(self.empty_state, text="Chưa có tài liệu", bg=ui.BG, fg=ui.INK_SOFT,
                                    font=(ui.FONT_TITLE, 10))
        self.empty_title.pack()
        self.empty_text = caption(self.empty_state, "Mở một thư mục chứa file PDF\nđể bắt đầu số hóa",
                                  size=9, )
        self.empty_text.configure(justify="center", anchor="center")
        self.empty_text.pack(pady=(ui.S(4), ui.S(12)))
        ui.RoundedButton(self.empty_state, "Mở thư mục", command=self.select_folder, variant="secondary",
                         height=34, font_size=9).pack()
        self.empty_state.place(relx=0.5, rely=0.35, anchor="center")

    def _build_preview_panel(self, parent):
        paned = tk.PanedWindow(parent, orient=tk.HORIZONTAL, bg=CANVAS_BG, bd=0,
                               sashwidth=ui.S(5), sashrelief=tk.FLAT, opaqueresize=True)
        paned.pack(fill=tk.BOTH, expand=True)

        # --- Ảnh trang đầu ---
        img_panel = tk.Frame(paned, bg=ui.BG)
        paned.add(img_panel, minsize=ui.S(300), stretch="always")
        bar = tk.Frame(img_panel, bg=ui.BG, padx=ui.S(16), pady=ui.S(10))
        bar.pack(fill=tk.X)
        section_title(bar, "Xem trước trang đầu").pack(side=tk.LEFT)
        self.btn_open_pdf = ui.RoundedButton(bar, "Mở file PDF", command=self.open_current_pdf,
                                             variant="secondary", height=32, font_size=9, bold=False)
        self.btn_open_pdf.pack(side=tk.RIGHT)
        self.btn_open_pdf.set_enabled(False)

        self.canvas = tk.Canvas(img_panel, bg=CANVAS_BG, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._schedule_redraw())
        self.canvas.bind("<Double-Button-1>", lambda e: self.open_current_pdf())

        # --- Văn bản OCR ---
        ocr_panel = tk.Frame(paned, bg=ui.BG)
        paned.add(ocr_panel, minsize=ui.S(240), width=ui.S(360), stretch="never")
        bar = tk.Frame(ocr_panel, bg=ui.BG, padx=ui.S(16), pady=ui.S(10))
        bar.pack(fill=tk.X)
        section_title(bar, "Văn bản nhận dạng").pack(side=tk.LEFT)
        self.btn_copy_ocr = ui.RoundedButton(bar, "Copy", command=self.copy_ocr_text,
                                             variant="secondary", height=32, font_size=9, bold=False,
                                             width=96)
        self.btn_copy_ocr.pack(side=tk.RIGHT)

        # Engine đã dùng + phân tích lại tài liệu hiện tại bằng mô hình nặng hơn
        self.engine_label = caption(ocr_panel, "", size=8)
        self.engine_label.pack(fill=tk.X, padx=ui.S(16))
        actions = tk.Frame(ocr_panel, bg=ui.BG, padx=ui.S(16), pady=ui.S(8))
        actions.pack(fill=tk.X)
        caption(actions, "Phân tích lại:", fg=ui.INK_SOFT).pack(side=tk.LEFT, padx=(0, ui.S(6)))
        self.btn_structure = ui.RoundedButton(actions, "Bố cục / bảng", variant="chip", height=28,
                                              font_size=9, bold=False,
                                              command=lambda: self.reanalyze("structure"))
        self.btn_structure.pack(side=tk.LEFT, padx=(0, ui.S(6)))
        self.btn_vl = ui.RoundedButton(actions, "Nâng cao (VL)", variant="chip", height=28,
                                       font_size=9, bold=False, command=lambda: self.reanalyze("vl"))
        self.btn_vl.pack(side=tk.LEFT)
        tk.Frame(ocr_panel, bg=ui.BORDER, height=1).pack(fill=tk.X)

        text_box = tk.Frame(ocr_panel, bg=ui.BG)
        text_box.pack(fill=tk.BOTH, expand=True)
        scroll = slim_scrollbar(text_box)
        self.ocr_text = tk.Text(
            text_box, wrap="word", font=(ui.FONT, 10), bd=0, relief=tk.FLAT, highlightthickness=0,
            bg=ui.BG, fg=ui.INK, insertbackground=ui.INK, selectbackground=ui.SELECTION,
            padx=ui.S(16), pady=ui.S(12), spacing1=ui.S(2), spacing3=ui.S(2), yscrollcommand=scroll.set,
        )
        self.ocr_text.tag_configure("hint", foreground=ui.INK_FAINT)
        scroll.configure(command=self.ocr_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.ocr_text.pack(fill=tk.BOTH, expand=True)
        self._set_ocr_text("Nội dung nhận dạng từ trang đầu của file PDF sẽ hiển thị tại đây.", hint=True)

    def _build_form_panel(self, parent):
        body = tk.Frame(parent, bg=ui.BG, padx=ui.S(22), pady=ui.S(14))
        body.pack(fill=tk.BOTH, expand=True)

        section_title(body, "Thông tin văn bản").pack(fill=tk.X)
        self.current_label = caption(body, "Chọn một file trong danh sách để bắt đầu", size=9)
        self.current_label.pack(fill=tk.X, pady=(ui.S(2), ui.S(14)))
        self.current_label.bind("<Configure>", lambda e: self.current_label.configure(wraplength=e.width))

        on_change = lambda *_: self.generate_new_filename()
        self.loai_vb = ui.OutlinedCombo(body, "Loại văn bản", DOC_TYPES, on_change=on_change)
        self.loai_vb.pack(fill=tk.X, pady=(0, ui.S(10)))
        self.loai_vb.input.bind("<KeyRelease>", on_change)

        self.fields = {}
        for key, label, kw in [
            ("co_quan", "Cơ quan ban hành", dict(helper="VD: CAT, CAX, UBND...")),
            ("so_ky_hieu", "Số ký hiệu", dict(helper="VD: 123/BC-CAX")),
            ("ngay", "Ngày ban hành", dict(helper="VD: 01/01/2024")),
            ("trich_yeu", "Trích yếu", dict(multiline=True, lines=2, font_size=10)),
        ]:
            field = ui.OutlinedField(body, label, **kw)
            field.pack(fill=tk.X, pady=(0, ui.S(8)))
            field.input.bind("<KeyRelease>", on_change)
            self.fields[key] = field
        self.fields["trich_yeu"].input.configure(wrap=tk.WORD)
        self.fields["trich_yeu"].input.bind("<Return>", lambda e: "break")

        tk.Frame(body, bg=ui.BORDER, height=1).pack(fill=tk.X, pady=(ui.S(6), ui.S(14)))

        self.new_name_field = ui.OutlinedField(body, "Tên file mới", multiline=True, lines=2, font_size=10,
                                               helper="Tự động tạo từ thông tin trên — có thể sửa trực tiếp")
        self.new_name_field.pack(fill=tk.X)
        self.new_name_field.input.bind("<Return>", lambda e: (self.rename_file(), "break")[1])

        self.btn_rename = ui.RoundedButton(body, "Đổi tên file   (Ctrl+S)", command=self.rename_file,
                                           height=44, font_size=11)
        self.btn_rename.pack(fill=tk.X, pady=(ui.S(14), ui.S(8)))
        row = tk.Frame(body, bg=ui.BG)
        row.pack(fill=tk.X)
        ui.RoundedButton(row, "‹  File trước", command=lambda: self.select_relative(-1),
                         variant="secondary", height=36, font_size=9, bold=False).pack(side=tk.LEFT)
        ui.RoundedButton(row, "File tiếp theo  ›", command=lambda: self.select_relative(1),
                         variant="secondary", height=36, font_size=9, bold=False).pack(side=tk.RIGHT)

        status_slot = tk.Frame(body, bg=ui.BG)
        status_slot.pack(fill=tk.X, pady=(ui.S(14), 0))
        self.status = ui.StatusBanner(status_slot)

    def _bind_shortcuts(self):
        r = self.root
        r.bind("<Control-o>", lambda e: self.select_folder())
        r.bind("<Control-s>", lambda e: self.rename_file())
        r.bind("<F5>", lambda e: self.reload_folder())
        r.bind("<Control-f>", lambda e: (self.search_field.focus(), "break")[1])

    # --------------------------------------------------
    # Thanh trạng thái
    # --------------------------------------------------
    def set_status(self, text, busy=False):
        self._busy = busy
        self._status_text = text
        self.status_label.configure(text=text, fg=ui.ACCENT if busy else ui.INK_SOFT)
        if busy:
            self._tick_spinner()

    def _tick_spinner(self):
        if not self._busy:
            return
        self._spin = (self._spin + 1) % len(SPINNER)
        self.status_label.configure(text=f"{SPINNER[self._spin]}  {self._status_text}")
        self.root.after(150, self._tick_spinner)

    def _update_license_badge(self):
        if self.is_licensed:
            info = get_license_info() or {}
            expiry = info.get("expiry_date")
            if not expiry or expiry == PERMANENT:
                text = "●  Đã kích hoạt bản quyền vĩnh viễn"
            else:
                text = f"●  Bản quyền đến {datetime.strptime(expiry, '%Y-%m-%d').strftime('%d/%m/%Y')}"
            self.license_badge.configure(text=text, fg=ui.SUCCESS)
        else:
            self.license_badge.configure(text=f"●  Dùng thử · còn {self.trial_remaining} ngày", fg=WARNING)

    # ==================================================
    # LICENSE & TRIAL
    # ==================================================
    def check_license_and_trial(self):
        """Kiểm tra license hoặc trial. Trả về True nếu có quyền sử dụng"""
        if check_license():
            self.is_licensed = True
            return True

        if check_trial():
            remaining = get_trial_info().get("remaining_days", 0)
            if remaining > 0:
                self.trial_remaining = remaining
                return True

        # Không có license và hết trial: bắt buộc kích hoạt
        self.show_license_dialog(expired=True)
        if check_license():
            self.is_licensed = True
            return True

        self.root.destroy()
        return False

    def open_activation(self):
        if self.show_license_dialog():
            self.is_licensed = True
            self.btn_activate.pack_forget()
            self._update_license_badge()
            self.status.show("Kích hoạt bản quyền thành công. Cảm ơn bạn đã sử dụng phần mềm!", "success",
                             auto_hide_ms=6000)

    def show_license_dialog(self, expired=False):
        """Hiển thị dialog nhập License Key. Trả về True nếu kích hoạt thành công."""
        main_visible = self.root.winfo_viewable()
        dialog = tk.Toplevel(self.root)
        ui.setup_window(dialog, "Kích hoạt bản quyền", 580, 600 if expired else 560)
        if main_visible:
            dialog.transient(self.root)
        try:
            dialog.wait_visibility()
            dialog.grab_set()
        except tk.TclError:
            pass
        dialog.focus_force()
        result = {"ok": False}

        ui.HeaderBar(dialog, "Kích hoạt bản quyền", f"Kích hoạt để sử dụng đầy đủ {APP_NAME}",
                     icon="key", height=80).pack(fill=tk.X)
        body = tk.Frame(dialog, bg=ui.BG, padx=ui.S(28), pady=ui.S(20))
        body.pack(fill=tk.BOTH, expand=True)

        if expired:
            ui.StatusBanner(body).show("Thời gian dùng thử đã hết. Vui lòng nhập License Key để tiếp tục.",
                                       "error")
            tk.Frame(body, bg=ui.BG, height=ui.S(14)).pack(fill=tk.X)

        steps = tk.Frame(body, bg=ui.SURFACE_SOFT, padx=ui.S(14), pady=ui.S(10))
        steps.pack(fill=tk.X, pady=(0, ui.S(18)))
        for i, text in enumerate([
            "Copy Code của máy bên dưới",
            "Gửi Code cho nhà cung cấp để nhận License Key",
            "Dán License Key vào ô bên dưới và bấm Kích hoạt",
        ], start=1):
            row = tk.Frame(steps, bg=ui.SURFACE_SOFT)
            row.pack(fill=tk.X, pady=ui.S(2))
            tk.Label(row, text=str(i), bg=ui.ACCENT, fg="white", font=(ui.FONT, 8, "bold"),
                     width=2).pack(side=tk.LEFT)
            tk.Label(row, text=text, bg=ui.SURFACE_SOFT, fg=ui.INK_SOFT, font=(ui.FONT, 9),
                     anchor="w").pack(side=tk.LEFT, padx=(ui.S(8), 0))

        machine_id = get_machine_id()
        code_row = tk.Frame(body, bg=ui.BG)
        code_row.pack(fill=tk.X)
        code_field = ui.OutlinedField(code_row, "Code của máy", mono=True, readonly=True, font_size=11)
        code_field.set(machine_id)

        def copy_code():
            ui.copy_to_clipboard(dialog, machine_id)
            copy_btn.set_text("Đã copy  ✓")
            dialog.after(2000, lambda: copy_btn.set_text("Copy Code"))

        copy_btn = ui.RoundedButton(code_row, "Copy Code", command=copy_code, variant="secondary",
                                    height=46, font_size=10, width=110)
        copy_btn.pack(side=tk.RIGHT, anchor="s", padx=(ui.S(10), 0))
        code_field.pack(side=tk.LEFT, fill=tk.X, expand=True)

        key_field = ui.OutlinedField(body, "License Key", multiline=True, lines=3, mono=True, font_size=10,
                                     helper="Dán License Key nhận được (Ctrl+V)")
        key_field.pack(fill=tk.X, pady=(ui.S(16), 0))

        status_slot = tk.Frame(body, bg=ui.BG)
        status_slot.pack(fill=tk.X, pady=(ui.S(12), 0))
        status = ui.StatusBanner(status_slot)

        def activate(event=None):
            license_key = re.sub(r"\s+", "", key_field.get())
            if not license_key:
                key_field.set_helper("Vui lòng nhập License Key", error=True)
                key_field.focus()
                return "break"
            is_valid, message = verify_license_key(license_key)
            if not is_valid:
                key_field.set_helper("License Key không hợp lệ", error=True)
                status.show(message, "error")
                return "break"
            if not save_license(license_key):
                status.show("Không lưu được license. Hãy chạy phần mềm ở thư mục có quyền ghi.", "error")
                return "break"
            key_field.set_helper("License Key hợp lệ")
            status.show("Kích hoạt thành công!", "success")
            result["ok"] = True
            dialog.after(900, dialog.destroy)
            return "break"

        key_field.input.bind("<Return>", activate)
        key_field.input.bind("<KeyRelease>", lambda e: key_field._error and key_field.set_helper(
            "Dán License Key nhận được (Ctrl+V)"), add="+")

        actions = tk.Frame(body, bg=ui.BG)
        actions.pack(side=tk.BOTTOM, fill=tk.X)
        ui.RoundedButton(actions, "Kích hoạt", command=activate, height=44, font_size=11,
                         width=150).pack(side=tk.RIGHT)
        ui.RoundedButton(actions, "Thoát" if expired else "Để sau", command=dialog.destroy,
                         variant="secondary", height=44, font_size=10, bold=False,
                         width=110).pack(side=tk.RIGHT, padx=(0, ui.S(10)))

        key_field.focus()
        dialog.wait_window()
        return result["ok"]

    def show_about(self):
        dialog = tk.Toplevel(self.root)
        ui.setup_window(dialog, "Giới thiệu", 600, 470)
        dialog.transient(self.root)
        dialog.wait_visibility()
        dialog.grab_set()

        ui.HeaderBar(dialog, APP_NAME, f"Phiên bản {APP_VERSION}", icon="doc", height=80).pack(fill=tk.X)
        body = tk.Frame(dialog, bg=ui.BG, padx=ui.S(28), pady=ui.S(20))
        body.pack(fill=tk.BOTH, expand=True)

        caption(body, APP_SUBTITLE + ".\nĐọc trang đầu văn bản, tự nhận diện loại văn bản, số ký hiệu, "
                "ngày ban hành, trích yếu và đặt tên file theo chuẩn thống nhất.",
                fg=ui.INK_SOFT, size=10, wraplength=ui.S(460)).pack(fill=tk.X)

        info = tk.Frame(body, bg=ui.SURFACE_SOFT, padx=ui.S(16), pady=ui.S(12))
        info.pack(fill=tk.X, pady=(ui.S(16), 0))
        rows = AUTHOR_LINES + [
            ("Công nghệ OCR", "PP-OCRv6 · VietOCR · PP-StructureV3 · PaddleOCR-VL 1.6"),
            ("Bảo mật", "Xử lý 100% trên máy, không cần Internet"),
            ("Bản quyền", self.license_badge.cget("text").lstrip("● ")),
        ]
        for label, value in rows:
            row = tk.Frame(info, bg=ui.SURFACE_SOFT)
            row.pack(fill=tk.X, pady=ui.S(2))
            caption(row, label, bg=ui.SURFACE_SOFT, width=14).pack(side=tk.LEFT)
            tk.Label(row, text=value, bg=ui.SURFACE_SOFT, fg=ui.INK, font=(ui.FONT, 10),
                     anchor="w").pack(side=tk.LEFT)

        ui.RoundedButton(body, "Đóng", command=dialog.destroy, variant="secondary", height=38,
                         font_size=10, width=110).pack(side=tk.BOTTOM, anchor="e")
        dialog.bind("<Escape>", lambda e: dialog.destroy())

    # ==================================================
    # FILE HANDLING
    # ==================================================
    def select_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Chọn thư mục chứa file PDF")
        if not folder:
            return
        self.selected_folder = folder
        self.renamed.clear()
        self.search_field.set("")
        parts = os.path.normpath(folder).split(os.sep)
        self.folder_label.configure(text=os.sep.join(["…"] + parts[-2:]) if len(parts) > 3 else os.path.normpath(folder))
        self.reload_folder()
        if self.visible_files:
            self.select_index(0)

    def reload_folder(self):
        if not self.selected_folder:
            return
        try:
            self.all_files = sorted(list_pdfs_in_folder(self.selected_folder), key=str.lower)
        except OSError as e:
            self.all_files = []
            self.status.show(f"Không đọc được thư mục: {e}", "error")
        self.renamed &= set(self.all_files)
        self.refresh_file_list()
        self.set_status(f"Đã mở thư mục — {len(self.all_files)} file PDF")

    def refresh_file_list(self):
        keyword = self.search_field.get().lower()
        current = os.path.basename(self.current_file_path) if self.current_file_path else None
        self.visible_files = [f for f in self.all_files if keyword in f.lower()]

        lb = self.file_listbox
        lb.delete(0, tk.END)
        for i, f in enumerate(self.visible_files):
            done = f in self.renamed
            lb.insert(tk.END, ("  ✓  " if done else "      ") + f)
            if done:
                lb.itemconfigure(i, fg=ui.SUCCESS, selectforeground=ui.SUCCESS)
            if f == current:
                lb.selection_set(i)
                lb.see(i)

        total = len(self.all_files)
        self.count_label.configure(text=f"{len(self.renamed)}/{total}" if self.renamed else str(total))
        if self.visible_files:
            self.empty_state.place_forget()
        else:
            if not self.selected_folder:
                self.empty_title.configure(text="Chưa có tài liệu")
                self.empty_text.configure(text="Mở một thư mục chứa file PDF\nđể bắt đầu số hóa")
            elif total:
                self.empty_title.configure(text="Không tìm thấy")
                self.empty_text.configure(text="Không có file nào khớp với\ntừ khóa tìm kiếm")
            else:
                self.empty_title.configure(text="Thư mục trống")
                self.empty_text.configure(text="Thư mục này không có file PDF nào")
            self.empty_state.place(relx=0.5, rely=0.35, anchor="center")

    def select_index(self, index):
        if not self.visible_files:
            return
        index = max(0, min(index, len(self.visible_files) - 1))
        lb = self.file_listbox
        lb.selection_clear(0, tk.END)
        lb.selection_set(index)
        lb.activate(index)
        lb.see(index)
        self.load_pdf(self.visible_files[index])

    def select_relative(self, step):
        if not self.visible_files:
            return
        sel = self.file_listbox.curselection()
        self.select_index(sel[0] + step if sel else 0)

    def on_file_select(self, event=None):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        filename = self.visible_files[sel[0]]
        if self.current_file_path and os.path.basename(self.current_file_path) == filename:
            return
        self.load_pdf(filename)

    def open_current_pdf(self):
        if self.current_file_path and os.path.exists(self.current_file_path):
            try:
                os.startfile(self.current_file_path)
            except OSError as e:
                self.status.show(f"Không mở được file: {e}", "error", auto_hide_ms=4000)

    def copy_ocr_text(self):
        if "hint" in self.ocr_text.tag_names("1.0"):
            return
        ui.copy_to_clipboard(self.root, self.ocr_text.get("1.0", tk.END).strip())
        self.btn_copy_ocr.set_text("Đã copy  ✓")
        self.root.after(1800, lambda: self.btn_copy_ocr.set_text("Copy"))

    def _set_ocr_text(self, text, hint=False):
        self.ocr_text.delete("1.0", tk.END)
        self.ocr_text.insert("1.0", text, ("hint",) if hint else ())

    def load_pdf(self, filename):
        self.current_file_path = os.path.join(self.selected_folder, filename)
        self.current_label.configure(text=filename, fg=ui.INK_SOFT)
        self.btn_open_pdf.set_enabled(True)

        # Xóa thông tin riêng của file trước (giữ lại Loại văn bản và Cơ quan ban hành)
        for key in ("so_ky_hieu", "ngay", "trich_yeu"):
            self.fields[key].set("")
        self.generate_new_filename()

        self.preview_image = None
        self.preview_state = "loading"
        self._redraw_preview()
        self._request_ocr(DEFAULT_MODE)

    def reanalyze(self, mode):
        """Phân tích lại file đang chọn bằng PP-StructureV3 hoặc PaddleOCR-VL (chỉ cho file này)."""
        if not self.current_file_path:
            self.status.show("Chọn một file PDF trước khi phân tích.", "info", auto_hide_ms=3000)
            return
        if mode == "vl" and self.ocr.device is not None and self.ocr.device_label() == "CPU":
            self.status.show("Máy không có GPU: chế độ Nâng cao (PaddleOCR-VL) có thể mất vài phút cho "
                             "mỗi trang. Bạn vẫn có thể chọn file khác trong lúc chờ.", "info", auto_hide_ms=8000)
        self._request_ocr(mode)

    def _request_ocr(self, mode):
        name = os.path.basename(self.current_file_path)
        self._set_ocr_text("Đang nhận dạng văn bản...", hint=True)
        self.engine_label.configure(text="")
        self.set_status(f"Đang nhận dạng: {name}", busy=True)
        self._token += 1
        self._requests.put((self._token, self.current_file_path, mode))

    # --------------------------------------------------
    # OCR chạy nền (không làm treo giao diện)
    # --------------------------------------------------
    def _ocr_worker(self):
        # Nạp sẵn mô hình ngay khi mở phần mềm để file đầu tiên không phải chờ lâu
        engine = self.ocr.warmup(lambda msg: self._results.put(("progress", 0, msg)))
        self._results.put(("ready", 0, engine))
        while True:
            token, path, mode = self._requests.get()
            # Bỏ qua các yêu cầu cũ nếu người dùng bấm chuyển file liên tục
            while not self._requests.empty():
                token, path, mode = self._requests.get_nowait()
            try:
                images = pdf_to_images(path, max_pages=1)
                if not images or not os.path.exists(images[0]):
                    raise RuntimeError("Không đọc được trang đầu của file PDF")
                img = Image.open(images[0])
                img.load()
                self._results.put(("image", token, img))
                if self._requests.empty():
                    result = self.ocr.recognize(
                        images[0], mode=mode,
                        progress=lambda msg, t=token: self._results.put(("progress", t, msg)))
                    self._results.put(("text", token, result))
            except Exception as e:
                self._results.put(("error", token, str(e)))

    def _poll_results(self):
        try:
            while True:
                kind, token, payload = self._results.get_nowait()
                if token != self._token:
                    continue
                if kind == "image":
                    self.preview_image = payload
                    self.preview_state = "image"
                    self._redraw_preview()
                elif kind == "text":
                    self._on_ocr_text(payload)
                elif kind == "progress":
                    self.set_status(payload, busy=True)
                elif kind == "ready":
                    self.set_status(f"Sẵn sàng — OCR: {payload}"
                                    + (f" ({self.ocr.device_label()})" if payload != "Tesseract" else "")
                                    + ". Bấm \"Mở thư mục PDF\" (Ctrl+O) để bắt đầu")
                else:
                    self.preview_state = "error"
                    self._redraw_preview()
                    self._set_ocr_text("Không nhận dạng được văn bản.", hint=True)
                    self.set_status("Lỗi khi xử lý file")
                    self.status.show(f"Lỗi xử lý file: {payload}", "error")
        except queue.Empty:
            pass
        self.root.after(80, self._poll_results)

    def _on_ocr_text(self, result):
        text = result.text
        shown = result.markdown or text
        if shown.strip():
            self._set_ocr_text(shown)
        else:
            self._set_ocr_text("Không tìm thấy chữ trên trang đầu.", hint=True)
        device = f" · {self.ocr.device_label()}" if result.engine != "Tesseract" else ""
        self.engine_label.configure(text=f"{result.engine} · {result.seconds:.1f} giây{device}")
        if result.notes:
            self.status.show(" ".join(result.notes), "info", auto_hide_ms=8000)

        meta = self.extract_metadata_from_ocr(text)
        if meta["so_ky_hieu"]:
            self.fields["so_ky_hieu"].set(meta["so_ky_hieu"])
        if meta["ngay_ban_hanh"]:
            self.fields["ngay"].set(meta["ngay_ban_hanh"])
        if meta["trich_yeu"]:
            self.fields["trich_yeu"].set(meta["trich_yeu"])
        if meta["loai_van_ban"]:
            self.loai_vb.set(meta["loai_van_ban"])
        self.generate_new_filename()

        found = sum(1 for k in ("so_ky_hieu", "ngay_ban_hanh", "trich_yeu", "loai_van_ban") if meta[k])
        self.set_status(f"Đã nhận dạng xong — tự điền {found}/4 trường. Kiểm tra lại rồi bấm Đổi tên (Ctrl+S)")

    # --------------------------------------------------
    # Vẽ ảnh xem trước (tự co giãn theo khung)
    # --------------------------------------------------
    def _schedule_redraw(self):
        if self._resize_job:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(60, self._redraw_preview)

    def _redraw_preview(self):
        self._resize_job = None
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 2 or h <= 2:
            return
        if self.preview_state == "image" and self.preview_image is not None:
            pad = ui.S(24)
            iw, ih = self.preview_image.size
            scale = min((w - pad * 2) / iw, (h - pad * 2) / ih)
            size = (max(1, int(iw * scale)), max(1, int(ih * scale)))
            self.tk_image = ImageTk.PhotoImage(self.preview_image.resize(size, Image.Resampling.LANCZOS))
            x, y = (w - size[0]) // 2, (h - size[1]) // 2
            for i, color in enumerate(("#CBD5E1", "#D5DCE6")):  # đổ bóng nhẹ
                off = ui.S(2) * (2 - i)
                c.create_rectangle(x + off, y + off, x + size[0] + off, y + size[1] + off,
                                   fill=color, outline="")
            c.create_image(x, y, anchor="nw", image=self.tk_image)
            return

        messages = {
            "empty": ("Chưa chọn tài liệu", "Chọn một file PDF ở danh sách bên trái để xem trước"),
            "loading": ("Đang tải trang đầu...", "Văn bản sẽ được nhận dạng tự động"),
            "error": ("Không xem trước được", "File có thể bị hỏng hoặc được bảo vệ"),
        }
        title, sub = messages.get(self.preview_state, messages["empty"])
        cx, cy = w / 2, h / 2
        pw, ph = ui.S(64), ui.S(84)
        ui.rounded_rect(c, cx - pw / 2, cy - ph - ui.S(10), cx + pw / 2, cy - ui.S(10), ui.S(8),
                        fill=ui.BG, outline=ui.BORDER)
        for i in range(4):
            yy = cy - ph + ui.S(8) + i * ui.S(12)
            c.create_line(cx - ui.S(18), yy, cx + (ui.S(18) if i < 3 else 0), yy, fill=ui.BORDER,
                          width=ui.S(3), capstyle=tk.ROUND)
        c.create_text(cx, cy + ui.S(16), text=title, fill=ui.INK_SOFT, font=(ui.FONT_TITLE, 12))
        c.create_text(cx, cy + ui.S(40), text=sub, fill=ui.INK_FAINT, font=(ui.FONT, 9))

    # ==================================================
    # OCR METADATA
    # ==================================================
    def remove_accents(self, s):
        s = unicodedata.normalize("NFKD", s)
        return "".join(c for c in s if not unicodedata.combining(c)).lower()

    @staticmethod
    def starts_new_sentence(line):
        """Dòng bắt đầu bằng chữ hoa nhưng không viết hoa toàn bộ -> câu mới của phần nội dung.
        (Trích yếu nhiều dòng thì dòng sau viết thường, hoặc viết hoa toàn bộ nếu là tiêu đề.)"""
        letters = [c for c in line if c.isalpha()]
        return bool(letters) and letters[0].isupper() and not all(c.isupper() for c in letters)

    def extract_metadata_from_ocr(self, text):
        result = {"so_ky_hieu": "", "ngay_ban_hanh": "", "trich_yeu": "", "loai_van_ban": ""}
        if not text:
            return result
        
        # Mapping từ khóa tiêu đề sang loại văn bản
        keyword_to_loai = {
            "báo cáo": "BC",
            "công văn": "CV",
            "kế hoạch": "KH",
            "kết luận": "KL",
            "quyết định": "QĐ",
            "nghị quyết": "NQ",
            "tờ trình": "TTr",
            "thông báo": "TB",
            "phương án": "PA",
            "chương trình": "CTr",
            "giấy mời": "GM",
            "danh sách": "DS"
        }

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
        
        # Danh sách từ khóa cần loại bỏ khỏi trích yếu (tiêu đề, đầu thư, v.v.)
        exclude_keywords = ["kính gửi", "giấy mời", "kế hoạch", "thông báo", "quyết định", "báo cáo", "nghị quyết"]

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
            # Lấy các dòng liên tiếp sau "V/v" cho đến khi gặp dòng dừng
            trich_yeu_lines = []
            # Chỉ dừng khi gặp các từ khóa này ở đầu dòng (tiêu đề riêng, không phải trong nội dung V/v)
            # Đặc biệt chú ý "kính gửi" - luôn dừng trước đó
            stop_keywords = ["kính gửi", "giấy mời", "kế hoạch", "quyết định", "báo cáo", "nghị quyết", "cơ quan"]
            stop_keywords_no_accents = [self.remove_accents(kw) for kw in stop_keywords]
            
            for i in range(vv_line_idx, min(vv_line_idx + 5, len(original_lines))):  # Tối đa 5 dòng
                line = original_lines[i].strip()
                if not line:
                    continue
                
                # Bỏ dấu để so sánh (xử lý lỗi OCR)
                line_no_accents = self.remove_accents(line)
                
                # Kiểm tra xem có phải dòng dừng không - chỉ kiểm tra các từ khóa ở ĐẦU dòng
                # Đây là các tiêu đề riêng biệt, không phải nội dung trong V/v
                is_stop_line = False
                for kw_no_accents in stop_keywords_no_accents:
                    # Kiểm tra nếu dòng bắt đầu bằng từ khóa (có thể có khoảng trắng đầu)
                    if re.match(r"^[\s]*" + re.escape(kw_no_accents), line_no_accents):
                        is_stop_line = True
                        break
                
                if is_stop_line:
                    # Gặp dòng dừng (như "Kính gửi"), break ngay lập tức
                    break
                
                # Kiểm tra xem có phải là số hoặc ngày không (thường là thông tin khác, dừng lại)
                if re.match(r"^[\s]*(?:so|ngay)[\s:]", line_no_accents):
                    break

                # Dòng tiếp theo bắt đầu một câu mới (viết hoa chữ đầu) là phần nội dung, không phải trích yếu
                if trich_yeu_lines and self.starts_new_sentence(line):
                    break

                # Lấy dòng này vào trích yếu (bao gồm cả dòng V/v và các dòng tiếp theo)
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

            # Có "V/v": loại văn bản lấy từ dòng tiêu đề đứng riêng (VD: "BÁO CÁO", "KẾ HOẠCH")
            for line in original_lines[:vv_line_idx]:
                title = re.sub(r"[^a-z ]", "", self.remove_accents(line)).strip()
                for kw, loai in keyword_to_loai.items():
                    if title == self.remove_accents(kw):
                        result["loai_van_ban"] = loai
                        break

        # Nếu không tìm thấy "V/v", tìm các từ khóa tiêu đề (thường viết hoa và in đậm)
        if not result["trich_yeu"]:
            # Danh sách từ khóa tiêu đề (so sánh không dấu để xử lý lỗi OCR)
            title_keywords_original = [
                "kính gửi", "giấy mời", "kế hoạch", "thông báo", "quyết định", 
                "báo cáo", "nghị quyết", "phương án", "công văn", "kết luận", 
                "tờ trình", "chương trình", "danh sách"
            ]
            # Tạo danh sách từ khóa không dấu để so sánh
            title_keywords_no_accents = [self.remove_accents(kw) for kw in title_keywords_original]
            
            # Tìm dòng chứa từ khóa tiêu đề (có thể viết hoa hoàn toàn hoặc viết hoa chữ cái đầu)
            title_line_idx = None
            matched_keyword_idx = None  # Lưu index của từ khóa đã match
            for idx, line in enumerate(original_lines):
                line_clean = line.strip()
                if not line_clean:
                    continue
                
                # Bỏ dấu của dòng để so sánh (xử lý lỗi OCR)
                line_no_accents = self.remove_accents(line_clean)
                
                # Kiểm tra xem dòng này có bắt đầu bằng một trong các từ khóa tiêu đề không
                for kw_idx, kw_no_accents in enumerate(title_keywords_no_accents):
                    # Kiểm tra nếu dòng bắt đầu bằng từ khóa (có thể có khoảng trắng đầu)
                    kw_pattern = r"^[\s]*" + re.escape(kw_no_accents) + r"[\s:]+(.+)"
                    match_kw = re.match(kw_pattern, line_no_accents)
                    if match_kw:
                        # Trường hợp: từ khóa + nội dung (ví dụ: "THÔNG BÁO: về việc...")
                        # Tìm vị trí từ khóa trong dòng gốc để lấy phần sau
                        kw_original = title_keywords_original[kw_idx]
                        # Thử match với từ khóa gốc trước (có dấu đúng)
                        match_original = re.search(r"^[\s]*" + re.escape(kw_original) + r"[\s:]+(.+)", line_clean, re.IGNORECASE)
                        if match_original:
                            result["trich_yeu"] = match_original.group(1).strip()
                        else:
                            # Nếu không match (do OCR sai dấu), tìm vị trí bằng cách so sánh không dấu
                            # Tìm vị trí từ khóa trong dòng gốc bằng cách so sánh từng đoạn không dấu
                            line_no_accents_lower = line_no_accents.lower()
                            kw_start_pos = line_no_accents_lower.find(kw_no_accents)
                            if kw_start_pos >= 0:
                                # Tìm vị trí tương ứng trong dòng gốc
                                # Đếm số ký tự không dấu từ đầu đến vị trí từ khóa
                                char_count = 0
                                original_pos = 0
                                for i, char in enumerate(line_clean):
                                    if char_count >= kw_start_pos:
                                        original_pos = i
                                        break
                                    # Đếm ký tự (không tính dấu kết hợp)
                                    if not unicodedata.combining(char):
                                        char_count += 1
                                
                                # Tìm vị trí kết thúc từ khóa (sau dấu cách hoặc dấu :)
                                content_start = original_pos + len(kw_original)  # Ước lượng
                                # Tìm chính xác hơn bằng cách tìm dấu cách/dấu : sau từ khóa
                                for i in range(original_pos, min(original_pos + len(kw_original) + 5, len(line_clean))):
                                    if line_clean[i] in [':', ' ', '\t']:
                                        # Tìm vị trí bắt đầu nội dung (sau các dấu cách/dấu :)
                                        content_start = i + 1
                                        while content_start < len(line_clean) and line_clean[content_start] in [' ', ':', '\t']:
                                            content_start += 1
                                        break
                                
                                if content_start < len(line_clean):
                                    result["trich_yeu"] = line_clean[content_start:].strip()
                                else:
                                    # Fallback: lấy phần sau từ khóa từ dòng không dấu
                                    result["trich_yeu"] = match_kw.group(1).strip()
                            else:
                                # Fallback: lấy phần sau từ khóa từ dòng không dấu
                                result["trich_yeu"] = match_kw.group(1).strip()
                        if result["trich_yeu"]:
                            # Tìm loại văn bản từ mapping
                            kw_original = title_keywords_original[kw_idx]
                            if kw_original in keyword_to_loai:
                                result["loai_van_ban"] = keyword_to_loai[kw_original]
                            return result
                    
                    # Kiểm tra nếu dòng chỉ chứa từ khóa (tiêu đề riêng, không có nội dung sau)
                    match_title_only = re.match(r"^[\s]*" + re.escape(kw_no_accents) + r"[\s:]*$", line_no_accents)
                    if match_title_only:
                        # Trường hợp: chỉ có từ khóa (ví dụ: "DANH SACH")
                        # Đánh dấu dòng này là tiêu đề, sẽ lấy các dòng sau làm trích yếu
                        title_line_idx = idx
                        matched_keyword_idx = kw_idx
                        break
                
                if title_line_idx is not None:
                    break
            
            # Nếu tìm thấy từ khóa tiêu đề, set loại văn bản
            if matched_keyword_idx is not None:
                kw_original = title_keywords_original[matched_keyword_idx]
                if kw_original in keyword_to_loai:
                    result["loai_van_ban"] = keyword_to_loai[kw_original]
            
            # Nếu tìm thấy dòng tiêu đề, lấy các dòng sau nó làm trích yếu
            if title_line_idx is not None:
                trich_yeu_lines = []
                stop_keywords = ["kính gửi", "cơ quan", "số", "ngày"]
                stop_keywords_no_accents = [self.remove_accents(kw) for kw in stop_keywords]
                
                # Lấy các dòng sau tiêu đề (bắt đầu từ dòng tiếp theo)
                for i in range(title_line_idx + 1, min(title_line_idx + 5, len(original_lines))):
                    line = original_lines[i].strip()
                    if not line:
                        continue
                    
                    # Bỏ dấu để so sánh (xử lý lỗi OCR)
                    line_no_accents = self.remove_accents(line)
                    
                    # Kiểm tra xem có phải dòng dừng không
                    is_stop_line = False
                    for kw_no_accents in stop_keywords_no_accents:
                        if re.match(r"^[\s]*" + re.escape(kw_no_accents), line_no_accents):
                            is_stop_line = True
                            break
                    
                    if is_stop_line:
                        break
                    
                    # Kiểm tra xem có phải là số hoặc ngày không (so sánh không dấu)
                    if re.match(r"^[\s]*(?:so|ngay)[\s:]", line_no_accents):
                        break

                    if trich_yeu_lines and self.starts_new_sentence(line):
                        break

                    # Lấy dòng này vào trích yếu
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

        return result

    # ==================================================
    # RENAME
    # ==================================================
    def get_entry_value(self, key):
        return re.sub(r"\s+", " ", self.fields[key].get()).strip()

    def generate_new_filename(self):
        loai = self.loai_vb.get().strip()
        cq = self.get_entry_value("co_quan")
        so = self.get_entry_value("so_ky_hieu")
        ngay_raw = self.get_entry_value("ngay")
        ngay = ngay_raw.replace("/", "-")

        # Xử lý trích yếu: bỏ dấu, chuyển lowercase, viết hoa chữ cái đầu (hoặc Title Case nếu không có loại văn bản), sau đó bỏ khoảng trắng và ký tự đặc biệt
        trich_yeu = self.get_entry_value("trich_yeu")
        if trich_yeu:
            # Bỏ dấu
            trich_yeu_no_accent = self.remove_accents(trich_yeu)
            # Đảm bảo tất cả đều lowercase
            trich_yeu_lower = trich_yeu_no_accent.lower()

            # Nếu có loại văn bản: viết hoa chữ cái đầu tiên
            # Nếu không có loại văn bản: viết hoa chữ cái đầu mỗi từ (Title Case)
            if loai:
                # Viết hoa chữ cái đầu tiên của chuỗi
                result_chars = []
                first_letter_capitalized = False
                for char in trich_yeu_lower:
                    if char.isalpha() and not first_letter_capitalized:
                        result_chars.append(char.upper())
                        first_letter_capitalized = True
                    else:
                        result_chars.append(char)
                trich_yeu_with_capital = ''.join(result_chars)
            else:
                # Không có loại văn bản: viết hoa chữ cái đầu mỗi từ (Title Case)
                trich_yeu_with_capital = trich_yeu_lower.title()

            # Bỏ khoảng trắng và các ký tự không phải chữ/số (như /, :, -)
            mota = re.sub(r'[^\w]', '', trich_yeu_with_capital)
        else:
            mota = ""

        parts = [loai, cq, so, ngay, mota]
        parts = [re.sub(r'[\\/:*?"<>|]', "", p) for p in parts if p]
        name = "_".join(parts) + ".pdf" if parts else ""
        self.new_name_field.set(name)

    def rename_file(self):
        if not self.current_file_path:
            self.status.show("Chưa chọn file nào. Chọn một file PDF trong danh sách bên trái.", "info",
                             auto_hide_ms=4000)
            return
        old_name = os.path.basename(self.current_file_path)
        new_name = re.sub(r'[\\/:*?"<>|\r\n\t]', "", self.new_name_field.get()).strip()
        if new_name and not new_name.lower().endswith(".pdf"):
            new_name += ".pdf"
        if not new_name or new_name.lower() == ".pdf":
            self.new_name_field.set_helper("Chưa có tên file mới — hãy điền thông tin văn bản", error=True)
            return
        if new_name == old_name:
            self.status.show("Tên mới trùng với tên hiện tại.", "info", auto_hide_ms=3000)
            return
        new_path = os.path.join(self.selected_folder, new_name)
        if os.path.exists(new_path) and os.path.normcase(new_path) != os.path.normcase(self.current_file_path):
            self.new_name_field.set_helper("Đã có file trùng tên trong thư mục", error=True)
            self.status.show(f"Đã tồn tại file \"{new_name}\". Hãy sửa lại tên file mới.", "error")
            return
        try:
            os.rename(self.current_file_path, new_path)
        except OSError as e:
            self.status.show(f"Không đổi tên được (file có thể đang được mở ở phần mềm khác): {e}", "error")
            return

        self.new_name_field.set_helper("Tự động tạo từ thông tin trên — có thể sửa trực tiếp")
        index = self.visible_files.index(old_name) if old_name in self.visible_files else 0
        self.renamed.add(new_name)
        self.current_file_path = new_path
        self.current_label.configure(text=new_name)
        self.reload_folder()
        self.status.show(f"Đã đổi tên:  {old_name}  →  {new_name}", "success", auto_hide_ms=6000)

        # Tự chuyển sang file tiếp theo chưa đổi tên
        pending = [i for i, f in enumerate(self.visible_files) if f not in self.renamed]
        if pending:
            nxt = next((i for i in pending if i >= index), pending[0])
            self.select_index(nxt)
        else:
            self.set_status(f"Hoàn tất — đã đổi tên {len(self.renamed)} file trong thư mục")


def selftest(pdf_or_image):
    """OCR_PDF.exe --selftest <file.pdf|ảnh>: kiểm tra OCR trên máy (không mở giao diện),
    ghi kết quả ra selftest.txt cạnh phần mềm."""
    import config
    from utils.ocr_engine import MODES

    lines = []
    try:
        path = pdf_or_image
        if path.lower().endswith(".pdf"):
            path = pdf_to_images(path, max_pages=1)[0]
        service = OcrService()
        lines.append(f"Thư mục model: {config.MODELS_DIR}")
        lines.append(f"PaddleOCR: {'có' if service.paddle_available() else 'KHÔNG'}"
                     f" | VietOCR: {'có' if service.vietocr_ready() else 'KHÔNG'}")
        if service.import_error:
            lines.append(service.import_error)
        for mode in ("fast", "structure"):
            r = service.recognize(path, mode=mode)
            lines.append(f"\n[{MODES[mode]}] {r.engine} · {r.seconds:.1f} giây · "
                         f"{service.device_label() if r.engine != 'Tesseract' else ''} {r.notes}")
            lines.append(r.text[:500])
            if service._viet_error:
                lines.append(f"Lỗi VietOCR:\n{service._viet_error}")
    except Exception as e:
        import traceback
        lines.append(f"LỖI: {e}\n{traceback.format_exc()}")
    with open(os.path.join(config.APP_DIR, "selftest.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
        return
    ui.enable_dpi_awareness()
    root = tk.Tk()
    ui.init_scale(root)
    app = PDFGuiApp(root)
    if app.ready:
        root.mainloop()


if __name__ == "__main__":
    main()
