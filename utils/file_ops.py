import os

def list_pdfs_in_folder(folder):
    return [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]

def rename_file(old_path, new_path):
    os.rename(old_path, new_path)

def delete_temp_images(folder):
    for f in os.listdir(folder):
        if f.endswith(".png"):
            os.remove(os.path.join(folder, f))