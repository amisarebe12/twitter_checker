[Setup]
; Tên và phiên bản ứng dụng
AppName=Twitter Checker IMAP
AppVersion=1.3.0
AppPublisher=Your Name/Company
AppCopyright=Copyright (C) 2024

; Thư mục cài đặt mặc định (Thường là C:\Program Files (x86)\Twitter Checker IMAP)
DefaultDirName={autopf}\Twitter Checker IMAP
DefaultGroupName=Twitter Checker IMAP
AllowNoIcons=yes

; Cấu hình file Setup đầu ra
OutputDir=Output
OutputBaseFilename=TwitterChecker_v1.3.0
SetupIconFile=X.ico

; Nén dữ liệu để dung lượng setup nhỏ nhất
Compression=lzma2/ultra64
SolidCompression=yes

; QUAN TRỌNG: Yêu cầu quyền Admin khi chạy file cài đặt
PrivilegesRequired=admin
DirExistsWarning=no
DisableProgramGroupPage=yes
DisableDirPage=no

[Dirs]
; QUAN TRỌNG: Cấp quyền đọc/ghi (modify) cho tất cả user vào thư mục cài đặt
; Điều này giúp ứng dụng không bị lỗi "Permission denied" khi lưu file config.json hoặc file log nếu người dùng cài đặt vào ổ C (Program Files)
Name: "{app}"; Permissions: users-modify

[Files]
; -------------------------------------------------------------------------
; BƯỚC 1: TRƯỚC KHI CHẠY FILE NÀY, BẠN PHẢI BUILD CODE THÀNH FILE EXE BẰNG LỆNH SAU:
; pyinstaller --noconsole --icon=X.ico --add-data "changelog.json;." --add-data "X.ico;." --add-data "X.png;." --name="TwitterChecker" main.py
; 
; BƯỚC 2: CẤU HÌNH ĐƯỜNG DẪN TỚI FILE EXE Ở BÊN DƯỚI:
; (Do bạn build ra dạng thư mục - Onedir, cấu hình như sau:)
Source: "dist\TwitterChecker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; (Nếu bạn build ra dạng 1 file duy nhất - Onefile, thì dùng dòng dưới và comment dòng trên)
; Source: "dist\TwitterChecker.exe"; DestDir: "{app}"; Flags: ignoreversion
; -------------------------------------------------------------------------

; Copy kèm các file icon để app có thể load khi chạy
Source: "X.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "X.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "changelog.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Tạo shortcut ở Start Menu
Name: "{autoprograms}\Twitter Checker IMAP"; Filename: "{app}\TwitterChecker.exe"; IconFilename: "{app}\X.ico"

; Tạo shortcut ở ngoài Desktop
Name: "{autodesktop}\Twitter Checker IMAP"; Filename: "{app}\TwitterChecker.exe"; Tasks: desktopicon; IconFilename: "{app}\X.ico"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
; Tùy chọn tự động chạy app sau khi cài đặt xong
Filename: "{app}\TwitterChecker.exe"; Description: "{cm:LaunchProgram,Twitter Checker IMAP}"; Flags: nowait postinstall skipifsilent