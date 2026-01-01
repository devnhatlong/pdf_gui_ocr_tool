# === generate_license.py ===
# Tool dành cho Admin để tạo License Key (GUI)

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os
from utils.license_utils import generate_license_key

def main():
    root = tk.Tk()
    root.title("Công cụ tạo License Key")
    root.geometry("700x600")
    root.resizable(True, True)
    root.minsize(700, 550)
    
    # Set icon nếu có
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base_dir, "assets", "logo.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except:
        pass
    
    # Frame chính
    main_frame = tk.Frame(root, padx=30, pady=30)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Tiêu đề
    title_label = tk.Label(
        main_frame,
        text="🔑 CÔNG CỤ TẠO LICENSE KEY",
        font=("Arial", 16, "bold"),
        pady=10
    )
    title_label.pack()
    
    # Hướng dẫn
    info_text = (
        "1. Yêu cầu người dùng chạy: python get_machine_id.py\n"
        "2. Người dùng sẽ copy Machine ID và gửi cho bạn\n"
        "3. Nhập Machine ID vào đây để tạo License Key"
    )
    tk.Label(
        main_frame,
        text=info_text,
        font=("Arial", 9),
        justify=tk.LEFT,
        fg="gray",
        anchor="w"
    ).pack(fill=tk.X, pady=(0, 20))
    
    # Machine ID input
    machine_id_frame = tk.Frame(main_frame)
    machine_id_frame.pack(fill=tk.X, pady=10)
    
    tk.Label(
        machine_id_frame,
        text="Machine ID (32 ký tự):",
        font=("Arial", 10, "bold"),
        anchor="w"
    ).pack(fill=tk.X, pady=(0, 5))
    
    machine_id_entry = tk.Entry(
        machine_id_frame,
        width=70,
        font=("Courier", 10)
    )
    machine_id_entry.pack(fill=tk.X)
    machine_id_entry.focus()
    
    # Bind Enter để tự động chuyển sang ô tiếp theo
    def on_machine_id_enter(event):
        expiry_entry.focus()
    machine_id_entry.bind("<Return>", on_machine_id_enter)
    
    # Expiry date input
    expiry_frame = tk.Frame(main_frame)
    expiry_frame.pack(fill=tk.X, pady=10)
    
    tk.Label(
        expiry_frame,
        text="Ngày hết hạn (YYYY-MM-DD):",
        font=("Arial", 10, "bold"),
        anchor="w"
    ).pack(fill=tk.X, pady=(0, 5))
    
    expiry_entry = tk.Entry(
        expiry_frame,
        width=70,
        font=("Arial", 10)
    )
    expiry_entry.pack(fill=tk.X)
    expiry_entry.insert(0, "2099-12-31")  # Giá trị mặc định
    
    # Hướng dẫn ngày hết hạn
    tk.Label(
        expiry_frame,
        text="(Để trống hoặc nhập 2099-12-31 cho license vĩnh viễn)",
        font=("Arial", 8),
        fg="gray",
        anchor="w"
    ).pack(fill=tk.X, pady=(2, 0))
    
    # Status label
    status_label = tk.Label(
        main_frame,
        text="",
        font=("Arial", 9),
        fg="red",
        anchor="w"
    )
    status_label.pack(fill=tk.X, pady=10)
    
    # License Key output
    output_frame = tk.Frame(main_frame)
    output_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
    
    tk.Label(
        output_frame,
        text="License Key đã tạo:",
        font=("Arial", 10, "bold"),
        anchor="w"
    ).pack(fill=tk.X, pady=(0, 5))
    
    # Text widget với scrollbar
    text_frame = tk.Frame(output_frame)
    text_frame.pack(fill=tk.BOTH, expand=True)
    
    scrollbar = tk.Scrollbar(text_frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    license_text = tk.Text(
        text_frame,
        width=70,
        height=6,
        font=("Courier", 9),
        wrap=tk.WORD,
        yscrollcommand=scrollbar.set,
        state="disabled"
    )
    license_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
    scrollbar.config(command=license_text.yview)
    
    def generate_license():
        """Tạo license key"""
        machine_id = machine_id_entry.get().strip().upper()
        expiry_date = expiry_entry.get().strip()
        
        # Validate Machine ID
        if not machine_id:
            status_label.config(text="❌ Vui lòng nhập Machine ID", fg="red")
            return
        
        if len(machine_id) != 32:
            status_label.config(
                text=f"❌ Machine ID phải có 32 ký tự (hiện tại: {len(machine_id)} ký tự)",
                fg="red"
            )
            return
        
        # Validate expiry date
        if not expiry_date:
            expiry_date = "2099-12-31"
        
        try:
            from datetime import datetime
            datetime.strptime(expiry_date, "%Y-%m-%d")
        except ValueError:
            status_label.config(
                text="❌ Ngày hết hạn không hợp lệ (format: YYYY-MM-DD, ví dụ: 2025-12-31)",
                fg="red"
            )
            return
        
        try:
            # Tạo license key
            license_key = generate_license_key(machine_id, expiry_date)
            
            # Hiển thị license key
            license_text.config(state="normal")
            license_text.delete(1.0, tk.END)
            license_text.insert(1.0, license_key)
            license_text.config(state="disabled")
            
            # Copy vào clipboard
            root.clipboard_clear()
            root.clipboard_append(license_key)
            
            status_label.config(
                text=f"✅ License Key đã được tạo và copy vào clipboard! (Hết hạn: {expiry_date})",
                fg="green"
            )
            
        except Exception as e:
            status_label.config(text=f"❌ Lỗi: {str(e)}", fg="red")
    
    def copy_license():
        """Copy license key vào clipboard"""
        license_key = license_text.get(1.0, tk.END).strip()
        if not license_key:
            messagebox.showwarning("Cảnh báo", "Chưa có License Key nào được tạo!")
            return
        
        root.clipboard_clear()
        root.clipboard_append(license_key)
        messagebox.showinfo("Thành công", "Đã copy License Key vào clipboard!")
    
    def clear_all():
        """Xóa tất cả"""
        machine_id_entry.delete(0, tk.END)
        expiry_entry.delete(0, tk.END)
        expiry_entry.insert(0, "2099-12-31")
        license_text.config(state="normal")
        license_text.delete(1.0, tk.END)
        license_text.config(state="disabled")
        status_label.config(text="")
        machine_id_entry.focus()
    
    # Button frame
    button_frame = tk.Frame(main_frame)
    button_frame.pack(fill=tk.X, pady=(20, 0))
    
    # Nút Tạo License Key (nút chính, lớn hơn)
    create_btn = tk.Button(
        button_frame,
        text="🔑 Tạo License Key",
        command=generate_license,
        bg="green",
        fg="white",
        font=("Arial", 12, "bold"),
        padx=25,
        pady=10,
        cursor="hand2"
    )
    create_btn.pack(side=tk.LEFT, padx=(0, 10))
    
    # Frame cho các nút phụ
    sub_button_frame = tk.Frame(button_frame)
    sub_button_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
    
    tk.Button(
        sub_button_frame,
        text="📋 Copy",
        command=copy_license,
        bg="blue",
        fg="white",
        font=("Arial", 10),
        padx=15,
        pady=8,
        cursor="hand2"
    ).pack(side=tk.LEFT, padx=(0, 5))
    
    tk.Button(
        sub_button_frame,
        text="🗑️ Xóa",
        command=clear_all,
        font=("Arial", 10),
        padx=15,
        pady=8,
        cursor="hand2"
    ).pack(side=tk.LEFT, padx=(0, 5))
    
    tk.Button(
        button_frame,
        text="❌ Thoát",
        command=root.quit,
        font=("Arial", 10),
        padx=15,
        pady=8,
        cursor="hand2"
    ).pack(side=tk.RIGHT)
    
    # Bind Enter trên expiry entry để tạo license
    def on_expiry_enter(event):
        generate_license()
    expiry_entry.bind("<Return>", on_expiry_enter)
    
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nĐã hủy.")
    except Exception as e:
        try:
            messagebox.showerror("Lỗi", f"Lỗi: {e}")
        except:
            print(f"\n❌ Lỗi: {e}")
