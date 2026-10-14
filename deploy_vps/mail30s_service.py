# -*- coding: utf-8 -*-
"""
Dịch vụ tích hợp API Mail30s / MailOTP (https://mail30s.com - https://api.mailotp.com)
Hỗ trợ:
- Kiểm tra số dư tài khoản
- Lấy danh sách sản phẩm (loại mail: Hotmail, Outlook, Gmail...)
- Mua mail tự động (/order/create)
- Đọc hộp thư nhận mã OTP (/emails/read)
- Polling chờ mã OTP với timeout tuỳ chỉnh (mặc định 20s)
"""

import time
import re
import json
import requests
from typing import Dict, Any, Optional, Tuple, List


class Mail30sService:
    BASE_AUTOMATION_URL = "https://api.mailotp.com/api/automation"
    BASE_READ_URL = "https://apiv1.mailotp.com/api"

    def __init__(self, api_key: str = "", timeout: int = 15):
        self.api_key = api_key.strip()
        self.http_timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        })

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Accept": "application/json"
        }

    def get_balance(self) -> Dict[str, Any]:
        """Lấy số dư tài khoản từ Mail30s"""
        if not self.api_key:
            return {"success": False, "message": "Chưa nhập API Key Mail30s"}

        url = f"{self.BASE_AUTOMATION_URL}/user/balance"
        try:
            params = {"api_key": self.api_key}
            res = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.http_timeout)
            data = res.json()
            if res.status_code == 200 and data.get("success"):
                user_data = data.get("data", {})
                return {
                    "success": True,
                    "balance": float(user_data.get("balance", 0)),
                    "email": user_data.get("email", ""),
                    "name": user_data.get("name", ""),
                    "level": user_data.get("level_name", "User")
                }
            return {
                "success": False,
                "message": data.get("message", f"HTTP {res.status_code}")
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi kết nối Mail30s: {str(e)}"}

    def get_products(self, min_stock: int = 0) -> List[Dict[str, Any]]:
        """Lấy danh sách các loại mail đang có tồn kho từ Mail30s"""
        if not self.api_key:
            return []

        url = f"{self.BASE_AUTOMATION_URL}/products"
        try:
            params = {"api_key": self.api_key}
            if min_stock > 0:
                params["min_stock"] = min_stock
            res = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.http_timeout)
            data = res.json()
            if res.status_code == 200 and data.get("success"):
                return data.get("data", [])
            return []
        except Exception:
            return []

    def buy_email(self, product_slug: str = "email-hotmail", quantity: int = 1) -> Dict[str, Any]:
        """
        Mua tài khoản email mới qua API.
        Trả về: dict chứa email, password, refresh_token, access_token
        """
        if not self.api_key:
            return {"success": False, "message": "Chưa nhập API Key Mail30s"}

        url = f"{self.BASE_AUTOMATION_URL}/order/create"
        try:
            params = {
                "api_key": self.api_key,
                "product_slug": product_slug,
                "quantity": quantity
            }
            res = self.session.get(url, params=params, headers=self._get_headers(), timeout=self.http_timeout)
            data = res.json()
            if res.status_code == 200 and data.get("success"):
                order_data = data.get("data", {})
                emails = order_data.get("emails", [])
                if emails:
                    mail_item = emails[0]
                    # Parse full_info nếu các trường đơn lẻ bị thiếu
                    full_info = mail_item.get("full_info", "")
                    email = mail_item.get("email", "")
                    password = mail_item.get("password", "")
                    refresh_token = mail_item.get("refresh_token") or mail_item.get("access_token", "")
                    
                    if not email and "|" in full_info:
                        parts = full_info.split("|")
                        email = parts[0] if len(parts) > 0 else ""
                        password = parts[1] if len(parts) > 1 else ""
                        if len(parts) > 2:
                            refresh_token = parts[2]

                    if not full_info:
                        parts = [email, password, refresh_token]
                        full_info = "|".join([p for p in parts if p])

                    return {
                        "success": True,
                        "order_id": order_data.get("order_id"),
                        "email": email.strip(),
                        "password": password.strip(),
                        "refresh_token": refresh_token.strip() if refresh_token else "",
                        "full_info": full_info.strip()
                    }
                return {"success": False, "message": "Đơn hàng thành công nhưng danh sách email rỗng."}
            return {
                "success": False,
                "message": data.get("message", f"HTTP {res.status_code}")
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi tạo đơn mua mail: {str(e)}"}

    def get_otp_shopmailmmo(self, mail_data: str, service: str = "facebook") -> Tuple[bool, Optional[str], str]:
        """
        Gọi API ShopMailMMO để lấy mã OTP:
        https://old.shopmailmmo.com/v1/api/hotmail/code?service=facebook&data=<mail_data>
        Định dạng trả về:
        {"code":"46369","email":"...","password":"...","status":"success"}
        """
        if not mail_data:
            return False, None, "Dữ liệu email trống"

        url = "https://old.shopmailmmo.com/v1/api/hotmail/code"
        params = {
            "service": service,
            "data": mail_data.strip()
        }
        try:
            res = self.session.get(url, params=params, timeout=self.http_timeout)
            try:
                data = res.json()
            except Exception:
                return False, None, f"HTTP {res.status_code}: Không parse được JSON"

            status = data.get("status", "")
            code = data.get("code")
            
            if status == "success" and code:
                code_str = str(code).strip()
                match = re.search(r'\b\d{5,8}\b', code_str)
                final_code = match.group(0) if match else code_str
                return True, final_code, "Lấy OTP thành công"

            err_msg = data.get("error") or data.get("message") or f"status={status}"
            return False, None, str(err_msg)
        except Exception as e:
            return False, None, f"Lỗi kết nối ShopMailMMO: {str(e)}"

    def read_inbox(self, hotmail: str, refresh_token: str = "", password: str = "", limit: int = 10) -> Dict[str, Any]:
        """
        Đọc danh sách email từ hộp thư Hotmail / Outlook qua Mail30s (phương thức phụ)
        """
        if not self.api_key:
            return {"success": False, "message": "Chưa nhập API Key Mail30s"}

        url = f"{self.BASE_READ_URL}/emails/read"
        payload = {
            "hotmail": hotmail.strip(),
            "refresh_token": refresh_token.strip(),
            "password": password.strip(),
            "folder": "Inbox",
            "limit": limit,
            "unread_only": False
        }
        
        headers = self._get_headers()
        headers["Content-Type"] = "application/json"

        try:
            res = self.session.post(
                url,
                params={"api_key": self.api_key},
                json=payload,
                headers=headers,
                timeout=self.http_timeout
            )
            data = res.json()
            if res.status_code == 200 and data.get("success"):
                inbox_data = data.get("data", {})
                return {
                    "success": True,
                    "emails": inbox_data.get("emails", []),
                    "total": inbox_data.get("total", 0)
                }
            return {
                "success": False,
                "message": data.get("message", f"HTTP {res.status_code}"),
                "emails": []
            }
        except Exception as e:
            return {"success": False, "message": f"Lỗi đọc hộp thư: {str(e)}", "emails": []}

    def extract_fb_otp(self, text: str) -> Optional[str]:
        """
        Trích xuất mã OTP Facebook từ tiêu đề / nội dung mail
        """
        if not text:
            return None
        patterns = [
            r'FB-(\d{5,8})',
            r'(?:code|mã|xác nhận|is)\s*(?:is|là|:)?\s*(\d{5,6})\b',
            r'\b(\d{5})\b',
            r'\b(\d{6})\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def wait_for_otp(
        self,
        hotmail: str = "",
        refresh_token: str = "",
        password: str = "",
        full_info: str = "",
        mail_data: str = "",
        timeout: int = 60,
        check_interval: int = 5,
        log_callback=None
    ) -> Tuple[bool, Optional[str], str]:
        """
        Vòng lặp chờ mã OTP Facebook từ API ShopMailMMO (https://old.shopmailmmo.com/v1/api/hotmail/code).
        Định kỳ ping mỗi 5 giây 1 lần cho đến khi có OTP hoặc hết timeout.
        Trả về: (success, otp_code, message)
        """
        # Xác định chuỗi data dùng để gọi ShopMailMMO
        raw_data = (mail_data or full_info or "").strip()
        if not raw_data:
            parts = [hotmail, password, refresh_token]
            raw_data = "|".join([p for p in parts if p])

        target_display = hotmail or (raw_data.split("|")[0] if raw_data else "email")
        start_time = time.time()
        elapsed = 0
        attempt = 1

        if log_callback:
            log_callback(f"[SHOPMAILMMO] Bắt đầu polling OTP cho {target_display} (Ping mỗi {check_interval}s, Timeout {timeout}s)...")

        while elapsed < timeout:
            ok, code, msg = self.get_otp_shopmailmmo(mail_data=raw_data, service="facebook")
            if ok and code:
                if log_callback:
                    log_callback(f"[SHOPMAILMMO] ==> ĐÃ BẮT ĐƯỢC MÃ OTP FACEBOOK: {code} <==")
                return True, code, "Thành công"

            elapsed = int(time.time() - start_time)
            rem = max(0, timeout - elapsed)
            if log_callback and rem > 0:
                log_callback(f"[SHOPMAILMMO] Lần {attempt}: Chưa có OTP ({msg}). Đợi {check_interval}s ({rem}s còn lại)...")

            if elapsed >= timeout:
                break

            time.sleep(check_interval)
            attempt += 1
            elapsed = int(time.time() - start_time)

        return False, None, f"Hết thời gian chờ mã OTP ({timeout}s)"
