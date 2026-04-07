from dataclasses import dataclass

@dataclass
class Account:
    email: str
    password: str
    original_line: str = ""
    status: str = "Chưa kiểm tra"
    note: str = ""

@dataclass
class AppConfig:
    imap_server: str = "imap.smtp.dev"
    imap_port: int = 143
    use_ssl: bool = False
    
    # MySQL Config
    mysql_host: str = ""
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = ""
    
    # Auto Config
    auto_save_path: str = ""