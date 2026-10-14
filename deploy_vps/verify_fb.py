import os
import random
import sys
import re
import json
import time
import uuid
import urllib.parse
import concurrent.futures
import requests as std_requests
from curl_cffi import requests

# Đảm bảo hiển thị tiếng Việt UTF-8 chuẩn trên Windows PowerShell / CMD
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
if sys.stderr.encoding != 'utf-8':
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from device_profiles import get_device_profile, generate_random_device_profile

class FBPhoneVerifier:
    def __init__(self, raw_cookie: str, proxy: str = None, user_agent: str = None, force_ios: bool = True):
        self.raw_cookie = raw_cookie
        self.proxy = proxy
        
        # Tự động đồng bộ Device Profile (Ưu tiên chuẩn iOS Mobile Safari như tool reg live cao)
        self.device = get_device_profile(user_agent=user_agent, force_ios=force_ios)
        self.is_ios = self.device.get("is_ios", True)
        self.ua = self.device["ua"]
        self.sec_ch_ua = self.device.get("sec_ch_ua")
        self.sec_ch_ua_model = self.device.get("sec_ch_ua_model")
        self.sec_ch_ua_platform_version = self.device.get("sec_ch_ua_platform_version")
        self.sec_ch_ua_full_version_list = self.device.get("sec_ch_ua_full_version_list")
        self.dpr = str(self.device.get("dpr", "3.0"))
        self.viewport = str(self.device.get("viewport", "393"))
        self.viewport_h = str(self.device.get("viewport_h", "852"))
        
        # Tự động đồng bộ Cookie: giữ nguyên hoặc sinh m_pixel_ratio, wd, locale=en_US chuẩn iPhone
        self.cookies_dict = self._parse_cookie(raw_cookie, is_ios=self.is_ios)
        
        impersonate_target = self.device.get("impersonate", "safari18_0_ios" if self.is_ios else "chrome131_android")
        os_label = f"iOS {self.device['os_version']}" if self.is_ios else f"Android {self.device['os_version']}"
        if self.device.get("is_custom"):
            print(f"[+] ĐỒNG BỘ THIẾT BỊ: {self.device['brand_name']} ({os_label}) [TLS: {impersonate_target}]")
        else:
            print(f"[+] Giả lập thiết bị: {self.device['brand_name']} ({os_label}) [TLS: {impersonate_target}]")
        print(f"    User-Agent: {self.ua}")
        
        # Cấu hình session với curl_cffi giả lập TLS Fingerprint & HTTP/2 chuẩn xác
        self.session = requests.Session(impersonate=impersonate_target)
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
            print(f"[+] Sử dụng Proxy: {self.proxy.split('@')[-1] if '@' in self.proxy else self.proxy}")
            
        # Nạp cookie đã làm sạch vào session
        for k, v in self.cookies_dict.items():
            self.session.cookies.set(k, v, domain=".facebook.com")
            
        # Tokens và IDs được bóc tách ĐỘNG 100% trong quá trình chạy
        self.tokens = {}
        self.bkv = "981d02932ae57e31b9365d9fbc55eb8bcac3ea662db02d859113b364288479bc"
        self.reg_info = None
        self.waterfall_id = None
        self.current_step = 10
        self.req_counter = 1
        
        # IDs cho bước nhập SĐT mới (Lấy động từ response bước mở form)
        self.change_phone_event_id = None
        self.phone_input_id = None
        
        # IDs cho bước nhập Email mới (Lấy động từ response mở form email)
        self.change_email_event_id = None
        self.email_input_id = None
        self.new_email = None
        
        # IDs cho bước xác minh OTP (Lấy động từ response màn hình OTP)
        self.otp_event_id = None
        self.otp_input_id = None
        self.new_phone = None
        self.impersonate_target = impersonate_target
        self.last_error = ""
        self.timeout = 40  # Tăng timeout lên 40 giây theo yêu cầu

        # Sinh Session State động cho từng tài khoản (cụm 2 và 3 giữ xuyên suốt phiên, cụm 1 sinh theo tương tác)
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        self._s_session = "".join(random.choice(chars) for _ in range(6))
        self._s_entropy = "".join(random.choice(chars) for _ in range(6))
        # Sinh 1 WebLiteLid duy nhất cố định xuyên suốt phiên của tài khoản (chuẩn HAR)
        self.lid = str(random.randint(7694900000000000000, 7694999999999999999))


    def _get_session_s(self) -> str:
        """Sinh chuỗi __s động chuẩn của Meta: interaction:session:entropy (VD: vcftp5:4be8an:7us9u7)"""
        chars = "abcdefghijklmnopqrstuvwxyz0123456789"
        interaction_id = "".join(random.choice(chars) for _ in range(6))
        return f"{interaction_id}:{self._s_session}:{self._s_entropy}"

    def _parse_cookie(self, raw_cookie: str, is_ios: bool = True) -> dict:
        """
        Bóc tách và chuẩn hóa Cookie:
        - Bỏ các key rác: ps_l, ps_n, noscript.
        - GIỮ NGUYÊN và chuẩn hóa: wd, m_pixel_ratio, locale=en_US (chuẩn như nick live của pro).
        - Nếu cookie fr cũ là dạng fr=2... (của Chrome cũ) thì bỏ để Facebook cấp fr mới cho Safari iOS.
        - Giữ nguyên các session token cốt lõi: datr, c_user, xs, sb, pas.
        """
        cookies = {}
        banned_keys = {"ps_l", "ps_n", "noscript"}
        for item in raw_cookie.split(";"):
            item = item.strip()
            if "=" in item:
                k, v = item.split("=", 1)
                k = k.strip()
                v = urllib.parse.unquote(v.strip())
                if k in banned_keys:
                    continue
                # Nếu là iOS và gặp fr=2... của Chrome cũ -> Bỏ để server FB cấp fr mới
                if is_ios and k == "fr" and v.startswith("2"):
                    continue
                cookies[k] = v

        if is_ios:
            # Luôn đồng bộ wd và m_pixel_ratio theo profile iOS đang giả lập (ghi đè độ phân giải 1080x1920 cũ của Android)
            vp_w = getattr(self, "viewport", "393")
            vp_h = getattr(self, "viewport_h", "852")
            cookies["wd"] = f"{vp_w}x{vp_h}"
            cookies["m_pixel_ratio"] = str(getattr(self, "dpr", "3.0"))
            if "locale" not in cookies or cookies.get("locale") in ["vi_VN", ""]:
                cookies["locale"] = "en_US"

        return cookies

    def get_cookie_string(self) -> str:
        """Lấy toàn bộ cookie của session dưới dạng chuỗi chuẩn sạch giống hệt định dạng của pro"""
        try:
            cookie_dict = self.session.cookies.get_dict()
            if cookie_dict:
                order = ["datr", "c_user", "m_pixel_ratio", "wd", "fr", "xs", "sb", "locale", "pas"]
                parts = []
                for k in order:
                    if k in cookie_dict:
                        parts.append(f"{k}={cookie_dict[k]}")
                for k, v in cookie_dict.items():
                    if k not in order:
                        parts.append(f"{k}={v}")
                return "; ".join(parts)
            return self.raw_cookie
        except Exception:
            return self.raw_cookie

    def _rebuild_session(self):
        """Tái tạo phiên curl_cffi sạch với proxy và cookies hiện tại để khắc phục ngắt kết nối TLS/Socket"""
        try:
            current_cookies = self.session.cookies.get_dict() if hasattr(self, 'session') and self.session else self.cookies_dict
            self.session = requests.Session(impersonate=self.impersonate_target)
            if self.proxy:
                self.session.proxies = {"http": self.proxy, "https": self.proxy}
            for k, v in current_cookies.items():
                self.session.cookies.set(k, v, domain=".facebook.com")
        except Exception:
            pass

    def _request_with_retry(self, method: str, url: str, max_retry_sec: float = 40.0, **kwargs):
        """
        Thực hiện HTTP request: Nếu proxy bị ngắt kết nối / TLS connect error / timeout:
        Tiếp tục kiên trì kết nối lại trên chính proxy đó trong tối đa 40 giây.
        Nếu quá 40 giây không kết nối được -> ném exception để dừng flow.
        """
        start_time = time.time()
        attempt = 0
        last_exc = None
        while True:
            attempt += 1
            elapsed = time.time() - start_time
            if elapsed >= max_retry_sec and attempt > 1:
                break
            try:
                remaining = max(3.0, max_retry_sec - elapsed)
                timeout_val = min(float(kwargs.get("timeout", self.timeout)), remaining)
                req_kwargs = dict(kwargs)
                req_kwargs["timeout"] = timeout_val
                
                if method.lower() == "get":
                    return self.session.get(url, **req_kwargs)
                else:
                    return self.session.post(url, **req_kwargs)
            except Exception as e:
                last_exc = e
                elapsed = time.time() - start_time
                if elapsed >= max_retry_sec:
                    break
                print(f"[*] Proxy bị ngắt kết nối ({e.__class__.__name__}). Đang thử kết nối lại... (Đã chờ {elapsed:.1f}s/40s)")
                self._rebuild_session()
                time.sleep(1.0)
                
        err_msg = f"Đã thử kết nối lại proxy trong {time.time() - start_time:.1f}s (vượt quá 40s) nhưng không thành công: {last_exc}"
        print(f"[-] {err_msg}")
        self.last_error = "PROXY_CONNECTION_FAILED"
        raise last_exc or Exception(err_msg)

    def _get_base_headers(self, referer: str = "https://m.facebook.com/confirmemail.php") -> dict:
        lang = "en-US,en;q=0.9" if self.is_ios else "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
        headers = {
            "authority": "m.facebook.com",
            "accept": "*/*",
            "accept-language": lang,
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "origin": "https://m.facebook.com",
            "referer": referer,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": self.ua,
            "x-asbd-id": "359341",
            "x-fb-lsd": self.tokens.get("lsd", ""),
        }
        # Safari trên iOS tuyệt đối không gửi Client Hints (sec-ch-ua*). Chỉ Android Chrome mới có.
        if not self.is_ios and self.sec_ch_ua:
            headers["sec-ch-ua"] = self.sec_ch_ua
            headers["sec-ch-ua-mobile"] = "?1"
            headers["sec-ch-ua-platform"] = '"Android"'
            headers["sec-ch-ua-platform-version"] = self.sec_ch_ua_platform_version
            headers["sec-ch-ua-model"] = self.sec_ch_ua_model
        return headers

    def _decode_unicode_escapes(self, text: str) -> str:
        """Giải mã an toàn tất cả chuỗi escape unicode (\\u0111, \u0111, v.v.)"""
        def decode_match(m):
            try:
                return chr(int(m.group(1), 16))
            except Exception:
                return m.group(0)
        return re.sub(r'\\+u([0-9a-fA-F]{4})', decode_match, text)

    def parse_screen_ui(self, resp_text: str, current_url: str = "") -> dict:
        """
        Bóc tách chính xác giao diện Facebook trả về:
        - Trích xuất controller_name
        - Giải mã toàn bộ câu chữ tiếng Việt xuất hiện trên màn hình
        - Phân loại rõ ràng loại form, tiêu đề, hướng dẫn và các nút bấm
        """
        decoded = self._decode_unicode_escapes(resp_text)
        
        # 1. Trích xuất controller_name từ JSON / Lispy payload
        m_ctrl = re.findall(r'"controller_name"\s*:\s*"([^"]+)"', decoded)
        ctrl = m_ctrl[0] if m_ctrl else ""
        
        # 2. Tìm tất cả các chuỗi tiếng Việt có nghĩa trên giao diện
        raw_strings = re.findall(r'"([^"\\]{3,200})"', decoded)
        vn_strings = []
        seen = set()
        for s in raw_strings:
            s_clean = s.strip()
            if re.search(r'[\u00C0-\u1EF9]', s_clean) and s_clean not in seen and len(s_clean) > 2:
                seen.add(s_clean)
                vn_strings.append(s_clean)
                
        # 3. Phân loại màn hình chuẩn xác theo Controller và Lispy state
        screen_id = "SCREEN_UNKNOWN"
        title = ""
        instruction = ""
        buttons = []
        error_msg = ""
        
        if ctrl == "BloksCAARegConfirmationFBBottomSheetController":
            screen_id = "SCREEN_BOTTOMSHEET"
            title = "Menu tùy chọn: 'Tôi không nhận được mã'"
            buttons = [s for s in vn_strings if s in ["Gửi lại mã đến SMS", "Đổi số di động", "Xác nhận bằng email", "Đăng xuất", "Đóng"]]
            instruction = "Menu chứa các tùy chọn đổi phương thức hoặc đổi số điện thoại mới."
        elif ctrl == "BloksCAARegConfirmationChangePhoneController":
            screen_id = "SCREEN_CHANGE_PHONE"
            title = "Form đổi SĐT: 'Số di động của bạn là gì?'"
            inst_cands = [s for s in vn_strings if "Số điện thoại sẽ dùng" in s or "Chúng tôi có thể gửi" in s or "Nhập số di động có thể dùng" in s]
            instruction = " ".join(inst_cands) if inst_cands else "Nhập số di động có thể dùng để liên hệ với bạn."
            buttons = [s for s in vn_strings if s in ["Tiếp", "Quay lại", "Đăng ký bằng email"]]
        elif ctrl == "BloksCAARegConfirmationChangeEmailController":
            screen_id = "SCREEN_CHANGE_EMAIL"
            title = "Form đổi Email: 'Địa chỉ email của bạn là gì?'"
            inst_cands = [s for s in vn_strings if "email" in s.lower() or "liên hệ" in s.lower()]
            instruction = " ".join(inst_cands) if inst_cands else "Nhập địa chỉ email có thể dùng để liên hệ với bạn."
            buttons = [s for s in vn_strings if s in ["Tiếp", "Quay lại", "Đăng ký bằng số di động"]]
        elif ctrl == "BloksCAARegContactPointPhoneAsyncController":
            screen_id = "ACTION_PHONE_SUBMITTED"
            title = "Action: Gửi số điện thoại mới lên Facebook"
            if 'is_phone_valid\\" true' in decoded or 'CAA_REG_CONFIRMATION_SCREEN' in decoded:
                instruction = "Server Facebook đã chấp nhận số điện thoại mới và kích hoạt gửi mã OTP."
            elif 'should_show_error\\" true' in decoded or 'should_show_error":true' in decoded:
                error_msg = "Số điện thoại không hợp lệ hoặc Facebook từ chối số này."
            else:
                instruction = "Server Facebook đã chấp nhận số điện thoại mới."
        elif ctrl == "BloksCAARegContactPointEmailAsyncController":
            screen_id = "ACTION_EMAIL_SUBMITTED"
            title = "Action: Gửi địa chỉ Email mới lên Facebook"
            # Tìm câu chữ phản hồi thực tế từ Facebook
            actual_vn = [s for s in vn_strings if any(k in s.lower() for k in ["mã", "xác nhận", "email", "tiếp", "gửi"])]
            if 'is_input_valid\\" true' in decoded or 'CAA_REG_CONFIRMATION_SCREEN' in decoded or 'conf_code' in decoded:
                instruction = actual_vn[0] if actual_vn else "Server Facebook đã chấp nhận Email mới và chuyển sang bước gửi mã OTP."
            elif 'should_show_error\\" true' in decoded or 'should_show_error":true' in decoded:
                error_msg = "Địa chỉ email không hợp lệ hoặc Facebook từ chối email này."
            else:
                instruction = actual_vn[0] if actual_vn else "Server Facebook đã phản hồi form email mới."
        elif ctrl == "BloksCAARegConfirmationController":
            screen_id = "SCREEN_ENTER_OTP"
            # Tìm tiêu đề thật từ Facebook trả về
            title_cands = [s for s in vn_strings if any(k in s.lower() for k in ["nhập mã", "xác nhận", "mã xác nhận"])]
            title = f"Form xác nhận mã: '{title_cands[0]}'" if title_cands else "Form xác nhận mã: 'Nhập mã xác nhận'"
            
            # Trích xuất chính xác câu hướng dẫn nguyên văn từ Facebook gửi về
            inst_cands = [s for s in vn_strings if any(k in s.lower() for k in ["nhập mã", "gửi tới", "gửi đến", "chữ số", "để xác nhận", "hãy nhập"])]
            if inst_cands:
                instruction = inst_cands[0]
            else:
                # Quét trực tiếp trong chuỗi giải mã
                raw_match = re.findall(r'\"([^\"]*(?:nhập mã|gửi tới|gửi đến|chữ số|xác nhận)[^\"]*)\"', decoded, re.IGNORECASE)
                if raw_match:
                    instruction = raw_match[0]
                else:
                    curr_cp = getattr(self, "new_email", "") or getattr(self, "new_phone", "") or self.reg_info.get("contactpoint", "")
                    instruction = f"Màn hình nhập mã xác nhận (Target: {curr_cp})"
            buttons = [s for s in vn_strings if s in ["Tiếp", "Tôi không nhận được mã", "Đóng"]]
        elif ctrl == "BloksCAARegConfirmationAsyncController":
            screen_id = "ACTION_SUBMIT_OTP"
            title = "Action: Xác minh mã OTP"
            if "confirmation_success" in decoded or "confirm_contact_point_finished" in decoded or "deoia=1" in decoded:
                target_label = "Email" if (getattr(self, "new_email", None) or self.reg_info.get("contactpoint_type") == "email") else "SĐT"
                instruction = f"Xác minh mã OTP thành công! {target_label} mới đã được kích hoạt trên tài khoản."
            else:
                m_actual_err = re.findall(r'CAA_REG_CONFIRMATION[^}]*error_message[^}]*"initial":"([^"]+)"', decoded)
                error_msg = m_actual_err[0] if (m_actual_err and m_actual_err[0]) else "Mã xác nhận không đúng hoặc đã hết hạn."
        elif "CAA_REG_CONFIRMATION_SCREEN" in decoded or "reg_info" in decoded:
            screen_id = "SCREEN_CONFIRMEMAIL_INIT"
            title = "Trang xác minh tài khoản ban đầu (confirmemail.php)"
            instruction = "Tìm thấy dữ liệu đăng ký reg_info của tài khoản."
        elif "/checkpoint" in current_url or "<title>checkpoint" in decoded.lower():
            screen_id = "SCREEN_CHECKPOINT"
            title = "Tài khoản bị khóa Checkpoint"
            error_msg = "Facebook chuyển hướng tới trang Checkpoint, cần xử lý mở khóa trước."
        elif "/login" in current_url or "<title>đăng nhập" in decoded.lower():
            screen_id = "SCREEN_LOGGED_OUT"
            title = "Phiên đăng nhập đã hết hạn"
            error_msg = "Cookie đã bị hủy hoặc chưa đăng nhập vào Facebook."
            
        return {
            "screen_id": screen_id,
            "controller": ctrl,
            "title": title,
            "instruction": instruction,
            "buttons": buttons,
            "error_msg": error_msg,
            "vn_strings": vn_strings
        }

    def print_flow_report(self, flow_step: str, ui_info: dict, is_expected: bool):
        """In báo cáo câu chữ xác nhận chuẩn chỉnh từng bước ra màn hình terminal"""
        print(f"\n{'-'*65}")
        print(f"[{flow_step}] KẾT QUẢ GIAO DIỆN FACEBOOK:")
        print(f"  • Màn hình nhận diện: [{ui_info['screen_id']}]")
        if ui_info.get("controller"):
            print(f"  • Controller: {ui_info['controller']}")
        if ui_info.get("title"):
            print(f"  • Tiêu đề: \"{ui_info['title']}\"")
        if ui_info.get("instruction"):
            print(f"  • Câu chữ hiển thị: \"{ui_info['instruction']}\"")
        if ui_info.get("buttons"):
            print(f"  • Các nút hành động: [{', '.join(ui_info['buttons'])}]")
            
        if ui_info.get("error_msg"):
            print(f"  • ⚠️ THÔNG BÁO LỖI: {ui_info['error_msg']}")
            print(f"  => TRẠNG THÁI: [THẤT BẠI] Flow dừng tại bước này.")
        elif is_expected:
            print(f"  => TRẠNG THÁI: [XÁC NHẬN ĐÚNG FORM] Tiến hành bước tiếp theo...")
        else:
            print(f"  => TRẠNG THÁI: [SAI MÀN HÌNH MONG ĐỢI]")
        print(f"{'-'*65}\n")

    def init_session(self) -> bool:
        """Bước 0: Load confirmemail.php để bóc tách tokens và reg_info gốc"""
        print("[*] Đang truy cập m.facebook.com/confirmemail.php để lấy session tokens...")
        headers = {
            "authority": "m.facebook.com",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "accept-language": "en-US,en;q=0.9" if self.is_ios else "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "upgrade-insecure-requests": "1",
            "user-agent": self.ua,
        }
        if not self.is_ios and self.sec_ch_ua:
            headers["sec-ch-ua"] = self.sec_ch_ua
            headers["sec-ch-ua-mobile"] = "?1"
            headers["sec-ch-ua-platform"] = '"Android"'
            headers["sec-ch-ua-model"] = self.sec_ch_ua_model
        
        try:
            resp = self._request_with_retry("get", "https://m.facebook.com/confirmemail.php", headers=headers, allow_redirects=True, max_retry_sec=40.0)
            html = resp.text
        except Exception as e:
            err_str = str(e)
            if "Timeout" in err_str or "timed out" in err_str:
                print(f"[-] Lỗi kết nối m.facebook.com (quá thời gian chờ 40s): {e}")
            else:
                print(f"[-] Lỗi kết nối m.facebook.com (Proxy die/lỗi mạng quá 40s): {e}")
            self.last_error = "PROXY_CONNECTION_FAILED"
            return False
        
        # Nhận diện màn hình ban đầu
        ui_info = self.parse_screen_ui(html, resp.url)
        if ui_info["screen_id"] == "SCREEN_CHECKPOINT":
            self.last_error = "CHECKPOINT"
            self.print_flow_report("FLOW 0: KHỞI TẠO PHIÊN", ui_info, False)
            return False
        elif ui_info["screen_id"] == "SCREEN_LOGGED_OUT":
            self.last_error = "LOGGED_OUT"
            self.print_flow_report("FLOW 0: KHỞI TẠO PHIÊN", ui_info, False)
            return False
        
        # 1. Parse fb_dtsg (ĐỘNG)
        m_dtsg = (
            re.findall(r'name="fb_dtsg"\s+value="([^"]+)"', html) or
            re.findall(r'\["DTSGInitialData",\[\],\{"token":"([^"]+)"', html) or
            re.findall(r'"dtsg":\{"token":"([^"]+)"', html) or
            re.findall(r'"token":"([a-zA-Z0-9_\-:]+:\d+:\d+)"', html)
        )
        if m_dtsg:
            self.tokens["fb_dtsg"] = m_dtsg[0]
            
        # 2. Parse lsd (ĐỘNG)
        m_lsd = (
            re.findall(r'name="lsd"\s+value="([^"]+)"', html) or
            re.findall(r'\["LSD",\[\],\{"token":"([^"]+)"', html) or
            re.findall(r'"LSDInitialData"[^}]*"token":"([^"]+)"', html)
        )
        if m_lsd:
            self.tokens["lsd"] = m_lsd[0]
            
        # 3. Parse jazoest (ĐỘNG)
        m_jazo = re.findall(r'name="jazoest"\s+value="([^"]+)"', html) or re.findall(r'jazoest=(\d+)', html)
        if m_jazo:
            self.tokens["jazoest"] = m_jazo[0]
        elif "fb_dtsg" in self.tokens:
            s = sum(ord(c) for c in self.tokens["fb_dtsg"])
            self.tokens["jazoest"] = f"2{s}"
            
        # 4. Spin tokens & haste_session (ĐỘNG)
        m_spin_r = re.findall(r'"__spin_r":(\d+)', html) or re.findall(r'"server_revision":(\d+)', html)
        m_spin_b = re.findall(r'"__spin_b":"([^"]+)"', html)
        m_spin_t = re.findall(r'"__spin_t":(\d+)', html)
        m_hsi = re.findall(r'"hsi":"([^"]+)"', html)
        m_hs = (
            re.findall(r'"haste_session":"([^"]+)"', html) or
            re.findall(r'__hs=([^&"\']+)', html) or
            re.findall(r'(\d+\.BP:mtouch_pkg\.[^"\']+)', html)
        )
        
        self.tokens["__spin_r"] = m_spin_r[0] if m_spin_r else "1050313345"
        self.tokens["__spin_b"] = m_spin_b[0] if m_spin_b else "trunk"
        self.tokens["__spin_t"] = m_spin_t[0] if m_spin_t else str(int(time.time()))
        self.tokens["__hsi"] = m_hsi[0] if m_hsi else ""
        self.tokens["__hs"] = m_hs[0] if m_hs else "20740.BP:mtouch_pkg.2.0...0"
        
        # 5. Version bundle __bkv (ĐỘNG)
        m_bkv = re.findall(r'__bkv=([a-f0-9]{32,})', html) or re.findall(r'versioning_id[\\\":]+([a-f0-9]{32,})', html)
        if m_bkv:
            self.bkv = m_bkv[0]
        
        # 6. Waterfall ID (ĐỘNG)
        wf_matches = re.findall(r'\\+"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\\+"', html)
        if wf_matches:
            self.waterfall_id = wf_matches[0]
        else:
            self.waterfall_id = str(uuid.uuid4())
            
        # 7. Parse reg_info gốc (ĐỘNG)
        m_reg = re.search(r'\\"(\{\\+\"first_name\\+\".*?tos_accepted_on_profile_info\\+\":null\})\s*\\"', html)
        if m_reg:
            clean_reg = re.sub(r'\\+\"', '"', m_reg.group(1)).replace('\\/', '/')
            try:
                self.reg_info = json.loads(clean_reg)
                print(f"[+] Lấy thành công reg_info: {self.reg_info.get('full_name')} (ID: {self.reg_info.get('user_id')})")
                print(f"[+] SĐT hiện tại trên acc: {self.reg_info.get('contactpoint')}")
            except Exception as e:
                print(f"[-] Parse reg_info json lỗi: {e}")
                
        if not self.reg_info:
            print("[-] Không tìm thấy reg_info trong trang confirmemail. Có thể acc đã verify hoặc cookie hết hạn.")
            return False
            
        self.print_flow_report("FLOW 0: KHỞI TẠO PHIÊN", ui_info, True)
        # Bắn telemetry giả lập browser render xong trang confirmemail
        self.send_wbloks_telemetry("com.bloks.www.bloks.caa.reg.confirmation", "https://m.facebook.com/confirmemail.php")
        return True

    def send_wbloks_telemetry(self, trace_policy: str = "com.bloks.www.bloks.caa.reg.confirmation", current_url: str = "https://m.facebook.com/confirmemail.php"):
        """
        Bắn giả lập các event log ngầm của Web Bloks runtime (Chrome Android thật):
        Gồm: RESPONSE_START -> CLIENT_IMPRESSION -> RESPONSE_END -> DISPLAY_JS_DONE -> WBLOKS_INVOKED -> ROOT_MOUNTED
        Giúp đánh lừa Meta AI rằng trang đã được parse và render hoàn chỉnh trên trình duyệt.
        """
        lid = getattr(self, "lid", str(random.randint(7694900000000000000, 7694999999999999999)))
        base_time = random.randint(2500, 3500)
        impid = "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=17))
        fb_dtsg = self.tokens.get("fb_dtsg", "")
        jazoest = self.tokens.get("jazoest", "")

        events = [
            ("RESPONSE_START", base_time),
            ("CLIENT_IMPRESSION", base_time + random.randint(10, 50)),
            ("RESPONSE_END", base_time + random.randint(80, 150)),
            ("DISPLAY_JS_DONE", base_time + random.randint(200, 350)),
            ("WBLOKS_INVOKED", base_time + random.randint(380, 500)),
            ("ROOT_MOUNTED", base_time + random.randint(600, 900))
        ]

        headers = {
            "authority": "m.facebook.com",
            "accept": "*/*",
            "content-length": "0",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "no-cors",
            "sec-fetch-dest": "empty",
            "referer": current_url,
            "user-agent": self.ua
        }
        if not self.is_ios and self.sec_ch_ua:
            headers["sec-ch-ua"] = self.sec_ch_ua
            headers["sec-ch-ua-mobile"] = "?1"
            headers["sec-ch-ua-platform"] = '"Android"'
            headers["sec-ch-ua-model"] = self.sec_ch_ua_model
            headers["sec-ch-ua-platform-version"] = self.sec_ch_ua_platform_version
            headers["sec-ch-ua-full-version-list"] = self.sec_ch_ua_full_version_list

        sent_count = 0
        for ev_name, ev_time in events:
            params = {
                "lid": lid,
                "event": ev_name,
                "relativeTime": str(ev_time),
                "tracePolicy": trace_policy,
                "bloksAppId": "fb_web",
                "u": current_url,
                "seo": "",
                "fbs": "",
                "impid": impid,
            }
            if fb_dtsg:
                params["fb_dtsg"] = fb_dtsg
            if jazoest:
                params["jazoest"] = jazoest

            url = f"https://m.facebook.com/async/wbloks/log/?{urllib.parse.urlencode(params)}"
            try:
                self.session.post(url, headers=headers, timeout=10)
                sent_count += 1
            except Exception:
                pass
        print(f"  [+] Bắn Telemetry Bloks ngầm ({sent_count}/{len(events)} events: CLIENT_IMPRESSION, ROOT_MOUNTED...)")

    def _build_post_data(self, params_dict: dict) -> dict:
        self.req_counter += 1
        return {
            "__user": self.cookies_dict.get("c_user", "0"),
            "__a": "1",
            "__req": str(self.req_counter),
            "__hs": self.tokens.get("__hs", "20740.BP:mtouch_pkg.2.0...0"),
            "dpr": self.dpr,
            "__ccg": "EXCELLENT",
            "__rev": self.tokens.get("__spin_r", "1050313345"),
            "__s": self._get_session_s(),
            "__hsi": self.tokens.get("__hsi", ""),
            "__dyn": "1KidAG1mws8-t0BBBwno4a2i5U4e1FwKwSwMxW0Horx67o1g8hw23E52q1ew2io0D24o1sE522G0pS0H83bw4FwmE2ewnE2Lx-220n6azo7u0zE2ZwrU6C2-0le0iS2eU2dwde2G0JU",
            "fb_dtsg": self.tokens.get("fb_dtsg", ""),
            "jazoest": self.tokens.get("jazoest", ""),
            "lsd": self.tokens.get("lsd", ""),
            "__jssesw": "10",
            "params": json.dumps(params_dict, separators=(",", ":"))
        }

    def open_not_received_code_bottomsheet(self) -> bool:
        """Bước 1a: Click 'Tôi không nhận được mã' (Mở menu bottomsheet)"""
        print("[*] Đang bấm 'Tôi không nhận được mã' (Mở menu chọn đổi số điện thoại)...")
        url = f"https://m.facebook.com/async/wbloks/fetch/?appid=com.bloks.www.bloks.caa.reg.confirmation.fb.bottomsheet&type=app&__bkv={self.bkv}"
        
        payload_params = {
            "params": json.dumps({
                "server_params": {
                    "waterfall_id": self.waterfall_id,
                    "is_platform_login": 0,
                    "is_from_logged_out": 0,
                    "access_flow_version": "pre_mt_behavior",
                    "login_surface": "unknown",
                    "current_step": self.current_step,
                    "reg_info": json.dumps(self.reg_info, separators=(",", ":")),
                    "flow_info": json.dumps({"flow_name": "new_to_family_fb_default", "flow_type": "ntf"}, separators=(",", ":"))
                },
                "client_input_params": {
                    "lois_settings": {"lois_token": ""},
                    "aac": "",
                    "gms_incoming_call_retriever_eligibility": "client_not_supported"
                }
            }, separators=(",", ":"))
        }
        
        post_data = self._build_post_data(payload_params)
        headers = self._get_base_headers()
        try:
            resp = self._request_with_retry("post", url, data=post_data, headers=headers)
        except Exception:
            return False
        
        ui_info = self.parse_screen_ui(resp.text)
        is_success = (resp.status_code == 200 and ui_info["screen_id"] == "SCREEN_BOTTOMSHEET")
        self.print_flow_report("FLOW 1: MỞ MENU KHÔNG NHẬN ĐƯỢC MÃ", ui_info, is_success)
        if is_success:
            self.send_wbloks_telemetry("com.bloks.www.bloks.caa.reg.confirmation.fb.bottomsheet")
        return is_success

    def request_change_phone_form(self) -> bool:
        """Bước 1b: Click 'Đổi số điện thoại' từ menu & bóc tách dynamic input ID"""
        # Mở bottomsheet trước
        if not self.open_not_received_code_bottomsheet():
            print("[-] Không thể mở menu Bottomsheet tùy chọn.")
            return False
            
        print("[*] Đang bấm 'Đổi số điện thoại' (Mở khung nhập số mới)...")
        url = f"https://m.facebook.com/async/wbloks/fetch/?appid=com.bloks.www.bloks.caa.reg.confirmation.change.phone&type=app&__bkv={self.bkv}"
        
        payload_params = {
            "params": json.dumps({
                "server_params": {
                    "waterfall_id": self.waterfall_id,
                    "is_platform_login": 0,
                    "is_from_logged_out": 0,
                    "access_flow_version": "pre_mt_behavior",
                    "login_surface": "unknown",
                    "current_step": self.current_step,
                    "reg_info": json.dumps(self.reg_info, separators=(",", ":")),
                    "flow_info": json.dumps({"flow_name": "new_to_family_fb_default", "flow_type": "ntf"}, separators=(",", ":"))
                },
                "client_input_params": {
                    "lois_settings": {"lois_token": ""},
                    "aac": ""
                }
            }, separators=(",", ":"))
        }
        
        post_data = self._build_post_data(payload_params)
        headers = self._get_base_headers()
        try:
            resp = self._request_with_retry("post", url, data=post_data, headers=headers)
        except Exception:
            return False
        
        ui_info = self.parse_screen_ui(resp.text)
        is_success = (resp.status_code == 200 and ui_info["screen_id"] == "SCREEN_CHANGE_PHONE")
        self.print_flow_report("FLOW 2: MỞ FORM ĐỔI SỐ ĐIỆN THOẠI", ui_info, is_success)
        
        if is_success:
            res_text = resp.text
            # Bóc tách ĐỘNG event_request_id và phone_input_id cho bước đổi số
            m_ev_input = re.search(r'\(dkc\s+\\"([a-f0-9\-]{36})\\"\s+1\s+1\s+\\"([^\\"]+)\\"', res_text)
            if m_ev_input:
                self.change_phone_event_id = m_ev_input.group(1)
                self.phone_input_id = m_ev_input.group(2)
                print(f"[+] Lấy động Event ID: {self.change_phone_event_id} | Phone Input ID: {self.phone_input_id}")
            else:
                m_input = re.findall(r'\"!\":\"([a-z0-9]+:\d+)\"', res_text)
                self.phone_input_id = m_input[0] if m_input else "4jdmdc:96"
                self.change_phone_event_id = str(uuid.uuid4())
                print(f"[!] Fallback Phone Input ID: {self.phone_input_id}")
            self.send_wbloks_telemetry("com.bloks.www.bloks.caa.reg.confirmation.change.phone")
            return True
        else:
            return False

    def submit_new_phone(self, new_phone: str) -> bool:
        """Bước 2: Gửi số điện thoại mới lên Server sử dụng dynamic IDs"""
        self.new_phone = new_phone.strip()
        print(f"[*] Đang submit số điện thoại mới: {self.new_phone}...")
        url = f"https://m.facebook.com/async/wbloks/fetch/?appid=com.bloks.www.bloks.caa.reg.async.contactpoint_phone.async&type=action&__bkv={self.bkv}"
        
        payload_params = {
            "params": json.dumps({
                "server_params": {
                    "event_request_id": self.change_phone_event_id or str(uuid.uuid4()),
                    "cp_funnel": 1,
                    "cp_source": 1,
                    "text_input_id": self.phone_input_id or "4jdmdc:96",
                    "reg_info": json.dumps(self.reg_info, separators=(",", ":")),
                    "flow_info": json.dumps({"flow_name": "new_to_family_fb_default", "flow_type": "ntf"}, separators=(",", ":")),
                    "current_step": self.current_step,
                    "INTERNAL__latency_qpl_marker_id": 36707139,
                    "INTERNAL__latency_qpl_instance_id": str(random.randint(20000000000000, 99999999999999)),
                    "device_id": None,
                    "family_device_id": None,
                    "waterfall_id": self.waterfall_id,
                    "offline_experiment_group": None,
                    "layered_homepage_experiment_group": None,
                    "is_platform_login": 0,
                    "is_from_logged_in_switcher": 0,
                    "is_from_logged_out": 0,
                    "access_flow_version": "pre_mt_behavior",
                    "login_surface": "unknown"
                },
                "client_input_params": {
                    "device_id": "",
                    "family_device_id": "",
                    "cloud_trust_token": None,
                    "block_store_machine_id": "",
                    "zero_balance_state": "",
                    "phone": self.new_phone,
                    "accounts_list": [],
                    "build_type": "",
                    "encrypted_msisdn": "",
                    "headers_infra_flow_id": "",
                    "was_headers_prefill_available": 0,
                    "was_headers_prefill_used": 0,
                    "fb_ig_device_id": [],
                    "whatsapp_installed_on_client": 0,
                    "confirmed_cp_and_code": {},
                    "msg_previous_cp": "",
                    "switch_cp_first_time_loading": 1,
                    "switch_cp_have_seen_suma": 0,
                    "has_rejected_rel": 0,
                    "login_upsell_phone_list": [],
                    "country_code": "",
                    "prefill_attempted_silent_auth": 0,
                    "device_network_info": None,
                    "seen_login_upsell": 0,
                    "network_bssid": None,
                    "lois_settings": {"lois_token": ""},
                    "aac": ""
                }
            }, separators=(",", ":"))
        }
        
        post_data = self._build_post_data(payload_params)
        headers = self._get_base_headers()
        try:
            resp = self._request_with_retry("post", url, data=post_data, headers=headers)
        except Exception:
            return False
        
        ui_info = self.parse_screen_ui(resp.text)
        has_next_screen = any(k in resp.text for k in [
            "push_screen_BloksCAARegConfirmationController",
            "CAA_REG_CONFIRMATION_SCREEN",
            "is_input_valid",
            "BloksCAARegConfirmationController"
        ])
        has_phone_echo = (self.new_phone in resp.text)
        has_otp_text = any("mã" in s.lower() or "xác nhận" in s.lower() for s in ui_info.get("vn_strings", [])) or "conf_code" in resp.text
        is_strictly_verified = (has_next_screen or has_phone_echo or has_otp_text)
        
        if not is_strictly_verified and not ui_info.get("error_msg"):
            ui_info["error_msg"] = "Facebook không trả về phản hồi chứa Số điện thoại hoặc tín hiệu kích hoạt mã OTP."

        is_success = (resp.status_code == 200 and ui_info["screen_id"] == "ACTION_PHONE_SUBMITTED" and not ui_info.get("error_msg") and is_strictly_verified)
        self.print_flow_report("FLOW 3: SUBMIT SỐ ĐIỆN THOẠI MỚI", ui_info, is_success)
        
        if is_success:
            self.reg_info["contactpoint"] = self.new_phone
            self.reg_info["contactpoint_type"] = "phone"
            return True
        else:
            return False

    def request_change_email_form(self) -> bool:
        """Bước 1b (Email): Click 'Đổi địa chỉ email' từ menu & bóc tách dynamic input ID"""
        if not self.open_not_received_code_bottomsheet():
            print("[-] Không thể mở menu Bottomsheet tùy chọn.")
            return False
            
        print("[*] Đang bấm 'Đổi sang xác thực Email'...")
        url = f"https://m.facebook.com/async/wbloks/fetch/?appid=com.bloks.www.bloks.caa.reg.confirmation.change.email&type=app&__bkv={self.bkv}"
        
        payload_params = {
            "params": json.dumps({
                "server_params": {
                    "waterfall_id": self.waterfall_id,
                    "is_platform_login": 0,
                    "is_from_logged_out": 0,
                    "access_flow_version": "pre_mt_behavior",
                    "login_surface": "unknown",
                    "current_step": self.current_step,
                    "INTERNAL_INFRA_screen_id": "CAA_REG_CONFIRMATION_CHANGE_EMAIL",
                    "reg_info": json.dumps(self.reg_info, separators=(",", ":")),
                    "flow_info": json.dumps({"flow_name": "new_to_family_fb_default", "flow_type": "ntf"}, separators=(",", ":"))
                },
                "client_input_params": {
                    "lois_settings": {"lois_token": ""},
                    "aac": ""
                }
            }, separators=(",", ":"))
        }
        
        post_data = self._build_post_data(payload_params)
        headers = self._get_base_headers()
        try:
            resp = self._request_with_retry("post", url, data=post_data, headers=headers)
        except Exception:
            return False
        
        ui_info = self.parse_screen_ui(resp.text)
        is_success = (resp.status_code == 200 and ui_info["screen_id"] == "SCREEN_CHANGE_EMAIL")
        self.print_flow_report("FLOW 2: MỞ FORM ĐỔI EMAIL", ui_info, is_success)
        
        if is_success:
            res_text = resp.text
            m_ev_input = re.search(r'\(dkc\s+\\"([a-f0-9\-]{36})\\"\s+1\s+1\s+\\"([^\\"]+)\\"', res_text)
            if m_ev_input:
                self.change_email_event_id = m_ev_input.group(1)
                self.email_input_id = m_ev_input.group(2)
                print(f"[+] Lấy động Event ID: {self.change_email_event_id} | Email Input ID: {self.email_input_id}")
            else:
                m_input = re.findall(r'\"!\":\"([a-z0-9]+:\d+)\"', res_text)
                self.email_input_id = m_input[0] if m_input else "iey9o:82"
                self.change_email_event_id = str(uuid.uuid4())
                print(f"[!] Fallback Email Input ID: {self.email_input_id}")
            self.send_wbloks_telemetry("com.bloks.www.bloks.caa.reg.confirmation.change.email")
            return True
        else:
            return False

    def submit_new_email(self, new_email: str) -> bool:
        """Bước 2 (Email): Gửi email mới lên Server sử dụng dynamic IDs"""
        self.new_email = new_email.strip()
        print(f"[*] Đang submit email mới: {self.new_email}...")
        url = f"https://m.facebook.com/async/wbloks/fetch/?appid=com.bloks.www.bloks.caa.reg.async.contactpoint_email.async&type=action&__bkv={self.bkv}"
        
        payload_params = {
            "params": json.dumps({
                "server_params": {
                    "event_request_id": self.change_email_event_id or str(uuid.uuid4()),
                    "cp_funnel": 1,
                    "cp_source": 1,
                    "text_input_id": self.email_input_id or "iey9o:82",
                    "reg_info": json.dumps(self.reg_info, separators=(",", ":")),
                    "flow_info": json.dumps({"flow_name": "new_to_family_fb_default", "flow_type": "ntf"}, separators=(",", ":")),
                    "current_step": self.current_step,
                    "INTERNAL__latency_qpl_marker_id": 36707139,
                    "INTERNAL__latency_qpl_instance_id": str(random.randint(20000000000000, 99999999999999)),
                    "device_id": None,
                    "family_device_id": None,
                    "waterfall_id": self.waterfall_id,
                    "offline_experiment_group": None,
                    "layered_homepage_experiment_group": None,
                    "is_platform_login": 0,
                    "is_from_logged_in_switcher": 0,
                    "is_from_logged_out": 0,
                    "access_flow_version": "pre_mt_behavior",
                    "login_surface": "unknown"
                },
                "client_input_params": {
                    "device_id": "",
                    "family_device_id": "",
                    "cloud_trust_token": None,
                    "block_store_machine_id": "",
                    "zero_balance_state": "",
                    "email": self.new_email,
                    "email_prefilled": 0,
                    "accounts_list": [],
                    "fb_ig_device_id": [],
                    "confirmed_cp_and_code": {},
                    "is_from_device_emails": 0,
                    "msg_previous_cp": "",
                    "switch_cp_first_time_loading": 1,
                    "switch_cp_have_seen_suma": 0,
                    "has_rejected_rel": 0,
                    "seen_login_upsell": 0,
                    "network_bssid": None,
                    "lois_settings": {"lois_token": ""},
                    "aac": ""
                }
            }, separators=(",", ":"))
        }
        
        post_data = self._build_post_data(payload_params)
        headers = self._get_base_headers()
        try:
            resp = self._request_with_retry("post", url, data=post_data, headers=headers)
        except Exception:
            return False
        
        ui_info = self.parse_screen_ui(resp.text)
        
        # Nhận diện tín hiệu Facebook chấp nhận Email:
        # 1. Có lệnh chuyển màn hình sang OTP: push_screen_BloksCAARegConfirmationController hoặc CAA_REG_CONFIRMATION_SCREEN
        # 2. Hoặc trường input hợp lệ: is_input_valid
        # 3. Hoặc có echo email / text OTP
        has_next_screen = any(k in resp.text for k in [
            "push_screen_BloksCAARegConfirmationController",
            "CAA_REG_CONFIRMATION_SCREEN",
            "is_input_valid",
            "BloksCAARegConfirmationController"
        ])
        has_email_echo = (self.new_email.lower() in resp.text.lower())
        has_otp_text = any("mã" in s.lower() or "xác nhận" in s.lower() or "otp" in s.lower() for s in ui_info.get("vn_strings", [])) or "conf_code" in resp.text
        is_strictly_verified = (has_next_screen or has_email_echo or has_otp_text)
        
        if not is_strictly_verified and not ui_info.get("error_msg"):
            ui_info["error_msg"] = "Facebook không trả về phản hồi chứa Email hoặc tín hiệu kích hoạt mã OTP."
            
        is_success = (resp.status_code == 200 and ui_info["screen_id"] == "ACTION_EMAIL_SUBMITTED" and not ui_info.get("error_msg") and is_strictly_verified)
        self.print_flow_report("FLOW 3: SUBMIT EMAIL MỚI", ui_info, is_success)
        
        if is_success:
            self.reg_info["contactpoint"] = self.new_email
            self.reg_info["contactpoint_type"] = "email"
            self.reg_info["is_using_unified_cp"] = False
            self.reg_info["conf_allow_back_nav_after_change_cp"] = True
            self.reg_info["screen_visited"] = ["CAA_REG_CONFIRMATION_SCREEN"]
            return True
        else:
            return False

    def prepare_otp_screen(self) -> bool:
        """Bước 3: Load lại giao diện confirmation để chuẩn bị submit OTP & bóc tách OTP dynamic IDs"""
        print("[*] Đang khởi tạo màn hình xác nhận mã OTP...")
        url = f"https://m.facebook.com/async/wbloks/fetch/?appid=com.bloks.www.bloks.caa.reg.confirmation&type=app&__bkv={self.bkv}"
        
        payload_params = {
            "params": json.dumps({
                "server_params": {
                    "device_id": self.reg_info.get("device_id"),
                    "waterfall_id": self.waterfall_id,
                    "is_platform_login": 0,
                    "is_from_logged_out": 0,
                    "access_flow_version": "pre_mt_behavior",
                    "login_surface": "unknown",
                    "current_step": self.current_step,
                    "INTERNAL_INFRA_screen_id": "CAA_REG_CONFIRMATION_SCREEN",
                    "reg_info": json.dumps(self.reg_info, separators=(",", ":")),
                    "flow_info": json.dumps({"flow_name": "new_to_family_fb_default", "flow_type": "ntf"}, separators=(",", ":"))
                },
                "client_input_params": {
                    "lois_settings": {"lois_token": ""},
                    "aac": ""
                }
            }, separators=(",", ":"))
        }
        
        post_data = self._build_post_data(payload_params)
        headers = self._get_base_headers(referer="https://m.facebook.com/caa/reg/confirmation/")
        try:
            resp = self._request_with_retry("post", url, data=post_data, headers=headers)
        except Exception:
            return False
        
        ui_info = self.parse_screen_ui(resp.text)
        
        # Bắt buộc: Giao diện phải chứa chữ 'Nhập mã' / 'Mã xác nhận' HOẶC chứa Email/SĐT đã gửi lên
        has_email_echo = bool(getattr(self, "new_email", "") and self.new_email.lower() in resp.text.lower())
        has_phone_echo = bool(getattr(self, "new_phone", "") and self.new_phone in resp.text)
        has_otp_screen_text = (
            any("nhập mã" in s.lower() or "mã xác nhận" in s.lower() or "hãy nhập" in s.lower() for s in ui_info.get("vn_strings", [])) or
            "nhập mã" in resp.text.lower() or
            "conf_code" in resp.text.lower()
        )
        is_strictly_verified = (has_otp_screen_text or has_email_echo or has_phone_echo)
        
        if not is_strictly_verified and not ui_info.get("error_msg"):
            ui_info["error_msg"] = "Không tìm thấy nội dung xác nhận mã OTP hoặc Email/SĐT trong phản hồi của Facebook."

        is_success = (resp.status_code == 200 and ui_info["screen_id"] == "SCREEN_ENTER_OTP" and is_strictly_verified)
        self.print_flow_report("FLOW 4: LOAD MÀN HÌNH NHẬP MÃ OTP", ui_info, is_success)
        
        if is_success:
            res_text = resp.text
            # Bóc tách ĐỘNG otp_event_id và otp_input_id chính xác 100%
            m_otp_meta = re.search(r'\(dkc\s+\\"([a-f0-9\-]{36})\\"\s+\\"([^\\"]+)\\"\s+false\s+\\"wa_retriever\\"', res_text)
            if m_otp_meta:
                self.otp_event_id = m_otp_meta.group(1)
                self.otp_input_id = m_otp_meta.group(2)
                print(f"[+] Lấy động OTP Event ID: {self.otp_event_id} | OTP Input ID: {self.otp_input_id}")
            else:
                m_ev = re.findall(r'\"([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})\"', res_text)
                for cand in m_ev:
                    if cand != self.waterfall_id:
                        self.otp_event_id = cand
                        break
                m_input_id = re.findall(r'\"(\d[a-z0-9]+:\d+)\"', res_text)
                self.otp_input_id = m_input_id[0] if m_input_id else "4jxy5o:64"
                if not self.otp_event_id:
                    self.otp_event_id = str(uuid.uuid4())
                print(f"[!] Fallback OTP Event ID: {self.otp_event_id} | Input ID: {self.otp_input_id}")
            self.send_wbloks_telemetry("com.bloks.www.bloks.caa.reg.confirmation", "https://m.facebook.com/caa/reg/confirmation/")
            return True
        else:
            return False

    def submit_otp(self, otp_code: str) -> bool:
        """Bước 4: Submit OTP để hoàn tất xác minh"""
        otp_code = otp_code.strip()
        print(f"[*] Đang gửi mã xác minh OTP: {otp_code}...")
        url = f"https://m.facebook.com/async/wbloks/fetch/?appid=com.bloks.www.bloks.caa.reg.confirmation.async&type=action&__bkv={self.bkv}"
        
        payload_params = {
            "params": json.dumps({
                "server_params": {
                    "event_request_id": self.otp_event_id,
                    "text_input_id": self.otp_input_id,
                    "sms_retriever_started_prior_step": 0,
                    "wa_timer_id": "wa_retriever",
                    "reg_info": json.dumps(self.reg_info, separators=(",", ":")),
                    "flow_info": json.dumps({"flow_name": "new_to_family_fb_default", "flow_type": "ntf"}, separators=(",", ":")),
                    "current_step": self.current_step,
                    "INTERNAL__latency_qpl_marker_id": 36707139,
                    "INTERNAL__latency_qpl_instance_id": str(random.randint(20000000000000, 99999999999999)),
                    "device_id": self.reg_info.get("device_id"),
                    "family_device_id": None,
                    "waterfall_id": self.waterfall_id,
                    "offline_experiment_group": None,
                    "layered_homepage_experiment_group": None,
                    "is_platform_login": 0,
                    "is_from_logged_in_switcher": 0,
                    "is_from_logged_out": 0,
                    "access_flow_version": "pre_mt_behavior",
                    "login_surface": "unknown"
                },
                "client_input_params": {
                    "family_device_id": "",
                    "cloud_trust_token": None,
                    "block_store_machine_id": "",
                    "code": otp_code,
                    "fb_ig_device_id": [],
                    "confirmed_cp_and_code": {},
                    "network_bssid": None,
                    "lois_settings": {"lois_token": ""},
                    "aac": ""
                }
            }, separators=(",", ":"))
        }
        
        post_data = self._build_post_data(payload_params)
        headers = self._get_base_headers(referer="https://m.facebook.com/caa/reg/confirmation/")
        try:
            resp = self._request_with_retry("post", url, data=post_data, headers=headers)
        except Exception:
            return False
        
        res_text = resp.text
        ui_info = self.parse_screen_ui(res_text)
        is_success = (ui_info["screen_id"] == "ACTION_SUBMIT_OTP" and not ui_info["error_msg"])
        self.print_flow_report("FLOW 5: XÁC MINH MÃ OTP", ui_info, is_success)
        
        if is_success:
            print("\n" + "="*60)
            print(" [SUCCESS] TÀI KHOẢN ĐÃ XÁC MINH SỐ ĐIỆN THOẠI THÀNH CÔNG!")
            print(f" UID: {self.reg_info.get('user_id')} | SĐT mới: {self.new_phone}")
            print("="*60 + "\n")
            
            # Follow redirect sang m.facebook.com/?deoia=1 để nhận cookie pas chuẩn iOS Safari
            try:
                final_headers = {
                    "authority": "m.facebook.com",
                    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "accept-language": "en-US,en;q=0.9" if self.is_ios else "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
                    "referer": "https://m.facebook.com/confirmemail.php",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "same-origin",
                    "upgrade-insecure-requests": "1",
                    "user-agent": self.ua,
                }
                if not self.is_ios and self.sec_ch_ua:
                    final_headers["sec-ch-ua"] = self.sec_ch_ua
                    final_headers["sec-ch-ua-mobile"] = "?1"
                    final_headers["sec-ch-ua-platform"] = '"Android"'

                redirect_res = self._request_with_retry("get", "https://m.facebook.com/?deoia=1", headers=final_headers, allow_redirects=True)
                final_url = str(redirect_res.url).lower()
                print(f"[+] Final URL: {redirect_res.url}")
                all_cookies = self.get_cookie_string()
                print(f"[+] Cookie sau verify:\n{all_cookies}\n")
                if any(k in final_url for k in ["checkpoint", "disabled", "/help/", "/login"]):
                    print(f"[-] Facebook đẩy vào Checkpoint sau khi submit OTP: {redirect_res.url}")
                    self.last_error = "CHECKPOINT_AFTER_OTP"
                    return False
            except Exception:
                pass
            return True
        else:
            return False

def parse_account_line(line: str) -> dict:
    """
    Tự động nhận diện linh hoạt mọi định dạng tài khoản:
    - uid|pass|cookie
    - uid|pass|token|cookie
    - uid|pass|2fa|cookie
    - uid|pass|cookie||orig_phone|date
    - hoặc chuỗi cookie raw đơn lẻ
    """
    line = line.strip()
    if not line:
        return None
        
    parts = [p.strip() for p in line.split("|")]
    
    uid = ""
    pwd = ""
    cookie = ""
    token = ""
    orig_phone = ""
    
    # 1. Tìm Cookie: phần tử chứa các key cốt lõi c_user=, xs=, datr=, sb=
    for p in parts:
        if any(k in p for k in ["c_user=", "xs=", "datr=", "sb="]):
            cookie = p
            break
            
    # 2. Tìm Token: phần tử bắt đầu bằng EAA (dài > 20 ký tự)
    for p in parts:
        if p.startswith("EAA") and len(p) > 20:
            token = p
            break
            
    # 3. Tìm SĐT gốc nếu có: bắt đầu bằng + hoặc dãy số 9-15 ký tự không phải UID
    for p in parts:
        if p.startswith("+") or (p.isdigit() and len(p) in [10, 11] and p != parts[0]):
            orig_phone = p
            break
            
    # 4. Tìm User-Agent nếu có: chứa Mozilla/5.0
    user_agent = ""
    for p in parts:
        if "Mozilla/5.0" in p:
            user_agent = p
            break

    # 5. Xác định UID và Password từ các phần tử còn lại
    remaining = [p for p in parts if p not in (cookie, token, orig_phone, user_agent) and p != ""]
    if remaining:
        if remaining[0].isdigit() and len(remaining[0]) >= 4:
            uid = remaining[0]
            if len(remaining) > 1:
                pwd = remaining[1]
        else:
            pwd = remaining[0]
            
    # Fallback: Nếu không tìm thấy UID ở các cột ngoài, tự động bóc tách từ c_user trong cookie
    if not uid and cookie:
        m_uid = re.search(r'c_user=(\d+)', cookie)
        if m_uid:
            uid = m_uid.group(1)
            
    return {
        "uid": uid,
        "pwd": pwd,
        "cookie": cookie,
        "token": token,
        "orig_phone": orig_phone,
        "user_agent": user_agent,
        "raw_line": line
    }

def load_accounts_from_novery(file_path: str = "novery.txt"):
    """Đọc và tự động nhận diện danh sách tài khoản từ file novery.txt theo mọi định dạng"""
    accounts = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, 1):
                parsed = parse_account_line(line)
                if parsed and parsed.get("cookie"):
                    parsed["index"] = line_idx
                    accounts.append(parsed)
    except Exception as e:
        print(f"[-] Lỗi đọc file {file_path}: {e}")
    return accounts

def remove_account_from_novery(raw_line: str, file_path: str = "novery.txt"):
    """Tự động xóa dòng tài khoản được chọn khỏi file novery.txt để tránh chạy trùng"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        target = raw_line.strip()
        remaining = [line for line in lines if line.strip() != target]
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(remaining)
        print(f"[+] Đã tự động xóa tài khoản khỏi {file_path} (còn lại {len(remaining)} acc).")
    except Exception as e:
        print(f"[-] Lỗi khi xóa tài khoản khỏi file: {e}")

def check_uid_live(uid: str, timeout: int = 5) -> bool:
    """
    Kiểm tra trạng thái hoạt động (Live/Die) của 1 Facebook UID theo cơ chế của bot-ban-hang-tele.
    - Truy cập public endpoint ảnh đại diện của Facebook mà không cần access token:
      https://graph.facebook.com/{uid}/picture?type=normal
    - allow_redirects=False để lấy URL redirect trong header 'Location' mà không tải ảnh.
    - LIVE: Location chứa 'scontent' hoặc 'lookaside' (CDN ảnh thật của user).
    - DIE/Checkpoint: Location chứa 'rsrc.php' (ảnh placeholder mặc định) hoặc status khác 302.
    """
    if not uid:
        return False
    url = f"https://graph.facebook.com/{uid}/picture?type=normal"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = std_requests.get(url, headers=headers, allow_redirects=False, timeout=timeout)
        if r.status_code == 302:
            loc = r.headers.get("Location", "")
            if "scontent" in loc or "lookaside" in loc:
                return True
            return False
        return False
    except Exception:
        return False

def check_multiple_uids(uids: list, max_workers: int = 20) -> dict:
    """Kiểm tra hàng loạt UID song song sử dụng ThreadPoolExecutor để tối ưu tốc độ"""
    results = {}
    if not uids:
        return results
    workers = min(max_workers, len(uids))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_uid = {executor.submit(check_uid_live, uid): uid for uid in uids}
        for future in concurrent.futures.as_completed(future_to_uid):
            uid = future_to_uid[future]
            try:
                results[uid] = future.result()
            except Exception:
                results[uid] = False
    return results

def format_proxy_url(raw_proxy: str, protocol: str = "http") -> str:
    """Định dạng chuỗi proxy sang dạng chuẩn HTTP hoặc SOCKS5 URI"""
    raw = raw_proxy.strip()
    if not raw:
        return None
    # Nếu là dòng acc hoặc cookie dán nhầm vào proxy -> Bỏ qua ngay
    if "|" in raw or "c_user=" in raw or "datr=" in raw:
        return None
    if raw.startswith(("http://", "https://", "socks5://", "socks5h://")):
        return raw
    parts = raw.split(":")
    if len(parts) == 4:
        # host:port:user:pass -> http://user:pass@host:port (HTTP CONNECT chuẩn cho cliproxy)
        return f"{protocol}://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    elif len(parts) == 2:
        return f"{protocol}://{parts[0]}:{parts[1]}"
    elif "@" in raw:
        return f"{protocol}://{raw}"
    return None

def load_proxies_from_file(file_path: str = "proxy.txt") -> list:
    """Tự động đọc danh sách proxy từ file proxy.txt (Ưu tiên giao thức HTTP CONNECT ổn định)"""
    proxies = []
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        formatted = format_proxy_url(line, protocol="http")
                        if formatted:
                            proxies.append(formatted)
    except Exception as e:
        print(f"[-] Lỗi đọc file proxy {file_path}: {e}")
    return proxies

def test_proxy_facebook(proxy_url: str, timeout: int = 8) -> tuple[bool, str]:
    """Kiểm tra xem proxy có thực sự kết nối được tới Facebook hay không bằng curl_cffi"""
    try:
        r = requests.get("https://m.facebook.com", proxy=proxy_url, timeout=timeout)
        if r.status_code in [200, 301, 302]:
            return True, "OK"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        # Nếu SOCKS5H gặp lỗi, thử lại nhanh với giao thức HTTP thường
        if "socks5h://" in proxy_url:
            fallback_http = proxy_url.replace("socks5h://", "http://")
            try:
                r2 = requests.get("https://m.facebook.com", proxy=fallback_http, timeout=timeout)
                if r2.status_code in [200, 301, 302]:
                    return True, "OK (HTTP)"
            except Exception:
                pass
        return False, str(e)

def get_proxy_public_ip(proxy_url: str) -> str:
    """Kiểm tra IP public của proxy để xác nhận vị trí địa lý"""
    try:
        r = requests.get("https://api.ipify.org?format=json", proxy=proxy_url, timeout=8)
        return r.json().get("ip", "Connected")
    except Exception:
        return "Connected"

def save_account_result(uid: str, pwd: str, new_phone: str, cookie: str, status: str = "LIVE", raw_line: str = None):
    """
    Tự động phân loại và lưu tài khoản vào 2 file riêng biệt:
    - live.txt: Các tài khoản LIVE thành công (uid|pwd|cookie||new_phone)
    - die.txt: Các tài khoản DIE (lưu định dạng gốc hoặc uid|pwd|cookie, bỏ hoàn toàn trạng thái lỗi)
    """
    if status == "LIVE":
        phone_part = f"||{new_phone}" if new_phone else ""
        line = f"{uid}|{pwd}|{cookie}{phone_part}\n"
        target_file = "live.txt"
    else:
        # BỎ HOÀN TOÀN TRẠNG THÁI LỖI THEO YÊU CẦU
        if raw_line and raw_line.strip():
            line = raw_line.strip() + "\n"
        else:
            phone_part = f"||{new_phone}" if new_phone else ""
            line = f"{uid}|{pwd}|{cookie}{phone_part}\n"
        target_file = "die.txt"

    try:
        with open(target_file, "a", encoding="utf-8") as f:
            f.write(line)
        print(f"[+] Đã lưu vào {target_file}: UID {uid}")
    except Exception as e:
        print(f"[-] Lỗi lưu file {target_file}: {e}")

    # Lưu lịch sử phụ vào verified_success.txt nếu cần
    if status == "LIVE":
        try:
            with open("verified_success.txt", "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass

def save_verified_account(uid: str, pwd: str, new_phone: str, cookie: str, status: str = "LIVE", file_path: str = None, raw_line: str = None):
    """Hàm tương thích ngược gọi save_account_result"""
    return save_account_result(uid, pwd, new_phone, cookie, status, raw_line=raw_line)


def main():
    print("==================================================")
    print("   TOOL VERIFY FB: ADD COOKIE -> ĐỔI SĐT -> OTP   ")
    print("==================================================")
    
    # 1. Tự động bốc Proxy US từ proxy.txt và kiểm tra kết nối với Facebook
    proxies = load_proxies_from_file("proxy.txt")
    selected_proxy = None
    if proxies:
        print(f"[*] Đã tìm thấy {len(proxies)} proxy trong proxy.txt.")
        random.shuffle(proxies)
        
        valid_proxy_found = False
        for p in proxies:
            print(f"[*] Đang test kết nối Proxy tới Facebook: {p.split('@')[-1]}...")
            fb_ok, reason = test_proxy_facebook(p, timeout=15)
            if fb_ok:
                selected_proxy = p
                proxy_ip = get_proxy_public_ip(p)
                print(f"[+] Proxy US HOẠT ĐỘNG TỐT: {p.split('@')[-1]} (IP: {proxy_ip})")
                valid_proxy_found = True
                break
            else:
                print(f"[-] Proxy {p.split('@')[-1]} không kết nối được FB: {reason}")
                
        if not valid_proxy_found:
            print("\n[!] CẢNH BÁO: Tất cả proxy trong proxy.txt đều không thể kết nối tới Facebook!")
            print("    (Do proxy bị chặn cổng/domain Meta hoặc proxy đã hết hạn)")
            print("\nLựa chọn chế độ mạng:")
            print("  [1] Tiếp tục chạy bằng IP trực tiếp (Không dùng proxy) [Khuyên dùng]")
            print("  [2] Nhập proxy khác thủ công")
            print("  [3] Thoát để kiểm tra lại proxy")
            p_choice = input("Lựa chọn của bạn (1/2/3) [1]: ").strip()
            
            if p_choice == "2":
                manual_p = input("Nhập proxy (ip:port:user:pass hoặc http://...): ").strip()
                if manual_p:
                    formatted = format_proxy_url(manual_p)
                    fb_ok, reason = test_proxy_facebook(formatted, timeout=6)
                    if fb_ok:
                        selected_proxy = formatted
                        print(f"[+] Đã áp dụng proxy thủ công: {selected_proxy}")
                    else:
                        print(f"[-] Proxy thủ công cũng không vào được FB ({reason}). Dùng IP trực tiếp.")
                        selected_proxy = None
            elif p_choice == "3":
                print("[-] Đã thoát theo yêu cầu.")
                return
            else:
                print("[+] Đã chọn chạy bằng IP trực tiếp.")
                selected_proxy = None
    else:
        print("[!] Không tìm thấy proxy trong proxy.txt, tiếp tục với IP trực tiếp.")
    
    accounts = load_accounts_from_novery("novery.txt")
    if not accounts:
        print("[-] Không tìm thấy tài khoản nào trong novery.txt!")
        raw_input = input("Nhập cookie hoặc dòng tài khoản thủ công (uid|pass|token|cookie...): ").strip()
        if not raw_input:
            return
        parsed = parse_account_line(raw_input)
        if not parsed or not parsed.get("cookie"):
            print("[-] Không tìm thấy cookie hợp lệ trong dữ liệu nhập!")
            return
        selected_account = parsed
    else:
        print(f"[+] Đã tải {len(accounts)} tài khoản từ novery.txt.")
        print("[*] Đang kiểm tra trạng thái LIVE bằng cơ chế Graph API bot Telegram...")
        
        # Quét trạng thái LIVE song song cho các tài khoản
        scan_limit = min(20, len(accounts))
        uids_to_check = [acc["uid"] for acc in accounts[:scan_limit]]
        live_results = check_multiple_uids(uids_to_check, max_workers=20)
        
        print("\nDanh sách tài khoản:")
        for idx, acc in enumerate(accounts[:scan_limit], 1):
            uid = acc["uid"]
            is_live = live_results.get(uid, False)
            status_tag = "[LIVE]" if is_live else "[DIE/CHECKPOINT]"
            print(f"  [{idx:02d}] UID: {uid} | {status_tag} | SĐT gốc: {acc.get('orig_phone', 'N/A')}")
        if len(accounts) > scan_limit:
            print(f"  ... và còn {len(accounts) - scan_limit} tài khoản khác.")
            
        choice = input(f"\nChọn số thứ tự account (1 - {len(accounts)}) [Mặc định 1]: ").strip()
        selected_idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(accounts) else 0
        selected_account = accounts[selected_idx]
        
        # Kiểm tra trước khi chạy
        is_acc_live = live_results.get(selected_account["uid"], True)
        if not is_acc_live:
            print(f"\n[!] CẢNH BÁO: UID {selected_account['uid']} đang báo [DIE/CHECKPOINT] trên Graph API.")
            ans = input("Bạn có muốn tiếp tục chạy tài khoản này không? (y/n) [y]: ").strip().lower()
            if ans == 'n':
                return
                
        print(f"\n[+] Đang xử lý UID: {selected_account['uid']}")
        # Account sẽ được xóa khỏi novery.txt sau khi hoàn tất verify thành công

    verifier = FBPhoneVerifier(
        raw_cookie=selected_account["cookie"],
        proxy=selected_proxy,
        user_agent=selected_account.get("user_agent")
    )
    
    # Bước 0: Khởi tạo session & bóc tách tokens
    if not verifier.init_session():
        print("[-] Không thể khởi tạo session từ cookie.")
        return

    # Bước 1: Mở form đổi số
    time.sleep(1.0)
    if not verifier.request_change_phone_form():
        return
        
    # Bước 2: Xin số điện thoại mới từ người dùng
    new_phone = input("\n[?] Nhập số điện thoại MỚI để nhận OTP (VD: +18129433687 hoặc +84...): ").strip()
    if not new_phone:
        print("[-] Số điện thoại không được để trống!")
        return
        
    print("[*] Đang gửi số điện thoại...")
    time.sleep(1.0)
    if not verifier.submit_new_phone(new_phone):
        return

    # Bước 3: Load màn hình OTP
    time.sleep(1.0)
    if not verifier.prepare_otp_screen():
        return

    # Bước 4: Xin mã OTP từ người dùng
    otp_code = input("\n[?] Nhập mã OTP đã nhận được (5 chữ số): ").strip()
    if not otp_code:
        print("[-] Mã OTP không được để trống!")
        return

    # Bước 5: Submit OTP
    print("[*] Đang gửi mã OTP...")
    time.sleep(1.0)
    success = verifier.submit_otp(otp_code)
    if success:
        all_cookies = verifier.get_cookie_string()
        
        # Ngâm phiên nhẹ 1 giây trước khi hậu kiểm tra
        print("[*] Đang ngâm phiên 1 giây trước khi kiểm tra trạng thái...")
        time.sleep(1.0)
        post_live = check_uid_live(selected_account.get("uid", ""))
        final_status = "LIVE" if post_live else "CHECKPOINT_REVIEW"
        print(f"[+] Trạng thái UID sau xác minh: [{final_status}]")
        
        save_verified_account(
            uid=selected_account.get("uid", ""),
            pwd=selected_account.get("pwd", ""),
            new_phone=new_phone,
            cookie=all_cookies,
            status=final_status
        )
        
        # Xóa tài khoản đã xử lý thành công khỏi novery.txt
        if selected_account.get("raw_line"):
            remove_account_from_novery(selected_account["raw_line"], "novery.txt")

if __name__ == "__main__":
    main()
