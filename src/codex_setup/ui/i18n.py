"""User-visible strings (en + vi). Every CLI/TUI message goes through ``t``."""

from __future__ import annotations

import locale
import os
from collections.abc import Mapping

_LANG = "en"

EN: dict[str, str] = {
    "version": "codex-setup {version}",
    "app_title": "Codex Setup Manager",
    "hint_no_tty": "Run `codex-setup` in a terminal for the interactive menu, or `codex-setup --help`.",
    # header
    "hdr_os": "OS",
    "hdr_cli": "Codex CLI",
    "hdr_desktop": "Desktop",
    "hdr_provider": "Provider / model",
    "hdr_config": "Config",
    "hdr_test": "Last API test",
    "hdr_key": "API key",
    "not_found": "not found",
    "desktop_installed": "installed",
    "desktop_missing": "not detected",
    "desktop_unsupported": "not supported",
    "cfg_ok": "ok",
    "cfg_invalid": "invalid",
    "cfg_missing": "missing",
    "never": "never",
    "none": "(none)",
    "dry_run_on": "DRY-RUN is ON: nothing will be written",
    # menu
    "menu_1": "Quick Setup",
    "menu_2": "Change Model",
    "menu_3": "API Settings",
    "menu_4": "Test Connection",
    "menu_5": "Windows Sandbox Fix",
    "menu_6": "Backup & Restore",
    "menu_7": "Diagnostics",
    "menu_8": "Profiles",
    "menu_9": "Uninstall Configuration",
    "menu_0": "Exit",
    "menu_L": "Launch Codex (key injected)",
    "menu_D": "Toggle dry-run",
    "menu_choice": "Choose",
    "invalid_choice": "Invalid choice.",
    "bye": "Bye.",
    "press_enter": "Press Enter to continue",
    # common
    "diff_title": "Proposed changes",
    "no_changes": "No changes needed.",
    "apply_confirm": "Apply these changes?",
    "cancelled": "Cancelled.",
    "applied": "Applied.",
    "applied_backup": "Applied. Backup: {path}",
    "dry_run_done": "Dry run: nothing was written.",
    "error": "Error: {msg}",
    "yes": "yes",
    "no": "no",
    "back": "Back",
    "ok": "OK",
    # quick setup
    "qs_base_url": "API base URL",
    "qs_url_no_path": "That URL has no path. Codex providers usually need /v1. Use {url} instead?",
    "qs_url_note": "Note: /v1 was appended: {url}",
    "qs_model": "Model",
    "qs_key": "API key (input hidden, leave empty to keep the stored key)",
    "qs_backend": "Where to store the key? (auto = OS keychain, session = this process only)",
    "qs_done": "Quick setup complete. Start Codex with the menu item L or `codex-setup launch`.",
    "qs_session_warn": "The key is kept in memory only for this session.",
    # model
    "model_title": "Models",
    "model_default": "default",
    "model_custom": "custom",
    "model_pick": "Pick a model number, or A add / E edit / R remove custom model",
    "model_name": "Model name",
    "model_old": "Custom model to change",
    "model_changed": "Model set to {model}.",
    # api
    "api_menu": "1 Change base URL, 2 Set API key, 3 Delete stored key, 0 Back",
    "api_url": "New base URL",
    "api_key": "New API key (input hidden)",
    "api_deleted": "Stored key deleted.",
    "api_key_saved": "Key saved ({backend}): {masked}",
    "api_delete_confirm": "Delete the stored API key?",
    # test
    "test_title": "Connection test",
    "test_step": "Step",
    "test_result": "Result",
    "test_problem": "Problem",
    "test_detail": "Detail",
    "test_overall": "Overall: {overall}",
    "test_running": "Testing {url} with model {model} ...",
    "test_model": "Model to test (empty = current)",
    # sandbox
    "sb_not_applicable": "Windows sandbox settings are not applicable on this system.",
    "sb_explain": (
        "Windows sandbox modes:\n"
        "  elevated   - needs a one-time administrator-approved setup. It can fail on managed PCs.\n"
        "  unelevated - uses a restricted token of your own account. Recommended when you see\n"
        "               \"Couldn't check Windows setup\", \"Couldn't check agent sandbox status\"\n"
        "               or \"Unable to send message\".\n"
        "This tool never turns the sandbox off."
    ),
    "sb_menu": "1 unelevated (recommended), 2 elevated, 3 remove the setting, 0 Back",
    "sb_set": "Windows sandbox set to {mode}.",
    "sb_removed": "Windows sandbox setting removed.",
    # backups
    "bk_title": "Backups",
    "bk_id": "ID",
    "bk_created": "Created",
    "bk_reason": "Reason",
    "bk_menu": "1 Create backup, 2 Restore backup, 3 Restore original, 0 Back",
    "bk_none": "No backups yet.",
    "bk_created_ok": "Backup created: {path}",
    "bk_pick": "Backup ID to restore",
    "bk_restore_confirm": "Restore this backup over the current config?",
    # diagnostics
    "dg_title": "Diagnostics",
    "dg_menu": "1 Run checks, 2 Paste an error message, 0 Back",
    "dg_paste": "Paste the error text",
    "dg_no_match": "No known issue matches that text.",
    "dg_check": "Check",
    "dg_fix": "Fix",
    # profiles
    "pf_title": "Profiles",
    "pf_menu": "1 Use, 2 Add, 3 Remove, 0 Back",
    "pf_name": "Profile name",
    "pf_pick": "Profile name",
    "pf_url": "Base URL",
    "pf_env_key": "Environment variable name for the key",
    "pf_model": "Default model",
    "pf_added": "Profile {name} saved.",
    "pf_removed": "Profile {name} removed.",
    "pf_none": "No profiles yet. Run Quick Setup first.",
    "pf_name_col": "Name",
    "pf_url_col": "Base URL",
    "pf_model_col": "Model",
    "pf_active": "active",
    # uninstall
    "un_info": (
        "This removes the provider tables created by this tool and restores your original\n"
        "model / model_provider. Backups and Codex data are never deleted."
    ),
    "un_confirm": "Uninstall the configuration?",
    "un_secret": "Also delete the stored API key?",
    "un_done": "Configuration restored.",
    # launch
    "ln_target": "Launch target (cli/app)",
    "ln_app_experimental": "Desktop launch is experimental: the app is started directly with the key in its environment.",
    "ln_args": "Extra Codex arguments (optional)",
    "ln_started": "Codex exited with code {code}.",
    "ln_app_started": "Codex Desktop started.",
    # env
    "env_warn_win": "This stores the key persistently in your Windows user environment.",
    "env_warn_posix": "This stores the key in plaintext in your shell startup file.",
    "env_consent": "I understand. Continue?",
    "env_installed": "Persistent environment written: {where}",
    "env_removed": "Persistent environment removed.",
    "env_nothing": "Nothing to remove.",
    # cli
    "cli_not_applicable": "Not applicable on this system.",
    "cli_need_key": "Provide the key with --key-stdin or run `codex-setup` for the prompt.",
    "cli_key_empty": "No key received on stdin.",
    "cli_confirm_noninteractive": "Confirmation needed but input is not interactive; re-run with --yes.",
    "cli_profile_listed": "Profiles",
    "cli_diag_ok": "Diagnostics finished.",
    "cli_cancel_sigint": "Interrupted.",
    "cli_need_arg": "Missing argument: {name}",
    "cli_url_default": "Using the default Lunovant URL.",
    "status_config_path": "Config file",
    "status_env_key": "Env variable",
    "status_sandbox": "Windows sandbox",
}

VI: dict[str, str] = {
    "version": "codex-setup {version}",
    "app_title": "Codex Setup Manager",
    "hint_no_tty": "Chạy `codex-setup` trong terminal để dùng menu tương tác, hoặc `codex-setup --help`.",
    "hdr_os": "Hệ điều hành",
    "hdr_cli": "Codex CLI",
    "hdr_desktop": "Desktop",
    "hdr_provider": "Provider / model",
    "hdr_config": "Cấu hình",
    "hdr_test": "Lần test API gần nhất",
    "hdr_key": "API key",
    "not_found": "không tìm thấy",
    "desktop_installed": "đã cài",
    "desktop_missing": "không phát hiện",
    "desktop_unsupported": "không được hỗ trợ",
    "cfg_ok": "hợp lệ",
    "cfg_invalid": "lỗi cú pháp",
    "cfg_missing": "chưa có",
    "never": "chưa bao giờ",
    "none": "(chưa có)",
    "dry_run_on": "Chế độ DRY-RUN đang BẬT: sẽ không ghi gì cả",
    "menu_1": "Cài đặt nhanh",
    "menu_2": "Đổi model",
    "menu_3": "Cài đặt API",
    "menu_4": "Kiểm tra kết nối",
    "menu_5": "Sửa lỗi Windows Sandbox",
    "menu_6": "Sao lưu & Khôi phục",
    "menu_7": "Chẩn đoán",
    "menu_8": "Profile",
    "menu_9": "Gỡ cấu hình",
    "menu_0": "Thoát",
    "menu_L": "Chạy Codex (tự nạp key)",
    "menu_D": "Bật/tắt dry-run",
    "menu_choice": "Chọn",
    "invalid_choice": "Lựa chọn không hợp lệ.",
    "bye": "Tạm biệt.",
    "press_enter": "Nhấn Enter để tiếp tục",
    "diff_title": "Các thay đổi sẽ áp dụng",
    "no_changes": "Không có thay đổi nào.",
    "apply_confirm": "Áp dụng các thay đổi này?",
    "cancelled": "Đã huỷ.",
    "applied": "Đã áp dụng.",
    "applied_backup": "Đã áp dụng. Bản sao lưu: {path}",
    "dry_run_done": "Chạy thử: chưa ghi gì cả.",
    "error": "Lỗi: {msg}",
    "yes": "có",
    "no": "không",
    "back": "Quay lại",
    "ok": "OK",
    "qs_base_url": "Địa chỉ API (base URL)",
    "qs_url_no_path": "URL này chưa có đường dẫn. Provider cho Codex thường cần /v1. Dùng {url} nhé?",
    "qs_url_note": "Lưu ý: đã thêm /v1: {url}",
    "qs_model": "Model",
    "qs_key": "API key (ẩn khi nhập, để trống để giữ key đã lưu)",
    "qs_backend": "Lưu key ở đâu? (auto = kho khoá của hệ điều hành, session = chỉ trong phiên này)",
    "qs_done": "Đã cài đặt xong. Mở Codex bằng phím L trong menu hoặc `codex-setup launch`.",
    "qs_session_warn": "Key chỉ được giữ trong bộ nhớ của phiên này.",
    "model_title": "Danh sách model",
    "model_default": "mặc định",
    "model_custom": "tuỳ chỉnh",
    "model_pick": "Chọn số model, hoặc A thêm / E sửa / R xoá model tuỳ chỉnh",
    "model_name": "Tên model",
    "model_old": "Model tuỳ chỉnh cần đổi",
    "model_changed": "Đã đặt model là {model}.",
    "api_menu": "1 Đổi base URL, 2 Đặt API key, 3 Xoá key đã lưu, 0 Quay lại",
    "api_url": "Base URL mới",
    "api_key": "API key mới (ẩn khi nhập)",
    "api_deleted": "Đã xoá key đã lưu.",
    "api_key_saved": "Đã lưu key ({backend}): {masked}",
    "api_delete_confirm": "Xoá API key đã lưu?",
    "test_title": "Kiểm tra kết nối",
    "test_step": "Bước",
    "test_result": "Kết quả",
    "test_problem": "Vấn đề",
    "test_detail": "Chi tiết",
    "test_overall": "Tổng kết: {overall}",
    "test_running": "Đang kiểm tra {url} với model {model} ...",
    "test_model": "Model cần kiểm tra (để trống = model hiện tại)",
    "sb_not_applicable": "Cài đặt Windows sandbox không áp dụng cho hệ điều hành này.",
    "sb_explain": (
        "Các chế độ Windows sandbox:\n"
        "  elevated   - cần cài đặt một lần với quyền quản trị được duyệt. Có thể lỗi trên máy do công ty quản lý.\n"
        "  unelevated - dùng token bị giới hạn của chính tài khoản bạn. Nên dùng khi gặp\n"
        "               \"Couldn't check Windows setup\", \"Couldn't check agent sandbox status\"\n"
        "               hoặc \"Unable to send message\".\n"
        "Công cụ này không bao giờ tắt sandbox."
    ),
    "sb_menu": "1 unelevated (khuyên dùng), 2 elevated, 3 xoá thiết lập, 0 Quay lại",
    "sb_set": "Đã đặt Windows sandbox là {mode}.",
    "sb_removed": "Đã xoá thiết lập Windows sandbox.",
    "bk_title": "Bản sao lưu",
    "bk_id": "ID",
    "bk_created": "Thời điểm",
    "bk_reason": "Lý do",
    "bk_menu": "1 Tạo bản sao lưu, 2 Khôi phục bản sao lưu, 3 Khôi phục bản gốc, 0 Quay lại",
    "bk_none": "Chưa có bản sao lưu nào.",
    "bk_created_ok": "Đã tạo bản sao lưu: {path}",
    "bk_pick": "ID bản sao lưu cần khôi phục",
    "bk_restore_confirm": "Khôi phục bản sao lưu này đè lên cấu hình hiện tại?",
    "dg_title": "Chẩn đoán",
    "dg_menu": "1 Chạy kiểm tra, 2 Dán thông báo lỗi, 0 Quay lại",
    "dg_paste": "Dán nội dung lỗi",
    "dg_no_match": "Không có lỗi quen thuộc nào khớp với nội dung này.",
    "dg_check": "Kiểm tra",
    "dg_fix": "Cách sửa",
    "pf_title": "Profile",
    "pf_menu": "1 Dùng, 2 Thêm, 3 Xoá, 0 Quay lại",
    "pf_name": "Tên profile",
    "pf_pick": "Tên profile",
    "pf_url": "Base URL",
    "pf_env_key": "Tên biến môi trường chứa key",
    "pf_model": "Model mặc định",
    "pf_added": "Đã lưu profile {name}.",
    "pf_removed": "Đã xoá profile {name}.",
    "pf_none": "Chưa có profile. Hãy chạy Cài đặt nhanh trước.",
    "pf_name_col": "Tên",
    "pf_url_col": "Base URL",
    "pf_model_col": "Model",
    "pf_active": "đang dùng",
    "un_info": (
        "Thao tác này xoá các bảng provider do công cụ tạo và khôi phục model / model_provider ban đầu.\n"
        "Bản sao lưu và dữ liệu của Codex không bao giờ bị xoá."
    ),
    "un_confirm": "Gỡ cấu hình?",
    "un_secret": "Xoá luôn API key đã lưu?",
    "un_done": "Đã khôi phục cấu hình.",
    "ln_target": "Chạy gì (cli/app)",
    "ln_app_experimental": "Chạy Desktop là tính năng thử nghiệm: ứng dụng được mở trực tiếp với key trong môi trường của nó.",
    "ln_args": "Tham số Codex thêm (không bắt buộc)",
    "ln_started": "Codex đã thoát với mã {code}.",
    "ln_app_started": "Đã mở Codex Desktop.",
    "env_warn_win": "Thao tác này lưu key lâu dài trong biến môi trường người dùng của Windows.",
    "env_warn_posix": "Thao tác này lưu key dạng văn bản thường trong file khởi động của shell.",
    "env_consent": "Tôi hiểu. Tiếp tục?",
    "env_installed": "Đã ghi biến môi trường lâu dài: {where}",
    "env_removed": "Đã xoá biến môi trường lâu dài.",
    "env_nothing": "Không có gì để xoá.",
    "cli_not_applicable": "Không áp dụng cho hệ điều hành này.",
    "cli_need_key": "Truyền key bằng --key-stdin hoặc chạy `codex-setup` để nhập qua prompt.",
    "cli_key_empty": "Không nhận được key từ stdin.",
    "cli_confirm_noninteractive": "Cần xác nhận nhưng đầu vào không tương tác; hãy chạy lại với --yes.",
    "cli_profile_listed": "Danh sách profile",
    "cli_diag_ok": "Đã chẩn đoán xong.",
    "cli_cancel_sigint": "Đã ngắt.",
    "cli_need_arg": "Thiếu tham số: {name}",
    "cli_url_default": "Dùng URL Lunovant mặc định.",
    "status_config_path": "File cấu hình",
    "status_env_key": "Biến môi trường",
    "status_sandbox": "Windows sandbox",
}

_TABLES: dict[str, dict[str, str]] = {"en": EN, "vi": VI}


def default_lang(env: Mapping[str, str] | None = None) -> str:
    e = os.environ if env is None else env
    forced = (e.get("CODEX_SETUP_LANG") or "").strip().lower()
    if forced in _TABLES:
        return forced
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = (e.get(key) or "").lower()
        if value:
            return "vi" if value.startswith("vi") else "en"
    try:
        loc = (locale.getlocale()[0] or "").lower()
    except (ValueError, TypeError):
        loc = ""
    return "vi" if loc.startswith("vi") else "en"


def set_lang(lang: str) -> None:
    global _LANG
    _LANG = lang if lang in _TABLES else "en"


def get_lang() -> str:
    return _LANG


def t(key: str, **kw: object) -> str:
    text = _TABLES[_LANG].get(key) or EN.get(key) or key
    return text.format(**kw) if kw else text
