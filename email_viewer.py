import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, PhotoImage
import imaplib
import email
from email.header import decode_header
import threading
import os
from models import Account, AppConfig

import sys

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

class EmailViewerWindow(ctk.CTkToplevel):
    def __init__(self, parent, account: Account, config: AppConfig):
        super().__init__(parent)
        self.account = account
        self.config = config
        
        self.title(f"Email Viewer - {self.account.email}")
        self.geometry("900x500")
        
        # Set Window Icon
        icon_png_path = get_resource_path("X.png")
        icon_ico_path = get_resource_path("X.ico")
        
        try:
            if os.path.exists(icon_ico_path):
                self.iconbitmap(icon_ico_path)
                self.after(200, lambda: self.iconbitmap(icon_ico_path))
            if os.path.exists(icon_png_path):
                self.iconphoto(False, PhotoImage(file=icon_png_path))
        except Exception as e:
            print(f"Không thể load icon: {e}")
                
        # Biến cờ để theo dõi trạng thái cửa sổ
        self.is_closed = False
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Configure layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        
        # Top Header Frame
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)
        
        self.lbl_status = ctk.CTkLabel(self.header_frame, text="Đang kết nối và tải danh sách email...", font=("Arial", 14, "bold"), text_color="#2563eb")
        self.lbl_status.grid(row=0, column=0, sticky="w")
        
        # Create Treeview (Table) for emails
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Treeview", 
                        background="#ffffff",
                        foreground="black",
                        rowheight=30,
                        fieldbackground="#ffffff",
                        font=("Arial", 11))
        style.configure("Treeview.Heading", 
                        font=("Arial", 11, "bold"), 
                        background="#f3f4f6", 
                        foreground="black")
        style.map("Treeview", background=[("selected", "#dbeafe")])

        # Frame chứa Treeview và Scrollbar
        self.table_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.table_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.table_frame.grid_rowconfigure(0, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

        columns = ("STT", "Người gửi", "Tiêu đề", "Ngày")
        self.tree = ttk.Treeview(self.table_frame, columns=columns, show="headings", selectmode="browse")
        
        # Define headings
        self.tree.heading("STT", text="STT", anchor="center")
        self.tree.heading("Người gửi", text="Người gửi", anchor="w")
        self.tree.heading("Tiêu đề", text="Tiêu đề", anchor="w")
        self.tree.heading("Ngày", text="Ngày", anchor="w")
        
        # Define columns
        self.tree.column("STT", width=50, minwidth=50, stretch=False, anchor="center")
        self.tree.column("Người gửi", width=200, minwidth=150)
        self.tree.column("Tiêu đề", width=400, minwidth=200)
        self.tree.column("Ngày", width=200, minwidth=150)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(self.table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Start loading emails in a separate thread
        threading.Thread(target=self.load_emails, daemon=True).start()

    def on_close(self):
        self.is_closed = True
        self.destroy()

    def update_status(self, text, color="#1f2937"):
        if not self.is_closed:
            # Sử dụng after để đảm bảo UI update được gọi từ main thread
            self.after(0, lambda: self._update_status_ui(text, color))
            
    def _update_status_ui(self, text, color):
        if not self.is_closed and self.winfo_exists():
            self.lbl_status.configure(text=text, text_color=color)

    def insert_row(self, values):
        if not self.is_closed:
            self.after(0, lambda: self._insert_row_ui(values))
            
    def _insert_row_ui(self, values):
        if not self.is_closed and self.winfo_exists():
            self.tree.insert("", "end", values=values)

    def decode_str(self, s, encoding):
        if isinstance(s, bytes):
            if encoding:
                try:
                    return s.decode(encoding)
                except:
                    return s.decode('utf-8', errors='ignore')
            else:
                return s.decode('utf-8', errors='ignore')
        return str(s)

    def load_emails(self):
        mail = None
        try:
            if self.config.use_ssl:
                mail = imaplib.IMAP4_SSL(self.config.imap_server, self.config.imap_port, timeout=20)
            else:
                mail = imaplib.IMAP4(self.config.imap_server, self.config.imap_port, timeout=20)
            
            mail.login(self.account.email, self.account.password)
            
            status, _ = mail.select("INBOX", readonly=True)
            if status != "OK":
                self.update_status("Không thể mở INBOX.", "#dc2626")
                return

            self.update_status("Đang đọc danh sách email...", "#2563eb")
            
            status, response = mail.search(None, "ALL")
            if status != "OK":
                self.update_status("Lỗi khi tìm kiếm email.", "#dc2626")
                return

            email_ids = response[0].split()
            if not email_ids:
                self.update_status("Hộp thư trống.", "#4b5563")
                return

            # Lấy tối đa 15 email mới nhất cho nhẹ
            latest_email_ids = email_ids[-15:]
            self.update_status(f"Đã tải {len(latest_email_ids)} email mới nhất.", "#16a34a")

            for i, e_id in enumerate(reversed(latest_email_ids), 1):
                if self.is_closed:
                    break # Dừng ngay nếu cửa sổ đã bị đóng
                    
                # CHỈ FETCH HEADER - Cực kỳ nhanh và nhẹ (bỏ BODY)
                status, msg_data = mail.fetch(e_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if status != "OK":
                    continue
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject, encoding = decode_header(msg.get("Subject", "No Subject"))[0]
                        subject = self.decode_str(subject, encoding)
                        
                        from_header, encoding = decode_header(msg.get("From", "Unknown"))[0]
                        from_header = self.decode_str(from_header, encoding)
                        
                        date_header = msg.get("Date", "Unknown Date")
                        
                        # Chèn trực tiếp vào bảng
                        self.insert_row((i, from_header, subject, date_header))
                        
        except Exception as e:
            self.update_status(f"Lỗi: {str(e)}", "#dc2626")
        finally:
            if mail:
                try: mail.logout()
                except: pass
