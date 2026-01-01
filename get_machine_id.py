# === get_machine_id.py ===
# Tool dành cho người dùng để lấy Machine ID
# Cách dùng: python get_machine_id.py

import sys
import tkinter as tk
from tkinter import messagebox
from utils.license_utils import get_machine_id

def main():
    # Tạo cửa sổ đơn giản
    root = tk.Tk()
    root.title("Lấy Machine ID")
    root.geometry("600x250")
    root.resizable(False, False)
    
    # Lấy Machine ID
    machine_id = get_machine_id()
    
    # Frame chính
    main_frame = tk.Frame(root, padx=20, pady=20)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Tiêu đề
    tk.Label(
        main_frame,
        text="Mã máy của bạn (Machine ID)",
        font=("Arial", 14, "bold"),
        pady=10
    ).pack()
    
    # Machine ID display
    id_frame = tk.Frame(main_frame)
    id_frame.pack(fill=tk.X, pady=10)
    
    machine_entry = tk.Entry(
        id_frame,
        width=70,
        font=("Courier", 11),
        justify=tk.CENTER
    )
    machine_entry.pack(fill=tk.X)
    machine_entry.insert(0, machine_id)
    machine_entry.config(state="readonly")
    
    # Nút Copy
    def copy_to_clipboard():
        root.clipboard_clear()
        root.clipboard_append(machine_id)
        messagebox.showinfo("Thành công", "Đã copy Machine ID vào clipboard!")
    
    button_frame = tk.Frame(main_frame)
    button_frame.pack(fill=tk.X, pady=20)
    
    tk.Button(
        button_frame,
        text="📋 Copy Machine ID",
        command=copy_to_clipboard,
        bg="blue",
        fg="white",
        font=("Arial", 11, "bold"),
        padx=20,
        pady=5
    ).pack()
    
    # Hướng dẫn
    tk.Label(
        main_frame,
        text="Gửi Machine ID này cho người quản trị để nhận License Key",
        font=("Arial", 9),
        fg="gray"
    ).pack(pady=10)
    
    # Chạy
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Lỗi: {e}")
        input("Nhấn Enter để thoát...")

