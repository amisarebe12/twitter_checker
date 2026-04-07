import os
import sys
import json
import threading
import subprocess
import requests

class GitHubUpdater:
    def __init__(self, repo_url, current_version):
        # repo_url like: https://github.com/amisarebe12/twitter_checker.git
        self.repo_url = repo_url.replace(".git", "")
        # Extract owner and repo: "amisarebe12/twitter_checker"
        parts = self.repo_url.split("github.com/")
        if len(parts) > 1:
            self.repo_path = parts[1].strip("/")
        else:
            self.repo_path = "amisarebe12/twitter_checker"
            
        self.api_url = f"https://api.github.com/repos/{self.repo_path}/releases/latest"
        self.current_version = current_version
        
        self.latest_version = None
        self.release_notes = None
        self.download_url = None
        self.is_downloading = False

    def check_for_update(self):
        """Kiểm tra xem có bản cập nhật mới trên GitHub không. Trả về True nếu có."""
        try:
            response = requests.get(self.api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.latest_version = data.get("tag_name", "").lstrip("v")
                self.release_notes = data.get("body", "Không có ghi chú cập nhật.")
                
                # Tìm file cài đặt (.exe)
                assets = data.get("assets", [])
                for asset in assets:
                    if asset.get("name", "").endswith(".exe"):
                        self.download_url = asset.get("browser_download_url")
                        break
                        
                # Nếu có version mới và link tải
                if self._is_newer_version(self.latest_version, self.current_version) and self.download_url:
                    return True
            return False
        except Exception as e:
            print(f"Lỗi khi kiểm tra cập nhật: {e}")
            return False

    def _is_newer_version(self, latest, current):
        try:
            # So sánh phiên bản (vd: 1.3.0 > 1.2.0)
            latest_parts = [int(x) for x in latest.split(".")]
            current_parts = [int(x) for x in current.split(".")]
            
            # Cân bằng độ dài mảng (nếu cần)
            max_len = max(len(latest_parts), len(current_parts))
            latest_parts += [0] * (max_len - len(latest_parts))
            current_parts += [0] * (max_len - len(current_parts))
            
            for l, c in zip(latest_parts, current_parts):
                if l > c: return True
                if l < c: return False
            return False
        except Exception:
            return False

    def download_and_install(self, progress_callback, completion_callback):
        """Tải file ngầm và tự động cài đặt."""
        if self.is_downloading or not self.download_url:
            return
            
        self.is_downloading = True
        
        def download_task():
            try:
                # Lưu file vào thư mục Temp của Windows
                temp_dir = os.environ.get("TEMP", os.path.dirname(__file__))
                file_path = os.path.join(temp_dir, f"TwitterChecker_Update_v{self.latest_version}.exe")
                
                response = requests.get(self.download_url, stream=True, timeout=15)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                block_size = 8192
                downloaded = 0
                
                with open(file_path, "wb") as f:
                    for data in response.iter_content(block_size):
                        downloaded += len(data)
                        f.write(data)
                        if total_size > 0:
                            percent = (downloaded / total_size)
                            # Báo cáo tiến độ về UI
                            progress_callback(percent)
                            
                # Tải xong, gọi callback hoàn thành
                self.is_downloading = False
                completion_callback(file_path, True, None)
                
            except Exception as e:
                self.is_downloading = False
                completion_callback(None, False, str(e))
                
        # Chạy thread tải ngầm
        threading.Thread(target=download_task, daemon=True).start()

    def run_installer(self, file_path):
        """Kích hoạt file Inno Setup và thoát app hiện tại."""
        try:
            # /VERYSILENT: Cài đặt hoàn toàn ngầm, không hiện UI Inno Setup
            # /SUPPRESSMSGBOXES: Bỏ qua mọi hộp thoại hỏi han
            # /NORESTART: Không tự khởi động lại máy
            subprocess.Popen([file_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"])
            sys.exit(0)
        except Exception as e:
            print(f"Lỗi khi chạy bộ cài đặt: {e}")
