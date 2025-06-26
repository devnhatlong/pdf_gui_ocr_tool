
def pdf_to_images(pdf_path, max_pages=1):
    from config import DPI, TEMP_IMAGE_FOLDER
    from pdf2image import convert_from_path
    import os

    os.makedirs(TEMP_IMAGE_FOLDER, exist_ok=True)
    output_path = os.path.join(TEMP_IMAGE_FOLDER, os.path.basename(pdf_path) + "_page1.png")

    if not os.path.exists(output_path):
        images = convert_from_path(pdf_path, dpi=DPI)
        if images:
            images[0].save(output_path, "PNG")
    return [output_path]
