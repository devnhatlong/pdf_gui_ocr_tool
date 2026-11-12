# === exporters.py ===
# Xuất kết quả: TXT, Markdown, JSON (kèm tọa độ OCR), DOCX, XLSX/CSV (bảng biểu), PDF và Searchable PDF
# (PDF gốc + lớp chữ ẩn để tìm kiếm, sao chép).

import csv
import io
import json
import os
import re
from html.parser import HTMLParser

import config

FORMATS = {
    "txt": ("Văn bản TXT", ".txt"),
    "md": ("Markdown", ".md"),
    "json": ("Dữ liệu JSON (kèm tọa độ OCR)", ".json"),
    "docx": ("Word DOCX", ".docx"),
    "xlsx": ("Excel XLSX (bảng biểu)", ".xlsx"),
    "csv": ("CSV (bảng biểu)", ".csv"),
    "pdf": ("PDF", ".pdf"),
    "searchable_pdf": ("PDF có lớp chữ (Searchable PDF)", ".pdf"),
}


# ==================================================
# Bảng biểu trong kết quả PP-StructureV3 / PaddleOCR-VL (HTML <table> hoặc Markdown |a|b|)
# ==================================================
class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self._row, self._cell, self._in_cell = [], None, [], False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th"):
            self._in_cell, self._cell = True, []
        elif tag == "br" and self._in_cell:
            self._cell.append("\n")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._in_cell = False
        elif tag == "tr" and self._row is not None and self.tables:
            self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def extract_tables(markdown):
    """Danh sách bảng (mỗi bảng là list các hàng) từ Markdown/HTML."""
    parser = _TableParser()
    parser.feed(markdown or "")
    tables = [t for t in parser.tables if t]
    rows = []
    for line in (markdown or "").splitlines():
        if line.strip().startswith("|") and line.strip().endswith("|"):
            if re.fullmatch(r"\|[\s:\-|]+\|", line.strip()):
                continue
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
        elif rows:
            tables.append(rows)
            rows = []
    if rows:
        tables.append(rows)
    return tables


def _strip_tables(markdown):
    md = re.sub(r"<table.*?</table>", "\n[Bảng]\n", markdown or "", flags=re.S | re.I)
    return md


# ==================================================
# Xuất
# ==================================================
def export(fmt, pages, out_path, doc=None):
    """pages: list dict {uid, text, markdown, lines, size, image_dpi, page(obj)} theo thứ tự."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    fn = {"txt": _txt, "md": _md, "json": _json, "docx": _docx, "xlsx": _xlsx, "csv": _csv,
          "pdf": _pdf, "searchable_pdf": _searchable_pdf}[fmt]
    fn(pages, out_path, doc)
    return out_path


def _txt(pages, out, doc):
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n\n\f".join(p["text"] for p in pages))


def _md(pages, out, doc):
    with open(out, "w", encoding="utf-8") as f:
        parts = [f"<!-- Trang {i + 1} -->\n\n" + (p.get("markdown") or p["text"]) for i, p in enumerate(pages)]
        f.write("\n\n---\n\n".join(parts))


def _json(pages, out, doc):
    data = {"source": doc.path if doc else "", "app": f"{config.APP_NAME} {config.APP_VERSION}", "pages": [
        {"page": i + 1, "engine": p.get("engine"), "size": p.get("size"), "text": p["text"],
         "markdown": p.get("markdown", ""), "lines": p.get("lines", []), "blocks": p.get("blocks", [])}
        for i, p in enumerate(pages)]}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _docx(pages, out, doc):
    from docx import Document as Docx
    from docx.enum.text import WD_BREAK
    from docx.shared import Pt

    d = Docx()
    style = d.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(13)
    for i, p in enumerate(pages):
        md = p.get("markdown") or ""
        tables = extract_tables(md)
        body = _strip_tables(md) if md else p["text"]
        t_index = 0
        for line in body.splitlines():
            if line.strip() == "[Bảng]" and t_index < len(tables):
                _docx_table(d, tables[t_index])
                t_index += 1
                continue
            heading = re.match(r"^\s{0,3}(#{1,6})\s+(.*)", line)
            if heading:
                d.add_heading(heading.group(2).strip(), level=min(3, len(heading.group(1))))
            else:
                text = re.sub(r"(\*\*|__|`)", "", line)
                d.add_paragraph(text)
        for table in tables[t_index:]:
            _docx_table(d, table)
        if i < len(pages) - 1:
            d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    d.save(out)


def _docx_table(d, rows):
    cols = max(len(r) for r in rows)
    table = d.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            table.cell(r, c).text = value


def _all_tables(pages):
    out = []
    for i, p in enumerate(pages):
        for t in extract_tables(p.get("markdown") or ""):
            out.append((i + 1, t))
    return out


def _xlsx(pages, out, doc):
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    wb.remove(wb.active)
    tables = _all_tables(pages)
    if not tables:   # không có bảng: mỗi dòng văn bản 1 hàng
        ws = wb.create_sheet("Văn bản")
        ws.append(["Trang", "Nội dung"])
        for i, p in enumerate(pages):
            for line in p["text"].splitlines():
                ws.append([i + 1, line])
    for n, (page_no, rows) in enumerate(tables, start=1):
        ws = wb.create_sheet(f"Bảng {n} (tr.{page_no})"[:31])
        for row in rows:
            ws.append(row)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for col in ws.columns:
            width = max(len(str(c.value or "")) for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(60, max(8, width + 2))
    wb.save(out)


def _csv(pages, out, doc):
    tables = _all_tables(pages)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if not tables:
            for i, p in enumerate(pages):
                for line in p["text"].splitlines():
                    w.writerow([i + 1, line])
        for n, (_page, rows) in enumerate(tables):
            if n:
                w.writerow([])
            w.writerows(rows)


REGISTER_HEADERS = ["STT", "Số ký hiệu", "Ngày ban hành", "Trích yếu",
                    "Tờ số", "Độ mật\n(Không mật/Mật/Tối mật/Tuyệt mật)", "Ghi chú"]
_REGISTER_WIDTHS = [8, 20, 15, 56, 9, 22, 16]


def export_register(rows, out_path):
    """Sổ danh mục văn bản (Excel). rows: list dict {so, ngay, trichyeu, to_so, do_mat, ghi_chu}
    (không có cột Cơ quan ban hành; khóa "coquan" nếu có sẽ bị bỏ qua).
    Times New Roman 14, căn giữa toàn bộ, header in đậm."""
    from openpyxl import Workbook
    from openpyxl.cell.rich_text import CellRichText, TextBlock
    from openpyxl.cell.text import InlineFont
    from openpyxl.styles import Alignment, Border, Font, Side
    from openpyxl.utils import get_column_letter

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Danh mục văn bản"
    body_font = Font(name="Times New Roman", size=14)
    head_font = Font(name="Times New Roman", size=14, bold=True)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    edge = Side(style="thin")
    border = Border(left=edge, right=edge, top=edge, bottom=edge)

    ws.append(REGISTER_HEADERS)
    for i, r in enumerate(rows, start=1):
        ws.append([i, r.get("so", ""), r.get("ngay", ""), r.get("trichyeu", ""),
                   r.get("to_so", ""), r.get("do_mat", "") or "Không mật", r.get("ghi_chu", "")])
    for c, width in enumerate(_REGISTER_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(c)].width = width
    for row in ws.iter_rows():
        for cell in row:
            cell.font = body_font
            cell.alignment = center
            cell.border = border
    for cell in ws[1]:
        cell.font = head_font
    # Cột Độ mật: "Độ mật" in đậm, phần "(Không mật/...)" không đậm
    secret = ws.cell(1, next(i for i, h in enumerate(REGISTER_HEADERS, start=1) if h.startswith("Độ mật")))
    secret.value = CellRichText(
        TextBlock(InlineFont(rFont="Times New Roman", sz=14, b=True), "Độ mật\n"),
        TextBlock(InlineFont(rFont="Times New Roman", sz=14, b=False), "(Không mật/Mật/Tối mật/Tuyệt mật)"),
    )
    secret.alignment = center
    ws.row_dimensions[1].height = 74
    ws.freeze_panes = "A2"
    wb.save(out_path)
    return out_path


def _pdf(pages, out, doc):
    doc.save_pages([p["page"] for p in pages], out)


def _searchable_pdf(pages, out, doc):
    """PDF gốc + lớp chữ ẩn (render mode 3) đặt đúng vị trí từng dòng OCR."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font = "Helvetica"
    if os.path.exists(config.SYSTEM_FONT):
        try:
            pdfmetrics.registerFont(TTFont("OCRFont", config.SYSTEM_FONT))
            font = "OCRFont"
        except Exception:
            pass

    tmp = out + ".base.pdf"
    doc.save_pages([p["page"] for p in pages], tmp)
    reader = PdfReader(tmp)
    writer = PdfWriter()
    for p, pdf_page in zip(pages, reader.pages):
        w_pt, h_pt = float(pdf_page.mediabox.width), float(pdf_page.mediabox.height)
        if (pdf_page.get("/Rotate") or 0) % 180:
            w_pt, h_pt = h_pt, w_pt
        img_w, img_h = p.get("size") or (0, 0)
        if p.get("lines") and img_w and img_h:
            sx, sy = w_pt / img_w, h_pt / img_h
            buf = io.BytesIO()
            c = canvas.Canvas(buf, pagesize=(w_pt, h_pt))
            for ln in p["lines"]:
                text = ln["text"].strip()
                if not text:
                    continue
                x1, y1, x2, y2 = ln["box"]
                size = max(4.0, (y2 - y1) * sy * 0.8)
                t = c.beginText()
                t.setTextRenderMode(3)                      # chữ ẩn
                t.setFont(font, size)
                natural = pdfmetrics.stringWidth(text, font, size) or 1
                t.setHorizScale(max(10, min(500, (x2 - x1) * sx / natural * 100)))
                t.setTextOrigin(x1 * sx, h_pt - y2 * sy + (y2 - y1) * sy * 0.2)
                t.textLine(text)
                c.drawText(t)
            c.save()
            overlay = PdfReader(io.BytesIO(buf.getvalue())).pages[0]
            if pdf_page.get("/Rotate"):
                pdf_page.transfer_rotation_to_content()
            pdf_page.merge_page(overlay)
        writer.add_page(pdf_page)
    with open(out, "wb") as f:
        writer.write(f)
    try:
        os.remove(tmp)
    except OSError:
        pass
