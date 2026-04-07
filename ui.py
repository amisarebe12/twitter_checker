import customtkinter as ctk
from tkinter import filedialog, messagebox, PhotoImage
import threading
from concurrent.futures import ThreadPoolExecutor
import os
from PIL import Image
import pymysql
import json
import time

from models import Account, AppConfig
from core import DefaultAccountParser, TwitterImapChecker, TwitterTimeAdderChecker
from email_viewer import EmailViewerWindow
from updater import GitHubUpdater

import sys

def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(__file__)
    return os.path.join(base_path, relative_path)

ctk.set_appearance_mode("Light")  # Chuyển sang Light/Dark nhẹ nhàng thay vì System bóng bẩy
ctk.set_default_color_theme("blue") # Vẫn giữ theme xanh nhưng màu lì hơn

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Twitter Checker - IMAP")
        self.geometry("900x650")
        
        # Set Application Icon (Title bar and Taskbar)
        icon_png_path = get_resource_path("X.png")
        icon_ico_path = get_resource_path("X.ico")
        
        try:
            # Ưu tiên dùng .ico cho góc trái màn hình (Windows)
            if os.path.exists(icon_ico_path):
                self.iconbitmap(icon_ico_path)
                self.after(200, lambda: self.iconbitmap(icon_ico_path))
            # Dùng .png cho Taskbar nếu được hỗ trợ
            if os.path.exists(icon_png_path):
                self.iconphoto(False, PhotoImage(file=icon_png_path))
        except Exception as e:
            print(f"Không thể load icon: {e}")
        
        # Tạo thư mục config trong AppData để tránh lỗi phân quyền
        appdata_dir = os.path.join(os.getenv('APPDATA', os.path.expanduser('~')), 'TwitterChecker')
        if not os.path.exists(appdata_dir):
            try:
                os.makedirs(appdata_dir)
            except Exception:
                appdata_dir = os.path.dirname(__file__)
        self.config_path = os.path.join(appdata_dir, "config.json")
        
        self.config = AppConfig()
        self.load_app_config()
        
        self.accounts: list[Account] = []
        self.parser = DefaultAccountParser()
        self.checker = TwitterImapChecker()
        self.is_running = False
        
        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.configure(fg_color="#E5E7EB") # Nền app màu xám nhạt nhất
        
        # Create TabView
        self.tabview = ctk.CTkTabview(
            self, 
            corner_radius=8, 
            fg_color="#F3F4F6", 
            segmented_button_fg_color="#E5E7EB", 
            segmented_button_selected_color="#FFFFFF", 
            segmented_button_selected_hover_color="#FFFFFF", 
            segmented_button_unselected_color="#E5E7EB", 
            segmented_button_unselected_hover_color="#D1D5DB", 
            text_color="#374151"
        )
        self.tabview.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        
        self.tab_main = self.tabview.add("Main")
        self.tab_auto = self.tabview.add("Auto")
        self.tab_add_time = self.tabview.add("Add Time")
        self.tab_mysql = self.tabview.add("MySQL")
        self.tab_settings = self.tabview.add("Cài Đặt")
        
        # Đặt màu nền chính cho tab là xám nhạt để các Card trắng nổi bật
        self.tab_main.configure(fg_color="#F3F4F6")
        self.tab_auto.configure(fg_color="#F3F4F6")
        self.tab_add_time.configure(fg_color="#F3F4F6")
        self.tab_mysql.configure(fg_color="#F3F4F6")
        self.tab_settings.configure(fg_color="#F3F4F6")
        
        self.setup_main_tab()
        self.setup_auto_tab()
        self.setup_add_time_tab()
        self.setup_mysql_tab()
        self.setup_settings_tab()
        self.setup_changelog()
        
    def load_app_config(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.config.imap_server = data.get("imap_server", self.config.imap_server)
                    self.config.imap_port = data.get("imap_port", self.config.imap_port)
                    self.config.use_ssl = data.get("use_ssl", self.config.use_ssl)
                    self.config.mysql_host = data.get("mysql_host", self.config.mysql_host)
                    self.config.mysql_user = data.get("mysql_user", self.config.mysql_user)
                    self.config.mysql_password = data.get("mysql_password", self.config.mysql_password)
                    self.config.mysql_database = data.get("mysql_database", self.config.mysql_database)
                    self.config.auto_save_path = data.get("auto_save_path", self.config.auto_save_path)
        except Exception as e:
            error_msg = f"Lỗi khi load cấu hình từ {self.config_path}: {e}"
            print(error_msg)
            messagebox.showwarning("Cảnh báo", error_msg)

    def save_app_config(self):
        try:
            data = {
                "imap_server": self.config.imap_server,
                "imap_port": self.config.imap_port,
                "use_ssl": self.config.use_ssl,
                "mysql_host": self.config.mysql_host,
                "mysql_user": self.config.mysql_user,
                "mysql_password": self.config.mysql_password,
                "mysql_database": self.config.mysql_database,
                "auto_save_path": self.config.auto_save_path
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            error_msg = f"Lỗi khi lưu cấu hình vào {self.config_path}:\n{e}"
            print(error_msg)
            # Log into MySQL console if UI is ready
            if hasattr(self, 'txt_mysql_log'):
                self.log_mysql(f"[ERROR] {error_msg}")
            messagebox.showerror("Lỗi", error_msg)

    def setup_changelog(self):
        # Đọc dữ liệu từ changelog.json
        self.app_version = "Unknown"
        self.changelog_data = []
        changelog_path = os.path.join(os.path.dirname(__file__), "changelog.json")
        try:
            if os.path.exists(changelog_path):
                with open(changelog_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.app_version = data.get("version", "Unknown")
                    self.changelog_data = data.get("history", [])
        except Exception as e:
            print(f"Lỗi đọc changelog: {e}")

        # Label hiển thị phiên bản ở góc dưới phải
        self.lbl_version = ctk.CTkLabel(
            self, 
            text=f"v{self.app_version}", 
            font=("Arial", 11, "underline"), 
            text_color="#6B7280",
            cursor="hand2"
        )
        self.lbl_version.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-5)
        self.lbl_version.bind("<Button-1>", self.toggle_changelog)

        # Mini-window hiển thị changelog (ẩn đi lúc đầu)
        self.changelog_frame = ctk.CTkFrame(self, fg_color="#FFFFFF", border_width=1, border_color="#E5E7EB", corner_radius=8, width=300, height=250)
        # Chặn không cho frame tự động thu nhỏ theo nội dung
        self.changelog_frame.pack_propagate(False) 
        
        # Tiêu đề
        header = ctk.CTkFrame(self.changelog_frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=10)
        ctk.CTkLabel(header, text="Lịch sử cập nhật", font=("Arial", 13, "bold"), text_color="#111827").pack(side="left")
        
        # Nút đóng
        btn_close = ctk.CTkButton(header, text="✕", width=20, height=20, fg_color="transparent", text_color="#6B7280", hover_color="#F3F4F6", command=self.toggle_changelog)
        btn_close.pack(side="right")

        # Nội dung changelog
        self.txt_changelog = ctk.CTkTextbox(self.changelog_frame, fg_color="#F9FAFB", text_color="#374151", border_width=0, wrap="word")
        self.txt_changelog.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Điền dữ liệu
        changelog_text = ""
        for item in self.changelog_data:
            changelog_text += f"v{item.get('version', '')} ({item.get('date', '')})\n"
            for change in item.get('changes', []):
                changelog_text += f"• {change}\n"
            changelog_text += "\n"
            
        self.txt_changelog.insert("1.0", changelog_text.strip())
        self.txt_changelog.configure(state="disabled")

        # Khởi tạo Updater và tự động check ngầm sau 1.5s
        self.updater = GitHubUpdater("https://github.com/amisarebe12/twitter_checker.git", self.app_version)
        self.after(1500, self.start_check_update_async)

    def start_check_update_async(self):
        def check():
            if self.updater.check_for_update():
                self.after(0, self.show_update_popup)
        threading.Thread(target=check, daemon=True).start()

    def show_update_popup(self):
        # Tạo popup thông báo cập nhật
        popup = ctk.CTkToplevel(self)
        popup.title("Cập nhật phiên bản mới")
        popup.geometry("400x250")
        popup.attributes('-topmost', True)
        popup.resizable(False, False)
        
        # Center popup
        popup.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (400 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (250 // 2)
        popup.geometry(f"+{x}+{y}")
        
        # UI Elements
        lbl_title = ctk.CTkLabel(popup, text=f"Đã có phiên bản v{self.updater.latest_version}", font=("Arial", 16, "bold"))
        lbl_title.pack(pady=(20, 5))
        
        txt_notes = ctk.CTkTextbox(popup, height=100, wrap="word")
        txt_notes.pack(padx=20, pady=5, fill="x")
        txt_notes.insert("1.0", self.updater.release_notes)
        txt_notes.configure(state="disabled")
        
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=15)
        
        btn_update = ctk.CTkButton(btn_frame, text="Cập nhật ngay", fg_color="#2563EB", hover_color="#1D4ED8", 
                                   command=lambda: [popup.destroy(), self.start_download_update()])
        btn_update.pack(side="left", padx=10)
        
        btn_cancel = ctk.CTkButton(btn_frame, text="Bỏ qua", fg_color="#E5E7EB", text_color="#374151", hover_color="#D1D5DB", 
                                   command=popup.destroy)
        btn_cancel.pack(side="right", padx=10)

    def start_download_update(self):
        # Hiển thị UI tiến trình ở góc dưới màn hình chính
        self.update_progress_frame = ctk.CTkFrame(self, fg_color="#F3F4F6", corner_radius=8, height=40)
        self.update_progress_frame.place(relx=0.02, rely=0.98, anchor="sw", relwidth=0.4)
        
        self.lbl_update_status = ctk.CTkLabel(self.update_progress_frame, text="Đang tải bản cập nhật: 0%", font=("Arial", 11), text_color="#374151")
        self.lbl_update_status.pack(side="left", padx=10, pady=10)
        
        self.pb_update = ctk.CTkProgressBar(self.update_progress_frame, width=150, progress_color="#10B981")
        self.pb_update.pack(side="right", padx=10, pady=10)
        self.pb_update.set(0)
        
        # Bắt đầu tải
        self.updater.download_and_install(
            progress_callback=self.on_update_progress,
            completion_callback=self.on_update_complete
        )

    def on_update_progress(self, percent):
        def update_ui():
            if hasattr(self, 'pb_update'):
                self.pb_update.set(percent)
                self.lbl_update_status.configure(text=f"Đang tải bản cập nhật: {int(percent * 100)}%")
        self.after(0, update_ui)

    def on_update_complete(self, file_path, success, error_msg):
        def finalize():
            if success:
                self.lbl_update_status.configure(text="Đang cài đặt...")
                # Đợi một chút rồi chạy cài đặt
                self.after(500, lambda: self.updater.run_installer(file_path))
            else:
                self.lbl_update_status.configure(text="Lỗi tải xuống!", text_color="#EF4444")
                messagebox.showerror("Lỗi Cập Nhật", f"Không thể tải bản cập nhật:\n{error_msg}")
                self.after(3000, self.update_progress_frame.destroy)
        self.after(0, finalize)

    def toggle_changelog(self, event=None):
        if self.changelog_frame.winfo_ismapped():
            self.changelog_frame.place_forget()
        else:
            self.changelog_frame.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-30)
        
    def setup_main_tab(self):
        self.tab_main.grid_columnconfigure(0, weight=1)
        self.tab_main.grid_columnconfigure(1, weight=1)
        self.tab_main.grid_rowconfigure(3, weight=1)
        
        # Top Frame for Inputs (Card 1)
        self.input_frame = ctk.CTkFrame(self.tab_main, fg_color="#FFFFFF", corner_radius=8)
        self.input_frame.grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.input_frame, text="Nhập danh sách tài khoản", font=("Arial", 13, "bold"), text_color="#111827").grid(row=0, column=0, columnspan=2, padx=15, pady=(10, 0), sticky="w")
        
        self.txt_accounts = ctk.CTkTextbox(self.input_frame, height=70, border_width=1, border_color="#E5E7EB", fg_color="#F9FAFB", text_color="#374151", corner_radius=6)
        self.txt_accounts.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="ew")
        self.txt_accounts.insert("1.0", "Nhập tài khoản (tự động nhận diện email chứa @ và mật khẩu theo sau), mỗi tài khoản 1 dòng...")
        
        self.btn_load_file = ctk.CTkButton(self.input_frame, text="Tải từ file", fg_color="#F3F4F6", text_color="#374151", hover_color="#E5E7EB", border_width=1, border_color="#D1D5DB", command=self.load_from_file, corner_radius=6)
        self.btn_load_file.grid(row=1, column=1, padx=(5, 15), pady=10)
        
        self.btn_add = ctk.CTkButton(self.input_frame, text="Thêm vào danh sách", fg_color="#4F46E5", hover_color="#4338CA", command=self.add_accounts, corner_radius=6)
        self.btn_add.grid(row=2, column=0, columnspan=2, padx=15, pady=(0, 15))
        
        # Controls Frame (Card 2)
        self.control_frame = ctk.CTkFrame(self.tab_main, fg_color="#FFFFFF", corner_radius=8)
        self.control_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        
        # Thread Config
        ctk.CTkLabel(self.control_frame, text="Số luồng:", font=("Arial", 12), text_color="#374151").pack(side="left", padx=(15, 5), pady=10)
        self.entry_threads = ctk.CTkEntry(self.control_frame, width=60, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_threads.pack(side="left", padx=5, pady=10)
        self.entry_threads.insert(0, "5")
        
        # Sửa màu thành màu lì (matte) không bóng
        self.btn_start = ctk.CTkButton(self.control_frame, text="Bắt đầu Check", fg_color="#059669", hover_color="#047857", corner_radius=6, command=self.start_checking)
        self.btn_start.pack(side="left", padx=(20, 10), pady=10)
        
        self.btn_stop = ctk.CTkButton(self.control_frame, text="Dừng", fg_color="#E11D48", hover_color="#BE123C", state="disabled", corner_radius=6, command=self.stop_checking)
        self.btn_stop.pack(side="left", padx=10, pady=10)
        
        self.btn_clear = ctk.CTkButton(self.control_frame, text="Xóa danh sách", fg_color="#F3F4F6", text_color="#EF4444", hover_color="#FEE2E2", border_width=1, border_color="#FCA5A5", corner_radius=6, command=self.clear_list)
        self.btn_clear.pack(side="right", padx=15, pady=10)
        
        # Stats Frame - Thiết kế hiện đại, nhỏ gọn và có thanh tiến trình (Card 3)
        self.stats_frame = ctk.CTkFrame(self.tab_main, fg_color="#FFFFFF", corner_radius=8)
        self.stats_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        self.stats_frame.grid_columnconfigure(0, weight=1) # Dành không gian cho Progress bar
        
        # Labels Container
        self.labels_frame = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        self.labels_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 5))
        
        self.lbl_total = ctk.CTkLabel(self.labels_frame, text="Tổng: 0", font=("Arial", 12, "bold"), text_color="#4B5563")
        self.lbl_total.pack(side="left", padx=(0, 20))
        
        self.lbl_success = ctk.CTkLabel(self.labels_frame, text="Thành công: 0", font=("Arial", 12, "bold"), text_color="#10B981")
        self.lbl_success.pack(side="left", padx=20)
        
        self.lbl_failed = ctk.CTkLabel(self.labels_frame, text="Thất bại: 0", font=("Arial", 12, "bold"), text_color="#EF4444")
        self.lbl_failed.pack(side="left", padx=20)
        
        self.lbl_percent = ctk.CTkLabel(self.labels_frame, text="0%", font=("Arial", 12, "bold"), text_color="#3B82F6")
        self.lbl_percent.pack(side="right", padx=0)
        
        # Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self.stats_frame, height=6, corner_radius=3, progress_color="#3B82F6", fg_color="#E5E7EB")
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        self.progress_bar.set(0) # Khởi tạo giá trị 0%
        
        # Results Frame (Card 4)
        self.results_frame = ctk.CTkFrame(self.tab_main, fg_color="#FFFFFF", corner_radius=8)
        self.results_frame.grid(row=3, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="nsew")
        self.results_frame.grid_columnconfigure(0, weight=1)
        self.results_frame.grid_columnconfigure(1, weight=1)
        self.results_frame.grid_rowconfigure(1, weight=1)
        
        # --- Success Column ---
        self.frame_success = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        self.frame_success.grid(row=0, column=0, rowspan=2, padx=(15, 10), pady=15, sticky="nsew")
        self.frame_success.grid_columnconfigure(0, weight=1)
        self.frame_success.grid_rowconfigure(1, weight=1)
        
        # Header for Success
        self.header_success = ctk.CTkFrame(self.frame_success, fg_color="transparent")
        self.header_success.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.header_success.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.header_success, text="Thành công (Live)", text_color="#10B981", font=("Arial", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.btn_copy_success = ctk.CTkButton(self.header_success, text="Copy Tất Cả", width=80, height=26, fg_color="transparent", text_color="#059669", border_width=1, border_color="#059669", hover_color="#ECFDF5", corner_radius=6, command=lambda: self.copy_to_clipboard(self.txt_success))
        self.btn_copy_success.grid(row=0, column=1, sticky="e")
        
        self.txt_success = ctk.CTkTextbox(self.frame_success, state="disabled", border_width=1, corner_radius=6, border_color="#D1FAE5", fg_color="#F9FAFB", text_color="#374151")
        self.txt_success.grid(row=1, column=0, sticky="nsew")
        self.txt_success.bind("<Double-1>", lambda e: self.on_result_double_click(e, self.txt_success))
        
        # --- Failed Column ---
        self.frame_failed = ctk.CTkFrame(self.results_frame, fg_color="transparent")
        self.frame_failed.grid(row=0, column=1, rowspan=2, padx=(10, 15), pady=15, sticky="nsew")
        self.frame_failed.grid_columnconfigure(0, weight=1)
        self.frame_failed.grid_rowconfigure(1, weight=1)
        
        # Header for Failed
        self.header_failed = ctk.CTkFrame(self.frame_failed, fg_color="transparent")
        self.header_failed.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.header_failed.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.header_failed, text="Thất bại (Die / Lỗi)", text_color="#EF4444", font=("Arial", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.btn_copy_failed = ctk.CTkButton(self.header_failed, text="Copy Tất Cả", width=80, height=26, fg_color="transparent", text_color="#E11D48", border_width=1, border_color="#E11D48", hover_color="#FEF2F2", corner_radius=6, command=lambda: self.copy_to_clipboard(self.txt_failed))
        self.btn_copy_failed.grid(row=0, column=1, sticky="e")
        
        self.txt_failed = ctk.CTkTextbox(self.frame_failed, state="disabled", border_width=1, corner_radius=6, border_color="#FEE2E2", fg_color="#F9FAFB", text_color="#374151")
        self.txt_failed.grid(row=1, column=0, sticky="nsew")
        self.txt_failed.bind("<Double-1>", lambda e: self.on_result_double_click(e, self.txt_failed))
        
    def copy_to_clipboard(self, textbox: ctk.CTkTextbox):
        text = textbox.get("1.0", "end-1c")
        if text.strip():
            self.clipboard_clear()
            self.clipboard_append(text)
            self.update()
            messagebox.showinfo("Thành công", "Đã copy danh sách vào Clipboard!")
        else:
            messagebox.showwarning("Trống", "Không có dữ liệu để copy.")
            
    def on_result_double_click(self, event, textbox: ctk.CTkTextbox):
        # Lấy dòng hiện tại tại vị trí con trỏ chuột (sử dụng tọa độ tương đối từ event)
        try:
            index = textbox.index(f"@{event.x},{event.y}")
            line_num = index.split(".")[0]
            line_text = textbox.get(f"{line_num}.0", f"{line_num}.end").strip()
            
            if not line_text or line_text.startswith("["): # Bỏ qua dòng trống hoặc dòng trạng thái [Đang kiểm tra...]
                return
                
            # Tìm Account tương ứng dựa trên original_line
            # Do kết quả Thất bại có nối thêm "|Lý do", nên cần tách lấy original_line gốc
            search_line = line_text
            if "|" in line_text:
                parts = line_text.split("|")
                # Trích xuất đoạn chứa email/pass
                for acc in self.accounts:
                    if acc.original_line in line_text:
                        EmailViewerWindow(self, acc, self.config)
                        return
                        
        except Exception as e:
            print(f"Lỗi khi mở Email Viewer: {e}")
        
    def get_mysql_connection(self):
        return pymysql.connect(
            host=self.entry_mysql_host.get().strip(),
            user=self.entry_mysql_user.get().strip(),
            password=self.entry_mysql_pass.get().strip(),
            database=self.entry_mysql_db.get().strip(),
            cursorclass=pymysql.cursors.DictCursor
        )

    def log_mysql(self, message):
        if not hasattr(self, '_log_tags_configured'):
            self.txt_mysql_log.tag_config("success", foreground="#10B981") # Xanh lá
            self.txt_mysql_log.tag_config("error", foreground="#EF4444")   # Đỏ
            self.txt_mysql_log.tag_config("warning", foreground="#F59E0B") # Cam
            self.txt_mysql_log.tag_config("info", foreground="#3B82F6")    # Xanh dương
            self._log_tags_configured = True

        tag = "info"
        if "[SUCCESS]" in message:
            tag = "success"
        elif "[ERROR]" in message:
            tag = "error"
        elif "[WARNING]" in message:
            tag = "warning"
            
        self.txt_mysql_log.insert("end", message + "\n", tag)
        self.txt_mysql_log.see("end")

    def test_mysql_connection(self):
        self.btn_mysql_connect.configure(state="disabled", text="Đang kết nối...")
        self.log_mysql("[INFO] Đang kiểm tra kết nối MySQL...")
        threading.Thread(target=self._test_mysql_connection_thread, daemon=True).start()

    def _test_mysql_connection_thread(self):
        try:
            conn = self.get_mysql_connection()
            conn.close()
            self.after(0, self._on_mysql_connect_success)
        except Exception as e:
            self.after(0, self._on_mysql_connect_error, str(e))

    def _on_mysql_connect_success(self):
        self.btn_mysql_connect.configure(state="normal", text="Kết nối")
        self.log_mysql("[SUCCESS] Kết nối MySQL thành công!")
        messagebox.showinfo("Thành công", "Kết nối MySQL thành công!")
        
        # Save config implicitly
        self.config.mysql_host = self.entry_mysql_host.get().strip()
        self.config.mysql_user = self.entry_mysql_user.get().strip()
        self.config.mysql_password = self.entry_mysql_pass.get().strip()
        self.config.mysql_database = self.entry_mysql_db.get().strip()
        self.save_app_config()

    def _on_mysql_connect_error(self, error_msg):
        self.btn_mysql_connect.configure(state="normal", text="Kết nối")
        self.log_mysql(f"[ERROR] Lỗi kết nối: {error_msg}")
        messagebox.showerror("Lỗi", f"Không thể kết nối MySQL:\n{error_msg}")

    def save_mysql_config(self):
        self.config.mysql_host = self.entry_mysql_host.get().strip()
        self.config.mysql_user = self.entry_mysql_user.get().strip()
        self.config.mysql_password = self.entry_mysql_pass.get().strip()
        self.config.mysql_database = self.entry_mysql_db.get().strip()
        self.save_app_config()
        self.log_mysql("[SUCCESS] Đã lưu cấu hình MySQL!")
        messagebox.showinfo("Thành công", "Đã lưu cấu hình MySQL!")

    def download_from_mysql(self):
        table = "accounts"
        
        try:
            conn = self.get_mysql_connection()
            with conn.cursor() as cursor:
                # Dựa trên cấu trúc bảng thực tế: id, UID, Password, Email, EmailPass, 2FA, Time
                query = f"SELECT id, UID, Password, Email, EmailPass, 2FA FROM {table} WHERE Time < NOW() - INTERVAL 30 MINUTE"
                self.log_mysql(f"[INFO] Đang thực thi: {query}")
                
                try:
                    cursor.execute(query)
                except pymysql.err.OperationalError as e:
                    self.log_mysql(f"[WARNING] Truy vấn chuẩn thất bại: {e}. Đang thử lấy tất cả cột (SELECT *)...")
                    query_fallback = f"SELECT * FROM {table} WHERE Time < NOW() - INTERVAL 30 MINUTE"
                    cursor.execute(query_fallback)
                    
                results = cursor.fetchall()
                
                if not results:
                    self.log_mysql("[INFO] Không tìm thấy tài khoản nào thỏa mãn điều kiện (>30p).")
                    messagebox.showinfo("Thông báo", "Không có tài khoản mới (>30p).")
                    return
                    
                downloaded_accounts = []
                self.downloaded_ids = []
                
                for row in results:
                    self.downloaded_ids.append(str(row.get('id', '')))
                    
                    uid = row.get('UID', '')
                    pwd = row.get('Password', '')
                    email = row.get('Email', '')
                    passmail = row.get('EmailPass', '')
                    twofa = row.get('2FA', '')
                    
                    line = f"{uid}|{pwd}|{email}|{passmail}|{twofa}"
                    downloaded_accounts.append(line)
                
                raw_text = "\n".join(downloaded_accounts)
                
                # Parse and add to main list
                new_accounts = self.parser.parse(raw_text)
                self.accounts.extend(new_accounts)
                
                # Append to txt_accounts
                current_text = self.txt_accounts.get("1.0", "end-1c")
                if "Nhập tài khoản" in current_text:
                    self.txt_accounts.delete("1.0", "end")
                    self.txt_accounts.insert("end", raw_text)
                else:
                    self.txt_accounts.insert("end", "\n" + raw_text if current_text.strip() else raw_text)
                
                self.update_results_view()
                self.log_mysql(f"[SUCCESS] Đã tải và thêm {len(new_accounts)} tài khoản vào danh sách.")
                messagebox.showinfo("Thành công", f"Đã tải {len(new_accounts)} tài khoản từ MySQL!")
                
        except Exception as e:
            self.log_mysql(f"[ERROR] Lỗi khi tải dữ liệu: {e}")
            messagebox.showerror("Lỗi", f"Lỗi khi tải dữ liệu:\n{e}")

    def delete_downloaded_mysql(self):
        if not hasattr(self, 'downloaded_ids') or not self.downloaded_ids:
            messagebox.showwarning("Cảnh báo", "Không có tài khoản nào được tải về để xóa!")
            return
            
        table = "accounts"
        try:
            conn = self.get_mysql_connection()
            with conn.cursor() as cursor:
                valid_ids = [i for i in self.downloaded_ids if i]
                if not valid_ids:
                    self.log_mysql("[INFO] Không có ID hợp lệ để xóa (có thể bảng không có cột 'id').")
                    messagebox.showwarning("Cảnh báo", "Không thể xóa: Không có ID hợp lệ (Bảng cần có cột 'id').")
                    return
                    
                format_strings = ','.join(['%s'] * len(valid_ids))
                query = f"DELETE FROM {table} WHERE id IN ({format_strings})"
                self.log_mysql(f"[INFO] Đang thực thi: DELETE FROM {table} WHERE id IN (...)")
                cursor.execute(query, tuple(valid_ids))
                conn.commit()
                
                deleted_count = cursor.rowcount
                self.log_mysql(f"[SUCCESS] Đã xóa {deleted_count} tài khoản khỏi database.")
                messagebox.showinfo("Thành công", f"Đã xóa {deleted_count} tài khoản khỏi database!")
                
                self.downloaded_ids = []
                
        except Exception as e:
            self.log_mysql(f"[ERROR] Lỗi khi xóa dữ liệu: {e}")
            messagebox.showerror("Lỗi", f"Lỗi khi xóa dữ liệu:\n{e}")


    def setup_add_time_tab(self):
        self.tab_add_time.grid_columnconfigure(0, weight=1)
        self.tab_add_time.grid_columnconfigure(1, weight=1)
        self.tab_add_time.grid_rowconfigure(3, weight=1)
        
        self.add_time_accounts = []
        self.add_time_checker = TwitterTimeAdderChecker()
        self.is_add_time_running = False
        
        # Top Frame for Inputs
        self.at_input_frame = ctk.CTkFrame(self.tab_add_time, fg_color="#FFFFFF", corner_radius=8)
        self.at_input_frame.grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="ew")
        self.at_input_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.at_input_frame, text="Nhập danh sách tài khoản (Add Time 2FA)", font=("Arial", 13, "bold"), text_color="#111827").grid(row=0, column=0, columnspan=2, padx=15, pady=(10, 0), sticky="w")
        
        self.at_txt_accounts = ctk.CTkTextbox(self.at_input_frame, height=70, border_width=1, border_color="#E5E7EB", fg_color="#F9FAFB", text_color="#374151", corner_radius=6)
        self.at_txt_accounts.grid(row=1, column=0, padx=(15, 5), pady=10, sticky="ew")
        self.at_txt_accounts.insert("1.0", "Nhập tài khoản, mỗi tài khoản 1 dòng...")
        
        self.at_btn_load_file = ctk.CTkButton(self.at_input_frame, text="Tải từ file", fg_color="#F3F4F6", text_color="#374151", hover_color="#E5E7EB", border_width=1, border_color="#D1D5DB", command=self.at_load_from_file, corner_radius=6)
        self.at_btn_load_file.grid(row=1, column=1, padx=(5, 15), pady=10)
        
        self.at_btn_add = ctk.CTkButton(self.at_input_frame, text="Thêm vào danh sách", fg_color="#18181B", hover_color="#27272A", text_color="#FAFAFA", command=self.at_add_accounts, corner_radius=6)
        self.at_btn_add.grid(row=2, column=0, padx=(15, 5), pady=(0, 15), sticky="ew")
        
        self.at_btn_add_sorted = ctk.CTkButton(self.at_input_frame, text="Thêm Data Đã Có Ngày", fg_color="#FAFAFA", hover_color="#F4F4F5", text_color="#18181B", border_width=1, border_color="#E4E4E7", command=self.at_add_already_sorted_accounts, corner_radius=6)
        self.at_btn_add_sorted.grid(row=2, column=1, padx=(5, 15), pady=(0, 15), sticky="ew")
        
        # Controls Frame
        self.at_control_frame = ctk.CTkFrame(self.tab_add_time, fg_color="#FFFFFF", corner_radius=8)
        self.at_control_frame.grid(row=1, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        
        ctk.CTkLabel(self.at_control_frame, text="Số luồng:", font=("Arial", 12), text_color="#374151").pack(side="left", padx=(15, 5), pady=10)
        self.at_entry_threads = ctk.CTkEntry(self.at_control_frame, width=60, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.at_entry_threads.pack(side="left", padx=5, pady=10)
        self.at_entry_threads.insert(0, "5")
        
        self.at_btn_start = ctk.CTkButton(self.at_control_frame, text="Bắt đầu", fg_color="#18181B", hover_color="#27272A", text_color="#FAFAFA", corner_radius=6, command=self.at_start_checking)
        self.at_btn_start.pack(side="left", padx=(20, 10), pady=10)
        
        self.at_btn_stop = ctk.CTkButton(self.at_control_frame, text="Dừng", fg_color="#FAFAFA", hover_color="#FEE2E2", text_color="#EF4444", border_width=1, border_color="#FECACA", state="disabled", corner_radius=6, command=self.at_stop_checking)
        self.at_btn_stop.pack(side="left", padx=10, pady=10)
        
        self.at_btn_clear = ctk.CTkButton(self.at_control_frame, text="Xóa danh sách", fg_color="#FAFAFA", text_color="#71717A", hover_color="#F4F4F5", border_width=1, border_color="#E4E4E7", corner_radius=6, command=self.at_clear_list)
        self.at_btn_clear.pack(side="right", padx=15, pady=10)
        
        # Stats Frame
        self.at_stats_frame = ctk.CTkFrame(self.tab_add_time, fg_color="#FFFFFF", corner_radius=8)
        self.at_stats_frame.grid(row=2, column=0, columnspan=2, padx=15, pady=5, sticky="ew")
        self.at_stats_frame.grid_columnconfigure(0, weight=1)
        
        self.at_labels_frame = ctk.CTkFrame(self.at_stats_frame, fg_color="transparent")
        self.at_labels_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=(10, 5))
        
        self.at_lbl_total = ctk.CTkLabel(self.at_labels_frame, text="Tổng: 0", font=("Arial", 12, "bold"), text_color="#4B5563")
        self.at_lbl_total.pack(side="left", padx=(0, 20))
        
        self.at_lbl_success = ctk.CTkLabel(self.at_labels_frame, text="Thành công: 0", font=("Arial", 12, "bold"), text_color="#10B981")
        self.at_lbl_success.pack(side="left", padx=20)
        
        self.at_lbl_failed = ctk.CTkLabel(self.at_labels_frame, text="Thất bại: 0", font=("Arial", 12, "bold"), text_color="#EF4444")
        self.at_lbl_failed.pack(side="left", padx=20)
        
        self.at_lbl_percent = ctk.CTkLabel(self.at_labels_frame, text="0%", font=("Arial", 12, "bold"), text_color="#3B82F6")
        self.at_lbl_percent.pack(side="right", padx=0)
        
        self.at_progress_bar = ctk.CTkProgressBar(self.at_stats_frame, height=6, corner_radius=3, progress_color="#3B82F6", fg_color="#E5E7EB")
        self.at_progress_bar.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 15))
        self.at_progress_bar.set(0)
        
        # Results Frame
        self.at_results_frame = ctk.CTkFrame(self.tab_add_time, fg_color="#FFFFFF", corner_radius=8)
        self.at_results_frame.grid(row=3, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="nsew")
        self.at_results_frame.grid_columnconfigure(0, weight=1)
        self.at_results_frame.grid_columnconfigure(1, weight=1)
        self.at_results_frame.grid_rowconfigure(1, weight=1)
        
        # Success Column
        self.at_frame_success = ctk.CTkFrame(self.at_results_frame, fg_color="transparent")
        self.at_frame_success.grid(row=0, column=0, rowspan=2, padx=(15, 10), pady=15, sticky="nsew")
        self.at_frame_success.grid_columnconfigure(0, weight=1)
        self.at_frame_success.grid_rowconfigure(1, weight=1)
        
        self.at_header_success = ctk.CTkFrame(self.at_frame_success, fg_color="transparent")
        self.at_header_success.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.at_header_success.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.at_header_success, text="Thành công", text_color="#10B981", font=("Arial", 13, "bold")).grid(row=0, column=0, sticky="w")
        
        self.at_btn_sort_success = ctk.CTkButton(self.at_header_success, text="Sắp xếp", width=60, height=26, fg_color="#FAFAFA", text_color="#18181B", border_width=1, border_color="#E4E4E7", hover_color="#F4F4F5", corner_radius=6, command=self.at_sort_success_results)
        self.at_btn_sort_success.grid(row=0, column=1, sticky="e", padx=(0, 10))
        
        self.at_btn_copy_success = ctk.CTkButton(self.at_header_success, text="Copy Tất Cả", width=80, height=26, fg_color="#FAFAFA", text_color="#18181B", border_width=1, border_color="#E4E4E7", hover_color="#F4F4F5", corner_radius=6, command=lambda: self.copy_to_clipboard(self.at_txt_success))
        self.at_btn_copy_success.grid(row=0, column=2, sticky="e")
        
        self.at_txt_success = ctk.CTkTextbox(self.at_frame_success, state="disabled", border_width=1, corner_radius=6, border_color="#D1FAE5", fg_color="#F9FAFB", text_color="#374151")
        self.at_txt_success.grid(row=1, column=0, sticky="nsew")
        
        # Failed Column
        self.at_frame_failed = ctk.CTkFrame(self.at_results_frame, fg_color="transparent")
        self.at_frame_failed.grid(row=0, column=1, rowspan=2, padx=(10, 15), pady=15, sticky="nsew")
        self.at_frame_failed.grid_columnconfigure(0, weight=1)
        self.at_frame_failed.grid_rowconfigure(1, weight=1)
        
        self.at_header_failed = ctk.CTkFrame(self.at_frame_failed, fg_color="transparent")
        self.at_header_failed.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.at_header_failed.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(self.at_header_failed, text="Thất bại", text_color="#EF4444", font=("Arial", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.at_btn_copy_failed = ctk.CTkButton(self.at_header_failed, text="Copy Tất Cả", width=80, height=26, fg_color="#FAFAFA", text_color="#18181B", border_width=1, border_color="#E4E4E7", hover_color="#F4F4F5", corner_radius=6, command=lambda: self.copy_to_clipboard(self.at_txt_failed))
        self.at_btn_copy_failed.grid(row=0, column=1, sticky="e")
        
        self.at_txt_failed = ctk.CTkTextbox(self.at_frame_failed, state="disabled", border_width=1, corner_radius=6, border_color="#FEE2E2", fg_color="#F9FAFB", text_color="#374151")
        self.at_txt_failed.grid(row=1, column=0, sticky="nsew")

    def at_load_from_file(self):
        filepath = filedialog.askopenfilename(
            title="Chọn file chứa tài khoản",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if filepath:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.at_txt_accounts.delete("1.0", "end")
                self.at_txt_accounts.insert("1.0", content)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")

    def at_sort_success_results(self):
        success_accounts = [acc for acc in self.add_time_accounts if acc.status == "Thành công"]
        if not success_accounts:
            messagebox.showinfo("Thông báo", "Không có tài khoản thành công để sắp xếp.")
            return

        def get_sort_key(acc):
            # original_line is expected to be: data|DD/MM
            parts = acc.original_line.split('|')
            if len(parts) > 1:
                date_str = parts[-1].strip()
                # Try to parse DD/MM
                try:
                    day, month = map(int, date_str.split('/'))
                    return (month, day)
                except:
                    pass
            # Fallback to a high value so unparseable dates go to the end
            return (99, 99)

        success_accounts.sort(key=get_sort_key)
        
        # Update the list by replacing the success accounts with sorted ones
        new_add_time_accounts = []
        for acc in self.add_time_accounts:
            if acc.status != "Thành công":
                new_add_time_accounts.append(acc)
        
        # Add sorted success accounts back
        new_add_time_accounts.extend(success_accounts)
        self.add_time_accounts = new_add_time_accounts
        
        self.at_update_results_view()
        messagebox.showinfo("Thành công", "Đã sắp xếp tài khoản theo ngày tháng!")

    def at_add_already_sorted_accounts(self):
        raw_text = self.at_txt_accounts.get("1.0", "end-1c")
        new_accounts = self.parser.parse(raw_text)
        if new_accounts:
            # For pre-sorted accounts, we force their status to 'Thành công' so they go directly to the success column
            for acc in new_accounts:
                acc.status = "Thành công"
            self.add_time_accounts.extend(new_accounts)
            self.at_update_results_view()
            self.at_txt_accounts.delete("1.0", "end")
            messagebox.showinfo("Thành công", f"Đã thêm {len(new_accounts)} tài khoản vào cột Thành công!")
        else:
            messagebox.showwarning("Cảnh báo", "Không tìm thấy tài khoản hợp lệ!")

    def at_add_accounts(self):
        raw_text = self.at_txt_accounts.get("1.0", "end-1c")
        new_accounts = self.parser.parse(raw_text)
        if new_accounts:
            self.add_time_accounts.extend(new_accounts)
            self.at_update_results_view()
            self.at_txt_accounts.delete("1.0", "end")
            messagebox.showinfo("Thành công", f"Đã thêm {len(new_accounts)} tài khoản!")
        else:
            messagebox.showwarning("Cảnh báo", "Không tìm thấy tài khoản hợp lệ!")

    def at_clear_list(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc muốn xóa toàn bộ danh sách?"):
            self.add_time_accounts.clear()
            self.at_update_results_view()

    def at_update_results_view(self):
        self.at_txt_success.configure(state="normal")
        self.at_txt_failed.configure(state="normal")
        self.at_txt_success.delete("1.0", "end")
        self.at_txt_failed.delete("1.0", "end")
        
        success_count = 0
        failed_count = 0
        total = len(self.add_time_accounts)
        
        for acc in self.add_time_accounts:
            if acc.status == "Thành công":
                self.at_txt_success.insert("end", f"{acc.original_line}\n")
                success_count += 1
            elif acc.status == "Thất bại":
                self.at_txt_failed.insert("end", f"{acc.original_line}|{acc.note}\n")
                failed_count += 1
                
        self.at_txt_success.configure(state="disabled")
        self.at_txt_failed.configure(state="disabled")
        
        self.at_lbl_total.configure(text=f"Tổng: {total}")
        self.at_lbl_success.configure(text=f"Thành công: {success_count}")
        self.at_lbl_failed.configure(text=f"Thất bại: {failed_count}")
        
        if total > 0:
            processed = success_count + failed_count
            percent = int((processed / total) * 100)
            self.at_progress_bar.set(processed / total)
            self.at_lbl_percent.configure(text=f"{percent}%")
        else:
            self.at_progress_bar.set(0)
            self.at_lbl_percent.configure(text="0%")

    def at_start_checking(self):
        if not self.add_time_accounts:
            messagebox.showwarning("Cảnh báo", "Danh sách tài khoản trống!")
            return
            
        try:
            num_threads = int(self.at_entry_threads.get())
            if num_threads <= 0: raise ValueError
        except ValueError:
            messagebox.showerror("Lỗi", "Số luồng phải là số nguyên dương!")
            return
            
        self.is_add_time_running = True
        self.at_btn_start.configure(state="disabled")
        self.at_btn_stop.configure(state="normal")
        self.at_btn_clear.configure(state="disabled")
        self.at_btn_add.configure(state="disabled")
        
        for acc in self.add_time_accounts:
            acc.status = "Chưa check"
            acc.note = ""
            
        self.at_update_results_view()
        
        threading.Thread(target=self.at_check_worker, args=(num_threads,), daemon=True).start()

    def at_stop_checking(self):
        self.is_add_time_running = False
        self.at_btn_stop.configure(state="disabled")

    def at_check_worker(self, num_threads):
        accounts_to_check = [acc for acc in self.add_time_accounts if acc.status == "Chưa check"]
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            for acc in accounts_to_check:
                if not self.is_add_time_running:
                    break
                executor.submit(self.at_check_single_account, acc)
                time.sleep(0.1)
                
        was_running = self.is_add_time_running
        self.is_add_time_running = False
        self.after(0, lambda: self.at_btn_start.configure(state="normal"))
        self.after(0, lambda: self.at_btn_stop.configure(state="disabled"))
        self.after(0, lambda: self.at_btn_clear.configure(state="normal"))
        self.after(0, lambda: self.at_btn_add.configure(state="normal"))
        
        if was_running:
            self.after(0, lambda: messagebox.showinfo("Hoàn thành", "Đã check xong toàn bộ danh sách (Add Time)!"))

    def at_check_single_account(self, account: Account):
        if not self.is_add_time_running:
            return
            
        self.add_time_checker.check(account, self.config)
        self.after(0, self.at_update_results_view)

    def setup_auto_tab(self):
        self.tab_auto.grid_columnconfigure(0, weight=1)
        self.tab_auto.grid_rowconfigure(1, weight=1)
        
        # Control Frame
        control_frame = ctk.CTkFrame(self.tab_auto, fg_color="#FFFFFF", corner_radius=8)
        control_frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        
        ctk.CTkLabel(control_frame, text="Điều khiển Tự động", font=("Arial", 16, "bold"), text_color="#111827").pack(pady=(10, 5))
        
        btn_frame = ctk.CTkFrame(control_frame, fg_color="transparent")
        btn_frame.pack(pady=10)
        
        ctk.CTkLabel(btn_frame, text="Số luồng:", text_color="#374151").pack(side="left", padx=5)
        self.auto_thread_var = ctk.StringVar(value="50")
        thread_menu = ctk.CTkOptionMenu(btn_frame, variable=self.auto_thread_var, values=["1", "5", "10", "20", "50", "100"], width=80)
        thread_menu.pack(side="left", padx=5)
        
        self.btn_auto_start = ctk.CTkButton(btn_frame, text="Bắt đầu Auto", fg_color="#059669", hover_color="#047857", corner_radius=6, command=self.start_auto)
        self.btn_auto_start.pack(side="left", padx=(20, 10))
        
        self.btn_auto_stop = ctk.CTkButton(btn_frame, text="Dừng Auto", fg_color="#E11D48", hover_color="#BE123C", state="disabled", corner_radius=6, command=self.stop_auto)
        self.btn_auto_stop.pack(side="left", padx=10)
        
        # Log Frame
        log_frame = ctk.CTkFrame(self.tab_auto, fg_color="#FFFFFF", corner_radius=8)
        log_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)
        
        ctk.CTkLabel(log_frame, text="Nhật ký hệ thống (Log)", font=("Arial", 14, "bold"), text_color="#111827").grid(row=0, column=0, pady=10, padx=10, sticky="w")
        
        self.txt_auto_log = ctk.CTkTextbox(log_frame, fg_color="#1F2937", text_color="#F9FAFB", corner_radius=6)
        self.txt_auto_log.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        # Define tag configurations for colored logs
        self.txt_auto_log.tag_config("INFO", foreground="#60A5FA")
        self.txt_auto_log.tag_config("SUCCESS", foreground="#34D399")
        self.txt_auto_log.tag_config("WARNING", foreground="#FBBF24")
        self.txt_auto_log.tag_config("ERROR", foreground="#F87171")

    def log_auto(self, message, level="INFO"):
        self.txt_auto_log.configure(state="normal")
        timestamp = time.strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        self.txt_auto_log.insert("end", log_line, level)
        self.txt_auto_log.see("end")
        self.txt_auto_log.configure(state="disabled")

    def start_auto(self):
        if not self.config.auto_save_path:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn đường dẫn lưu file ở tab Cài Đặt trước khi chạy Auto!")
            self.tabview.set("Cài Đặt")
            return
            
        self.btn_auto_start.configure(state="disabled")
        self.btn_auto_stop.configure(state="normal")
        self.is_auto_running = True
        
        self.auto_thread = threading.Thread(target=self.auto_worker, daemon=True)
        self.auto_thread.start()

    def stop_auto(self):
        self.is_auto_running = False
        self.btn_auto_stop.configure(state="disabled")
        self.log_auto("Đang dừng tiến trình Auto...", "WARNING")
        
    def auto_worker(self):
        self.log_auto("Bắt đầu quy trình Auto", "INFO")
        
        # B1: Tải tài khoản từ database
        self.log_auto("B1: Đang tải tài khoản từ MySQL...", "INFO")
        
        table = "accounts"
        downloaded_accounts = []
        downloaded_ids = []
        try:
            conn = self.get_mysql_connection()
            with conn.cursor() as cursor:
                query = f"SELECT id, UID, Password, Email, EmailPass, 2FA FROM {table} WHERE Time < NOW() - INTERVAL 30 MINUTE"
                try:
                    cursor.execute(query)
                except pymysql.err.OperationalError:
                    query_fallback = f"SELECT * FROM {table} WHERE Time < NOW() - INTERVAL 30 MINUTE"
                    cursor.execute(query_fallback)
                    
                results = cursor.fetchall()
                if not results:
                    self.log_auto("Không tìm thấy tài khoản nào mới từ MySQL (>30p).", "WARNING")
                    self.end_auto_process()
                    return
                    
                for row in results:
                    downloaded_ids.append(str(row.get('id', '')))
                    uid = row.get('UID', '')
                    pwd = row.get('Password', '')
                    email = row.get('Email', '')
                    passmail = row.get('EmailPass', '')
                    twofa = row.get('2FA', '')
                    line = f"{uid}|{pwd}|{email}|{passmail}|{twofa}"
                    downloaded_accounts.append(line)
                    
            self.log_auto(f"Đã tải thành công {len(downloaded_accounts)} tài khoản.", "SUCCESS")
        except Exception as e:
            self.log_auto(f"Lỗi khi tải dữ liệu từ MySQL: {e}", "ERROR")
            self.end_auto_process()
            return
            
        if not self.is_auto_running:
            self.end_auto_process()
            return
            
        # Parse accounts
        raw_text = "\n".join(downloaded_accounts)
        auto_accounts = self.parser.parse(raw_text)
        
        if not auto_accounts:
            self.log_auto("Không phân tích được tài khoản hợp lệ từ dữ liệu MySQL.", "WARNING")
            self.end_auto_process()
            return
            
        # B2: Check live
        self.log_auto(f"B2: Chuyển sang tab Main để check {len(auto_accounts)} tài khoản với {self.auto_thread_var.get()} luồng...", "INFO")
        
        # Đưa data sang Main tab
        self.accounts.clear()
        self.accounts.extend(auto_accounts)
        self.after(0, self.update_results_view)
        
        # Chuyển UI sang tab Main
        self.after(0, self.tabview.set, "Main")
        
        # Thiết lập số luồng ở tab Main
        def set_threads():
            self.entry_threads.delete(0, "end")
            self.entry_threads.insert(0, self.auto_thread_var.get())
        self.after(0, set_threads)
        
        # Bắt đầu check bên Main tab
        self.after(0, self.start_checking)
        
        # Chờ 1 chút để start_checking kịp set self.is_running = True
        time.sleep(1)
        
        # Đợi cho quá trình check ở Main tab hoàn tất
        while self.is_running and self.is_auto_running:
            time.sleep(1)
            
        if not self.is_auto_running:
            # Nếu người dùng bấm Dừng Auto
            self.log_auto("Quá trình check bị dừng bởi người dùng (Auto).", "WARNING")
            self.after(0, self.stop_checking)
            self.end_auto_process()
            return
            
        # Lấy kết quả từ self.accounts
        checked_accounts = self.accounts
        success_count = sum(1 for acc in checked_accounts if acc.status == "Thành công")
        
        self.log_auto(f"Hoàn thành check. Có {success_count}/{len(checked_accounts)} tài khoản thành công.", "INFO")
        
        # B3: Lưu kết quả thành công
        if success_count > 0:
            self.log_auto(f"B3: Đang lưu các tài khoản thành công vào {self.config.auto_save_path}...", "INFO")
            try:
                with open(self.config.auto_save_path, "a", encoding="utf-8") as f:
                    for acc in checked_accounts:
                        if acc.status == "Thành công":
                            f.write(acc.original_line + "\n")
                self.log_auto("Đã lưu thành công.", "SUCCESS")
            except Exception as e:
                self.log_auto(f"Lỗi khi lưu file: {e}", "ERROR")
                
        if not self.is_auto_running:
            self.end_auto_process()
            return
            
        # B4: Xóa tài khoản đã tải khỏi DB
        self.log_auto("B4: Đang xóa các tài khoản đã tải khỏi MySQL...", "INFO")
        try:
            conn = self.get_mysql_connection()
            with conn.cursor() as cursor:
                valid_ids = [i for i in downloaded_ids if i]
                if valid_ids:
                    format_strings = ','.join(['%s'] * len(valid_ids))
                    query = f"DELETE FROM {table} WHERE id IN ({format_strings})"
                    cursor.execute(query, tuple(valid_ids))
                    conn.commit()
                    self.log_auto(f"Đã xóa {cursor.rowcount} tài khoản khỏi database.", "SUCCESS")
                else:
                    self.log_auto("Không có ID hợp lệ để xóa khỏi database.", "WARNING")
        except Exception as e:
            self.log_auto(f"Lỗi khi xóa dữ liệu MySQL: {e}", "ERROR")
            
        self.log_auto("Quy trình Auto đã hoàn tất toàn bộ.", "SUCCESS")
        self.end_auto_process()

    def end_auto_process(self):
        self.is_auto_running = False
        try:
            self.btn_auto_start.configure(state="normal")
            self.btn_auto_stop.configure(state="disabled")
        except:
            pass

    def setup_mysql_tab(self):
        self.tab_mysql.grid_columnconfigure(0, weight=1)
        self.tab_mysql.grid_rowconfigure(2, weight=1)
        
        # MySQL Config Frame
        config_frame = ctk.CTkFrame(self.tab_mysql, fg_color="#FFFFFF", corner_radius=8)
        config_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        config_frame.grid_columnconfigure(1, weight=1)
        config_frame.grid_columnconfigure(3, weight=1)
        
        ctk.CTkLabel(config_frame, text="Cấu hình MySQL Server", font=("Arial", 16, "bold"), text_color="#111827").grid(row=0, column=0, columnspan=4, pady=(20, 10))
        
        # Host
        ctk.CTkLabel(config_frame, text="Host:", text_color="#374151").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.entry_mysql_host = ctk.CTkEntry(config_frame, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_mysql_host.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.entry_mysql_host.insert(0, self.config.mysql_host)
        
        # User
        ctk.CTkLabel(config_frame, text="User:", text_color="#374151").grid(row=1, column=2, padx=10, pady=10, sticky="e")
        self.entry_mysql_user = ctk.CTkEntry(config_frame, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_mysql_user.grid(row=1, column=3, padx=10, pady=10, sticky="ew")
        self.entry_mysql_user.insert(0, self.config.mysql_user)
        
        # Password
        ctk.CTkLabel(config_frame, text="Password:", text_color="#374151").grid(row=2, column=0, padx=10, pady=10, sticky="e")
        self.entry_mysql_pass = ctk.CTkEntry(config_frame, show="*", border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_mysql_pass.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        self.entry_mysql_pass.insert(0, self.config.mysql_password)
        
        # Database
        ctk.CTkLabel(config_frame, text="Database:", text_color="#374151").grid(row=2, column=2, padx=10, pady=10, sticky="e")
        self.entry_mysql_db = ctk.CTkEntry(config_frame, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_mysql_db.grid(row=2, column=3, padx=10, pady=10, sticky="ew")
        self.entry_mysql_db.insert(0, self.config.mysql_database)

        # Actions Frame
        action_frame = ctk.CTkFrame(self.tab_mysql, fg_color="#FFFFFF", corner_radius=8)
        action_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        action_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.btn_mysql_connect = ctk.CTkButton(action_frame, text="Kết nối", fg_color="#4F46E5", hover_color="#4338CA", corner_radius=6, command=self.test_mysql_connection)
        self.btn_mysql_connect.grid(row=0, column=0, padx=10, pady=15)
        
        self.btn_mysql_save = ctk.CTkButton(action_frame, text="Lưu Cấu Hình", fg_color="#475569", hover_color="#334155", corner_radius=6, command=self.save_mysql_config)
        self.btn_mysql_save.grid(row=0, column=1, padx=10, pady=15)
        
        self.btn_mysql_download = ctk.CTkButton(action_frame, text="Tải về từ MySQL", fg_color="#059669", hover_color="#047857", corner_radius=6, command=self.download_from_mysql)
        self.btn_mysql_download.grid(row=0, column=2, padx=10, pady=15)
        
        self.btn_mysql_delete = ctk.CTkButton(action_frame, text="Xóa đã tải", fg_color="#E11D48", hover_color="#BE123C", corner_radius=6, command=self.delete_downloaded_mysql)
        self.btn_mysql_delete.grid(row=0, column=3, padx=10, pady=15)
        
        # Log Frame
        log_frame = ctk.CTkFrame(self.tab_mysql, fg_color="#FFFFFF", corner_radius=8)
        log_frame.grid(row=2, column=0, padx=20, pady=(10, 20), sticky="nsew")
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.txt_mysql_log = ctk.CTkTextbox(log_frame, fg_color="#F9FAFB", text_color="#374151", border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.txt_mysql_log.grid(row=0, column=0, padx=15, pady=15, sticky="nsew")
        self.txt_mysql_log.insert("1.0", "[INFO] Sẵn sàng kết nối MySQL...\n")

    def setup_settings_tab(self):
        self.tab_settings.grid_columnconfigure(0, weight=1)
        
        frame = ctk.CTkFrame(self.tab_settings, fg_color="#FFFFFF", corner_radius=8)
        frame.grid(row=0, column=0, padx=20, pady=20, sticky="ew")
        
        ctk.CTkLabel(frame, text="Cấu hình SMTP/IMAP Server", font=("Arial", 16, "bold"), text_color="#111827").grid(row=0, column=0, columnspan=2, pady=(20, 10))
        
        ctk.CTkLabel(frame, text="IMAP Server:", text_color="#374151").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.entry_server = ctk.CTkEntry(frame, width=300, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_server.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        self.entry_server.insert(0, self.config.imap_server)
        
        ctk.CTkLabel(frame, text="Port:", text_color="#374151").grid(row=2, column=0, padx=10, pady=10, sticky="e")
        self.entry_port = ctk.CTkEntry(frame, width=100, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_port.grid(row=2, column=1, padx=10, pady=10, sticky="w")
        self.entry_port.insert(0, str(self.config.imap_port))
        
        self.switch_ssl = ctk.CTkSwitch(frame, text="Sử dụng SSL", text_color="#374151", progress_color="#2563EB")
        self.switch_ssl.grid(row=3, column=1, padx=10, pady=10, sticky="w")
        if self.config.use_ssl:
            self.switch_ssl.select()
        else:
            self.switch_ssl.deselect()
            
        self.btn_save_config = ctk.CTkButton(frame, text="Lưu Cấu Hình", fg_color="#4F46E5", hover_color="#4338CA", corner_radius=6, command=self.save_config)
        self.btn_save_config.grid(row=4, column=0, columnspan=2, pady=(10, 20))
        
        # Thêm phần cấu hình Auto
        auto_frame = ctk.CTkFrame(self.tab_settings, fg_color="#FFFFFF", corner_radius=8)
        auto_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        ctk.CTkLabel(auto_frame, text="Cấu hình Auto (Tab Auto)", font=("Arial", 16, "bold"), text_color="#111827").grid(row=0, column=0, columnspan=3, pady=(20, 10))
        
        ctk.CTkLabel(auto_frame, text="Đường dẫn lưu file:", text_color="#374151").grid(row=1, column=0, padx=10, pady=10, sticky="e")
        self.entry_auto_save = ctk.CTkEntry(auto_frame, width=300, border_width=1, border_color="#E5E7EB", corner_radius=6)
        self.entry_auto_save.grid(row=1, column=1, padx=10, pady=10, sticky="w")
        self.entry_auto_save.insert(0, self.config.auto_save_path)
        
        self.btn_browse_auto_save = ctk.CTkButton(auto_frame, text="Chọn file", width=80, fg_color="#475569", hover_color="#334155", corner_radius=6, command=self.browse_auto_save_path)
        self.btn_browse_auto_save.grid(row=1, column=2, padx=10, pady=10, sticky="w")
        
        self.btn_save_auto_config = ctk.CTkButton(auto_frame, text="Lưu Cấu Hình Auto", fg_color="#4F46E5", hover_color="#4338CA", corner_radius=6, command=self.save_auto_config)
        self.btn_save_auto_config.grid(row=2, column=0, columnspan=3, pady=(10, 20))
        
    def browse_auto_save_path(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
            title="Chọn nơi lưu tài khoản Auto"
        )
        if filepath:
            self.entry_auto_save.delete(0, "end")
            self.entry_auto_save.insert(0, filepath)
            
    def save_auto_config(self):
        path = self.entry_auto_save.get().strip()
        self.config.auto_save_path = path
        self.save_app_config()
        messagebox.showinfo("Thành công", "Đã lưu cấu hình Auto.")
        
    def load_from_file(self):
        filepath = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if filepath:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.txt_accounts.delete("1.0", "end")
                self.txt_accounts.insert("1.0", content)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không thể đọc file: {e}")
                
    def add_accounts(self):
        raw_text = self.txt_accounts.get("1.0", "end-1c")
        if raw_text.strip() == "" or raw_text.startswith("Nhập tài khoản"):
            return
            
        new_accounts = self.parser.parse(raw_text)
        self.accounts.extend(new_accounts)
        
        self.update_results_view()
        self.txt_accounts.delete("1.0", "end")
        messagebox.showinfo("Thành công", f"Đã thêm {len(new_accounts)} tài khoản.")
        
    def clear_list(self):
        self.accounts.clear()
        self.update_results_view()
        
    def update_results_view(self):
        self.txt_success.configure(state="normal")
        self.txt_failed.configure(state="normal")
        
        self.txt_success.delete("1.0", "end")
        self.txt_failed.delete("1.0", "end")
        
        success_count = 0
        failed_count = 0
        
        for acc in self.accounts:
            if acc.status == "Thành công":
                self.txt_success.insert("end", f"{acc.original_line}\n")
                success_count += 1
            elif acc.status == "Thất bại":
                self.txt_failed.insert("end", f"{acc.original_line}|{acc.note}\n")
                failed_count += 1
            elif acc.status == "Đang kiểm tra...":
                self.txt_success.insert("end", f"[{acc.status}] {acc.original_line}\n")
                
        total = len(self.accounts)
        self.lbl_total.configure(text=f"Tổng: {total}")
        self.lbl_success.configure(text=f"Thành công: {success_count}")
        self.lbl_failed.configure(text=f"Thất bại: {failed_count}")
        
        # Update Progress Bar and Percent
        checked_count = success_count + failed_count
        if total > 0:
            progress = checked_count / total
            percent = int(progress * 100)
            self.progress_bar.set(progress)
            self.lbl_percent.configure(text=f"{percent}%")
        else:
            self.progress_bar.set(0)
            self.lbl_percent.configure(text="0%")
            
        self.txt_success.configure(state="disabled")
        self.txt_failed.configure(state="disabled")
        
    def save_config(self):
        server = self.entry_server.get().strip()
        port_str = self.entry_port.get().strip()
        use_ssl = bool(self.switch_ssl.get())
        
        if not server or not port_str.isdigit():
            messagebox.showerror("Lỗi", "Thông tin cấu hình không hợp lệ.")
            return
            
        self.config.imap_server = server
        self.config.imap_port = int(port_str)
        self.config.use_ssl = use_ssl
        self.save_app_config()
        messagebox.showinfo("Thành công", "Đã lưu cấu hình.")
        
    def start_checking(self):
        if not self.accounts:
            messagebox.showwarning("Cảnh báo", "Danh sách tài khoản trống.")
            return
            
        try:
            self.max_threads = int(self.entry_threads.get().strip())
            if self.max_threads <= 0:
                raise ValueError("Số luồng phải là số nguyên dương.")
            if self.max_threads > 100:
                messagebox.showwarning("Cảnh báo", "Để đảm bảo an toàn và tránh bị server chặn IP, số luồng tối đa được giới hạn ở 100.")
                self.max_threads = 100
                self.entry_threads.delete(0, "end")
                self.entry_threads.insert(0, "100")
        except ValueError:
            messagebox.showerror("Lỗi", "Số luồng phải là số nguyên dương.")
            return
            
        self.is_running = True
        self.btn_start.configure(state="disabled", text="Đang chạy...")
        self.btn_stop.configure(state="normal")
        self.btn_clear.configure(state="disabled")
        self.entry_threads.configure(state="disabled")
        
        # Reset progress
        self.progress_bar.set(0)
        self.lbl_percent.configure(text="0%")
        
        # Run in thread
        threading.Thread(target=self.process_accounts, daemon=True).start()
        
    def stop_checking(self):
        self.is_running = False
        self.btn_stop.configure(state="disabled")
        
    def check_single_account(self, idx, acc):
        if not self.is_running:
            return
            
        if acc.status != "Chưa kiểm tra":
            return
            
        # Update status to checking
        acc.status = "Đang kiểm tra..."
        self.after(0, self.update_results_view)
        
        # Check
        updated_acc = self.checker.check(acc, self.config)
        
        # Update result
        self.accounts[idx] = updated_acc
        self.after(0, self.update_results_view)
        
    def process_accounts(self):
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = []
            for idx, acc in enumerate(self.accounts):
                if not self.is_running:
                    break
                futures.append(executor.submit(self.check_single_account, idx, acc))
                
            # Wait for all futures to complete
            for future in futures:
                future.result()
                if not self.is_running:
                    # Cancel pending futures if stopped
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
            
        self.after(0, self.checking_finished)
        
    def checking_finished(self):
        self.is_running = False
        self.btn_start.configure(state="normal", text="Bắt đầu Check")
        self.btn_stop.configure(state="disabled")
        self.btn_clear.configure(state="normal")
        self.entry_threads.configure(state="normal")
        
        # Đảm bảo full 100% khi chạy xong
        if len(self.accounts) > 0:
            self.progress_bar.set(1)
            self.lbl_percent.configure(text="100%")
            
        # Không hiện thông báo nếu đang chạy Auto để tránh bị block quy trình
        if not getattr(self, 'is_auto_running', False):
            messagebox.showinfo("Hoàn tất", "Đã hoàn tất quá trình kiểm tra.")
