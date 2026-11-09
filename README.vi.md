# Codex Setup Manager

[English](README.md) | Tiếng Việt

Codex Setup Manager (`codex-setup`) giúp bạn cấu hình OpenAI Codex (bản CLI và ứng dụng Desktop) để dùng API của Lunovant. Công cụ sửa file `config.toml` của Codex một cách an toàn, lưu khóa API trong kho bí mật của hệ điều hành, kiểm tra kết nối và mở Codex kèm khóa API.

## Công cụ này làm gì

- Thêm nhà cung cấp Lunovant và model mặc định vào `$CODEX_HOME/config.toml` (giữ nguyên các cài đặt và ghi chú khác của bạn).
- Lưu khóa API trong Keychain (macOS), Credential Manager (Windows) hoặc Secret Service (Linux). Khóa không bao giờ được ghi vào `config.toml`.
- Kiểm tra kết nối từng bước (kết nối, khóa, danh sách model, Responses API, streaming).
- Mở Codex CLI hoặc Desktop với khóa được truyền qua biến môi trường.
- Sửa các lỗi sandbox thường gặp trên Windows.
- Sao lưu cấu hình trước mỗi thay đổi, có thể khôi phục hoặc gỡ bỏ hoàn toàn.
- Giao diện tiếng Anh và tiếng Việt (`--lang en|vi`).

Các model: `gpt-6.1-sol` (mặc định), `gpt-6.1-terra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`.
Base URL: `https://api.lunovant.tech`. Endpoint API: `https://api.lunovant.tech/v1`.

## Hệ điều hành hỗ trợ

| Hệ điều hành | Kiến trúc | Codex CLI | Ứng dụng Codex Desktop |
| --- | --- | --- | --- |
| Windows 10 / 11 | x64 | Có | Có |
| macOS (Apple Silicon) | arm64 | Có | Có |
| macOS (Intel) | x64 | Có | Bản tải Desktop được tài liệu nêu là cho Apple Silicon; trên Intel hãy dùng CLI |
| Ubuntu 24.04 | x64 | Có | Ứng dụng Linux đang ở bản preview |
| Ubuntu 22.04 | x64 | Có | Không có ứng dụng Desktop chính thức; hãy dùng CLI |

Ứng dụng Desktop trên Linux là bản preview, dành cho Ubuntu 24.04/26.04, Debian 13, Fedora 43/44 và Arch. Bạn cần cài Codex riêng; Codex Setup Manager không cài Codex thay bạn.

## Tải về

1. Mở trang GitHub Releases của dự án và tải file phù hợp với máy của bạn:
   - `codex-setup-windows-x64.exe`
   - `codex-setup-macos-arm64` (Mac chip Apple Silicon)
   - `codex-setup-macos-x64` (Mac Intel)
   - `codex-setup-linux-x64`
2. Tải thêm file `.sha256` tương ứng rồi kiểm tra:
   - macOS: `shasum -a 256 codex-setup-macos-arm64`
   - Linux: `sha256sum codex-setup-linux-x64`
   - Windows (PowerShell): `Get-FileHash .\codex-setup-windows-x64.exe -Algorithm SHA256`

   Chuỗi hiển thị phải trùng với nội dung file `.sha256`.

## Chạy lần đầu

File chạy trên Windows chưa được ký số, nên SmartScreen sẽ hiện cảnh báo ở lần chạy đầu tiên.

### macOS

Bản phát hành được ký bằng Developer ID và được Apple công chứng (notarize) khi các secret ký của maintainer có sẵn, nên chỉ cần:

```bash
chmod +x ./codex-setup-macos-arm64
./codex-setup-macos-arm64
```

Nếu bản build chưa được ký và Gatekeeper chặn, hãy cho phép riêng file này (`xattr -d` trả về mã 1 khi thuộc tính không tồn tại, nên đừng nối bằng `&&`):

```bash
chmod +x ./codex-setup-macos-arm64
xattr -d com.apple.quarantine ./codex-setup-macos-arm64 2>/dev/null; ./codex-setup-macos-arm64
```

Cách khác: trong Finder, bấm chuột phải vào file, chọn Open (Mở), rồi xác nhận Open. Đừng tắt Gatekeeper cho toàn bộ máy.

### Windows

Bấm đúp vào file `.exe` (hoặc chạy trong Terminal). Nếu thấy "Windows protected your PC", bấm More info, rồi chọn Run anyway. Không cần quyền quản trị viên.

### Linux

```bash
chmod +x ./codex-setup-linux-x64
./codex-setup-linux-x64
```

Để tiện dùng, bạn có thể đổi tên file thành `codex-setup` và đặt vào thư mục trong `PATH`. Các ví dụ bên dưới dùng tên `codex-setup`.

## Hướng dẫn Quick Setup

Chạy `codex-setup` không kèm tham số để mở menu:

```
1  Quick Setup
2  Change Model
3  API Settings
4  Test Connection
5  Windows Sandbox Fix   (chỉ trên Windows)
6  Backup & Restore
7  Diagnostics
8  Profiles
9  Uninstall Configuration
0  Exit
L  Launch Codex (kèm khóa API)
```

Chọn 1 và làm theo hướng dẫn: xác nhận base URL, dán khóa API (ký tự được ẩn), chọn model, xem phần thay đổi và xác nhận. Sau đó chọn 4 để kiểm tra kết nối và L để mở Codex. Không có gì bị thay đổi cho đến khi bạn xác nhận, và công cụ luôn sao lưu trước.

## Tham khảo lệnh

Tùy chọn chung: `--codex-home PATH`, `--lang en|vi`. Các lệnh ghi dữ liệu hỗ trợ `--dry-run` (chỉ xem thay đổi) và `--yes` (bỏ qua bước xác nhận).

| Lệnh | Công dụng |
| --- | --- |
| `status` | Xem cấu hình, nhà cung cấp, model, khóa và trạng thái Codex |
| `setup [--base-url URL] [--model M] [--key-stdin] [--secret-backend auto\|keyring\|file\|session]` | Quick Setup |
| `model [NAME]` | Xem hoặc đổi model |
| `api [--base-url URL] [--key-stdin \| --delete-key]` | Đổi base URL hoặc khóa, hoặc xóa khóa đã lưu |
| `test [--model M]` | Kiểm tra kết nối |
| `sandbox [elevated\|unelevated\|remove]` | Chế độ sandbox Windows (hệ khác: không áp dụng) |
| `backup create\|list\|restore ID\|original` | Quản lý bản sao lưu |
| `diagnose [--text TEXT]` | Kiểm tra cục bộ, hoặc giải thích một thông báo lỗi |
| `profile list\|add\|use\|remove` | Quản lý profile |
| `launch [cli\|app] [-- codex args...]` | Mở Codex kèm khóa API |
| `env install\|remove` | Lưu khóa thành biến môi trường lâu dài (tùy chọn) |
| `uninstall` | Gỡ những gì công cụ đã thêm |
| `--version` | Hiển thị phiên bản |

Ví dụ:

```bash
codex-setup setup --dry-run              # xem trước thay đổi, không ghi gì
codex-setup model gpt-6.1-terra          # đổi model
codex-setup test                         # kiểm tra kết nối
codex-setup sandbox unelevated           # phương án thay thế cho sandbox Windows
codex-setup launch cli                   # mở Codex CLI kèm khóa
codex-setup launch app                   # mở Codex Desktop kèm khóa (thử nghiệm)
echo "sk-..." | codex-setup api --key-stdin
```

Hãy ưu tiên nhập khóa ở ô nhập ẩn thay vì `--key-stdin`: khóa gõ trực tiếp trên dòng lệnh có thể còn lưu trong lịch sử shell. Chỉ dùng `--key-stdin` cho tự động hóa, và lấy khóa từ nguồn được bảo vệ.

## Khóa API được lưu như thế nào

Thứ tự lưu trữ (`--secret-backend auto`):

1. Kho bí mật của hệ điều hành: Keychain (macOS), Credential Manager (Windows) hoặc Secret Service (Linux).
2. Chỉ trong phiên làm việc: nếu máy không có kho bí mật, khóa chỉ nằm trong bộ nhớ đến khi chương trình thoát.
3. File văn bản thường: chỉ khi bạn chủ động chọn `--secret-backend file`. Khóa được lưu trong `secrets.json` ở thư mục dữ liệu của ứng dụng, chỉ chủ sở hữu được đọc. File này không được mã hóa; công cụ sẽ cảnh báo bạn.

Codex đọc khóa từ biến môi trường `LUNOVANT_API_KEY` (giá trị `env_key` trong `config.toml`), không đọc từ file cấu hình. Vì vậy biến này phải có trong tiến trình khởi động Codex:

- `codex-setup launch cli` / `launch app` mở Codex với biến đó chỉ trong tiến trình ấy. Không ghi gì ra đĩa.
- `codex-setup env install` lưu khóa thành biến môi trường lâu dài (Windows: biến môi trường của người dùng; macOS/Linux: một khối đánh dấu trong file rc của shell). Cách này ghi khóa dạng văn bản thường, chỉ dùng nếu bạn chấp nhận điều đó. Dùng `codex-setup env remove` để hoàn tác.

Khóa không bao giờ nằm trong `config.toml`, log hay tham số dòng lệnh.

## config.toml sau khi cấu hình

```toml
model = "gpt-6.1-sol"
model_provider = "lunovant"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
env_key = "LUNOVANT_API_KEY"
wire_api = "responses"
```

File nằm ở `~/.codex/config.toml` (Windows: `%USERPROFILE%\.codex\config.toml`), hoặc trong thư mục `CODEX_HOME` nếu bạn có đặt. Các id nhà cung cấp dựng sẵn `openai`, `ollama`, `lmstudio`, `amazon-bedrock` và `gcp` được dành riêng; công cụ không bao giờ ghi bảng cho các id này.

## Sandbox trên Windows

Codex trên Windows chạy lệnh trong sandbox với hai chế độ:

- `elevated`: cần một bước thiết lập một lần do quản trị viên phê duyệt.
- `unelevated`: dùng token bị hạn chế của chính tài khoản của bạn. Không cần quản trị viên phê duyệt.

Hãy chọn `unelevated` khi bước thiết lập elevated bị chặn (không có quyền quản trị, chính sách công ty, phần mềm bảo mật). Chạy:

```
codex-setup sandbox unelevated
```

Các lỗi thường gặp mà cách này xử lý:

- "Couldn't check Windows setup"
- "Couldn't check agent sandbox status"
- "Unable to send message"

Không bao giờ tắt sandbox; công cụ này không có tùy chọn đó và không đụng đến Defender hay UAC. `codex-setup sandbox remove` đưa về mặc định của Codex. File log sandbox: `%USERPROFILE%\.codex\.sandbox\sandbox.log` (`$CODEX_HOME/.sandbox/sandbox.log`). Lệnh `codex-setup diagnose` đọc các dòng cuối của log này và đã che khóa API.

## Xử lý sự cố

Hãy chạy `codex-setup test` và `codex-setup diagnose` trước. Để giải thích một thông báo bạn gặp: `codex-setup diagnose --text "thông báo"`.

- Provider mismatch ("model provider mismatch"): cuộc trò chuyện cũ vẫn gắn với nhà cung cấp lúc nó được tạo. Hãy bắt đầu một thread hoặc phiên mới. Công cụ không bao giờ sửa file phiên của Codex.
- 401 Unauthorized: khóa sai, hết hạn hoặc có khoảng trắng thừa. Đặt lại khóa bằng `codex-setup api`.
- 403 Forbidden: khóa không có quyền dùng model hoặc endpoint này. Hãy kiểm tra gói dịch vụ với Lunovant.
- 404 Not Found: sai URL hoặc tên model. URL nên kết thúc bằng `/v1`; kiểm tra lại tên model.
- 429 Too Many Requests: vượt giới hạn tốc độ. Chờ một lúc rồi thử lại.
- Thiếu biến `LUNOVANT_API_KEY`: mở Codex bằng `codex-setup launch`, hoặc dùng `env install`.

## Sao lưu, khôi phục và gỡ cài đặt

Mỗi thay đổi đều được sao lưu trước, và lần cài đầu tiên còn giữ một bản chụp cấu hình gốc của bạn.

```bash
codex-setup backup list
codex-setup backup restore ID
codex-setup backup original
codex-setup uninstall --dry-run
codex-setup uninstall
```

Gỡ cài đặt sẽ xóa các bảng nhà cung cấp do công cụ tạo, khôi phục `model` / `model_provider` ban đầu của bạn (hoặc xóa chúng), chỉ xóa cài đặt sandbox nếu chính công cụ đã đặt, và chỉ xóa khóa đã lưu khi bạn xác nhận. Công cụ không bao giờ xóa bản sao lưu hay dữ liệu của Codex.

## Quyền riêng tư

- Khóa API chỉ được gửi đến base URL đã cấu hình (mặc định `https://api.lunovant.tech`).
- Không có telemetry, không thu thập dữ liệu sử dụng.
- Khóa không bao giờ xuất hiện trong `config.toml`, log hay tham số dòng lệnh. Thông báo lỗi đã được che khóa.

## Build từ mã nguồn

Cần Python 3.11 trở lên.

```bash
pip install -e ".[dev]"
pytest
python scripts/build.py --smoke
```

File chạy và file `.sha256` được ghi vào thư mục `dist/`. Bản build chỉ dành cho hệ điều hành và kiến trúc hiện tại.

## Ký số (maintainer)

Các job macOS trên CI ký bằng chứng chỉ Developer ID Application và công chứng file chạy khi có secret `MACOS_CERT_P12`. Nếu không có, chúng build bản không ký. Các secret của repository:

- `MACOS_CERT_P12`: base64 của file `.p12` Developer ID Application
- `MACOS_CERT_PASSWORD`: mật khẩu của file `.p12` đó
- `APPLE_API_KEY_P8`: nội dung khóa API App Store Connect (`.p8`)
- `APPLE_API_KEY_ID`: key ID của khóa API đó
- `APPLE_API_ISSUER_ID`: issuer ID của team App Store Connect

Chạy cục bộ: `python scripts/build.py --codesign-identity "<identity>"` (hoặc biến môi trường `MACOS_SIGN_IDENTITY`). Dùng `-` cho chữ ký ad-hoc. Công chứng bằng `scripts/notarize_macos.sh <binary>`.

## Hạn chế đã biết / chưa được xác minh

- Mở ứng dụng Desktop kèm khóa API (`launch app`) là tính năng thử nghiệm. Chưa xác minh được rằng ứng dụng Desktop khởi động theo cách này luôn kế thừa biến môi trường.
- Việc phát hiện Desktop trên Windows có thể bỏ sót bản cài từ Microsoft Store; "not detected" không phải lúc nào cũng có nghĩa là chưa cài.
- File chạy Windows chưa được ký (có cảnh báo SmartScreen). File chạy macOS chỉ được ký và công chứng khi đã cấu hình các secret ký.

## Giấy phép

MIT, xem [LICENSE](LICENSE).
