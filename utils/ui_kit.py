# === ui_kit.py ===
# (Dùng chung với license_tool/utils/ui_kit.py, có bổ sung OutlinedCombo, icon "doc", nút header.)
# Bộ widget giao diện hiện đại cho Tkinter thuần (không cần thư viện ngoài, chạy offline):
#   - OutlinedField : ô nhập kiểu "Outlined Text Field" (Material Design) — viền bo góc,
#                     nhãn nằm trên đường viền (notched outline), đổi màu khi focus.
#   - RoundedButton : nút bo góc có hover / disabled, các kiểu primary / secondary / ghost / chip.
#   - OutlinedSelect: ô chọn cùng kiểu Outlined (bấm để mở danh sách).
#   - OutlinedCombo : ô nhập tự do kèm danh sách gợi ý.
#   - HeaderBar     : dải tiêu đề có icon (key / monitor).
#   - StatusBanner  : thông báo trạng thái (thành công / lỗi / thông tin).
# Bảng màu trung tính (slate + xanh dương) để dùng chung cho mọi sản phẩm.

import ctypes
import os
import sys
import tkinter as tk
from tkinter import font as tkfont

# ------------------------------------------------------------
# Màu sắc & font
# ------------------------------------------------------------
BG = "#FFFFFF"            # nền cửa sổ
SURFACE_SOFT = "#F1F5F9"  # nền hộp thông tin phụ
BORDER = "#CBD5E1"
BORDER_HOVER = "#94A3B8"
INK = "#0F172A"
INK_SOFT = "#475569"
INK_FAINT = "#94A3B8"
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "#DBEAFE"
ACCENT_SOFT_HOVER = "#BFDBFE"
SELECTION = "#BFDBFE"
HEADER_TOP = "#1E293B"
HEADER_BOTTOM = "#0F172A"
HEADER_MID = "#172033"    # màu giữa dải gradient (nền cho nút đặt trên header)
HEADER_TEXT = "#F8FAFC"
HEADER_SUBTEXT = "#94A3B8"
SUCCESS = "#15803D"
SUCCESS_BG = "#ECFDF3"
DANGER = "#DC2626"
DANGER_BG = "#FEF2F2"
INFO = "#1D4ED8"
INFO_BG = "#EFF6FF"

FONT = "Segoe UI"
FONT_TITLE = "Segoe UI Semibold"
FONT_MONO = "Consolas"

_scale = 1.0


def enable_dpi_awareness():
    """Bật DPI awareness trên Windows để chữ sắc nét trên màn hình scale 125%/150%."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def init_scale(root):
    """Tính hệ số scale theo DPI màn hình. Gọi 1 lần ngay sau khi tạo Tk()."""
    global _scale
    _scale = max(1.0, root.winfo_fpixels("1i") / 96.0)


def S(px):
    """Đổi kích thước thiết kế (ở 96 DPI) sang pixel thực tế."""
    return int(round(px * _scale))


def resource_path(relative):
    """Đường dẫn tới file đi kèm — chạy được cả khi chạy .py lẫn khi đã đóng gói .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, relative)


def setup_window(root, title, width, height, resizable=False):
    root.title(title)
    root.configure(bg=BG)
    try:
        root.iconbitmap(resource_path(os.path.join("assets", "logo.ico")))
    except Exception:
        pass
    w, h = S(width), S(height)
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 3
    root.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
    root.resizable(resizable, resizable)
    if resizable:
        root.minsize(w, h)


def rounded_rect(canvas, x1, y1, x2, y2, r, **kwargs):
    """Vẽ hình chữ nhật bo góc trên Canvas (polygon smooth)."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1,
        x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r, x2, y2,
        x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2,
        x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ------------------------------------------------------------
# Nút bo góc
# ------------------------------------------------------------
class RoundedButton(tk.Canvas):
    VARIANTS = {
        #            nền      nền hover   chữ     viền
        "primary":   (ACCENT, ACCENT_HOVER, "#FFFFFF", ACCENT),
        "secondary": (BG, SURFACE_SOFT, INK, BORDER),
        "ghost":     (BG, SURFACE_SOFT, INK_SOFT, BG),
        "chip":      (BG, SURFACE_SOFT, INK_SOFT, BORDER),
        "chip-active": (ACCENT_SOFT, ACCENT_SOFT_HOVER, ACCENT_HOVER, ACCENT),
        "success":   (SUCCESS, "#166534", "#FFFFFF", SUCCESS),
        "header":    ("#273449", "#334155", HEADER_TEXT, "#3B4A61"),
        "header-accent": (ACCENT, ACCENT_HOVER, "#FFFFFF", ACCENT),
    }

    def __init__(self, parent, text, command=None, variant="primary", height=40,
                 font_size=10, bold=True, width=None, bg=BG):
        super().__init__(parent, highlightthickness=0, bd=0, bg=bg, cursor="hand2")
        self._text = text
        self._command = command
        self._variant = variant
        self._hover = False
        self._enabled = True
        self._font = tkfont.Font(family=FONT, size=font_size, weight="bold" if bold else "normal")
        natural_w = self._font.measure(text) + S(36)
        self.configure(width=S(width) if width else natural_w, height=S(height))
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._on_click)

    def _set_hover(self, value):
        self._hover = value
        self._draw()

    def _on_click(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if self._enabled and inside and self._command:
            self._command()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 2 or h <= 2:
            return
        bg, bg_hover, fg, border = self.VARIANTS[self._variant]
        fill = bg_hover if (self._hover and self._enabled) else bg
        radius = h / 2 if self._variant.startswith("chip") else S(9)
        rounded_rect(self, 1, 1, w - 1, h - 1, radius, fill=fill, outline=border, width=1)
        self.create_text(w / 2, h / 2, text=self._text, fill=fg if self._enabled else INK_FAINT, font=self._font)

    def set_text(self, text):
        self._text = text
        self._draw()

    def set_variant(self, variant):
        self._variant = variant
        self._draw()

    def set_enabled(self, enabled):
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()


# ------------------------------------------------------------
# Ô nhập kiểu Outlined (nhãn nằm trên viền)
# ------------------------------------------------------------
class OutlinedField(tk.Frame):
    def __init__(self, parent, label, *, multiline=False, lines=4, mono=False, readonly=False,
                 font_size=11, justify="left", helper=None, bg=BG):
        super().__init__(parent, bg=bg)
        self._label = label
        self._bg = bg
        self._multiline = multiline
        self._readonly = readonly
        self._focused = False
        self._hover = False
        self._error = False

        self._label_font = tkfont.Font(family=FONT, size=9, weight="bold")
        self._input_font = tkfont.Font(family=FONT_MONO if mono else FONT, size=font_size)
        self._notch = self._label_font.metrics("linespace") // 2  # nửa chiều cao nhãn = vị trí đường viền

        line_h = self._input_font.metrics("linespace")
        box_h = (line_h * lines + S(22)) if multiline else max(S(46), line_h + S(26))
        self.canvas = tk.Canvas(self, height=self._notch + box_h, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill=tk.X)

        common = dict(bd=0, relief=tk.FLAT, bg=bg, fg=INK, font=self._input_font,
                      insertbackground=INK, highlightthickness=0,
                      selectbackground=SELECTION, selectforeground=INK)
        if multiline:
            self.input = tk.Text(self.canvas, wrap=tk.CHAR, height=lines, padx=0, pady=0, **common)
            if readonly:
                self.input.configure(state="disabled", cursor="arrow")
        else:
            self.input = tk.Entry(self.canvas, justify=justify, readonlybackground=bg,
                                  disabledbackground=bg, **common)
            if readonly:
                self.input.configure(state="readonly")
        self._window = self.canvas.create_window(0, 0, window=self.input, anchor="nw")

        # Dòng phụ bên dưới: gợi ý / lỗi (trái) + bộ đếm (phải)
        self._footer = tk.Frame(self, bg=bg)
        self._helper = tk.Label(self._footer, text=helper or "", bg=bg, fg=INK_FAINT,
                                font=(FONT, 8), anchor="w", justify="left")
        self._helper.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._counter = tk.Label(self._footer, text="", bg=bg, fg=INK_FAINT, font=(FONT, 8))
        self._counter.pack(side=tk.RIGHT)
        if helper:
            self._footer.pack(fill=tk.X, padx=S(14), pady=(S(3), 0))

        self.canvas.bind("<Configure>", lambda e: self._draw())
        self.canvas.bind("<Button-1>", lambda e: self.input.focus_set())
        for w in (self.canvas, self.input):
            w.bind("<Enter>", lambda e: self._set_hover(True), add="+")
            w.bind("<Leave>", lambda e: self._set_hover(False), add="+")
        self.input.bind("<FocusIn>", lambda e: self._set_focus(True), add="+")
        self.input.bind("<FocusOut>", lambda e: self._set_focus(False), add="+")

    # --- vẽ ---
    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _set_focus(self, v):
        self._focused = v
        self._draw()

    def _draw(self):
        c = self.canvas
        c.delete("outline")
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 2:
            return
        top = self._notch
        if self._error:
            color, width = DANGER, 2
        elif self._focused:
            color, width = ACCENT, 2
        elif self._hover and not self._readonly:
            color, width = BORDER_HOVER, 1
        else:
            color, width = BORDER, 1
        rounded_rect(c, 1, top, w - 1, h - 1, S(10), fill=self._bg, outline=color, width=width, tags="outline")

        # Khuyết viền cho nhãn: nền trùng màu nền -> nhãn "nằm trên" đường viền
        label_x = S(12)
        text_w = self._label_font.measure(self._label)
        c.create_rectangle(label_x, 0, label_x + text_w + S(8), top * 2,
                           fill=self._bg, outline="", tags="outline")
        label_color = DANGER if self._error else (ACCENT if self._focused else INK_SOFT)
        c.create_text(label_x + S(4), top, text=self._label, anchor="w",
                      fill=label_color, font=self._label_font, tags="outline")
        c.tag_lower("outline")

        pad_x = S(14)
        if self._multiline:
            c.coords(self._window, pad_x, top + S(11))
            c.itemconfigure(self._window, width=w - pad_x * 2, height=h - top - S(20))
        else:
            c.coords(self._window, pad_x, top + (h - top) / 2)
            c.itemconfigure(self._window, anchor="w", width=w - pad_x * 2)

    # --- API ---
    def get(self):
        if self._multiline:
            return self.input.get("1.0", tk.END).strip()
        return self.input.get().strip()

    def set(self, value):
        if self._multiline:
            self.input.configure(state="normal")
            self.input.delete("1.0", tk.END)
            self.input.insert("1.0", value)
            if self._readonly:
                self.input.configure(state="disabled")
        else:
            self.input.configure(state="normal")
            self.input.delete(0, tk.END)
            self.input.insert(0, value)
            if self._readonly:
                self.input.configure(state="readonly")

    def focus(self):
        self.input.focus_set()
        if not self._multiline:
            self.input.icursor(tk.END)

    def set_helper(self, text, error=False):
        self._error = error
        self._helper.configure(text=text, fg=DANGER if error else INK_FAINT)
        if not self._footer.winfo_ismapped():
            self._footer.pack(fill=tk.X, padx=S(14), pady=(S(3), 0))
        self._draw()

    def set_counter(self, text, ok=None):
        color = INK_FAINT if ok is None else (SUCCESS if ok else INK_FAINT)
        self._counter.configure(text=text, fg=color)
        if not self._footer.winfo_ismapped():
            self._footer.pack(fill=tk.X, padx=S(14), pady=(S(3), 0))


# ------------------------------------------------------------
# Ô chọn kiểu Outlined (bấm để mở danh sách lựa chọn)
# ------------------------------------------------------------
class OutlinedSelect(OutlinedField):
    def __init__(self, parent, label, options, on_change=None, helper=None, bg=BG):
        super().__init__(parent, label, readonly=True, helper=helper, bg=bg)
        self._choices = list(options)
        self._on_change = on_change
        self._value = None
        self.input.configure(cursor="hand2")
        self.canvas.configure(cursor="hand2")
        self._menu = tk.Menu(self, tearoff=0, font=(FONT, 10), bg=BG, fg=INK,
                             activebackground=ACCENT_SOFT, activeforeground=INK, bd=0)
        for opt in self._choices:
            self._menu.add_command(label=opt, command=lambda o=opt: self.select(o))
        for w in (self.canvas, self.input):
            w.bind("<Button-1>", self._open)
        self.input.bind("<Down>", self._open)
        self.input.bind("<space>", self._open)

    def _draw(self):
        super()._draw()
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 2:
            return
        # Mũi tên ▾ bên phải
        cx, cy, s = w - S(20), self._notch + (h - self._notch) / 2, S(5)
        c.create_polygon(cx - s, cy - s / 2, cx + s, cy - s / 2, cx, cy + s / 2,
                         fill=INK_SOFT, outline="", tags="outline")
        c.itemconfigure(self._window, width=w - S(14) * 2 - S(20))

    def _open(self, event=None):
        self.input.focus_set()
        x = self.canvas.winfo_rootx()
        y = self.canvas.winfo_rooty() + self.canvas.winfo_height()
        self._menu.configure(font=(FONT, 10))
        self._menu.tk_popup(x, y)
        return "break"

    def select(self, option):
        self._value = option
        self.set(option)
        if self._on_change:
            self._on_change(option)

    def value(self):
        return self._value


# ------------------------------------------------------------
# Ô nhập có danh sách gợi ý (gõ tự do hoặc bấm mũi tên ▾ để chọn)
# ------------------------------------------------------------
class OutlinedCombo(OutlinedField):
    def __init__(self, parent, label, options, on_change=None, helper=None, bg=BG):
        """options: list các cặp (giá trị, mô tả) — menu hiện "giá trị — mô tả", chọn sẽ điền giá trị."""
        super().__init__(parent, label, helper=helper, bg=bg)
        self._on_change = on_change
        self._menu = tk.Menu(self, tearoff=0, font=(FONT, 10), bg=BG, fg=INK,
                             activebackground=ACCENT_SOFT, activeforeground=INK, bd=0)
        for value, desc in options:
            text = f"{value}  —  {desc}" if desc else value
            self._menu.add_command(label=text, command=lambda v=value: self.select(v))
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.input.bind("<Alt-Down>", self._open)
        self.input.bind("<Down>", self._open)

    def _draw(self):
        super()._draw()
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w <= 2:
            return
        cx, cy, s = w - S(20), self._notch + (h - self._notch) / 2, S(5)
        c.create_polygon(cx - s, cy - s / 2, cx + s, cy - s / 2, cx, cy + s / 2,
                         fill=INK_SOFT, outline="", tags="outline")
        c.itemconfigure(self._window, width=w - S(14) * 2 - S(20))

    def _on_canvas_click(self, event):
        if event.x >= self.canvas.winfo_width() - S(40):
            return self._open()
        self.input.focus_set()

    def _open(self, event=None):
        self.input.focus_set()
        x = self.canvas.winfo_rootx()
        y = self.canvas.winfo_rooty() + self.canvas.winfo_height()
        self._menu.tk_popup(x, y)
        return "break"

    def select(self, value):
        self.set(value)
        self.input.icursor(tk.END)
        if self._on_change:
            self._on_change(value)


# ------------------------------------------------------------
# Dải tiêu đề (icon vẽ bằng Canvas, không cần file ảnh)
# ------------------------------------------------------------
class HeaderBar(tk.Canvas):
    def __init__(self, parent, title, subtitle, icon="key", height=88):
        super().__init__(parent, height=S(height), highlightthickness=0, bd=0, bg=HEADER_BOTTOM)
        self._title = title
        self._subtitle = subtitle
        self._icon = icon
        self._title_font = tkfont.Font(family=FONT_TITLE, size=15)
        self._sub_font = tkfont.Font(family=FONT, size=9)
        self.bind("<Configure>", lambda e: self._draw())

    @staticmethod
    def _mix(c1, c2, t):
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))

    def _logo(self):
        """Logo assets/logo_<px>.png, chọn cỡ hợp với DPI màn hình (None nếu không có)."""
        if not hasattr(self, "_logo_img"):
            self._logo_img = None
            want = S(52)
            for px in (48, 72, 96):
                if px >= want or px == 96:
                    try:
                        self._logo_img = tk.PhotoImage(file=resource_path(os.path.join("assets", f"logo_{px}.png")))
                    except Exception:
                        pass
                    break
        return self._logo_img

    def _draw_icon(self, cx, cy):
        """Logo nếu có; không có thì vẽ icon trắng trên nền ô vuông bo góc màu nhấn."""
        logo = self._logo()
        if logo:
            self.create_image(cx, cy, image=logo)
            return
        size = S(46)
        rounded_rect(self, cx - size / 2, cy - size / 2, cx + size / 2, cy + size / 2, S(12),
                     fill=ACCENT, outline="")
        line = dict(fill="white", width=max(2, S(2.4)), capstyle=tk.ROUND)
        if self._icon == "doc":
            w, h, fold = S(18), S(24), S(6)
            x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
            self.create_polygon(x1, y1, x2 - fold, y1, x2, y1 + fold, x2, y2, x1, y2,
                                fill="", outline="white", width=max(2, S(2)), joinstyle=tk.ROUND)
            self.create_line(x2 - fold, y1, x2 - fold, y1 + fold, x2, y1 + fold,
                             fill="white", width=max(1, S(1.6)))
            for i, ln in enumerate((S(10), S(10), S(6))):
                yy = y1 + S(10) + i * S(4.5)
                self.create_line(x1 + S(4), yy, x1 + S(4) + ln, yy, fill="white",
                                 width=max(1, S(1.6)), capstyle=tk.ROUND)
        elif self._icon == "monitor":
            w, h = S(24), S(16)
            rounded_rect(self, cx - w / 2, cy - h / 2 - S(3), cx + w / 2, cy + h / 2 - S(3), S(3),
                         fill="", outline="white", width=max(2, S(2.2)))
            self.create_line(cx, cy + h / 2 - S(3), cx, cy + S(9), **line)
            self.create_line(cx - S(7), cy + S(10), cx + S(7), cy + S(10), **line)
        else:  # key
            r = S(7)
            kx, ky = cx - S(6), cy - S(1)
            self.create_oval(kx - r, ky - r, kx + r, ky + r, outline="white", width=max(2, S(2.4)))
            self.create_line(kx + r, ky, cx + S(13), ky, **line)
            self.create_line(cx + S(7), ky, cx + S(7), ky + S(6), **line)
            self.create_line(cx + S(12), ky, cx + S(12), ky + S(5), **line)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        steps = 24
        for i in range(steps):
            self.create_rectangle(0, h * i / steps, w, h * (i + 1) / steps + 1, outline="",
                                  fill=self._mix(HEADER_TOP, HEADER_BOTTOM, i / (steps - 1)))
        cx, cy = S(28) + S(23), h / 2
        self._draw_icon(cx, cy)
        tx = cx + S(26) + S(16)
        self.create_text(tx, cy - S(10), text=self._title, anchor="w", fill=HEADER_TEXT, font=self._title_font)
        self.create_text(tx, cy + S(13), text=self._subtitle, anchor="w", fill=HEADER_SUBTEXT, font=self._sub_font)


# ------------------------------------------------------------
# Thông báo trạng thái
# ------------------------------------------------------------
class StatusBanner(tk.Frame):
    STYLES = {
        "success": (SUCCESS_BG, SUCCESS),
        "error": (DANGER_BG, DANGER),
        "info": (INFO_BG, INFO),
    }

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self._bar = tk.Frame(self, width=S(4))
        self._bar.pack(side=tk.LEFT, fill=tk.Y)
        self._label = tk.Label(self, font=(FONT, 9), anchor="w", justify="left", padx=S(12), pady=S(8))
        self._label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        # Xuống dòng theo độ rộng thật của thông báo (tính lại khi cửa sổ đổi kích thước)
        self._label.bind("<Configure>", lambda e: self._label.configure(wraplength=max(S(120), e.width - S(24))))
        self._after = None

    def show(self, text, kind="info", auto_hide_ms=None):
        bg, fg = self.STYLES[kind]
        self.configure(bg=bg)
        self._bar.configure(bg=fg)
        self._label.configure(text=text, bg=bg, fg=fg)
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        if auto_hide_ms:
            self._after = self.after(auto_hide_ms, self.hide)
        if not self.winfo_ismapped():
            self.pack(fill=tk.X)
        return self

    def hide(self):
        self._label.configure(text="")
        self.pack_forget()


def copy_to_clipboard(root, text):
    """Copy và giữ nội dung trong clipboard kể cả khi đóng tool."""
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
