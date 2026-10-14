import time
import re
import requests

class AutoSMSService:
    """
    Module kết nối tự động với hệ thống thuê số và nhận OTP autosms.site:
    - Base URL: https://autosms.site
    - Lấy số dư: /api/balance?key={api_key}
    - Thuê số: /api/buy-number/{country}/{service}?key={api_key}
    - Lấy OTP: /api/orders/{order_id}?key={api_key}
    """
    def __init__(self, api_key: str, country: str = "us", service: str = "facebook"):
        self.api_key = api_key.strip()
        self.country = country.strip().lower()
        self.service = service.strip().lower()
        self.base_url = "https://autosms.site"

    def get_balance(self) -> dict:
        """Kiểm tra số dư tài khoản autosms.site"""
        url = f"{self.base_url}/api/balance?key={self.api_key}"
        try:
            r = requests.get(url, timeout=10)
            res = r.json()
            if res.get("success"):
                bal = res.get("data", {}).get("balance", 0)
                email = res.get("data", {}).get("email", "")
                return {"success": True, "balance": bal, "email": email}
            return {"success": False, "message": res.get("message", "Lỗi kiểm tra số dư")}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def buy_number(self) -> tuple[bool, str, str, str]:
        """
        Thuê số điện thoại mới theo quốc gia và dịch vụ Facebook
        Returns: (success: bool, phone: str, order_id: str, error_message: str)
        """
        url = f"{self.base_url}/api/buy-number/{self.country}/{self.service}?key={self.api_key}"
        try:
            r = requests.get(url, timeout=15)
            res = r.json()
            if res.get("success") and res.get("data"):
                data = res["data"]
                phone = str(data.get("phone", "")).strip()
                # Chuẩn hóa format số điện thoại (đảm bảo có dấu + ở đầu)
                if phone and not phone.startswith("+"):
                    phone = "+" + phone
                order_id = str(data.get("order_id", ""))
                return True, phone, order_id, ""
            return False, "", "", res.get("message", "Không thể thuê số (Có thể tạm hết số hoặc hết tiền)")
        except Exception as e:
            return False, "", "", str(e)

    def wait_for_otp(self, order_id: str, timeout: int = 20, check_interval: int = 3, log_callback=None) -> tuple[bool, str]:
        """
        Tự động gọi API mỗi 3 giây để bắt mã OTP từ SMS gửi về (Tối đa timeout giây, mặc định max 20s)
        Returns: (success: bool, otp_code_or_error: str)
        """
        start_time = time.time()
        url = f"{self.base_url}/api/orders/{order_id}?key={self.api_key}"
        
        while time.time() - start_time < timeout:
            try:
                r = requests.get(url, timeout=5)
                res = r.json()
                if res.get("success") and res.get("data"):
                    data = res["data"]
                    raw_code = data.get("code")
                    if raw_code and str(raw_code).strip() and str(raw_code).strip() != "None":
                        # Trích xuất mã OTP 5-8 chữ số
                        code_str = str(raw_code).strip()
                        m = re.search(r'\b(\d{5,8})\b', code_str)
                        otp = m.group(1) if m else code_str
                        return True, otp
                        
                    remaining = int(timeout - (time.time() - start_time))
                    if remaining < 0:
                        remaining = 0
                    if log_callback:
                        log_callback(f"[*] Đang đợi SMS OTP từ Facebook... (Còn lại: {remaining}s)")
                else:
                    msg = res.get("message", "")
                    if log_callback and msg:
                        log_callback(f"[-] Trạng thái đơn: {msg}")
            except Exception as e:
                if log_callback:
                    log_callback(f"[!] Lỗi kết nối check OTP: {e}")

            time.sleep(check_interval)

        return False, "Quá thời gian chờ OTP (Max 20s)"
