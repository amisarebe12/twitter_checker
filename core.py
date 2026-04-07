import imaplib
import email
import time
import random
import socket
from email.header import decode_header
from models import Account, AppConfig
from abc import ABC, abstractmethod

class IAccountParser(ABC):
    @abstractmethod
    def parse(self, raw_data: str) -> list[Account]:
        pass

class DefaultAccountParser(IAccountParser):
    def parse(self, raw_data: str) -> list[Account]:
        accounts = []
        if not raw_data:
            return accounts
        lines = raw_data.strip().split('\n')
        for line in lines:
            line_clean = line.strip()
            if not line_clean:
                continue
                
            parts = line_clean.split('|')
            email = None
            password = None
            
            for i, part in enumerate(parts):
                part_clean = part.strip()
                # Kiểm tra một chuỗi có phải là email hợp lệ hay không (có @ và dấu . sau @)
                if '@' in part_clean and '.' in part_clean.split('@')[-1]:
                    # Kiểm tra trường hợp dính liền dạng email:password trong cùng 1 cụm
                    if ':' in part_clean and part_clean.find('@') < part_clean.find(':'):
                        subparts = part_clean.split(':', 1)
                        email = subparts[0].strip()
                        password = subparts[1].strip()
                        break
                    
                    # Nếu không dính dấu ':', lấy giá trị hiện tại làm email, giá trị sau '|' làm password
                    email = part_clean
                    if i + 1 < len(parts):
                        password = parts[i+1].strip()
                    break
            
            if email and password:
                # Xóa các khoảng trắng, ký tự rác (nếu có)
                email = email.strip(" \t\n\r\"'")
                password = password.strip(" \t\n\r\"'")
                accounts.append(Account(email=email, password=password, original_line=line_clean))
        return accounts

class IAccountChecker(ABC):
    @abstractmethod
    def check(self, account: Account, config: AppConfig) -> Account:
        pass

class TwitterImapChecker(IAccountChecker):
    def check(self, account: Account, config: AppConfig) -> Account:
        max_retries = 3
        for attempt in range(max_retries):
            mail = None
            try:
                # Anti-spam: Random delay before connecting, slightly longer on retries
                if attempt > 0:
                    time.sleep(random.uniform(2.0, 4.0))
                else:
                    time.sleep(random.uniform(0.5, 1.5))
                
                # Connect to the server with a timeout (Python 3.9+)
                if config.use_ssl:
                    mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port, timeout=30)
                else:
                    mail = imaplib.IMAP4(config.imap_server, config.imap_port, timeout=30)
                
                # Login
                try:
                    mail.login(account.email, account.password)
                except imaplib.IMAP4.error as e:
                    error_msg = str(e)
                    # If it's explicitly an auth failure, don't retry, just return immediately
                    if "AUTHENTICATIONFAILED" in error_msg.upper() or "invalid credentials" in error_msg.lower() or "login failed" in error_msg.lower():
                        account.status = "Thất bại"
                        account.note = f"Sai tài khoản hoặc mật khẩu (Thử log: {account.email} | pass: {account.password})"
                        return account
                    else:
                        raise e # Raise to trigger retry for other errors (like rate limit, too many connections)
                
                # Select inbox
                status, messages = mail.select("INBOX")
                if status != "OK":
                    account.status = "Thất bại"
                    account.note = "Không thể mở INBOX"
                    if mail:
                        try: mail.logout()
                        except: pass
                    return account
                
                # Chờ server smtp.dev load và đồng bộ mail (Thường các server mail chậm cần thời gian delay sau khi select INBOX)
                time.sleep(3)
                
                # Search for all emails
                status, response = mail.search(None, "ALL")
                if status == "OK":
                    email_ids = response[0].split()
                    
                    # Read all emails, stopping only when 'sus' is found or all are read
                    for e_id in reversed(email_ids):
                        status, msg_data = mail.fetch(e_id, "(RFC822)")
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                
                                # check subject
                                subject, encoding = decode_header(msg["Subject"])[0] if msg["Subject"] else ("", None)
                                if isinstance(subject, bytes):
                                    if encoding:
                                        try:
                                            subject = subject.decode(encoding)
                                        except:
                                            subject = subject.decode('utf-8', errors='ignore')
                                    else:
                                        subject = subject.decode('utf-8', errors='ignore')
                                
                                # check body
                                body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        try:
                                            body_bytes = part.get_payload(decode=True)
                                            if body_bytes:
                                                body += body_bytes.decode(errors="ignore")
                                        except:
                                            pass
                                else:
                                    body_bytes = msg.get_payload(decode=True)
                                    if body_bytes:
                                        body = body_bytes.decode(errors="ignore")
                                
                                # check "suspended" or "sus"
                                content_to_check = str(subject) + " " + body
                                content_lower = content_to_check.lower()
                                if "suspend" in content_lower or "bị đình chỉ" in content_lower:
                                    account.status = "Thất bại"
                                    account.note = "Bị đình chỉ (suspended)"
                                    if mail:
                                        try: mail.logout()
                                        except: pass
                                    return account
                                    
                account.status = "Thành công"
                account.note = "Live"
                if mail:
                    try: mail.logout()
                    except: pass
                return account
                
            except Exception as e:
                if mail:
                    try: mail.logout()
                    except: pass
                    
                error_str = str(e)
                # If this was the last attempt, return the failure
                if attempt == max_retries - 1:
                    account.status = "Thất bại"
                    if "timeout" in error_str.lower() or isinstance(e, socket.timeout):
                        account.note = "Lỗi kết nối (Timeout)"
                    elif "AUTHENTICATIONFAILED" in error_str.upper() or "login failed" in error_str.lower() or "invalid credentials" in error_str.lower():
                        account.note = f"Sai tài khoản hoặc mật khẩu (Thử log: {account.email} | pass: {account.password})"
                    elif "too many" in error_str.lower() or "limit" in error_str.lower():
                        account.note = "Bị chặn do Rate Limit"
                    else:
                        account.note = f"Lỗi IMAP: {error_str}"
                    return account
            
        return account

class TwitterTimeAdderChecker(IAccountChecker):
    def check(self, account: Account, config: AppConfig) -> Account:
        max_retries = 3
        for attempt in range(max_retries):
            mail = None
            try:
                if attempt > 0:
                    time.sleep(random.uniform(2.0, 4.0))
                else:
                    time.sleep(random.uniform(0.5, 1.5))
                
                if config.use_ssl:
                    mail = imaplib.IMAP4_SSL(config.imap_server, config.imap_port, timeout=30)
                else:
                    mail = imaplib.IMAP4(config.imap_server, config.imap_port, timeout=30)
                
                try:
                    mail.login(account.email, account.password)
                except imaplib.IMAP4.error as e:
                    error_msg = str(e)
                    if "AUTHENTICATIONFAILED" in error_msg.upper() or "invalid credentials" in error_msg.lower() or "login failed" in error_msg.lower():
                        account.status = "Thất bại"
                        account.note = f"Sai tài khoản hoặc mật khẩu"
                        return account
                    else:
                        raise e
                
                status, messages = mail.select("INBOX")
                if status != "OK":
                    account.status = "Thất bại"
                    account.note = "Không thể mở INBOX"
                    if mail:
                        try: mail.logout()
                        except: pass
                    return account
                
                time.sleep(3)
                
                status, response = mail.search(None, "ALL")
                if status == "OK":
                    email_ids = response[0].split()
                    
                    found_date = None
                    for e_id in reversed(email_ids):
                        status, msg_data = mail.fetch(e_id, "(RFC822.HEADER)")
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                
                                subject, encoding = decode_header(msg["Subject"])[0] if msg["Subject"] else ("", None)
                                if isinstance(subject, bytes):
                                    if encoding:
                                        try: subject = subject.decode(encoding)
                                        except: subject = subject.decode('utf-8', errors='ignore')
                                    else:
                                        subject = subject.decode('utf-8', errors='ignore')
                                
                                subject_lower = str(subject).lower()
                                # Check for specific subjects
                                if "two-factor authentication is good to go" in subject_lower or "two factor authentic action is good to go" in subject_lower:
                                    date_header = msg["Date"]
                                    if date_header:
                                        from email.utils import parsedate_to_datetime
                                        try:
                                            dt = parsedate_to_datetime(date_header)
                                            found_date = dt.strftime("%d/%m")
                                        except:
                                            found_date = str(date_header)[:15] # fallback
                                    break
                        if found_date:
                            break
                    
                    if found_date:
                        account.status = "Thành công"
                        account.note = f"Đã thêm ngày: {found_date}"
                        # Append date to original line
                        account.original_line = f"{account.original_line}|{found_date}"
                    else:
                        account.status = "Thất bại"
                        account.note = "Không tìm thấy mail 2FA"
                
                if mail:
                    try: mail.logout()
                    except: pass
                return account
                
            except Exception as e:
                if mail:
                    try: mail.logout()
                    except: pass
                    
                error_str = str(e)
                if attempt == max_retries - 1:
                    account.status = "Thất bại"
                    if "timeout" in error_str.lower() or isinstance(e, socket.timeout):
                        account.note = "Lỗi kết nối (Timeout)"
                    elif "AUTHENTICATIONFAILED" in error_str.upper() or "login failed" in error_str.lower() or "invalid credentials" in error_str.lower():
                        account.note = "Sai tài khoản hoặc mật khẩu"
                    elif "too many" in error_str.lower() or "limit" in error_str.lower():
                        account.note = "Bị chặn do Rate Limit"
                    else:
                        account.note = f"Lỗi IMAP: {error_str}"
                    return account
            
        return account