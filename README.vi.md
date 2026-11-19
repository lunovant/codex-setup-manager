# Codex Setup Manager

[English](README.md) | Tiếng Việt

Codex Setup Manager (`codex-setup`) giúp bạn cấu hình OpenAI Codex (bản CLI và ứng dụng Desktop) để dùng API của Lunovant. Công cụ sửa file `config.toml` của Codex một cách an toàn, lưu khóa API trong kho bí mật của hệ điều hành, kiểm tra kết nối và mở Codex kèm khóa API.

## Bắt đầu nhanh

1. **Tải về**: Tải bản cài đặt phù hợp với máy của bạn trong mục Releases trên GitHub ([xem liên kết tải về bên dưới](#tải-về)).
2. **Mở ứng dụng**: Mở ứng dụng Codex Setup (`Codex Setup.app` trên macOS, hoặc bấm đúp vào `codex-setup-windows-x64.exe` trên Windows).
3. **Dán key**: Dán key Lunovant của bạn vào ô **Dán key Lunovant**.
4. **Bấm "Cài đặt Codex" & mở Codex**: Bấm **Cài đặt Codex**, đợi ứng dụng kiểm tra tự động xong rồi bấm **Mở Codex Desktop** (hoặc mở Codex trong VS Code / terminal) để bắt đầu sử dụng ngay!

## Dùng cùng tài khoản ChatGPT cá nhân

Nếu bạn đã đăng nhập tài khoản ChatGPT cá nhân trong Codex từ trước, Codex Setup Manager cho phép bạn dùng song song cả hai rất thuận tiện:

- **Hai chế độ hoạt động**:
  - **Lunovant**: Mọi nơi (ứng dụng Desktop, extension trong VS Code / Cursor và lệnh `codex`) đều dùng Lunovant làm mặc định.
  - **Tài khoản ChatGPT**: Trả về dùng tài khoản ChatGPT cá nhân làm mặc định ở mọi nơi. Khi cần dùng Lunovant, bạn chỉ cần gõ lệnh `codex -p lunovant` trong terminal.
- **Cách chuyển đổi**:
  - Trên giao diện đồ họa (GUI): Bấm nút gạt chế độ (**Lunovant** / **Tài khoản ChatGPT**) trong ô **Chế độ đang dùng** ở màn hình Cài đặt nhanh.
  - Qua dòng lệnh (CLI): Chạy lệnh `codex-setup mode lunovant` hoặc `codex-setup mode personal`.
  - **Lưu ý**: Sau khi đổi chế độ, hãy khởi động lại ứng dụng Codex Desktop hoặc tải lại cửa sổ VS Code (`⌘⇧P` / `Ctrl+Shift+P` → chọn **Developer: Reload Window**) để thay đổi có hiệu lực.
- **Tách riêng lịch sử chat theo từng chế độ**:
  - Các đoạn chat được Codex lưu riêng biệt cho từng chế độ. Đoạn chat của tài khoản cá nhân và của Lunovant không bị lẫn vào nhau; khi bạn chuyển lại về chế độ cũ, lịch sử chat cũ của chế độ đó sẽ xuất hiện lại.
- **Tính năng đám mây (Cloud task) và tìm kiếm web**:
  - Các tính năng Cloud task và tìm kiếm web của Codex yêu cầu chế độ tài khoản ChatGPT cá nhân.
- **Bảo mật đăng nhập ChatGPT**:
  - Công cụ tuyệt đối không bao giờ đọc, ghi log hay gửi thông tin đăng nhập ChatGPT (`auth.json`) của bạn đi đâu cả. Công cụ chỉ kiểm tra xem file đăng nhập này có tồn tại trên máy hay không để hỗ trợ bạn chuyển đổi chế độ.

## Cách dùng sau khi cài

Sau khi cài đặt xong, bạn có thể dùng Codex ở bất kỳ đâu:

- **Codex Desktop / ứng dụng ChatGPT**:
  - Mở ứng dụng rồi bắt đầu cuộc trò chuyện. Khung chọn model sẽ hiện model mặc định của bạn (ví dụ `gpt-6.1-sol`). Hãy khởi động lại app sau khi đổi chế độ.
- **VS Code / Cursor (extension Codex)**:
  - Mở khung Codex ở thanh bên phải, hoặc bấm `⌘⇧P` (macOS) / `Ctrl+Shift+P` (Windows/Linux) rồi chạy **Codex: Open Codex Sidebar**.
  - Ở chế độ Lunovant, bạn không cần đăng nhập tài khoản ChatGPT—có thể bắt đầu hỏi đáp và viết code ngay lập tức.
  - Hãy tải lại cửa sổ (bấm `⌘⇧P` / `Ctrl+Shift+P` → gõ **Developer: Reload Window**) sau khi đổi chế độ.
- **Terminal (dòng lệnh)**:
  - `codex`: Chạy Codex với chế độ mặc định hiện tại.
  - `codex -p lunovant`: Luôn luôn dùng Lunovant (kể cả khi bạn đang để chế độ tài khoản ChatGPT cá nhân).
  - Ngay trong phiên Codex, bạn có thể gõ `/model` để xem và đổi model đang dùng.
- **Lưu ý**:
  - **Đặt tên chat**: Mỗi khi bạn tạo một chat mới trong app hoặc IDE, Codex sẽ gọi thêm một model nhỏ để tự động đặt tên cho cuộc trò chuyện (chỉ tốn vài phần trăm 💎).
  - **Xem số dư**: Bạn có thể tra cứu số dư 💎 và thông tin gói bất cứ lúc nào tại [https://ai.lunovant.tech/dashboard](https://ai.lunovant.tech/dashboard).

## Công cụ này làm gì

- Thêm nhà cung cấp Lunovant và model mặc định vào `$CODEX_HOME/config.toml` (giữ nguyên các cài đặt và ghi chú khác của bạn).
- Cài đặt nhanh (One-click setup) cấu hình khóa API trong `config.toml` dưới dạng `experimental_bearer_token` (quyền file `0600` trên macOS/Linux) đồng thời lưu vào kho bí mật hệ điều hành (macOS Keychain, Windows Credential Manager hoặc Linux Secret Service).
- Kiểm tra kết nối từng bước (kết nối, khóa, danh sách model, Responses API, streaming).
- Khởi chạy Codex CLI hoặc Desktop trực tiếp hoặc kèm khóa được truyền qua biến môi trường.
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

## Ứng dụng Desktop

Codex Setup Manager có cửa sổ ứng dụng (không cần dùng terminal), khi mở sẽ vào thẳng màn hình **Cài đặt nhanh** (**One-click setup**):

- Dán key Lunovant, rồi bấm **Cài đặt Codex** (**Set up Codex**).
- Ứng dụng kiểm tra key (gói cước, số 💎 còn lại, ngày hết hạn).
- Lấy danh sách các model mà key có quyền sử dụng từ máy chủ.
- Kiểm tra từng model song song (hiển thị ✓ kèm độ trễ hoặc ⚠ kèm lý do lỗi, hỗ trợ thử lại từng model).
- Ghi cấu hình kèm bản sao lưu tự động và chọn model mặc định (`gpt-6.1-sol` nếu chạy tốt).
- Sau khi xong, hiển thị nút **Mở Codex Desktop** (**Open Codex Desktop**), **Mở Codex CLI** (**Open Codex CLI**) và ô chọn model mặc định.

Các tab cài đặt chi tiết trước đây (Model, API & key, Kiểm tra kết nối, Windows Sandbox, Sao lưu & Khôi phục, Chẩn đoán, Mở Codex, Gỡ cài đặt) vẫn được giữ trong mục **Nâng cao** (**Advanced**).

Bản tải cho các hệ điều hành:
- **macOS**: tải `codex-setup-macos-arm64-app.zip` (Apple Silicon) hoặc `codex-setup-macos-x64-app.zip` (Intel), giải nén, kéo **Codex Setup.app** vào Applications rồi mở. Ứng dụng đã được ký và công chứng (notarize).
- **Windows**: bấm đúp vào `codex-setup-windows-x64.exe`. Cần Microsoft Edge WebView2, đã cài sẵn trên Windows 10/11. Nếu thiếu, cài [Evergreen runtime](https://developer.microsoft.com/microsoft-edge/webview2/).
- **Linux**: file `codex-setup-linux-x64` dùng menu văn bản (chưa có cửa sổ app: thư viện GTK chưa build được trên máy build Ubuntu 22.04). Mọi chức năng vẫn có đủ trong menu và các lệnh CLI.

Vẫn dùng được dòng lệnh: `codex-setup <lệnh>`, hoặc `codex-setup --tui` cho menu văn bản.

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

Codex Setup Manager mở thẳng vào màn hình **Cài đặt nhanh** (**One-click setup**):

1. **Dán key**: Dán khóa Lunovant của bạn và bấm **Cài đặt Codex** (**Set up Codex**).
2. **Tự động kiểm tra**: Ứng dụng kiểm tra key (gói cước, số 💎 còn lại, hạn dùng), lấy danh sách model được cấp phép, và kiểm tra từng model song song (hiển thị ✓ kèm độ trễ hoặc ⚠ kèm lý do lỗi, có nút thử lại riêng cho từng model).
3. **Ghi cấu hình**: Cấu hình được ghi an toàn kèm bản sao lưu tự động, tự động chọn `gpt-6.1-sol` làm model mặc định (hoặc model hoạt động đầu tiên).
4. **Mở và sử dụng**: Bấm **Mở Codex Desktop** (**Open Codex Desktop**) hoặc **Mở Codex CLI** (**Open Codex CLI**) để bắt đầu ngay, hoặc chuyển đổi model mặc định từ danh sách chọn.

> Quy trình Cài đặt nhanh từng bước trước đây vẫn tồn tại trong mục **Nâng cao** (**Advanced**) trên giao diện đồ họa hoặc lựa chọn 1 trong menu văn bản (`codex-setup --tui`).

## Tham khảo lệnh

Tùy chọn chung: `--codex-home PATH`, `--lang en|vi`. Các lệnh ghi dữ liệu hỗ trợ `--dry-run` (chỉ xem thay đổi) và `--yes` (bỏ qua bước xác nhận).

| Lệnh | Công dụng |
| --- | --- |
| `status` | Xem cấu hình, nhà cung cấp, model, khóa và trạng thái Codex |
| `setup --auto [--keep-personal] [--base-url URL]` | Cài đặt nhanh tự động (đọc key từ stdin, kiểm tra model, ghi cấu hình). Dùng `--keep-personal` nếu muốn giữ tài khoản ChatGPT làm mặc định |
| `setup [--base-url URL] [--model M] [--key-stdin] [--secret-backend auto\|keyring\|file\|session]` | Cài đặt nhanh (từng bước) |
| `mode [lunovant\|personal]` | Xem hoặc chuyển đổi chế độ mặc định giữa Lunovant và tài khoản ChatGPT cá nhân |
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
# Cài đặt nhanh qua stdin (đọc key từ stdin; không bao giờ truyền key làm tham số)
pbpaste | codex-setup setup --auto

# Cài đặt nhanh nhưng giữ tài khoản ChatGPT cá nhân làm mặc định
pbpaste | codex-setup setup --auto --keep-personal

# Chuyển đổi chế độ mặc định
codex-setup mode lunovant                # chuyển sang mặc định dùng Lunovant
codex-setup mode personal                # chuyển sang mặc định dùng tài khoản ChatGPT cá nhân
codex-setup mode                         # kiểm tra chế độ hiện tại

codex-setup setup --dry-run              # xem trước thay đổi, không ghi gì
codex-setup model gpt-6.1-terra          # đổi model
codex-setup test                         # kiểm tra kết nối
codex-setup sandbox unelevated           # phương án thay thế cho sandbox Windows
codex-setup launch cli                   # mở Codex CLI kèm khóa
codex-setup launch app                   # mở Codex Desktop kèm khóa (thử nghiệm)
echo "sk-..." | codex-setup api --key-stdin
```

Tuyệt đối không truyền khóa API dưới dạng tham số dòng lệnh: khóa sẽ bị lộ vào lịch sử shell và danh sách tiến trình (`ps`). Để tự động hóa, hãy truyền khóa qua stdin: `pbpaste | codex-setup setup --auto` (macOS) hoặc `Get-Clipboard | codex-setup setup --auto` (Windows PowerShell).

## Khóa API được lưu như thế nào

Cài đặt nhanh (One-click setup) ghi trực tiếp khóa API vào `~/.codex/config.toml` (trên Windows là `%USERPROFILE%\.codex\config.toml`) dưới trường `experimental_bearer_token`. Nhờ đó, cả Codex Desktop và bất kỳ terminal mới mở nào đều dùng được ngay mà không cần cấu hình biến môi trường.

- **Phân quyền file**: Trên macOS và Linux, file `config.toml` được ghi với quyền hạn chế nghiêm ngặt `0600` (chỉ chủ sở hữu có quyền đọc/ghi), và các bản sao lưu do công cụ tạo ra cũng giữ nguyên quyền `0600`.
- **Kho khóa hệ điều hành**: Đồng thời, khóa cũng được lưu vào kho khóa của hệ điều hành (macOS Keychain, Windows Credential Manager hoặc Linux Secret Service) nếu khả dụng.
- **Đánh đổi về bảo mật (tradeoff)**: Khóa được lưu dạng văn bản thường (plaintext) bên trong `config.toml`. Mặc dù đã giới hạn quyền chỉ tài khoản người dùng của bạn truy cập (mode `0600`), bất kỳ ứng dụng hoặc tập lệnh nào chạy dưới quyền người dùng của bạn đều có thể đọc được file này.

Nếu không muốn lưu khóa trong `config.toml`, mục **Nâng cao** (**Advanced**) vẫn cung cấp luồng biến môi trường (`env_key = "LUNOVANT_API_KEY"`), khi đó khóa được lưu trong kho khóa hệ điều hành và được đưa vào tiến trình qua `codex-setup launch` hoặc lưu lâu dài bằng `codex-setup env install`.

Khóa không bao giờ được ghi ra log hay nhận qua tham số dòng lệnh.

## config.toml sau khi cấu hình

Khi ở **chế độ Lunovant**:

```toml
model = "gpt-6.1-sol"
model_provider = "lunovant"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
wire_api = "responses"
experimental_bearer_token = "sk-…"
```

Khi ở **chế độ tài khoản ChatGPT**:

Dòng `model_provider` ở cấp cao nhất sẽ không có (hoặc được hoàn trả về cài đặt cá nhân của bạn), trong khi phần cấu hình `[model_providers.lunovant]` vẫn được giữ lại:

```toml
model = "gpt-6.1-sol"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
wire_api = "responses"
experimental_bearer_token = "sk-…"
```

### File profile (`lunovant.config.toml`)

Bên cạnh `config.toml`, Codex Setup Manager còn tạo file `$CODEX_HOME/lunovant.config.toml` để lệnh `codex -p lunovant` luôn luôn hoạt động trong cả 2 chế độ:

```toml
# Managed by Codex Setup Manager: use with  codex -p lunovant
model_provider = "lunovant"
model = "gpt-6.1-sol"
```

> **Lưu ý về dòng `profile = "..."` cũ**: Các phiên bản Codex mới sẽ từ chối khởi động nếu trong `config.toml` còn dòng `profile = "..."` ở cấp cao nhất. Codex Setup Manager sẽ tự động phát hiện và xoá bỏ thiết lập `profile = "..."` cũ này để Codex khởi động bình thường, đồng thời vẫn giữ nguyên các bảng `[profiles.*]` (Codex bản mới sẽ tự động bỏ qua chúng).

Các file cấu hình nằm ở `~/.codex/` (trên Windows là `%USERPROFILE%\.codex\`), hoặc trong thư mục `CODEX_HOME` nếu bạn có đặt. Trên macOS và Linux, file `config.toml` được tạo với quyền `0600`. Các id nhà cung cấp dựng sẵn `openai`, `ollama`, `lmstudio`, `amazon-bedrock` và `gcp` được dành riêng; công cụ không bao giờ ghi bảng cho các id này.

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
- Khóa không bao giờ xuất hiện trong log hay tham số dòng lệnh. Trong `config.toml`, khóa được bảo vệ bằng quyền file chỉ người dùng sở hữu (`0600`). Thông báo lỗi đều được che khóa tự động.

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
