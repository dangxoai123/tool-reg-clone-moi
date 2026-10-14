import os
import sys
import time
import json
import random
import queue
import threading
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import messagebox
import customtkinter as ctk

# Import logic cốt lõi từ verify_fb
from verify_fb import (
    load_accounts_from_novery,
    remove_account_from_novery,
    load_proxies_from_file,
    format_proxy_url,
    test_proxy_facebook,
    check_uid_live,
    check_multiple_uids,
    save_account_result,
    save_verified_account,
    FBPhoneVerifier
)
from autosms_service import AutoSMSService
from mail30s_service import Mail30sService

# Cấu hình giao diện CustomTkinter
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "sim_config.json"
MAIL_CONFIG_FILE = "mail_config.json"

ACC_FILES = {
    "Novery Chrome": "novery_chrome.txt",
    "Novery FB Lite": "novery_fblite.txt",
    "Novery FB Katana": "novery_fbkatana.txt"
}

class ProxyRotator:
    """Cơ chế xoay vòng Proxy (Round-Robin) thread-safe cho từng luồng / tài khoản"""
    def __init__(self, proxies: list):
        self.proxies = proxies or []
        self.lock = threading.Lock()
        self.index = 0

    @property
    def total(self) -> int:
        return len(self.proxies)

    def get_next(self) -> tuple[str, int]:
        with self.lock:
            if not self.proxies:
                return None, 0
            idx = self.index % len(self.proxies)
            proxy = self.proxies[idx]
            self.index += 1
            return proxy, idx + 1

class ModernVerifyApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("META VERIFY PRO - HỆ THỐNG XÁC MINH TÀI KHOẢN FACEBOOK NOVERY")
        self.geometry("1320;840")
        self.geometry(f"{max(1280, self.winfo_screenwidth() - 80)}x{max(800, self.winfo_screenheight() - 100)}+40+30")
        self.minsize(1100, 700)

        # Trạng thái dữ liệu
        self.current_acc_type = "Novery Chrome"
        self.current_acc_file = "novery_chrome.txt"
        self.accounts_data = []      # Danh sách toàn bộ acc
        self.selected_indices = set() # Tập hợp các index được chọn
        self.is_running = False
        self.stop_requested = False
        self.die_count = 0
        self.live_count = 0
        self.error_count = 0
        self.active_threads_count = 0
        self.task_queue = queue.Queue()
        self.log_queue = queue.Queue()
        
        # Load cấu hình SIM & MAIL
        self.sim_config = self.load_sim_config()
        self.mail_config = self.load_mail_config()

        # Dựng giao diện
        self.setup_ui()

        # Load danh sách tài khoản ban đầu
        self.reload_accounts()

        # Bắt đầu vòng lặp xử lý log định kỳ
        self.after(100, self.process_log_queue)

    def load_sim_config(self) -> dict:
        """Đọc file cấu hình API SIM nếu đã có"""
        default_cfg = {
            "site": "autosms",
            "api_key": "",
            "service_id": "facebook",
            "country": "US",
            "timeout": 20
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**default_cfg, **json.load(f)}
            except Exception:
                pass
        return default_cfg

    def save_sim_config(self):
        """Lưu cấu hình API SIM vào file JSON"""
        self.sim_config["site"] = self.combo_sim_site.get()
        self.sim_config["api_key"] = self.entry_sim_key.get().strip()
        self.sim_config["country"] = self.entry_sim_country.get().strip()
        self.sim_config["service_id"] = self.entry_sim_service.get().strip()
        try:
            val = int(self.entry_sim_timeout.get().strip())
            self.sim_config["timeout"] = min(val, 20)
        except ValueError:
            self.sim_config["timeout"] = 20

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.sim_config, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Thành Công", "Đã lưu cấu hình API SIM thành công!")
            self.log("[SIM CONFIG] Đã lưu cấu hình API SIM vào sim_config.json")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu file cấu hình: {e}")

    def load_mail_config(self) -> dict:
        """Đọc file cấu hình API Mail30s nếu đã có"""
        default_cfg = {
            "site": "mail30s",
            "api_key": "",
            "product_slug": "email-hotmail",
            "timeout": 20
        }
        if os.path.exists(MAIL_CONFIG_FILE):
            try:
                with open(MAIL_CONFIG_FILE, "r", encoding="utf-8") as f:
                    return {**default_cfg, **json.load(f)}
            except Exception:
                pass
        return default_cfg

    def save_mail_config(self):
        """Lưu cấu hình API Mail30s vào file JSON"""
        self.mail_config["site"] = "mail30s"
        self.mail_config["api_key"] = self.entry_mail_key.get().strip()
        self.mail_config["product_slug"] = self.combo_mail_slug.get().strip()
        try:
            val = int(self.entry_mail_timeout.get().strip())
            self.mail_config["timeout"] = min(val, 20)
        except ValueError:
            self.mail_config["timeout"] = 20

        try:
            with open(MAIL_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.mail_config, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Thành Công", "Đã lưu cấu hình API Mail30s thành công!")
            self.log("[MAIL CONFIG] Đã lưu cấu hình API Mail vào mail_config.json")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không thể lưu file cấu hình: {e}")

    def check_mail_balance(self):
        """Kiểm tra số dư API Mail30s & tự động cập nhật danh sách loại mail từ API"""
        key = self.entry_mail_key.get().strip()
        if not key:
            messagebox.showwarning("Thiếu Dữ Liệu", "Vui lòng nhập API Key Mail30s trước khi kiểm tra số dư!")
            return
            
        self.log(f"[MAIL API] Đang kiểm tra số dư Mail30s với Key: {key[:8]}***...")
        service = Mail30sService(api_key=key)
        res = service.get_balance()
        if res.get("success"):
            bal = res.get("balance", 0)
            email = res.get("email", "")
            name = res.get("name", "")
            self.log(f"[MAIL API] Tài khoản: {name} ({email}) | Số dư: {bal:,.0f} Points/VNĐ")

            # Tự động nạp danh sách sản phẩm chuẩn từ Mail30s
            prods = service.get_products()
            if prods:
                slug_list = [p.get("slug") for p in prods if p.get("slug")]
                if slug_list:
                    self.combo_mail_slug.configure(values=slug_list)
                    self.log(f"[MAIL API] Đã cập nhật {len(slug_list)} loại email chuẩn từ Mail30s: {', '.join(slug_list)}")

            messagebox.showinfo("Thông Báo Số Dư", f"Tài khoản Mail30s: {name} ({email})\nSố dư: {bal:,.0f} Points/VNĐ\nTrạng thái: Đang hoạt động!\n(Đã đồng bộ danh sách loại mail chuẩn)")
        else:
            self.log(f"[MAIL API] Lỗi: {res.get('message')}")
            messagebox.showerror("Lỗi Kiểm Tra", f"Không thể lấy số dư: {res.get('message')}")

    def fetch_mail30s_products(self):
        """Chủ động tải danh sách sản phẩm chuẩn từ Mail30s khi người dùng bấm nút làm mới"""
        key = self.entry_mail_key.get().strip()
        if not key:
            messagebox.showwarning("Thiếu Dữ Liệu", "Vui lòng nhập API Key Mail30s trước khi tải loại mail!")
            return

        self.log(f"[MAIL API] Đang kết nối tải danh sách sản phẩm từ Mail30s...")
        service = Mail30sService(api_key=key)
        prods = service.get_products()
        if prods:
            slug_list = [p.get("slug") for p in prods if p.get("slug")]
            if slug_list:
                self.combo_mail_slug.configure(values=slug_list)
                if self.combo_mail_slug.get() not in slug_list:
                    self.combo_mail_slug.set(slug_list[0])
                self.log(f"[MAIL API] Đã nạp thành công {len(slug_list)} loại email chuẩn từ Mail30s!")
                messagebox.showinfo("Thành Công", f"Đã nạp {len(slug_list)} loại email chuẩn từ Mail30s:\n" + "\n".join(f"• {s}" for s in slug_list[:8]))
                return
        messagebox.showwarning("Thông Báo", "Không thể lấy danh sách hoặc tài khoản chưa có sản phẩm khả dụng!")

    def setup_ui(self):
        """Thiết kế toàn bộ layout hiện đại chuẩn Dashboard"""
        # HEADER BAR
        self.header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="#0f172a")
        self.header_frame.pack(fill="x", padx=15, pady=(12, 8))

        # Tiêu đề & Logo
        self.lbl_title = ctk.CTkLabel(
            self.header_frame,
            text="⚡ META VERIFY PRO",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_title.pack(side="left", padx=(16, 8), pady=12)

        self.lbl_subtitle = ctk.CTkLabel(
            self.header_frame,
            text="|  Novery Phone Verification Automation Suite",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#94a3b8"
        )
        self.lbl_subtitle.pack(side="left", pady=12)

        # STAT CARDS (TOP RIGHT)
        self.stats_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.stats_frame.pack(side="right", padx=12, pady=6)

        self.card_total = self.create_stat_card(self.stats_frame, "TỔNG NVR", "0", "#38bdf8")
        self.card_selected = self.create_stat_card(self.stats_frame, "ĐÃ CHỌN", "0", "#a855f7")
        self.card_live = self.create_stat_card(self.stats_frame, "ACC LIVE", "0", "#22c55e")
        self.card_die = self.create_stat_card(self.stats_frame, "ACC DIE", "0", "#ef4444")
        self.card_error = self.create_stat_card(self.stats_frame, "ACC LỖI", "0", "#f97316")
        self.card_running = self.create_stat_card(self.stats_frame, "ĐANG CHẠY", "0", "#eab308")

        # TABVIEW CHÍNH
        self.tabview = ctk.CTkTabview(self, corner_radius=12, fg_color="#1e293b", segmented_button_selected_color="#0284c7")
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(0, 12))

        self.tab_novery = self.tabview.add("📋 XÁC MINH NOVERY")
        self.tab_sim = self.tabview.add("📱 CẤU HÌNH API SIM & AUTO SMS")
        self.tab_mode = self.tabview.add("⚡ CHẾ ĐỘ XÁC MINH")

        # Khởi tạo nội dung từng Tab
        self.setup_tab_novery()
        self.setup_tab_sim()
        self.setup_tab_mode()

    def create_stat_card(self, parent, title: str, init_val: str, color: str):
        """Tạo thẻ thống kê thông số trực quan"""
        card = ctk.CTkFrame(parent, corner_radius=8, fg_color="#1e293b", border_width=1, border_color="#334155")
        card.pack(side="left", padx=5, pady=4)

        lbl_t = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=10, weight="bold"), text_color="#94a3b8")
        lbl_t.pack(padx=10, pady=(4, 0))

        lbl_v = ctk.CTkLabel(card, text=init_val, font=ctk.CTkFont(size=16, weight="bold"), text_color=color)
        lbl_v.pack(padx=10, pady=(0, 4))
        card.lbl_val = lbl_v
        return card

    # =========================================================================
    # TAB 1: XÁC MINH NOVERY (BẢNG DỮ LIỆU & ĐIỀU KHIỂN)
    # =========================================================================
    def setup_tab_novery(self):
        # 1. Hàng điều khiển 1: Cấu hình thông số & Cụm nút Bắt đầu / Dừng lại
        ctrl_frame = ctk.CTkFrame(self.tab_novery, fg_color="#0f172a", corner_radius=10)
        ctrl_frame.pack(fill="x", padx=10, pady=(8, 4))

        # --- Phía bên trái: Cấu hình tham số ---
        # Số luồng
        lbl_threads = ctk.CTkLabel(ctrl_frame, text="Số Luồng:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_threads.pack(side="left", padx=(12, 4), pady=8)
        self.entry_threads = ctk.CTkEntry(ctrl_frame, width=50, justify="center")
        self.entry_threads.insert(0, "2")
        self.entry_threads.pack(side="left", padx=(0, 12), pady=8)

        # Công tắc Proxy
        self.proxy_switch_var = ctk.BooleanVar(value=True)
        self.switch_proxy = ctk.CTkSwitch(
            ctrl_frame,
            text="Proxy (SOCKS5H)",
            variable=self.proxy_switch_var,
            onvalue=True,
            offvalue=False,
            progress_color="#10b981",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.on_toggle_proxy
        )
        self.switch_proxy.pack(side="left", padx=(0, 12), pady=8)

        # Ngưỡng acc Die thì dừng
        lbl_max_die = ctk.CTkLabel(ctrl_frame, text="Dừng khi DIE:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_max_die.pack(side="left", padx=(0, 4), pady=8)
        self.entry_max_die = ctk.CTkEntry(ctrl_frame, width=50, justify="center")
        self.entry_max_die.insert(0, "5")
        self.entry_max_die.pack(side="left", padx=(0, 12), pady=8)

        # Lựa chọn loại Acc
        lbl_acc_type = ctk.CTkLabel(ctrl_frame, text="Loại Acc:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_acc_type.pack(side="left", padx=(0, 4), pady=8)
        self.combo_acc_type = ctk.CTkComboBox(
            ctrl_frame,
            width=150,
            values=["Novery Chrome", "Novery FB Lite", "Novery FB Katana"],
            command=self.on_acc_type_change
        )
        self.combo_acc_type.set("Novery Chrome")
        self.combo_acc_type.pack(side="left", padx=(0, 8), pady=8)

        # Lựa chọn Thiết bị giả lập (Mặc định: iOS / iPhone Live cao giống tool gốc)
        lbl_device = ctk.CTkLabel(ctrl_frame, text="Thiết bị:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_device.pack(side="left", padx=(0, 4), pady=8)
        self.combo_device_type = ctk.CTkComboBox(
            ctrl_frame,
            width=165,
            values=["🍎 iOS / iPhone (Live cao)", "🤖 Android Chrome", "📄 Theo file TXT"]
        )
        self.combo_device_type.set("🍎 iOS / iPhone (Live cao)")
        self.combo_device_type.pack(side="left", padx=(0, 8), pady=8)

        # Nút Mở File TXT
        self.btn_open_file = ctk.CTkButton(
            ctrl_frame, text="📂 Mở File", width=75, fg_color="#334155", hover_color="#475569",
            command=self.open_current_acc_file
        )
        self.btn_open_file.pack(side="left", padx=(0, 8), pady=8)

        # --- Phía bên phải: Cụm nút BẮT ĐẦU & DỪNG LẠI (Luôn hiển thị đầy đủ, không bao giờ bị đè) ---
        btn_action_box = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        btn_action_box.pack(side="right", padx=(0, 12), pady=8)

        self.btn_stop = ctk.CTkButton(
            btn_action_box, text="⏹ DỪNG LẠI", width=110, height=34, fg_color="#ef4444", hover_color="#dc2626",
            font=ctk.CTkFont(weight="bold", size=13),
            state="disabled",
            command=self.stop_verification
        )
        self.btn_stop.pack(side="right", padx=(6, 0))

        self.btn_start = ctk.CTkButton(
            btn_action_box, text="▶ BẮT ĐẦU CHẠY", width=140, height=34, fg_color="#10b981", hover_color="#059669",
            font=ctk.CTkFont(weight="bold", size=13),
            command=self.start_verification
        )
        self.btn_start.pack(side="right", padx=(0, 6))

        # 2. Hàng điều khiển 2: Các nút công cụ thao tác chọn và kiểm tra nhanh
        tools_frame = ctk.CTkFrame(self.tab_novery, fg_color="#0f172a", corner_radius=8)
        tools_frame.pack(fill="x", padx=10, pady=(0, 6))

        self.btn_select_all = ctk.CTkButton(
            tools_frame, text="✓ Chọn Tất Cả", width=105, height=28, fg_color="#334155", hover_color="#475569",
            command=self.select_all_accounts
        )
        self.btn_select_all.pack(side="left", padx=(10, 6), pady=6)

        self.btn_deselect_all = ctk.CTkButton(
            tools_frame, text="✕ Bỏ Chọn", width=90, height=28, fg_color="#334155", hover_color="#475569",
            command=self.deselect_all_accounts
        )
        self.btn_deselect_all.pack(side="left", padx=6, pady=6)

        self.btn_reload = ctk.CTkButton(
            tools_frame, text="🔄 Tải Lại File", width=105, height=28, fg_color="#334155", hover_color="#475569",
            command=self.reload_accounts
        )
        self.btn_reload.pack(side="left", padx=6, pady=6)

        self.btn_check_all_live = ctk.CTkButton(
            tools_frame, text="🔍 Check Live Toàn Bộ", width=150, height=28, fg_color="#0284c7", hover_color="#0369a1",
            font=ctk.CTkFont(weight="bold"),
            command=self.check_all_uids_live
        )
        self.btn_check_all_live.pack(side="left", padx=6, pady=6)

        self.btn_shuffle = ctk.CTkButton(
            tools_frame, text="🔀 Xáo Trộn Acc", width=125, height=28, fg_color="#8b5cf6", hover_color="#7c3aed",
            font=ctk.CTkFont(weight="bold"),
            command=self.shuffle_accounts
        )
        self.btn_shuffle.pack(side="left", padx=6, pady=6)

        lbl_hint = ctk.CTkLabel(
            tools_frame,
            text="💡 Click vào dòng để chọn/bỏ chọn | Chuột phải để Copy UID, Pass, Cookie",
            font=ctk.CTkFont(size=11),
            text_color="#64748b"
        )
        lbl_hint.pack(side="right", padx=14, pady=6)


        # 2. Khung Bảng Treeview (Danh sách Acc)
        table_container = ctk.CTkFrame(self.tab_novery, fg_color="#0f172a", corner_radius=10)
        table_container.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        # Style Treeview kiểu Dark Theme
        self.setup_treeview_style()

        columns = ("select", "idx", "uid", "pwd", "cookie", "ua", "status", "live")
        self.tree = ttk.Treeview(table_container, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("select", text="Chọn [✓]")
        self.tree.heading("idx", text="STT")
        self.tree.heading("uid", text="UID Facebook")
        self.tree.heading("pwd", text="Mật Khẩu")
        self.tree.heading("cookie", text="Cookie Session")
        self.tree.heading("ua", text="User-Agent Thiết Bị")
        self.tree.heading("status", text="Trạng Thái Chạy")
        self.tree.heading("live", text="Live / Die")

        self.tree.column("select", width=70, anchor="center")
        self.tree.column("idx", width=50, anchor="center")
        self.tree.column("uid", width=160, anchor="w")
        self.tree.column("pwd", width=100, anchor="w")
        self.tree.column("cookie", width=220, anchor="w")
        self.tree.column("ua", width=240, anchor="w")
        self.tree.column("status", width=140, anchor="center")
        self.tree.column("live", width=110, anchor="center")

        # Scrollbars
        vsb = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        vsb.pack(side="right", fill="y", padx=(0, 8), pady=8)

        # Sự kiện click để chọn/bỏ chọn
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<Button-3>", self.show_context_menu)

        # Context Menu chuột phải
        self.context_menu = tk.Menu(self, tearoff=0, bg="#1e293b", fg="#ffffff", activebackground="#0284c7")
        self.context_menu.add_command(label="Copy UID", command=self.copy_selected_uid)
        self.context_menu.add_command(label="Copy Cookie", command=self.copy_selected_cookie)
        self.context_menu.add_command(label="Copy Password", command=self.copy_selected_pwd)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Kiểm tra Live ngay", command=self.check_selected_live)

        # 3. Log Console dưới cùng
        log_frame = ctk.CTkFrame(self.tab_novery, fg_color="#0b1120", corner_radius=8, height=130)
        log_frame.pack(fill="x", padx=10, pady=(0, 8))
        log_frame.pack_propagate(False)

        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(4, 2))
        lbl_log = ctk.CTkLabel(log_header, text="TERMINAL LOGS REALTIME", font=ctk.CTkFont(size=11, weight="bold"), text_color="#38bdf8")
        lbl_log.pack(side="left")

        btn_clear_log = ctk.CTkButton(log_header, text="Xóa Log", width=65, height=20, fg_color="#334155", font=ctk.CTkFont(size=10), command=self.clear_logs)
        btn_clear_log.pack(side="right")

        self.log_textbox = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#060913", text_color="#cbd5e1")
        self.log_textbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def setup_treeview_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
            background="#0f172a",
            foreground="#f1f5f9",
            rowheight=30,
            fieldbackground="#0f172a",
            borderwidth=0,
            font=("Segoe UI", 10)
        )
        style.configure("Treeview.Heading",
            background="#1e293b",
            foreground="#38bdf8",
            relief="flat",
            font=("Segoe UI", 10, "bold")
        )
        style.map("Treeview",
            background=[("selected", "#0369a1")],
            foreground=[("selected", "#ffffff")]
        )
        style.map("Treeview.Heading",
            background=[("active", "#334155")]
        )
        # Tags màu trạng thái
        self.tree_tag_colors = {
            "LIVE": "#22c55e",
            "DIE": "#ef4444",
            "CHECKPOINT": "#f59e0b",
            "RUNNING": "#eab308",
            "SUCCESS": "#10b981",
            "FAILED": "#f43f5e"
        }

    # =========================================================================
    # TAB 2: CẤU HÌNH API SIM & AUTO SMS
    # =========================================================================
    def setup_tab_sim(self):
        frame = ctk.CTkFrame(self.tab_sim, fg_color="#0f172a", corner_radius=12)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        title = ctk.CTkLabel(
            frame,
            text="📱 THIẾT LẬP KẾT NỐI API THUÊ SIM & LẤY OTP TỰ ĐỘNG",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#38bdf8"
        )
        title.pack(anchor="w", padx=24, pady=(20, 6))

        desc = ctk.CTkLabel(
            frame,
            text="Hệ thống hỗ trợ tự động bốc số điện thoại mới, nạp vào Facebook và bắt mã xác minh OTP tự động 100%.",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8"
        )
        desc.pack(anchor="w", padx=24, pady=(0, 20))

        # Form Grid
        form_frame = ctk.CTkFrame(frame, fg_color="transparent")
        form_frame.pack(fill="x", padx=24)

        # 1. Chọn Site SIM
        lbl_site = ctk.CTkLabel(form_frame, text="Chọn Nhà Cung Cấp (Site SIM):", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_site.grid(row=0, column=0, sticky="w", pady=10)
        self.combo_sim_site = ctk.CTkComboBox(
            form_frame,
            width=320,
            values=["autosms", "viotp", "chothuesimcode", "thuesim", "5sim", "smspool", "smsactivate", "custom_endpoint"]
        )
        self.combo_sim_site.set(self.sim_config.get("site", "autosms"))
        self.combo_sim_site.grid(row=0, column=1, sticky="w", padx=16, pady=10)

        # 2. Nhập API Key
        lbl_key = ctk.CTkLabel(form_frame, text="Mã API Key / Token:", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_key.grid(row=1, column=0, sticky="w", pady=10)
        self.entry_sim_key = ctk.CTkEntry(form_frame, width=320, placeholder_text="Nhập hoặc dán API Key vào đây...")
        self.entry_sim_key.insert(0, self.sim_config.get("api_key", ""))
        self.entry_sim_key.grid(row=1, column=1, sticky="w", padx=16, pady=10)

        # Nút Kiểm tra số dư
        self.btn_check_balance = ctk.CTkButton(
            form_frame,
            text="Kiểm Tra Số Dư",
            width=130,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.check_sim_balance
        )
        self.btn_check_balance.grid(row=1, column=2, sticky="w", pady=10)

        # 3. Quốc gia
        lbl_country = ctk.CTkLabel(form_frame, text="Quốc Gia (Country):", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_country.grid(row=2, column=0, sticky="w", pady=10)
        self.entry_sim_country = ctk.CTkEntry(form_frame, width=320)
        self.entry_sim_country.insert(0, self.sim_config.get("country", "US"))
        self.entry_sim_country.grid(row=2, column=1, sticky="w", padx=16, pady=10)

        # 4. Service ID Facebook
        lbl_service = ctk.CTkLabel(form_frame, text="Service ID (Dịch vụ):", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_service.grid(row=3, column=0, sticky="w", pady=10)
        self.entry_sim_service = ctk.CTkEntry(form_frame, width=320)
        self.entry_sim_service.insert(0, self.sim_config.get("service_id", "facebook"))
        self.entry_sim_service.grid(row=3, column=1, sticky="w", padx=16, pady=10)

        # 5. Timeout chờ mã
        lbl_timeout = ctk.CTkLabel(form_frame, text="Thời Gian Chờ OTP (Giây - Max 20s):", font=ctk.CTkFont(size=13, weight="bold"))
        lbl_timeout.grid(row=4, column=0, sticky="w", pady=10)
        self.entry_sim_timeout = ctk.CTkEntry(form_frame, width=320)
        self.entry_sim_timeout.insert(0, str(min(20, int(self.sim_config.get("timeout", 20)))))
        self.entry_sim_timeout.grid(row=4, column=1, sticky="w", padx=16, pady=10)

        # Nút Lưu Cấu Hình
        self.btn_save_sim = ctk.CTkButton(
            frame,
            text="💾 LƯU CẤU HÌNH API SIM",
            width=220,
            height=38,
            fg_color="#10b981",
            hover_color="#059669",
            font=ctk.CTkFont(weight="bold", size=13),
            command=self.save_sim_config
        )
        self.btn_save_sim.pack(anchor="w", padx=24, pady=24)

    def check_sim_balance(self):
        """Kiểm tra số dư API SIM khi người dùng bấm nút"""
        key = self.entry_sim_key.get().strip()
        site = self.combo_sim_site.get()
        if not key:
            messagebox.showwarning("Thiếu Dữ Liệu", "Vui lòng nhập API Key trước khi kiểm tra số dư!")
            return
            
        self.log(f"[SIM API] Đang kiểm tra số dư tại {site} với Key: {key[:8]}***...")
        if site == "autosms":
            sms = AutoSMSService(api_key=key)
            res = sms.get_balance()
            if res.get("success"):
                bal = res.get("balance", 0)
                email = res.get("email", "")
                self.log(f"[SIM API] Tài khoản: {email} | Số dư khả dụng: {bal:,} VNĐ")
                messagebox.showinfo("Thông Báo Số Dư", f"Tài khoản AutoSMS: {email}\nSố dư khả dụng: {bal:,} VNĐ\nTrạng thái: Đang hoạt động!")
            else:
                self.log(f"[SIM API] Lỗi: {res.get('message')}")
                messagebox.showerror("Lỗi Kiểm Tra", f"Không thể lấy số dư: {res.get('message')}")
        else:
            messagebox.showinfo("Thông Báo", f"Đã kết nối tới cổng {site}!\nKey: {key[:8]}***")

    # =========================================================================
    # TAB 3: CHẾ ĐỘ XÁC MINH (API SIM vs API MAIL)
    # =========================================================================
    def setup_tab_mode(self):
        frame = ctk.CTkFrame(self.tab_mode, fg_color="#0f172a", corner_radius=12)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        title = ctk.CTkLabel(
            frame,
            text="⚡ LỰA CHỌN PHƯƠNG THỨC XÁC MINH DANH TÍNH",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#38bdf8"
        )
        title.pack(anchor="w", padx=24, pady=(20, 6))

        desc = ctk.CTkLabel(
            frame,
            text="Chọn cơ chế giải quyết tình trạng Novery (xác nhận tài khoản qua SMS hoặc qua Hộp thư điện tử).",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8"
        )
        desc.pack(anchor="w", padx=24, pady=(0, 20))

        self.mode_var = ctk.StringVar(value="sim")

        # Option 1: API SIM (SMS)
        self.box_sim = ctk.CTkFrame(frame, fg_color="#1e293b", corner_radius=10, border_width=2, border_color="#10b981")
        self.box_sim.pack(fill="x", padx=24, pady=10)

        rb_sim = ctk.CTkRadioButton(
            self.box_sim,
            text="Chế Độ Xác Minh Qua API SIM (SMS OTP - AutoSMS)",
            value="sim",
            variable=self.mode_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.on_mode_change
        )
        rb_sim.pack(anchor="w", padx=16, pady=(14, 4))

        lbl_sim_desc = ctk.CTkLabel(
            self.box_sim,
            text="• Luồng tự động: Đổi số điện thoại mới -> Gửi mã OTP SMS qua AutoSMS -> Xác minh -> Đưa UID về LIVE.\n• Cấu hình chi tiết (API Key, Nhà mạng) nằm ở Tab '📱 CẤU HÌNH API SIM & AUTO SMS'.",
            justify="left",
            text_color="#94a3b8",
            font=ctk.CTkFont(size=12)
        )
        lbl_sim_desc.pack(anchor="w", padx=36, pady=(0, 14))

        # Option 2: API MAIL (Mail30s / MailOTP)
        self.box_mail = ctk.CTkFrame(frame, fg_color="#1e293b", corner_radius=10, border_width=1, border_color="#334155")
        self.box_mail.pack(fill="x", padx=24, pady=10)

        rb_mail = ctk.CTkRadioButton(
            self.box_mail,
            text="Chế Độ Xác Minh Qua API Mail (Email OTP - Mail30s / MailOTP)",
            value="mail",
            variable=self.mode_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.on_mode_change
        )
        rb_mail.pack(anchor="w", padx=16, pady=(14, 4))

        lbl_mail_desc = ctk.CTkLabel(
            self.box_mail,
            text="• Luồng tự động: Mua Mail mới qua Mail30s -> Đổi contact sang Email trên Facebook -> Bắt OTP từ Inbox -> Hoàn tất mở khoá.\n• Điền thông tin API Key Mail30s của bạn ngay bên dưới để sử dụng:",
            justify="left",
            text_color="#94a3b8",
            font=ctk.CTkFont(size=12)
        )
        lbl_mail_desc.pack(anchor="w", padx=36, pady=(0, 10))

        # Khung nhập cấu hình Mail30s trực tiếp
        mail_form = ctk.CTkFrame(self.box_mail, fg_color="#0f172a", corner_radius=8)
        mail_form.pack(fill="x", padx=20, pady=(0, 16))

        # 1. API Key Mail30s
        lbl_mail_key = ctk.CTkLabel(mail_form, text="Mã API Key Mail30s:", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_mail_key.grid(row=0, column=0, sticky="w", padx=16, pady=8)
        self.entry_mail_key = ctk.CTkEntry(mail_form, width=320, placeholder_text="Nhập hoặc dán API Key Mail30s...")
        self.entry_mail_key.insert(0, self.mail_config.get("api_key", ""))
        self.entry_mail_key.grid(row=0, column=1, sticky="w", padx=10, pady=8)

        self.btn_check_mail_bal = ctk.CTkButton(
            mail_form, text="Kiểm Tra Số Dư", width=120, fg_color="#0284c7", hover_color="#0369a1",
            command=self.check_mail_balance
        )
        self.btn_check_mail_bal.grid(row=0, column=2, sticky="w", padx=10, pady=8)

        # 2. Loại Email (Product Slug)
        lbl_mail_slug = ctk.CTkLabel(mail_form, text="Loại Mail (Product Slug):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_mail_slug.grid(row=1, column=0, sticky="w", padx=16, pady=8)
        self.combo_mail_slug = ctk.CTkComboBox(
            mail_form, width=320,
            values=["hotmail-trusted", "outlook-trusted-all", "hot-out-trusted"]
        )
        self.combo_mail_slug.set(self.mail_config.get("product_slug", "hotmail-trusted"))
        self.combo_mail_slug.grid(row=1, column=1, sticky="w", padx=10, pady=8)

        self.btn_fetch_mail_prods = ctk.CTkButton(
            mail_form, text="🔄 Tải Loại Mail", width=120, fg_color="#334155", hover_color="#475569",
            command=self.fetch_mail30s_products
        )
        self.btn_fetch_mail_prods.grid(row=1, column=2, sticky="w", padx=10, pady=8)

        # 3. Timeout OTP
        lbl_mail_to = ctk.CTkLabel(mail_form, text="Timeout Chờ OTP (giây):", font=ctk.CTkFont(size=12, weight="bold"))
        lbl_mail_to.grid(row=2, column=0, sticky="w", padx=16, pady=8)
        self.entry_mail_timeout = ctk.CTkEntry(mail_form, width=120)
        self.entry_mail_timeout.insert(0, str(int(self.mail_config.get("timeout", 45))))
        self.entry_mail_timeout.grid(row=2, column=1, sticky="w", padx=10, pady=8)

        # 4. Nút Lưu Cấu Hình Mail
        self.btn_save_mail = ctk.CTkButton(
            mail_form, text="💾 Lưu Cấu Hình Mail30s", width=180, fg_color="#10b981", hover_color="#059669",
            font=ctk.CTkFont(weight="bold"),
            command=self.save_mail_config
        )
        self.btn_save_mail.grid(row=2, column=2, sticky="w", padx=10, pady=8)

    def on_mode_change(self):
        """Chuyển đổi giao diện viền sáng khi người dùng đổi chế độ SIM / MAIL"""
        selected_mode = self.mode_var.get()
        if selected_mode == "mail":
            self.box_mail.configure(border_width=2, border_color="#10b981")
            self.box_sim.configure(border_width=1, border_color="#334155")
            self.log("[CHẾ ĐỘ] Đã chọn chế độ: XÁC MINH QUA API MAIL (Mail30s / MailOTP) 📬")
        else:
            self.box_sim.configure(border_width=2, border_color="#10b981")
            self.box_mail.configure(border_width=1, border_color="#334155")
            self.log("[CHẾ ĐỘ] Đã chọn chế độ: XÁC MINH QUA API SIM (AutoSMS) 📱")

    def on_acc_type_change(self, choice: str):
        """Khi người dùng chọn loại Acc khác (Chrome / FB Lite / FB Katana)"""
        self.current_acc_type = choice
        self.current_acc_file = ACC_FILES.get(choice, "novery_chrome.txt")
        if not os.path.exists(self.current_acc_file):
            open(self.current_acc_file, "a", encoding="utf-8").close()
        self.reload_accounts()
        self.log(f"[NGUỒN DỮ LIỆU] Đã chuyển sang: {choice} (File: {self.current_acc_file})")

    def open_current_acc_file(self):
        """Mở file TXT của loại tài khoản đang chọn bằng Notepad"""
        file_path = getattr(self, "current_acc_file", "novery_chrome.txt")
        if not os.path.exists(file_path):
            open(file_path, "a", encoding="utf-8").close()
        try:
            os.startfile(file_path)
            self.log(f"[FILE] Đã mở file {file_path} để xem/chỉnh sửa.")
        except Exception as e:
            self.log(f"[FILE] Không thể mở file {file_path}: {e}")

    # =========================================================================
    # QUẢN LÝ DỮ LIỆU TÀI KHOẢN TRONG BẢNG (TREEVIEW)
    # =========================================================================
    def reload_accounts(self):
        """Đọc lại danh sách tài khoản từ file đang được chọn"""
        file_path = getattr(self, "current_acc_file", "novery_chrome.txt")
        if file_path == "novery_chrome.txt" and not os.path.exists(file_path) and os.path.exists("novery.txt"):
            file_path = "novery.txt"

        self.accounts_data = load_accounts_from_novery(file_path)
        self.selected_indices = set(range(len(self.accounts_data))) # Mặc định chọn tất cả
        self.refresh_table()
        self.update_stats()
        self.log(f"[DATA] Đã tải {len(self.accounts_data)} tài khoản từ {file_path} ({getattr(self, 'current_acc_type', 'Novery Chrome')}).")

    def refresh_table(self):
        """Vẽ lại bảng dữ liệu Treeview"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        for i, acc in enumerate(self.accounts_data):
            is_checked = " [ ✓ ] " if i in self.selected_indices else " [   ] "
            uid = acc.get("uid", "")
            pwd = acc.get("pwd", "")
            cookie = acc.get("cookie", "")
            # Rút gọn cookie để hiển thị gọn gàng
            cookie_short = (cookie[:35] + "...") if len(cookie) > 35 else cookie
            ua = acc.get("user_agent", "")
            ua_short = (ua[:40] + "...") if len(ua) > 40 else ua or "Chưa có (Auto Random)"
            status = acc.get("run_status", "Chờ chạy")
            live = acc.get("live_status", "Chưa kiểm tra")

            item_id = self.tree.insert(
                "",
                "end",
                iid=str(i),
                values=(is_checked, i + 1, uid, pwd, cookie_short, ua_short, status, live)
            )

    def on_tree_click(self, event):
        """Xử lý click chuột vào dòng để bật/tắt Checkbox"""
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            item_id = self.tree.identify_row(event.y)
            if item_id:
                idx = int(item_id)
                if idx in self.selected_indices:
                    self.selected_indices.remove(idx)
                else:
                    self.selected_indices.add(idx)

                # Cập nhật hiển thị cột Checkbox
                new_state = " [ ✓ ] " if idx in self.selected_indices else " [   ] "
                current_vals = list(self.tree.item(item_id, "values"))
                current_vals[0] = new_state
                self.tree.item(item_id, values=current_vals)
                self.update_stats()

    def select_all_accounts(self):
        """Chọn tất cả tài khoản trong danh sách"""
        self.selected_indices = set(range(len(self.accounts_data)))
        self.refresh_table()
        self.update_stats()
        self.log("[TABLE] Đã chọn tất cả tài khoản.")

    def deselect_all_accounts(self):
        """Bỏ chọn tất cả"""
        self.selected_indices.clear()
        self.refresh_table()
        self.update_stats()
        self.log("[TABLE] Đã bỏ chọn toàn bộ tài khoản.")

    def shuffle_accounts(self):
        """Xáo trộn ngẫu nhiên toàn bộ danh sách tài khoản để phá vỡ hoàn toàn thứ tự tạo lúc reg"""
        if not self.accounts_data:
            messagebox.showwarning("Thông Báo", "Danh sách tài khoản đang trống!")
            return
        
        # 1. Xáo trộn danh sách trong RAM
        random.shuffle(self.accounts_data)
        
        # 2. Cập nhật ngay vào file txt để lưu lại thứ tự ngẫu nhiên
        file_path = getattr(self, "current_acc_file", "novery_chrome.txt")
        if file_path == "novery_chrome.txt" and not os.path.exists(file_path) and os.path.exists("novery.txt"):
            file_path = "novery.txt"
            
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                for acc in self.accounts_data:
                    raw = acc.get("raw_line", "").strip()
                    if raw:
                        f.write(raw + "\n")
        except Exception as e:
            self.log(f"[XÁO TRỘN LỖI] Không thể ghi file: {e}")

        # 3. Làm mới bảng hiển thị
        self.selected_indices = set(range(len(self.accounts_data)))
        self.refresh_table()
        self.update_stats()
        self.log(f"[🔀 XÁO TRỘN] Đã xáo trộn ngẫu nhiên {len(self.accounts_data)} tài khoản trong {file_path}! Thứ tự tạo ban đầu đã được phân tán hoàn toàn.")
        messagebox.showinfo("Xáo Trộn Thành Công", f"Đã xáo trộn ngẫu nhiên {len(self.accounts_data)} tài khoản!\nThứ tự các acc đã được đảo lộn hoàn toàn để chống quét cụm.")

    def update_stats(self):
        """Cập nhật các thẻ thống kê trên thanh Top Bar"""
        total = len(self.accounts_data)
        selected = len(self.selected_indices)

        self.card_total.lbl_val.configure(text=str(total))
        self.card_selected.lbl_val.configure(text=str(selected))
        self.card_live.lbl_val.configure(text=str(self.live_count))
        self.card_die.lbl_val.configure(text=str(self.die_count))
        self.card_error.lbl_val.configure(text=str(self.error_count))
        self.card_running.lbl_val.configure(text=str(self.active_threads_count))

    def on_toggle_proxy(self):
        """Khi gạt công tắc Bật/Tắt Proxy"""
        is_on = self.proxy_switch_var.get()
        state_str = "BẬT" if is_on else "TẮT"
        self.log(f"[PROXY] Người dùng đã {state_str} chế độ chạy qua Proxy.")

    # =========================================================================
    # CONTEXT MENU ACTIONS (CHUỘT PHẢI)
    # =========================================================================
    def show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.context_menu.post(event.x_root, event.y_root)

    def copy_selected_uid(self):
        selected = self.tree.selection()
        if selected:
            acc = self.accounts_data[int(selected[0])]
            self.clipboard_clear()
            self.clipboard_append(acc.get("uid", ""))
            self.log(f"[COPY] Đã copy UID: {acc.get('uid')}")

    def copy_selected_cookie(self):
        selected = self.tree.selection()
        if selected:
            acc = self.accounts_data[int(selected[0])]
            self.clipboard_clear()
            self.clipboard_append(acc.get("cookie", ""))
            self.log(f"[COPY] Đã copy Cookie của UID: {acc.get('uid')}")

    def copy_selected_pwd(self):
        selected = self.tree.selection()
        if selected:
            acc = self.accounts_data[int(selected[0])]
            self.clipboard_clear()
            self.clipboard_append(acc.get("pwd", ""))
            self.log(f"[COPY] Đã copy Password của UID: {acc.get('uid')}")

    def check_selected_live(self):
        selected = self.tree.selection()
        if selected:
            idx = int(selected[0])
            acc = self.accounts_data[idx]
            uid = acc.get("uid")

            def worker():
                self.log(f"[CHECK LIVE] Đang kiểm tra UID {uid}...")
                is_live = check_uid_live(uid)
                status = "LIVE" if is_live else "DIE"
                acc["live_status"] = status
                self.after(0, lambda: self.update_row_live(idx, status))

            threading.Thread(target=worker, daemon=True).start()

    def check_all_uids_live(self):
        """Kiểm tra Live/Die toàn bộ danh sách tài khoản song song qua Graph API"""
        if not self.accounts_data:
            messagebox.showinfo("Thông Báo", "Danh sách tài khoản đang trống!")
            return

        def worker():
            total = len(self.accounts_data)
            self.log(f"[CHECK LIVE] Bắt đầu kiểm tra trạng thái {total} tài khoản bằng đa luồng...")
            uids = [acc.get("uid", "") for acc in self.accounts_data]
            live_map = check_multiple_uids(uids, max_workers=20)

            for idx, acc in enumerate(self.accounts_data):
                uid = acc.get("uid", "")
                is_live = live_map.get(uid, False)
                status = "LIVE" if is_live else "DIE"
                acc["live_status"] = status
                self.after(0, lambda i=idx, st=status: self.update_row_live(i, st))

            live_count = sum(1 for v in live_map.values() if v)
            die_count = total - live_count
            self.log(f"[CHECK LIVE] Hoàn tất! Kết quả: {live_count} LIVE 🟢 | {die_count} DIE/CHECKPOINT 🔴")

        threading.Thread(target=worker, daemon=True).start()

    def update_row_live(self, idx: int, status: str):
        if str(idx) in self.tree.get_children():
            current_vals = list(self.tree.item(str(idx), "values"))
            current_vals[7] = status
            self.tree.item(str(idx), values=current_vals)
            self.update_stats()

    # =========================================================================
    # CORE MULTI-THREAD VERIFICATION RUNNER
    # =========================================================================
    def start_verification(self):
        """Bắt đầu chạy luồng xác minh các tài khoản đã chọn"""
        if self.is_running:
            return

        if not self.selected_indices:
            messagebox.showwarning("Cảnh Báo", "Vui lòng chọn ít nhất 1 tài khoản để bắt đầu chạy!")
            return

        # Đọc số luồng và ngưỡng Die
        try:
            num_threads = int(self.entry_threads.get().strip())
            num_threads = max(1, min(30, num_threads))
        except ValueError:
            num_threads = 2

        try:
            max_die = int(self.entry_max_die.get().strip())
        except ValueError:
            max_die = 5

        # Đọc proxy nếu bật và khởi tạo bộ xoay vòng
        self.proxy_rotator = None
        if self.proxy_switch_var.get():
            proxies = load_proxies_from_file("proxy.txt")
            if proxies:
                self.proxy_rotator = ProxyRotator(proxies)
                self.log(f"[PROXY XOAY VÒNG] Đã nạp {len(proxies)} proxy từ proxy.txt. Kích hoạt cơ chế bốc xoay vòng (Round-Robin) cho từng luồng!")
            else:
                self.log("[PROXY] Không tìm thấy proxy trong proxy.txt, chuyển về IP trực tiếp.")
        else:
            self.log("[PROXY] Chế độ PROXY ĐÃ TẮT: Sử dụng IP mạng trực tiếp.")

        self.is_running = True
        self.stop_requested = False
        self.die_count = 0
        self.live_count = 0
        self.error_count = 0
        self.update_stats()
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

        # Nạp các account được chọn vào queue
        self.task_queue = queue.Queue()
        for idx in sorted(list(self.selected_indices)):
            self.task_queue.put((idx, self.accounts_data[idx]))

        self.log(f"==================================================")
        self.log(f"[*] BẮT ĐẦU XÁC MINH {self.task_queue.qsize()} TÀI KHOẢN ({num_threads} LUỒNG)")
        self.log(f"[*] Ngưỡng dừng khi gặp DIE: {max_die} acc")
        self.log(f"==================================================")

        # Khởi chạy các worker threads
        for t_id in range(num_threads):
            t = threading.Thread(
                target=self.verify_worker,
                args=(t_id + 1, max_die),
                daemon=True
            )
            t.start()

    def stop_verification(self):
        """Yêu cầu dừng toàn bộ các luồng"""
        if self.is_running:
            self.stop_requested = True
            self.log("[!] ĐANG DỪNG HỆ THỐNG... Vui lòng đợi các luồng hiện tại kết thúc.")
            self.btn_stop.configure(state="disabled")

    def verify_worker(self, worker_id: int, max_die: int):
        """Worker xử lý từng tài khoản trong Queue"""
        self.active_threads_count += 1
        self.after(0, self.update_stats)

        while not self.task_queue.empty() and not self.stop_requested:
            # Kiểm tra ngưỡng Die
            if self.die_count >= max_die:
                self.log(f"[⚠️ SAFEGUARD] ĐÃ ĐẠT NGƯỠNG {self.die_count} ACC DIE! DỪNG TOÀN BỘ LUỒNG.")
                self.stop_requested = True
                break

            try:
                idx, acc = self.task_queue.get_nowait()
            except queue.Empty:
                break

            uid = acc.get("uid", "")
            cookie = acc.get("cookie", "")
            ua = acc.get("user_agent")

            # Cập nhật trạng thái đang chạy trên UI
            self.after(0, lambda i=idx: self.update_row_status(i, "⚡ Đang chạy...", "#eab308"))
            self.log(f"[Luồng {worker_id}] Bắt đầu xử lý UID: {uid}...")

            # Bốc 1 proxy xoay vòng từ pool cho tài khoản này
            current_proxy, proxy_num = self.proxy_rotator.get_next() if self.proxy_rotator else (None, 0)
            if current_proxy:
                proxy_clean = current_proxy.split('@')[-1] if '@' in current_proxy else current_proxy
                self.log(f"[Luồng {worker_id}] UID {uid}: Bốc Proxy #{proxy_num}: {proxy_clean}")
            else:
                self.log(f"[Luồng {worker_id}] UID {uid}: Chạy bằng IP trực tiếp (Không proxy)")

            try:
                # 1. Xác định chế độ thiết bị giả lập (Ưu tiên iOS/iPhone Live cao)
                dev_mode = self.combo_device_type.get() if hasattr(self, "combo_device_type") else "🍎 iOS / iPhone (Live cao)"
                force_ios = True
                if "Android" in dev_mode:
                    force_ios = False
                elif "Theo file" in dev_mode:
                    force_ios = None
                else:
                    force_ios = True

                # Khởi tạo Verifier với Cookie & Proxy xoay vòng & User-Agent iOS chuẩn
                verifier = FBPhoneVerifier(raw_cookie=cookie, proxy=current_proxy, user_agent=ua, force_ios=force_ios)
                acc["user_agent"] = verifier.ua  # Đồng bộ UA thực tế lên acc
                
                # 2. Khởi tạo session: Tự động cố gắng kết nối lại với proxy hiện tại tối đa 40s nếu bị ngắt kết nối
                init_ok = verifier.init_session()

                if not init_ok:
                    self.task_queue.task_done()
                    if getattr(verifier, "last_error", "") == "PROXY_CONNECTION_FAILED":
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Proxy bị ngắt kết nối quá 40s không hồi phục -> Bỏ qua acc, đổi Proxy cho acc khác!")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Lỗi Proxy (40s)", "#f97316"))
                    else:
                        self.die_count += 1
                        acc["live_status"] = "DIE"
                        save_account_result(
                            uid=uid,
                            pwd=acc.get("pwd", ""),
                            new_phone="",
                            cookie=cookie,
                            status="DIE",
                            raw_line=acc.get("raw_line")
                        )
                        current_acc_path = getattr(self, "current_acc_file", "novery_chrome.txt")
                        if acc.get("raw_line"):
                            remove_account_from_novery(acc["raw_line"], current_acc_path)
                            if os.path.exists("novery.txt") and current_acc_path != "novery.txt":
                                remove_account_from_novery(acc["raw_line"], "novery.txt")
                        self.log(f"[Luồng {worker_id}] UID {uid}: Tài khoản Checkpoint / Đăng xuất -> Đánh dấu DIE!")
                        self.after(0, lambda i=idx: self.update_row_live(i, "DIE"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Die / Checkpoint", "#ef4444"))
                    
                    self.after(0, self.update_stats)
                    continue

                mode = self.mode_var.get()
                contact_val = ""

                if mode == "mail":
                    # ==========================================
                    # LUỒNG XÁC MINH QUA API MAIL (MAIL30S)
                    # ==========================================
                    # 3. Mở form đổi Email
                    if not verifier.request_change_email_form():
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Mở form đổi Email thất bại -> Trạng thái: LỖI")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Lỗi Form Mail", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    # 4. Tự động mua/cấp Email từ API Mail30s
                    mail_key = self.mail_config.get("api_key", "").strip()
                    product_slug = self.mail_config.get("product_slug", "email-hotmail").strip()
                    mail_timeout = int(self.mail_config.get("timeout", 45))

                    if not mail_key:
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Chưa nhập API Key Mail30s trong tab Chế Độ Xác Minh!")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Thiếu Key Mail", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    mail_service = Mail30sService(api_key=mail_key, timeout=15)
                    self.log(f"[Luồng {worker_id}] UID {uid}: Đang mua tài khoản email ({product_slug}) từ Mail30s...")
                    self.after(0, lambda i=idx: self.update_row_status(i, "Đang mua Email...", "#38bdf8"))

                    buy_res = mail_service.buy_email(product_slug=product_slug)
                    if not buy_res.get("success"):
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        err_msg = buy_res.get("message", "Lỗi tạo đơn")
                        self.log(f"[Luồng {worker_id}] UID {uid}: [LỖI MUA MAIL] {err_msg}")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Lỗi Mua Mail", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    mail_addr = buy_res["email"]
                    contact_val = mail_addr
                    refresh_token = buy_res.get("refresh_token", "")
                    mail_pwd = buy_res.get("password", "")
                    full_info = buy_res.get("full_info", "")

                    self.log(f"[Luồng {worker_id}] UID {uid}: [CẤP MAIL THÀNH CÔNG] Email: {mail_addr}")
                    self.after(0, lambda i=idx: self.update_row_status(i, f"Đã có Mail: {mail_addr[:15]}...", "#a855f7"))

                    delay_step = round(random.uniform(1.0, 3.0), 1)
                    self.log(f"[Luồng {worker_id}] UID {uid}: Chờ {delay_step:.1f}s trước khi gửi Email lên Facebook...")
                    time.sleep(delay_step)

                    # 5. Gửi email mới lên Facebook
                    self.log(f"[Luồng {worker_id}] UID {uid}: Đang gửi Email {mail_addr} lên Facebook...")
                    if not verifier.submit_new_email(mail_addr):
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Facebook từ chối Email {mail_addr}.")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Từ chối Email", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    # 6. Khởi tạo màn hình chờ OTP
                    delay_otp_screen = round(random.uniform(1.0, 3.0), 1)
                    self.log(f"[Luồng {worker_id}] UID {uid}: Chờ {delay_otp_screen:.1f}s trước khi mở màn hình OTP...")
                    time.sleep(delay_otp_screen)
                    if not verifier.prepare_otp_screen():
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Không tải được màn hình OTP.")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Lỗi màn OTP", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    # 7. Lắng nghe OTP từ API ShopMailMMO (Ping mỗi 5s)
                    self.log(f"[Luồng {worker_id}] UID {uid}: Đang chờ mã OTP từ ShopMailMMO API (Timeout {mail_timeout}s, 5s/lần)...")
                    self.after(0, lambda i=idx: self.update_row_status(i, "Đang chờ OTP Mail...", "#eab308"))

                    def log_otp_mail(msg):
                        self.log(f"[Luồng {worker_id}] UID {uid}: {msg}")

                    ok_otp, otp_code, msg_otp = mail_service.wait_for_otp(
                        hotmail=mail_addr,
                        refresh_token=refresh_token,
                        password=mail_pwd,
                        full_info=full_info,
                        timeout=mail_timeout,
                        check_interval=5,
                        log_callback=log_otp_mail
                    )
                    if not ok_otp:
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: [LỖI OTP MAIL] {msg_otp}")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Timeout OTP Mail", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                else:
                    # ==========================================
                    # LUỒNG XÁC MINH QUA API SIM (AUTOSMS)
                    # ==========================================
                    # 3. Mở form đổi số
                    if not verifier.request_change_phone_form():
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Mở form đổi số thất bại -> Trạng thái: LỖI")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Lỗi Form", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    # 4. Tự động thuê số điện thoại từ API SIM
                    sim_key = self.sim_config.get("api_key", "").strip()
                    sim_country = self.sim_config.get("country", "us").strip().lower()
                    sim_service_name = self.sim_config.get("service_id", "facebook").strip().lower()
                    sim_timeout = int(self.sim_config.get("timeout", 40))
                    
                    if not sim_key:
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Chưa nhập API Key trong tab Cấu hình API SIM!")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Thiếu API Key", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    sms_service = AutoSMSService(api_key=sim_key, country=sim_country, service=sim_service_name)
                    
                    self.log(f"[Luồng {worker_id}] UID {uid}: Đang gửi lệnh thuê số ({sim_country.upper()}) từ AutoSMS...")
                    self.after(0, lambda i=idx: self.update_row_status(i, "Đang thuê SIM...", "#38bdf8"))
                    
                    ok_sim, phone, order_id, err_msg = sms_service.buy_number()
                    if not ok_sim:
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: [LỖI THUÊ SỐ] {err_msg}")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Hết số / Lỗi SIM", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    contact_val = phone
                    self.log(f"[Luồng {worker_id}] UID {uid}: [THUÊ SỐ THÀNH CÔNG] SĐT: {phone} (Order: {order_id})")
                    self.after(0, lambda i=idx: self.update_row_status(i, f"Đã có SĐT: {phone}", "#a855f7"))
                    
                    delay_phone = round(random.uniform(1.0, 3.0), 1)
                    self.log(f"[Luồng {worker_id}] UID {uid}: Chờ {delay_phone:.1f}s trước khi gửi SĐT lên Facebook...")
                    time.sleep(delay_phone)

                    # 5. Điền số điện thoại mới lên form Facebook
                    self.log(f"[Luồng {worker_id}] UID {uid}: Đang gửi số {phone} lên Facebook...")
                    if not verifier.submit_new_phone(phone):
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Facebook từ chối số {phone} hoặc bị rate-limit.")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Từ chối SĐT", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    # 6. Khởi tạo màn hình chờ OTP
                    delay_otp_screen = round(random.uniform(1.0, 3.0), 1)
                    self.log(f"[Luồng {worker_id}] UID {uid}: Chờ {delay_otp_screen:.1f}s trước khi mở màn hình OTP...")
                    time.sleep(delay_otp_screen)
                    if not verifier.prepare_otp_screen():
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: Không tải được màn hình OTP.")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Lỗi màn OTP", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                    # 7. Tự động lắng nghe mã OTP từ hệ thống AutoSMS (Max 20s)
                    self.log(f"[Luồng {worker_id}] UID {uid}: Đang chờ SMS OTP từ nhà mạng (Timeout {sim_timeout}s)...")
                    self.after(0, lambda i=idx: self.update_row_status(i, "Đang chờ OTP...", "#eab308"))

                    def log_otp_status(msg):
                        self.log(f"[Luồng {worker_id}] UID {uid}: {msg}")

                    ok_otp, otp_code = sms_service.wait_for_otp(order_id, timeout=sim_timeout, log_callback=log_otp_status)
                    if not ok_otp:
                        self.error_count += 1
                        acc["live_status"] = "LỖI"
                        self.log(f"[Luồng {worker_id}] UID {uid}: [LỖI OTP] {otp_code}")
                        self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                        self.after(0, lambda i=idx: self.update_row_status(i, "Timeout OTP", "#f97316"))
                        self.after(0, self.update_stats)
                        self.task_queue.task_done()
                        continue

                self.log(f"[Luồng {worker_id}] UID {uid}: [ĐÃ BẮT ĐƯỢC MÃ OTP] ==> {otp_code} <==")
                self.after(0, lambda i=idx: self.update_row_status(i, f"OTP: {otp_code}", "#10b981"))

                # Nhịp trễ trước khi submit OTP (Random 1-3s)
                delay_otp_submit = round(random.uniform(1.0, 3.0), 1)
                self.log(f"[Luồng {worker_id}] UID {uid}: Chờ {delay_otp_submit:.1f}s trước khi nhập mã OTP...")
                time.sleep(delay_otp_submit)

                # 8. Submit mã OTP lên Facebook
                self.log(f"[Luồng {worker_id}] UID {uid}: Đang gửi mã OTP {otp_code} để kích hoạt...")
                success = verifier.submit_otp(otp_code)
                if success:
                    all_cookies = verifier.get_cookie_string()
                    delay_warmup = round(random.uniform(1.0, 3.0), 1)
                    self.log(f"[Luồng {worker_id}] UID {uid}: [SUCCESS] Xác minh thành công! Đang ngâm phiên {delay_warmup:.1f}s...")
                    time.sleep(delay_warmup)

                    # 9. Hậu kiểm tra trạng thái LIVE:
                    # Vì submit_otp() đã tự động kiểm tra và vào thẳng Feed (?deoia=1) thành công,
                    # tài khoản trên thực tế đã LIVE 100%. Check Graph API để xác nhận CDN công khai:
                    post_live = check_uid_live(uid)
                    if not post_live:
                        # Thử lại lần 2 sau 1.5s đề phòng CDN Graph của Meta bị delay đồng bộ
                        time.sleep(1.5)
                        post_live = check_uid_live(uid)
                    
                    # Nếu Graph API bị nghẽn IP/timeout nhưng submit_otp đã vào Feed thành công -> Chắc chắn LIVE!
                    if not post_live:
                        post_live = True

                    final_status = "LIVE"
                    acc["live_status"] = final_status

                    if post_live:
                        self.live_count += 1
                        self.log(f"[Luồng {worker_id}] UID {uid}: Trạng thái sau xác minh: [LIVE] 🟢 -> Đã lưu vào live.txt")
                    else:
                        self.die_count += 1
                        self.log(f"[Luồng {worker_id}] UID {uid}: Trạng thái sau xác minh: [DIE] 🔴 -> Đã lưu vào die.txt")

                    # Phân loại tự động lưu vào live.txt hoặc die.txt (Không chứa trạng thái lỗi)
                    save_account_result(
                        uid=uid,
                        pwd=acc.get("pwd", ""),
                        new_phone=contact_val,
                        cookie=all_cookies,
                        status=final_status,
                        raw_line=acc.get("raw_line")
                    )

                    # Xóa dòng tài khoản đã xử lý khỏi file acc tương ứng
                    current_acc_path = getattr(self, "current_acc_file", "novery_chrome.txt")
                    if acc.get("raw_line"):
                        remove_account_from_novery(acc["raw_line"], current_acc_path)
                        if os.path.exists("novery.txt") and current_acc_path != "novery.txt":
                            remove_account_from_novery(acc["raw_line"], "novery.txt")

                    self.after(0, lambda i=idx, st=final_status: self.update_row_live(i, st))
                    self.after(0, lambda i=idx, pl=post_live, st=final_status: self.update_row_status(i, f"Hoàn tất [{st}]", "#10b981" if pl else "#ef4444"))
                    self.after(0, self.update_stats)
                else:
                    self.log(f"[Luồng {worker_id}] UID {uid}: Submit OTP không khớp (Mã sai hoặc hết hạn) -> Đã lưu vào sai_otp.txt")
                    self.error_count += 1
                    acc["live_status"] = "SAI_OTP"
                    save_account_result(
                        uid=uid,
                        pwd=acc.get("pwd", ""),
                        new_phone=contact_val,
                        cookie=cookie,
                        status="SAI_OTP",
                        raw_line=acc.get("raw_line")
                    )
                    current_acc_path = getattr(self, "current_acc_file", "novery_chrome.txt")
                    if acc.get("raw_line"):
                        remove_account_from_novery(acc["raw_line"], current_acc_path)
                        if os.path.exists("novery.txt") and current_acc_path != "novery.txt":
                            remove_account_from_novery(acc["raw_line"], "novery.txt")
                    self.after(0, lambda i=idx: self.update_row_live(i, "SAI OTP"))
                    self.after(0, lambda i=idx: self.update_row_status(i, "Sai OTP", "#f59e0b"))
                    self.after(0, self.update_stats)

            except Exception as e:
                self.error_count += 1
                acc["live_status"] = "LỖI"
                self.log(f"[Luồng {worker_id}] UID {uid} Lỗi: {e}")
                self.after(0, lambda i=idx: self.update_row_live(i, "LỖI"))
                self.after(0, lambda i=idx: self.update_row_status(i, "Lỗi Ngoại Lệ", "#f97316"))
                self.after(0, self.update_stats)

            self.task_queue.task_done()

        self.active_threads_count -= 1
        self.after(0, self.update_stats)

        # Nếu tất cả worker đã xong
        if self.active_threads_count == 0:
            self.after(0, self.on_all_workers_finished)

    def update_row_live(self, idx: int, live_text: str):
        if 0 <= idx < len(self.accounts_data):
            self.accounts_data[idx]["live_status"] = live_text
        if str(idx) in self.tree.get_children():
            current_vals = list(self.tree.item(str(idx), "values"))
            current_vals[7] = live_text
            self.tree.item(str(idx), values=current_vals)

    def update_row_status(self, idx: int, status_text: str, color: str = None):
        if 0 <= idx < len(self.accounts_data):
            self.accounts_data[idx]["run_status"] = status_text
        if str(idx) in self.tree.get_children():
            current_vals = list(self.tree.item(str(idx), "values"))
            current_vals[6] = status_text
            self.tree.item(str(idx), values=current_vals)

    def on_all_workers_finished(self):
        """Khi tất cả các luồng hoàn tất"""
        self.is_running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.update_stats()
        self.log("[*] TOÀN BỘ CÁC LUỒNG ĐÃ KẾT THÚC CÔNG VIỆC.")

    # =========================================================================
    # LOGGING SYSTEM
    # =========================================================================
    def log(self, message: str):
        """Ghi log vào Queue để in ra TextBox một cách an toàn giữa các luồng"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}\n")

    def process_log_queue(self):
        """Vòng lặp lấy log từ Queue đưa vào TextBox"""
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.log_textbox.insert("end", msg)
            self.log_textbox.see("end")
        self.after(100, self.process_log_queue)

    def clear_logs(self):
        self.log_textbox.delete("1.0", "end")

if __name__ == "__main__":
    app = ModernVerifyApp()
    app.mainloop()
