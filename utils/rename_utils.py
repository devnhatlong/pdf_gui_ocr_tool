import re

def extract_metadata(text):
    # Mẫu đơn giản, có thể thay đổi sau
    co_quan = re.search(r"(BỘ\s[\w\s]+|UBND\s[\w\s]+|CÔNG AN\s[\w\s]+)", text.upper())
    so_hieu = re.search(r"S[ốo]:\s*(\S+)", text)
    ngay = re.search(r"ngày\s*(\d{1,2}).*tháng\s*(\d{1,2}).*năm\s*(\d{4})", text)

    return {
        "co_quan": co_quan.group(1).strip().replace(" ", "_") if co_quan else "unknown",
        "so_hieu": so_hieu.group(1) if so_hieu else "unknown",
        "ngay": f"{ngay.group(1).zfill(2)}-{ngay.group(2).zfill(2)}-{ngay.group(3)}" if ngay else "unknown"
    }

def generate_filename(meta):
    return f"VB_{meta['co_quan']}_{meta['so_hieu']}_{meta['ngay']}.pdf"