"""Known Codex error messages mapped to explanations and fix steps (en + vi)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class KnownIssue:
    id: str
    patterns: tuple[str, ...]
    title: dict[str, str]
    explanation: dict[str, str]
    steps: dict[str, list[str]]


_SANDBOX_EN = (
    "On Windows, Codex runs commands in a sandbox. `elevated` needs a one-time setup approved by an "
    "administrator. `unelevated` uses a restricted token of your own user and needs no admin approval."
)
_SANDBOX_VI = (
    "Trên Windows, Codex chạy lệnh trong sandbox. Chế độ `elevated` cần thiết lập một lần do quản trị viên "
    "phê duyệt. Chế độ `unelevated` dùng token bị giới hạn của chính tài khoản bạn, không cần quyền admin."
)
_SANDBOX_STEPS_EN = [
    "Try `codex-setup sandbox unelevated` first, then restart Codex.",
    "Use `elevated` only if an administrator can approve its one-time setup.",
    "This tool never disables the sandbox and never touches Defender, UAC or admin settings.",
    "Check $CODEX_HOME/.sandbox/sandbox.log for details (run `codex-setup diagnose`).",
]
_SANDBOX_STEPS_VI = [
    "Hãy thử `codex-setup sandbox unelevated` trước, rồi khởi động lại Codex.",
    "Chỉ dùng `elevated` khi có quản trị viên phê duyệt thiết lập một lần của nó.",
    "Công cụ này không bao giờ tắt sandbox và không đụng tới Defender, UAC hay quyền admin.",
    "Xem chi tiết trong $CODEX_HOME/.sandbox/sandbox.log (chạy `codex-setup diagnose`).",
]

ISSUES: tuple[KnownIssue, ...] = (
    KnownIssue(
        "provider_mismatch",
        ("model provider mismatch", "provider mismatch", "different model provider",
         "thread was created with"),
        {"en": "Model provider mismatch", "vi": "Lệch nhà cung cấp model (provider mismatch)"},
        {
            "en": "Existing threads stay bound to the provider they were created with. After switching "
                  "provider, old threads keep failing. This tool never edits session files.",
            "vi": "Các thread cũ luôn gắn với provider lúc được tạo. Sau khi đổi provider, thread cũ sẽ "
                  "tiếp tục lỗi. Công cụ này không bao giờ sửa file session.",
        },
        {
            "en": ["Start a new thread/session after switching provider.",
                   "Verify `model_provider` in config.toml with `codex-setup status`."],
            "vi": ["Hãy tạo thread/session mới sau khi đổi provider.",
                   "Kiểm tra `model_provider` trong config.toml bằng `codex-setup status`."],
        },
    ),
    KnownIssue(
        "windows_setup",
        ("couldn't check windows setup", "could not check windows setup", "couldn’t check windows setup"),
        {"en": "Couldn't check Windows setup", "vi": "Không kiểm tra được thiết lập Windows"},
        {"en": "Codex could not verify the Windows sandbox setup. " + _SANDBOX_EN,
         "vi": "Codex không xác minh được thiết lập sandbox trên Windows. " + _SANDBOX_VI},
        {"en": _SANDBOX_STEPS_EN, "vi": _SANDBOX_STEPS_VI},
    ),
    KnownIssue(
        "sandbox_status",
        ("couldn't check agent sandbox status", "could not check agent sandbox status",
         "couldn’t check agent sandbox status"),
        {"en": "Couldn't check agent sandbox status", "vi": "Không kiểm tra được trạng thái sandbox của agent"},
        {"en": "Codex could not read the agent sandbox status. " + _SANDBOX_EN,
         "vi": "Codex không đọc được trạng thái sandbox của agent. " + _SANDBOX_VI},
        {"en": _SANDBOX_STEPS_EN, "vi": _SANDBOX_STEPS_VI},
    ),
    KnownIssue(
        "unable_to_send",
        ("unable to send message", "unable to send"),
        {"en": "Unable to send message", "vi": "Không gửi được tin nhắn"},
        {
            "en": "Codex could not send the request. Common causes: Windows sandbox setup failed, a wrong "
                  "base URL, a missing API key variable, or a provider mismatch on an old thread. "
                  + _SANDBOX_EN,
            "vi": "Codex không gửi được yêu cầu. Nguyên nhân thường gặp: sandbox Windows chưa thiết lập được, "
                  "sai base URL, thiếu biến môi trường chứa API key, hoặc thread cũ bị lệch provider. "
                  + _SANDBOX_VI,
        },
        {
            "en": ["Run `codex-setup test` to check URL, key and model.",
                   "Start a new thread if you switched provider.",
                   "On Windows, try `codex-setup sandbox unelevated` first (the tool never disables the sandbox)."],
            "vi": ["Chạy `codex-setup test` để kiểm tra URL, key và model.",
                   "Tạo thread mới nếu bạn vừa đổi provider.",
                   "Trên Windows, thử `codex-setup sandbox unelevated` trước (công cụ không tắt sandbox)."],
        },
    ),
    KnownIssue(
        "unauthorized",
        ("401", "unauthorized", "invalid api key", "incorrect api key"),
        {"en": "401 Unauthorized", "vi": "401 Không được phép"},
        {"en": "The provider rejected the API key.", "vi": "Nhà cung cấp từ chối API key."},
        {
            "en": ["Re-enter the key with `codex-setup api --key-stdin`.",
                   "Make sure the key belongs to this provider and has not been revoked."],
            "vi": ["Nhập lại key bằng `codex-setup api --key-stdin`.",
                   "Đảm bảo key thuộc đúng provider này và chưa bị thu hồi."],
        },
    ),
    KnownIssue(
        "forbidden",
        ("403", "forbidden"),
        {"en": "403 Forbidden", "vi": "403 Bị cấm truy cập"},
        {"en": "The key is valid but has no access to this endpoint or model.",
         "vi": "Key hợp lệ nhưng không có quyền truy cập endpoint hoặc model này."},
        {
            "en": ["Check the key's permissions and plan in the provider dashboard.",
                   "Try another model with `codex-setup model`."],
            "vi": ["Kiểm tra quyền và gói của key trong trang quản lý của provider.",
                   "Thử model khác bằng `codex-setup model`."],
        },
    ),
    KnownIssue(
        "model_not_found",
        ("404", "model not found", "does not exist", "model_not_found"),
        {"en": "Model not found (404)", "vi": "Không tìm thấy model (404)"},
        {"en": "The provider does not know this model name, or the URL is wrong.",
         "vi": "Provider không biết tên model này, hoặc URL bị sai."},
        {
            "en": ["Pick a listed model with `codex-setup model`.",
                   "Check that the base URL ends with /v1."],
            "vi": ["Chọn model có trong danh sách bằng `codex-setup model`.",
                   "Kiểm tra base URL có kết thúc bằng /v1."],
        },
    ),
    KnownIssue(
        "rate_limited",
        ("429", "rate limit", "too many requests"),
        {"en": "Rate limited (429)", "vi": "Bị giới hạn tốc độ (429)"},
        {"en": "Too many requests or the quota is used up.",
         "vi": "Quá nhiều yêu cầu hoặc đã hết hạn mức."},
        {
            "en": ["Wait a bit and retry.", "Check your quota and balance with the provider."],
            "vi": ["Đợi một lúc rồi thử lại.", "Kiểm tra hạn mức và số dư với provider."],
        },
    ),
    KnownIssue(
        "responses_incompatible",
        ("responses api", "/responses", "response.completed", "wire_api", "incompatible"),
        {"en": "Responses API not compatible", "vi": "API Responses không tương thích"},
        {"en": "Codex needs a streaming OpenAI Responses API. The provider does not offer it at this URL.",
         "vi": "Codex cần API Responses kiểu OpenAI có hỗ trợ streaming. Provider không cung cấp tại URL này."},
        {
            "en": ["Run `codex-setup test` to see which step fails.",
                   "Check the base URL (usually ends with /v1) and that wire_api = \"responses\"."],
            "vi": ["Chạy `codex-setup test` để xem bước nào lỗi.",
                   "Kiểm tra base URL (thường kết thúc bằng /v1) và wire_api = \"responses\"."],
        },
    ),
    KnownIssue(
        "invalid_config",
        (r"config\.toml.*(parse|invalid|expected|error)", r"(parse|invalid|toml).*config\.toml"),
        {"en": "Invalid config.toml", "vi": "config.toml không hợp lệ"},
        {"en": "config.toml has a TOML syntax error, so Codex cannot read it.",
         "vi": "config.toml có lỗi cú pháp TOML nên Codex không đọc được."},
        {
            "en": ["Fix the reported line, or restore a backup with `codex-setup backup list` / `restore`."],
            "vi": ["Sửa dòng được báo lỗi, hoặc khôi phục bản sao lưu bằng `codex-setup backup list` / `restore`."],
        },
    ),
    KnownIssue(
        "env_missing",
        (r"environment variable.*(missing|not set|not found|is not set)",
         r"(missing|not set).*environment variable", r"LUNOVANT_API_KEY"),
        {"en": "API key environment variable missing", "vi": "Thiếu biến môi trường chứa API key"},
        {"en": "Codex reads the API key from an environment variable, and it is not set in this process.",
         "vi": "Codex đọc API key từ biến môi trường, nhưng biến này chưa được đặt trong tiến trình hiện tại."},
        {
            "en": ["Start Codex with `codex-setup launch` (injects the key).",
                   "Or opt in to `codex-setup env install` (stores the key in plaintext)."],
            "vi": ["Khởi chạy Codex bằng `codex-setup launch` (tự truyền key).",
                   "Hoặc chủ động dùng `codex-setup env install` (lưu key dạng văn bản thường)."],
        },
    ),
    KnownIssue(
        "codex_not_found",
        ("codex: command not found", "not recognized as an internal or external command",
         "codex: not found"),
        {"en": "Codex CLI not found", "vi": "Không tìm thấy Codex CLI"},
        {"en": "The `codex` command is not on PATH.",
         "vi": "Lệnh `codex` không nằm trong PATH."},
        {
            "en": ["Install the Codex CLI and reopen the terminal.", "Check PATH includes its install folder."],
            "vi": ["Cài Codex CLI rồi mở lại terminal.", "Kiểm tra PATH có chứa thư mục cài đặt."],
        },
    ),
)


def _matches(issue: KnownIssue, text: str) -> bool:
    for pat in issue.patterns:
        if pat.lower() in text:
            return True
        try:
            if re.search(pat, text, re.IGNORECASE | re.DOTALL):
                return True
        except re.error:
            continue
    return False


def lookup(text: str) -> list[KnownIssue]:
    low = (text or "").lower()
    if not low.strip():
        return []
    return [i for i in ISSUES if _matches(i, low)]
