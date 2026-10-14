import random

# Danh sách hơn 100 thiết bị Android thực tế phổ biến nhất hiện nay
ANDROID_DEVICES = [
    # --- SAMSUNG GALAXY S SERIES ---
    ("SM-S928B", "Samsung Galaxy S24 Ultra", 14, 3.0, 412),
    ("SM-S928U", "Samsung Galaxy S24 Ultra (US)", 14, 3.0, 412),
    ("SM-S926B", "Samsung Galaxy S24+", 14, 3.0, 412),
    ("SM-S921B", "Samsung Galaxy S24", 14, 3.0, 393),
    ("SM-S918B", "Samsung Galaxy S23 Ultra", 14, 2.8125, 384),
    ("SM-S918U", "Samsung Galaxy S23 Ultra (US)", 14, 2.8125, 384),
    ("SM-S916B", "Samsung Galaxy S23+", 14, 2.8125, 384),
    ("SM-S911B", "Samsung Galaxy S23", 14, 3.0, 393),
    ("SM-S908B", "Samsung Galaxy S22 Ultra", 13, 2.8125, 384),
    ("SM-S906B", "Samsung Galaxy S22+", 13, 2.8125, 384),
    ("SM-S901B", "Samsung Galaxy S22", 13, 3.0, 393),
    ("SM-G998B", "Samsung Galaxy S21 Ultra 5G", 13, 3.5, 412),
    ("SM-G996B", "Samsung Galaxy S21+ 5G", 13, 2.625, 412),
    ("SM-G991B", "Samsung Galaxy S21 5G", 13, 2.625, 412),
    ("SM-G990B", "Samsung Galaxy S21 FE 5G", 14, 2.625, 412),
    ("SM-S711B", "Samsung Galaxy S23 FE", 14, 2.625, 412),
    ("SM-S721B", "Samsung Galaxy S24 FE", 14, 2.625, 412),

    # --- SAMSUNG GALAXY Z SERIES (FOLD & FLIP) ---
    ("SM-F956B", "Samsung Galaxy Z Fold6", 14, 2.625, 412),
    ("SM-F741B", "Samsung Galaxy Z Flip6", 14, 2.625, 412),
    ("SM-F946B", "Samsung Galaxy Z Fold5", 14, 2.625, 375),
    ("SM-F731B", "Samsung Galaxy Z Flip5", 14, 2.625, 412),
    ("SM-F936B", "Samsung Galaxy Z Fold4", 13, 2.625, 375),
    ("SM-F721B", "Samsung Galaxy Z Flip4", 13, 2.625, 412),

    # --- SAMSUNG GALAXY A & M SERIES ---
    ("SM-A556B", "Samsung Galaxy A55 5G", 14, 2.625, 412),
    ("SM-A546B", "Samsung Galaxy A54 5G", 14, 2.625, 412),
    ("SM-A536B", "Samsung Galaxy A53 5G", 13, 2.625, 412),
    ("SM-A528B", "Samsung Galaxy A52s 5G", 13, 2.625, 412),
    ("SM-A356B", "Samsung Galaxy A35 5G", 14, 2.625, 412),
    ("SM-A346B", "Samsung Galaxy A34 5G", 14, 2.625, 412),
    ("SM-A336B", "Samsung Galaxy A33 5G", 13, 2.625, 412),
    ("SM-A256B", "Samsung Galaxy A25 5G", 14, 2.625, 412),
    ("SM-A156B", "Samsung Galaxy A15 5G", 14, 2.625, 412),
    ("SM-A155F", "Samsung Galaxy A15 4G", 14, 2.625, 412),
    ("SM-A057F", "Samsung Galaxy A05s", 14, 2.625, 412),
    ("SM-M546B", "Samsung Galaxy M54 5G", 14, 2.625, 412),
    ("SM-M346B", "Samsung Galaxy M34 5G", 14, 2.625, 412),

    # --- GOOGLE PIXEL SERIES ---
    ("Pixel 9 Pro XL", "Google Pixel 9 Pro XL", 15, 2.8, 412),
    ("Pixel 9 Pro Fold", "Google Pixel 9 Pro Fold", 15, 2.625, 412),
    ("Pixel 9 Pro", "Google Pixel 9 Pro", 15, 2.8, 412),
    ("Pixel 9", "Google Pixel 9", 15, 2.625, 412),
    ("Pixel 8 Pro", "Google Pixel 8 Pro", 14, 2.625, 412),
    ("Pixel 8", "Google Pixel 8", 14, 2.625, 412),
    ("Pixel 8a", "Google Pixel 8a", 14, 2.625, 412),
    ("Pixel 7 Pro", "Google Pixel 7 Pro", 14, 2.625, 412),
    ("Pixel 7", "Google Pixel 7", 14, 2.625, 412),
    ("Pixel 7a", "Google Pixel 7a", 14, 2.625, 412),
    ("Pixel 6 Pro", "Google Pixel 6 Pro", 13, 2.625, 412),
    ("Pixel 6", "Google Pixel 6", 13, 2.625, 412),
    ("Pixel 6a", "Google Pixel 6a", 13, 2.625, 412),

    # --- XIAOMI & REDMI SERIES ---
    ("24030PN60G", "Xiaomi 14 Ultra", 14, 3.0, 412),
    ("23116PN5BC", "Xiaomi 14 Pro", 14, 3.0, 412),
    ("23127PN0CG", "Xiaomi 14", 14, 3.0, 412),
    ("2211133G", "Xiaomi 13 Pro", 13, 3.0, 412),
    ("2211133C", "Xiaomi 13", 13, 3.0, 393),
    ("2203121C", "Xiaomi 12 Pro", 13, 3.0, 412),
    ("2210132C", "Xiaomi Redmi Note 12 Discovery", 14, 1.7, 424),
    ("23090RA98G", "Redmi Note 13 Pro+ 5G", 14, 2.75, 412),
    ("2312DRA50G", "Redmi Note 13 Pro 5G", 14, 2.75, 412),
    ("23129RAA4G", "Redmi Note 13 5G", 13, 2.75, 412),
    ("23124RA7EO", "Redmi Note 13 4G", 14, 2.75, 412),
    ("22101316G", "Redmi Note 12 Pro+ 5G", 13, 2.75, 412),
    ("22101316C", "Redmi Note 12 Pro 5G", 13, 2.75, 412),
    ("23021RAAEG", "Redmi Note 12 4G", 13, 2.75, 412),
    ("23076RN4BI", "Redmi 12 5G", 13, 2.75, 412),
    ("23053RN02A", "Redmi 12 4G", 13, 2.75, 412),
    ("23108RN04Y", "Redmi 13C", 14, 2.0, 360),
    ("2311DRK48G", "POCO X6 Pro 5G", 14, 2.75, 412),
    ("23122PCD1G", "POCO X6 5G", 14, 2.75, 412),
    ("24053PY09G", "POCO F6 5G", 14, 3.0, 412),
    ("24069PC21G", "POCO F6 Pro 5G", 14, 3.0, 412),
    ("23049PCD8G", "POCO F5 5G", 13, 2.75, 412),
    ("23013PC75G", "POCO X5 Pro 5G", 13, 2.75, 412),
    ("23049PCD8I", "POCO F5 Pro", 13, 3.0, 412),
    ("22041216G", "POCO F4 GT", 13, 2.75, 412),

    # --- ONEPLUS SERIES ---
    ("CPH2581", "OnePlus 12", 14, 3.0, 450),
    ("CPH2609", "OnePlus 12R", 14, 3.0, 450),
    ("CPH2449", "OnePlus 11", 14, 3.0, 450),
    ("CPH2413", "OnePlus 10 Pro 5G", 13, 3.0, 450),
    ("CPH2493", "OnePlus Nord 3 5G", 14, 2.75, 412),
    ("CPH2613", "OnePlus Nord 4", 14, 2.75, 412),
    ("CPH2513", "OnePlus Nord CE 3 Lite 5G", 14, 2.625, 412),
    ("CPH2569", "OnePlus Open", 14, 2.625, 412),

    # --- OPPO SERIES ---
    ("CPH2607", "OPPO Find X7 Ultra", 14, 3.0, 412),
    ("CPH2599", "OPPO Reno11 Pro 5G", 14, 2.75, 412),
    ("CPH2619", "OPPO Reno12 Pro 5G", 14, 2.75, 412),
    ("CPH2625", "OPPO Reno12 5G", 14, 2.75, 412),
    ("CPH2505", "OPPO Find N3 Flip", 14, 2.625, 412),
    ("CPH2499", "OPPO Find N3", 14, 2.625, 412),
    ("CPH2527", "OPPO Reno10 Pro+ 5G", 13, 2.75, 412),
    ("CPH2531", "OPPO Reno10 5G", 13, 2.75, 412),
    ("CPH2565", "OPPO A79 5G", 14, 2.625, 412),
    ("CPH2579", "OPPO A58", 13, 2.625, 412),

    # --- VIVO & IQOO SERIES ---
    ("V2324A", "vivo X100 Pro", 14, 3.0, 412),
    ("V2309A", "iQOO 12 Pro", 14, 3.0, 412),
    ("V2307A", "iQOO 12", 14, 3.0, 412),
    ("V2314A", "iQOO Neo9 Pro", 14, 2.75, 412),
    ("V2303A", "vivo V30 Pro", 14, 2.75, 412),
    ("V2318", "vivo V30 5G", 14, 2.75, 412),
    ("V2250", "vivo V27 5G", 13, 2.75, 412),
    ("V2322", "vivo Y200 5G", 14, 2.625, 412),
    ("V2310", "vivo Y36", 13, 2.625, 412),

    # --- REALME SERIES ---
    ("RMX3850", "Realme GT 6", 14, 3.0, 412),
    ("RMX3851", "Realme GT 6T", 14, 3.0, 412),
    ("RMX3840", "Realme 12 Pro+ 5G", 14, 2.75, 412),
    ("RMX3842", "Realme 12 Pro 5G", 14, 2.75, 412),
    ("RMX3867", "Realme 12 5G", 14, 2.75, 412),
    ("RMX3771", "Realme 11 Pro+ 5G", 13, 2.75, 412),
    ("RMX3740", "Realme 11 5G", 13, 2.75, 412),
    ("RMX3710", "Realme C55", 13, 2.625, 412),

    # --- MOTOROLA SERIES ---
    ("XT2401-2", "Motorola Edge 50 Ultra", 14, 2.75, 412),
    ("XT2403-2", "Motorola Edge 50 Pro", 14, 2.75, 412),
    ("XT2405-1", "Motorola Edge 50 Fusion", 14, 2.75, 412),
    ("XT2301-4", "Motorola Edge 40 Pro", 13, 2.75, 412),
    ("XT2303-2", "Motorola Edge 40", 13, 2.75, 412),
    ("XT2341-2", "Moto G84 5G", 13, 2.625, 412),
    ("XT2343-1", "Moto G54 5G", 13, 2.625, 412),

    # --- SONY & ASUS ---
    ("XQ-EC54", "Sony Xperia 1 VI", 14, 2.625, 412),
    ("XQ-DQ54", "Sony Xperia 1 V", 13, 2.625, 412),
    ("XQ-DE54", "Sony Xperia 5 V", 13, 2.625, 384),
    ("AI2401_C", "Asus ROG Phone 8 Pro", 14, 2.75, 412),
    ("AI2205", "Asus ROG Phone 7 Ultimate", 13, 2.75, 412),
    ("ASUS_AI2401_A", "Asus Zenfone 11 Ultra", 14, 2.75, 412)
]

# Các build version thực tế của Chrome 131 trên Android
CHROME_BUILDS = [
    "131.0.6778.39",
    "131.0.6778.69",
    "131.0.6778.85",
    "131.0.6778.104",
    "131.0.6778.135",
    "131.0.6778.150",
    "131.0.6778.200",
    "131.0.6778.260"
]

# Danh sách thiết bị iPhone thực tế phổ biến nhất hiện nay
IPHONE_DEVICES = [
    # (Identifier, Model Name, iOS Ver Underscore, iOS Ver Dot, DPR, Viewport Width, Viewport Height)
    ("iPhone16,2", "iPhone 15 Pro Max", "17_5_1", "17.5.1", 3.0, 430, 932),
    ("iPhone16,1", "iPhone 15 Pro", "17_4_1", "17.4.1", 3.0, 393, 852),
    ("iPhone15,4", "iPhone 15", "17_4_1", "17.4.1", 3.0, 393, 852),
    ("iPhone15,5", "iPhone 15 Plus", "17_5_1", "17.5.1", 3.0, 430, 932),
    ("iPhone15,3", "iPhone 14 Pro Max", "17_3_1", "17.3.1", 3.0, 430, 932),
    ("iPhone15,2", "iPhone 14 Pro", "17_4_1", "17.4.1", 3.0, 393, 852),
    ("iPhone14,7", "iPhone 14", "17_2_1", "17.2.1", 3.0, 390, 844),
    ("iPhone14,8", "iPhone 14 Plus", "17_4_1", "17.4.1", 3.0, 428, 926),
    ("iPhone14,3", "iPhone 13 Pro Max", "17_4_1", "17.4.1", 3.0, 428, 926),
    ("iPhone14,2", "iPhone 13 Pro", "17_4_1", "17.4.1", 3.0, 390, 844),
    ("iPhone14,5", "iPhone 13", "17_4_1", "17.4.1", 3.0, 390, 844),
    ("iPhone13,4", "iPhone 12 Pro Max", "17_2", "17.2", 3.0, 428, 926),
    ("iPhone13,2", "iPhone 12", "17_3_1", "17.3.1", 3.0, 390, 844),
    ("iPhone12,8", "iPhone SE (2nd Gen)", "17_4_1", "17.4.1", 2.0, 375, 667),
    ("iPhone14,6", "iPhone SE (3rd Gen)", "17_5_1", "17.5.1", 2.0, 375, 667),
    ("iPhone16,2", "iPhone 15 Pro Max (iOS 18)", "18_0", "18.0", 3.0, 430, 932),
    ("iPhone16,1", "iPhone 15 Pro (iOS 18)", "18_0", "18.0", 3.0, 393, 852),
    ("iPhone15,4", "iPhone 15 (iOS 18)", "18_0", "18.0", 3.0, 393, 852),
    ("iPhone16,2", "iPhone 15 Pro Max (iOS 18.5)", "18_5", "18.5", 3.0, 430, 932),
    ("iPhone16,1", "iPhone 15 Pro (iOS 18.5)", "18_5", "18.5", 3.0, 393, 852),
    ("iPhone15,4", "iPhone 15 (iOS 18.5)", "18_5", "18.5", 3.0, 393, 852),
]

def generate_random_device_profile(platform: str = "ios") -> dict:
    """
    Sinh ngẫu nhiên 1 cấu hình Device Profile:
    - Nếu platform="ios": Giả lập Mobile Safari iPhone (chuẩn TLS & HTTP/2 Safari, không gửi sec-ch-ua)
    - Nếu platform="android": Giả lập Chrome 131 Android (kèm đầy đủ Client Hints)
    """
    if platform.lower() == "ios":
        ident, model_name, ios_under, ios_dot, dpr, vp_w, vp_h = random.choice(IPHONE_DEVICES)
        ua = f"Mozilla/5.0 (iPhone; CPU iPhone OS {ios_under} like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{ios_dot} Mobile/15E148 Safari/604.1"
        impersonate = "safari18_0_ios" if ios_dot.startswith("18.") else "safari17_2_ios"
        return {
            "platform": "iOS",
            "is_ios": True,
            "model": model_name,
            "identifier": ident,
            "brand_name": f"Apple {model_name}",
            "os_version": ios_dot,
            "ua": ua,
            "sec_ch_ua": None,
            "sec_ch_ua_model": None,
            "sec_ch_ua_platform": None,
            "sec_ch_ua_platform_version": None,
            "sec_ch_ua_full_version_list": None,
            "dpr": str(dpr),
            "viewport": str(vp_w),
            "viewport_h": str(vp_h),
            "impersonate": impersonate,
            "is_custom": False
        }
    else:
        model, brand_name, base_os, base_dpr, base_viewport = random.choice(ANDROID_DEVICES)
        os_ver = random.choice([base_os, base_os, base_os + 1]) if base_os < 15 else 15
        chrome_build = random.choice(CHROME_BUILDS)
        dpr_str = str(base_dpr)
        viewport_str = str(base_viewport)
        ua = f"Mozilla/5.0 (Linux; Android {os_ver}; {model}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
        return {
            "platform": "Android",
            "is_ios": False,
            "model": model,
            "brand_name": brand_name,
            "os_version": str(os_ver),
            "ua": ua,
            "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            "sec_ch_ua_model": f'"{model}"',
            "sec_ch_ua_platform": '"Android"',
            "sec_ch_ua_platform_version": f'"{os_ver}.0.0"',
            "sec_ch_ua_full_version_list": f'"Google Chrome";v="{chrome_build}", "Chromium";v="{chrome_build}", "Not_A Brand";v="24.0.0.0"',
            "dpr": dpr_str,
            "viewport": viewport_str,
            "impersonate": "chrome131_android",
            "is_custom": False
        }

def get_device_profile(user_agent: str = None, force_ios: bool = True) -> dict:
    """
    Tự động đồng bộ Device Profile:
    - force_ios = True (Mặc định): Luôn ưu tiên dùng Profile iPhone / Safari (giống tool reg tỉ lệ live cao).
      Nếu đầu vào có User-Agent iPhone thì đồng bộ, nếu là Android thì nâng cấp sang iPhone sạch.
    - force_ios = False: Sử dụng Android Chrome.
    - force_ios = None: Tự động bóc tách theo User-Agent có sẵn (nếu iPhone thì giữ iPhone, Android thì giữ Android).
    """
    import re

    # 1. Trường hợp buộc sử dụng iOS (hoặc tự động phát hiện thấy iPhone trong UA)
    if force_ios is True or (force_ios is None and user_agent and ("iPhone" in user_agent or "CPU iPhone OS" in user_agent)):
        if user_agent and ("iPhone" in user_agent or "CPU iPhone OS" in user_agent):
            ua = user_agent.strip()
            # Bóc tách phiên bản iOS
            m_ver = re.search(r'CPU iPhone OS ([\d_]+)', ua)
            ios_ver = m_ver.group(1).replace('_', '.') if m_ver else "17.4.1"
            impersonate = "safari18_0_ios" if ios_ver.startswith("18.") else "safari17_2_ios"
            return {
                "platform": "iOS",
                "is_ios": True,
                "model": "iPhone",
                "brand_name": f"Apple iPhone (iOS {ios_ver})",
                "os_version": ios_ver,
                "ua": ua,
                "sec_ch_ua": None,
                "sec_ch_ua_model": None,
                "sec_ch_ua_platform": None,
                "sec_ch_ua_platform_version": None,
                "sec_ch_ua_full_version_list": None,
                "dpr": "3.0",
                "viewport": "393",
                "viewport_h": "852",
                "impersonate": impersonate,
                "is_custom": True
            }
        # Nếu chưa có UA hoặc UA cũ là Android mà người dùng chọn iOS -> Sinh Profile iOS ngẫu nhiên sạch 100%
        profile = generate_random_device_profile(platform="ios")
        profile["is_custom"] = False
        return profile

    # 2. Trường hợp dùng Android
    if user_agent and "Android" in user_agent:
        ua = user_agent.strip()
        os_ver = "14"
        model = "Android Device"
        chrome_major = "131"
        chrome_build = "131.0.6778.150"
        
        m_os = re.search(r'Android\s+([\d\.]+)', ua)
        if m_os:
            os_ver = m_os.group(1)
            
        m_model = re.search(r'Android\s+[\d\.]+;\s*([^;\)]+)', ua)
        if m_model:
            model = m_model.group(1).strip()
            
        m_chrome = re.search(r'Chrome/([\d\.]+)', ua)
        if m_chrome:
            chrome_build = m_chrome.group(1)
            chrome_major = chrome_build.split('.')[0]
            
        return {
            "platform": "Android",
            "is_ios": False,
            "model": model,
            "brand_name": f"Đồng bộ ({model})",
            "os_version": os_ver,
            "ua": ua,
            "sec_ch_ua": f'"Chromium";v="{chrome_major}", "Not=A?Brand";v="24", "Google Chrome";v="{chrome_major}"',
            "sec_ch_ua_model": f'"{model}"',
            "sec_ch_ua_platform": '"Android"',
            "sec_ch_ua_platform_version": f'"{os_ver}.0.0"',
            "sec_ch_ua_full_version_list": f'"Chromium";v="{chrome_build}", "Google Chrome";v="{chrome_build}"',
            "dpr": "2.625",
            "viewport": "412",
            "impersonate": "chrome131_android",
            "is_custom": True
        }
        
    # Fallback mặc định sinh Android hoặc iOS theo force_ios
    target_platform = "ios" if force_ios in (True, None) else "android"
    profile = generate_random_device_profile(platform=target_platform)
    profile["is_custom"] = False
    return profile


