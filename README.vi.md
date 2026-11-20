# Lunovant Setup

[English](README.md) | Tiếng Việt

Lunovant Setup (`lunovant-setup`) là công cụ cài đặt tất cả-trong-một giúp bạn kết nối **OpenAI Codex** và **Claude Code** với hệ thống API của Lunovant một cách dễ dàng và an toàn. Công cụ tự động lưu trữ cấu hình, bảo mật khóa API, kiểm tra kết nối model và cho phép bạn dùng song song với các tài khoản cá nhân có sẵn.

Ứng dụng tự động nhận diện loại key bạn nhập vào:
- **Key Orion**: Cài đặt cho OpenAI Codex (cả bản dòng lệnh CLI và app Desktop).
- **Key Lyra**: Cài đặt cho Claude Code (cả trong terminal và extension trên VS Code / Cursor).
- **Key kết hợp (có cả hai dòng)**: Tự động cài đặt đồng thời cả Codex và Claude Code chỉ với 1 cú click chuột!

*(Nâng cấp: nếu bạn từng dùng app "Codex Setup" cũ, có thể xóa nó sau khi cài "Lunovant Setup.app". Cài đặt và key đã lưu vẫn được giữ nguyên. Lệnh `codex-setup` cũ vẫn dùng được như một tên gọi khác.)*

---

## Bắt đầu nhanh (4 bước đơn giản)

1. **Tải về**: Tải bản cài đặt phù hợp với hệ điều hành máy tính của bạn trong mục Releases trên GitHub ([xem liên kết tải về bên dưới](#tải-về)).
2. **Mở ứng dụng**: Mở Lunovant Setup (`Lunovant Setup.app` trên macOS, hoặc bấm đúp vào `lunovant-setup-windows-x64.exe` trên Windows).
   > **Lưu ý cho người dùng Windows**: Ở lần mở đầu tiên, tính năng SmartScreen của Windows sẽ hiện thông báo **"Windows protected your PC"** (do file chạy chưa được đăng ký chứng chỉ số). Bạn chỉ cần bấm vào chữ **More info**, sau đó chọn **Run anyway**. Ứng dụng hoàn toàn không yêu cầu quyền quản trị viên (Administrator).
3. **Dán key**: Dán key Lunovant của bạn (key Orion, Lyra hoặc combo) vào ô **Dán key Lunovant**.
4. **Bấm "Cài đặt" & bắt đầu dùng**: Bấm nút **Cài đặt** (**Install**). Ứng dụng sẽ tự động kiểm tra key, nhận diện gói sản phẩm, kiểm tra các model đang chạy tốt và ghi cấu hình an toàn kèm bản sao lưu tự động. Sau khi hoàn tất, bạn có thể bắt đầu sử dụng ngay (mở Codex Desktop/CLI, hoặc gõ lệnh `claude` trong terminal hay mở trong VS Code/Cursor)!

---

## Claude Code

Lunovant Setup hỗ trợ đầy đủ và tối ưu nhất cho Claude Code (trên cả dòng lệnh terminal và extension VS Code / Cursor).

### Những gì được ghi vào máy

- **File cấu hình chính**: Ứng dụng cập nhật file `~/.claude/settings.json` (trên Windows là `%USERPROFILE%\.claude\settings.json`).
- **Các biến môi trường**: Ghi vào mục `"env"` các giá trị sau:
  - `ANTHROPIC_BASE_URL`: Địa chỉ máy chủ Lunovant (`https://api.lunovant.tech`)
  - `ANTHROPIC_AUTH_TOKEN`: Key API Lunovant của bạn
  - `ANTHROPIC_DEFAULT_OPUS_MODEL`: Mã model Opus 5.5 (`claude-opus-5-5`)
  - `ANTHROPIC_DEFAULT_SONNET_MODEL`: Mã model Sonnet 5.5 (`claude-sonnet-5-5`)
  - `ANTHROPIC_DEFAULT_HAIKU_MODEL`: Mã model Haiku 5.5 (`claude-haiku-5-5`)
- **Model mặc định**: chỉ đặt `"model": "opus"` ở cấp cao nhất khi `settings.json` chưa có `model` (gỡ cài đặt sẽ xóa nếu vẫn là `"opus"`). Không ghi `ANTHROPIC_MODEL`, nên `/model sonnet` / `/model haiku` được nhớ cho các lần mở sau. Bản cài cũ được tự động chuyển đổi.
- **Giữ nguyên các cài đặt khác**: Mọi thiết lập riêng hoặc tùy chỉnh cá nhân trước đây của bạn trong file `settings.json` (nằm ngoài các biến mà công cụ quản lý) đều được giữ nguyên 100%.
- **Tự động sao lưu**: File `settings.json` luôn được sao lưu tự động trước khi ghi bất kỳ thay đổi nào.
- **File cấu hình riêng (`~/.claude/lunovant-settings.json`)**: Được tạo với quyền bảo mật nghiêm ngặt `0600` (chỉ tài khoản của bạn đọc/ghi được). Nhờ file này, bạn luôn có thể gọi Lunovant bất cứ lúc nào bằng lệnh: `claude --settings ~/.claude/lunovant-settings.json`.

### 3 model được kiểm tra & cách tiết kiệm 💎

Lunovant Setup cấu hình sẵn 3 model chuẩn nhất của dòng họ Claude:
- **Opus 5.5** (`claude-opus-5-5`, mặc định): Model thông minh và mạnh mẽ nhất, phù hợp cho các bài toán kiến trúc phức tạp và viết code chuyên sâu.
- **Sonnet 5.5** (`claude-sonnet-5-5`): Cân bằng hoàn hảo giữa tốc độ và trí thông minh, rất thích hợp cho công việc lập trình hàng ngày.
- **Haiku 5.5** (`claude-haiku-5-5`): Cực kỳ nhanh và nhẹ, thích hợp để sửa lỗi nhỏ, viết tài liệu hoặc các tác vụ nhanh gọn.

**Vì sao chỉ kiểm tra 3 model này?** Mỗi lần thử gọi model để kiểm tra đều làm tiêu hao tài nguyên. Để giúp bạn **tiết kiệm số dư 💎**, Lunovant Setup chỉ kiểm tra đúng 3 model sẽ được thiết lập thay vì gọi toàn bộ danh sách model có trên máy chủ.

### Cách dùng Claude Code sau khi cài

- **Dùng trong Terminal**:
  - `claude`: Mở Claude Code với chế độ mặc định hiện tại.
  - `claude --settings ~/.claude/lunovant-settings.json`: Luôn luôn chạy Claude Code qua Lunovant (dùng được ở mọi chế độ).
- **Tiết kiệm 💎 ngay trong phiên làm việc**:
  - Khi đang trò chuyện trong Claude Code, bạn có thể gõ lệnh `/model sonnet` hoặc `/model haiku` để đổi sang model nhẹ hơn, giúp tiết kiệm tối đa 💎.
- **Dùng trên VS Code / Cursor (extension Claude Code)**:
  - Extension chính thức của Claude Code dùng chung file cấu hình `settings.json` nói trên, nên bạn không cần phải cấu hình thêm bất kỳ bước nào!
  - Chỉ cần tải lại cửa sổ IDE (bấm `⌘⇧P` trên Mac hoặc `Ctrl+Shift+P` trên Windows → chọn **Developer: Reload Window**) sau khi đổi chế độ.
- **Lưu ý về app Claude trên máy tính**:
  - Ứng dụng chat Claude Desktop (app cửa sổ thông thường của Anthropic) **không thể** dùng qua Lunovant; chỉ có **Claude Code** (bản terminal và extension IDE) mới dùng được.

### Dùng song song với tài khoản Claude cá nhân (Pro/Max)

Nếu bạn đã đăng nhập tài khoản Claude cá nhân từ trước trên máy, Lunovant Setup cho phép chuyển đổi rất tiện lợi:
- **Hai chế độ hoạt động**:
  - **Lunovant**: Terminal `claude` và extension trong VS Code/Cursor mặc định dùng Lunovant.
  - **Tài khoản Claude (cá nhân)**: Mặc định quay về dùng gói cá nhân của bạn. Khi cần dùng Lunovant, bạn chỉ cần gõ `claude --settings ~/.claude/lunovant-settings.json`.
- **Cách chuyển chế độ**:
  - Trên giao diện đồ họa: Bấm nút chuyển đổi chế độ ở mục Claude Code.
  - Qua dòng lệnh CLI: Chạy `lunovant-setup mode lunovant --line claude` hoặc `lunovant-setup mode personal --line claude`.
  - Khởi động lại terminal hoặc reload cửa sổ IDE sau khi chuyển.
- **Cam kết quyền riêng tư**:
  - Ứng dụng chỉ kiểm tra xem trên máy đã có đăng nhập hay chưa (bằng cách kiểm tra sự hiện diện của trường `oauthAccount` trong file `~/.claude.json`). Công cụ **tuyệt đối không bao giờ** đọc, lưu trữ, ghi log hay gửi mật khẩu, token hay tài khoản cá nhân của bạn từ file `.credentials.json` hay kho khóa hệ điều hành đi đâu cả.

---

## OpenAI Codex

Lunovant Setup cấu hình OpenAI Codex (bản CLI và app Desktop) để sử dụng với API Lunovant.

### Dùng cùng tài khoản ChatGPT cá nhân

Nếu bạn đã đăng nhập tài khoản ChatGPT cá nhân trong Codex từ trước:
- **Hai chế độ hoạt động**:
  - **Lunovant**: Mọi nơi (app Codex Desktop, extension VS Code/Cursor và lệnh `codex`) đều dùng Lunovant làm mặc định.
  - **Tài khoản ChatGPT**: Trả về dùng tài khoản ChatGPT cá nhân làm mặc định. Khi cần dùng Lunovant, bạn gõ lệnh `codex -p lunovant` trong terminal.
- **Cách chuyển đổi**:
  - Trên giao diện đồ họa: Bấm nút chuyển chế độ (**Lunovant** / **Tài khoản ChatGPT**) trong ô **Chế độ đang dùng**.
  - Qua dòng lệnh CLI: Chạy `lunovant-setup mode lunovant --line codex` hoặc `lunovant-setup mode personal --line codex`.
  - Khởi động lại app Codex Desktop hoặc tải lại cửa sổ VS Code (`⌘⇧P` / `Ctrl+Shift+P` → **Developer: Reload Window**) sau khi chuyển chế độ.
- **Tách riêng lịch sử trò chuyện**:
  - Lịch sử chat được lưu riêng cho từng chế độ. Cuộc trò chuyện cá nhân và Lunovant không bị trộn lẫn; khi bạn chuyển lại về chế độ cũ, lịch sử tương ứng sẽ xuất hiện lại đầy đủ.
- **Tính năng đám mây (Cloud task) và tìm kiếm web**:
  - Các tính năng này của Codex yêu cầu bạn chuyển sang chế độ tài khoản ChatGPT cá nhân.
- **Bảo mật đăng nhập ChatGPT**:
  - Ứng dụng không bao giờ đọc, ghi log hay gửi thông tin đăng nhập ChatGPT (`auth.json`) của bạn. Ứng dụng chỉ kiểm tra xem file đăng nhập có tồn tại trên máy hay không để hỗ trợ chuyển chế độ.

### Cách dùng Codex sau khi cài

- **Codex Desktop / ứng dụng ChatGPT**:
  - Mở app và bắt đầu chat. Danh sách model sẽ hiện model mặc định của bạn (ví dụ `gpt-6.1-sol`). Hãy khởi động lại app sau khi đổi chế độ.
- **VS Code / Cursor (extension Codex)**:
  - Mở khung Codex ở thanh bên phải, hoặc bấm `⌘⇧P` / `Ctrl+Shift+P` rồi chạy **Codex: Open Codex Sidebar**.
  - Ở chế độ Lunovant, bạn không cần đăng nhập tài khoản ChatGPT—có thể bắt đầu hỏi đáp và code ngay lập tức.
  - Tải lại cửa sổ (bấm `⌘⇧P` / `Ctrl+Shift+P` → gõ **Developer: Reload Window**) sau khi đổi chế độ.
- **Terminal (dòng lệnh)**:
  - `codex`: Chạy Codex với chế độ mặc định hiện tại.
  - `codex -p lunovant`: Luôn dùng Lunovant (kể cả khi bạn đang để chế độ tài khoản ChatGPT cá nhân).
  - Gõ `/model` trong phiên làm việc để xem và đổi model đang dùng.
- **Lưu ý hữu ích**:
  - **Tự động đặt tên chat**: Mỗi lần tạo chat mới trong app hoặc IDE, Codex sẽ gọi một model nhỏ để tự động tạo tiêu đề cuộc trò chuyện (chỉ tốn khoảng vài phần trăm 💎).
  - **Kiểm tra số dư**: Bạn có thể tra cứu số dư 💎 và thông tin gói dịch vụ bất kỳ lúc nào tại [https://ai.lunovant.tech/dashboard](https://ai.lunovant.tech/dashboard).

### Dùng trong IDE

Phím tắt ghi theo macOS; trên Windows và Linux dùng `Ctrl`/`Alt` thay cho `⌘`/`⌥`.

- **Codex**:
  - **VS Code**: mở khung Codex như hướng dẫn ở trên.
  - **Cursor**: cài extension "Codex" (publisher OpenAI), rồi `⌘⇧P` → **Open Codex Sidebar** (thanh bên phải; `⌥⌘B` để hiện/ẩn). Khung chat / "New Agent" riêng của Cursor là AI của Cursor và không dùng 💎 Lunovant. Nếu Cursor mở cửa sổ "Agents", bấm **IDE ↗** để quay lại editor. Reload Window sau khi đổi chế độ.
  - **JetBrains** (IntelliJ IDEA, Android Studio, PyCharm, WebStorm…): các agent trong AI Assistant không dùng Lunovant. Mở tab Terminal của IDE trong dự án và chạy `codex`.
  - **Xcode**: các coding agent tích hợp sẵn chưa được hỗ trợ. Mở Terminal tại thư mục dự án và chạy `codex`.
- **Claude Code**:
  - **VS Code**: cài extension Claude Code; không cần cấu hình thêm.
  - **Cursor**: cài extension "Claude Code" (publisher Anthropic); mở bằng biểu tượng ✻ ở góc trên bên phải editor hoặc "✻ Claude Code" ở thanh trạng thái. Lưu ý tương tự về khung chat / cửa sổ Agents của Cursor; Reload Window sau khi đổi chế độ.
  - **JetBrains**: Settings → Plugins → Marketplace → cài "Claude Code [Beta]", khởi động lại IDE, rồi bấm biểu tượng Claude trên thanh công cụ. Nếu báo "Cannot launch Claude Code", vào Settings → Tools → Claude Code [Beta] → "Claude command" và dán kết quả của `which claude` (macOS/Linux) hoặc `where claude` (Windows); khung "Cách dùng" trong ứng dụng cũng hiện sẵn đường dẫn này. "Claude Agent" tích hợp sẵn trong AI Assistant không dùng Lunovant.
  - **Xcode**: chưa hỗ trợ; chạy `claude` trong Terminal tại thư mục dự án.

### Công cụ làm gì cho Codex

- Thêm nhà cung cấp Lunovant và model mặc định vào `$CODEX_HOME/config.toml` (giữ nguyên các cấu hình khác của bạn).
- Cài đặt nhanh ghi key API vào `config.toml` dưới dạng `experimental_bearer_token` (quyền file `0600` trên macOS/Linux) và lưu vào kho bảo mật của hệ điều hành (macOS Keychain, Windows Credential Manager hoặc Linux Secret Service).
- Tự động tạo `$CODEX_HOME/lunovant.config.toml` để lệnh `codex -p lunovant` luôn chạy được ở bất kỳ chế độ nào.
- Kiểm tra kết nối mạng, key, danh sách model và khả năng phản hồi streaming.
- Tự động xử lý lỗi sandbox thường gặp trên Windows.
- Sao lưu cấu hình trước khi sửa đổi, dễ dàng khôi phục lại ban đầu.

Các model Codex: `gpt-6.1-sol` (mặc định), `gpt-6.1-terra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`.
Base URL: `https://api.lunovant.tech`. API endpoint: `https://api.lunovant.tech/v1`.

---

### Danh sách model trong Codex

- Danh sách chọn model của Codex hiển thị đúng các model Lunovant đang bán (file danh mục `lunovant-models.json` trong `$CODEX_HOME`; Codex không bao giờ hỏi nhà cung cấp danh sách model).
- Mở ứng dụng sẽ tự làm mới danh sách: model mới xuất hiện, còn danh sách mà Codex bản mới không đọc được sẽ tự động bị gỡ. Dòng lệnh làm tương tự bằng `lunovant-setup refresh-catalog` (cũng chạy trước `status` / `mode`; `--offline` bỏ qua mạng và giữ danh sách đã biết gần nhất).
- Nếu Codex báo lỗi `failed to parse model_catalog_json ...`, hãy mở Lunovant Setup (app tự làm mới hoặc gỡ danh sách không hợp lệ) hoặc chạy `lunovant-setup refresh-catalog`.

## Hệ điều hành hỗ trợ

| Hệ điều hành | Kiến trúc | Codex CLI / Desktop | Claude Code (CLI / IDE) | Ứng dụng Lunovant Setup |
| --- | --- | --- | --- | --- |
| Windows 10 / 11 | x64 | Có / Có | Có / Có | Cửa sổ đồ họa (.exe) |
| macOS (Apple Silicon) | arm64 | Có / Có | Có / Có | Cửa sổ đồ họa (.app) |
| macOS (Intel) | x64 | Có / Chỉ CLI | Có / Có | Cửa sổ đồ họa (.app) |
| Ubuntu 24.04 | x64 | Có / Bản preview | Có / Có | Menu giao diện văn bản (TUI / CLI) |
| Ubuntu 22.04 | x64 | Có / Chỉ CLI | Có / Có | Menu giao diện văn bản (TUI / CLI) |

Lunovant Setup không cài sẵn Codex hoặc Claude Code vào máy bạn; bạn cần cài đặt chúng riêng biệt.

---

## Giao diện đồ họa ứng dụng

Lunovant Setup có giao diện trực quan, thân thiện (không cần mở cửa sổ dòng lệnh đen xì), tự động mở thẳng vào tab **Cài đặt nhanh** (**One-click setup**):

- Dán key Lunovant của bạn, rồi bấm **Cài đặt** (**Install**).
- Ứng dụng kiểm tra tính hợp lệ của key (gói cước, số 💎 còn lại, hạn dùng).
- Ứng dụng tự động phát hiện loại sản phẩm theo quyền của key:
  - Nếu key có model `gpt-*` → cấu hình cho Codex.
  - Nếu key có model `claude-*` → cấu hình cho Claude Code.
  - Nếu key có cả hai → tự động cài đặt cả hai dòng sản phẩm.
- Kiểm tra các model song song, hiển thị dấu tích xanh ✓ và độ trễ hoặc cảnh báo ⚠ nếu có lỗi.
- Ghi cấu hình tự động và tạo bản sao lưu an toàn.
- Cung cấp sẵn các nút mở nhanh tiện lợi (**Mở Codex Desktop**, **Mở Codex CLI**, hoặc **Mở Terminal với Claude Code**) cùng thanh chọn đổi model mặc định.

Các chức năng cấu hình chuyên sâu trước đây cho Codex (Model, API & key, Kiểm tra kết nối, Windows Sandbox, Sao lưu & Khôi phục, Chẩn đoán, Gỡ cài đặt) vẫn được giữ đầy đủ tại mục **Codex nâng cao** (**Codex advanced**).

---

## Tải về

1. Truy cập mục [Releases trên GitHub](https://github.com/lunovant/lunovant-setup/releases) và tải file tương ứng với máy của bạn:
   - `lunovant-setup-windows-x64.exe` (cho Windows)
   - `lunovant-setup-macos-arm64-app.zip` (cho Mac chip Apple Silicon)
   - `lunovant-setup-macos-x64-app.zip` (cho Mac chip Intel)
   - `lunovant-setup-macos-arm64` / `lunovant-setup-macos-x64` (bản dòng lệnh Mac)
   - `lunovant-setup-linux-x64` (bản dòng lệnh Linux)
2. Tải thêm file `.sha256` tương ứng để kiểm tra tính toàn vẹn của file:
   - macOS: `shasum -a 256 lunovant-setup-macos-arm64`
   - Linux: `sha256sum lunovant-setup-linux-x64`
   - Windows (PowerShell): `Get-FileHash .\lunovant-setup-windows-x64.exe -Algorithm SHA256`

---

## Hướng dẫn mở ứng dụng lần đầu

### Windows

Bấm đúp vào file `lunovant-setup-windows-x64.exe`.
Vì file chạy chưa được ký chứng chỉ số đắt tiền của Microsoft, màn hình SmartScreen sẽ hiện thông báo màu xanh:
> **"Windows protected your PC"**

Bạn chỉ cần bấm vào **More info**, sau đó chọn **Run anyway**. Ứng dụng sẽ mở ngay lập tức mà không đòi hỏi quyền quản trị viên.
*(Yêu cầu máy có sẵn Microsoft Edge WebView2, vốn đã cài sẵn trên hầu hết các máy Windows 10 và 11).*

### macOS

Tải file `lunovant-setup-macos-arm64-app.zip` (hoặc bản `x64`), giải nén và kéo file **Lunovant Setup.app** vào thư mục `Applications` (Ứng dụng).

Nếu dùng bản CLI độc lập trong Terminal:
```bash
chmod +x ./lunovant-setup-macos-arm64
./lunovant-setup-macos-arm64
```

Nếu Gatekeeper trên Mac chặn file dòng lệnh:
```bash
chmod +x ./lunovant-setup-macos-arm64
xattr -d com.apple.quarantine ./lunovant-setup-macos-arm64 2>/dev/null; ./lunovant-setup-macos-arm64
```
Hoặc trong Finder, bấm chuột phải vào file, chọn **Open**, rồi bấm xác nhận **Open**.

### Linux

```bash
chmod +x ./lunovant-setup-linux-x64
./lunovant-setup-linux-x64
```

---

## Bảng tra cứu lệnh CLI

Các tùy chọn chung: `--codex-home PATH`, `--lang en|vi`. Các lệnh ghi cấu hình hỗ trợ `--dry-run` (chỉ xem thử thay đổi) và `--yes` (bỏ qua hỏi xác nhận).

| Lệnh | Công dụng |
| --- | --- |
| `status` | Xem thông tin cấu hình, model, khóa API và trạng thái |
| `setup --auto [--keep-personal] [--base-url URL]` | Cài đặt tự động một chạm cho Codex và/hoặc Claude Code (đọc key từ stdin). Thêm `--keep-personal` nếu muốn giữ tài khoản cá nhân làm mặc định |
| `setup [--base-url URL] [--model M] [--key-stdin] [--secret-backend auto\|keyring\|file\|session]` | Cài đặt Codex từng bước thủ công |
| `mode [lunovant\|personal] [--line codex\|claude]` | Xem hoặc chuyển đổi chế độ mặc định giữa Lunovant và tài khoản cá nhân cho Codex, Claude Code hoặc cả hai |
| `model [NAME]` | Xem hoặc đổi model mặc định của Codex |
| `api [--base-url URL] [--key-stdin \| --delete-key]` | Đổi base URL hoặc khóa, hoặc xóa khóa đã lưu của Codex |
| `test [--model M]` | Kiểm tra kết nối API của Codex |
| `sandbox [elevated\|unelevated\|remove]` | Cấu hình chế độ sandbox Windows cho Codex |
| `backup create\|list\|restore ID\|original` | Quản lý các bản sao lưu cấu hình |
| `diagnose [--text TEXT]` | Tự động chẩn đoán sự cố hoặc giải thích thông báo lỗi |
| `profile list\|add\|use\|remove` | Quản lý các cấu hình profile Codex |
| `launch [cli\|app] [-- codex args...]` | Mở Codex kèm key được đưa vào biến môi trường |
| `env install\|remove` | Lưu khóa thành biến môi trường lâu dài (tùy chọn) |
| `uninstall` | Gỡ bỏ toàn bộ cấu hình do công cụ tạo |
| `--version` | Xem phiên bản của công cụ |

### Ví dụ thao tác CLI

```bash
# Cài đặt tự động một chạm qua stdin (không bao giờ truyền key dưới dạng tham số dòng lệnh)
pbpaste | lunovant-setup setup --auto

# Cài đặt tự động nhưng giữ tài khoản cá nhân làm mặc định
pbpaste | lunovant-setup setup --auto --keep-personal

# Chuyển đổi chế độ cho toàn bộ các dòng sản phẩm
lunovant-setup mode lunovant
lunovant-setup mode personal

# Chuyển đổi chế độ riêng cho từng sản phẩm
lunovant-setup mode lunovant --line claude    # Chỉ đổi cho Claude Code
lunovant-setup mode lunovant --line codex     # Chỉ đổi cho Codex
lunovant-setup mode                          # Xem chế độ hiện tại

# Tiện ích cho Codex
lunovant-setup model gpt-6.1-terra
lunovant-setup test
lunovant-setup sandbox unelevated
```

> **Mẹo bảo mật**: Tuyệt đối không truyền khóa API trực tiếp làm tham số dòng lệnh (như `-k` hay `--key`), vì khóa sẽ bị lưu vào lịch sử gõ lệnh của máy và danh sách tiến trình (`ps`). Hãy truyền qua stdin như hướng dẫn: `pbpaste | lunovant-setup setup --auto` (trên macOS) hoặc `Get-Clipboard | lunovant-setup setup --auto` (trên PowerShell Windows).

---

## Chi tiết các file cấu hình được tạo

### Claude Code

**`~/.claude/settings.json`** (ở chế độ Lunovant):
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.lunovant.tech",
    "ANTHROPIC_AUTH_TOKEN": "sk-...",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5-5",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-5-5"
  },
  "model": "opus"
}
```

**`~/.claude/lunovant-settings.json`** (file profile cố định, phân quyền `0600`):
Lưu sẵn khối `env` ở trên, giúp bạn dùng được lệnh `claude --settings ~/.claude/lunovant-settings.json` trong mọi trường hợp.

### OpenAI Codex

**`~/.codex/config.toml`** (ở chế độ Lunovant):
```toml
model = "gpt-6.1-sol"
model_provider = "lunovant"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
wire_api = "responses"
experimental_bearer_token = "sk-..."
```

**`~/.codex/lunovant.config.toml`** (file profile cố định):
```toml
# Managed by Lunovant Setup: use with codex -p lunovant
model_provider = "lunovant"
model = "gpt-6.1-sol"
```

---

## Sandbox trên Windows (cho Codex)

Codex trên Windows chạy các lệnh thực thi trong môi trường sandbox với hai chế độ:
- `elevated`: Cần một lần cấp quyền quản trị viên khi cài đặt.
- `unelevated`: Chạy với quyền hạn chế của chính tài khoản người dùng bình thường, không cần quyền quản trị viên.

Nếu gặp lỗi sandbox ("Couldn't check Windows setup" hoặc "Unable to send message"), hãy chuyển sang chế độ `unelevated`:
```cmd
lunovant-setup sandbox unelevated
```

Nếu muốn quay lại mặc định ban đầu của Codex: `lunovant-setup sandbox remove`.

---

## Xử lý sự cố thường gặp

Hãy chạy `lunovant-setup test` và `lunovant-setup diagnose` đầu tiên khi gặp lỗi.

- **401 Unauthorized**: Key không chính xác, đã hết hạn hoặc bị dán thiếu ký tự. Hãy kiểm tra lại key của bạn.
- **403 Forbidden**: Gói dịch vụ của key không có quyền truy cập model này. Hãy kiểm tra lại gói của bạn tại trang quản lý Lunovant.
- **404 Not Found**: Sai địa chỉ URL hoặc sai tên model.
- **429 Too Many Requests**: Đã vượt quá giới hạn tốc độ gọi. Hãy đợi một chút rồi thử lại.
- **App chat Claude trên máy tính không dùng được Lunovant**: Ứng dụng chat desktop của Claude không hỗ trợ chuyển máy chủ; hãy dùng Claude Code trong terminal (`claude`) hoặc extension trong VS Code / Cursor.

---

## Sao lưu, khôi phục và gỡ cài đặt

Mọi thao tác thay đổi cấu hình đều được tự động tạo bản sao lưu trước:
```bash
lunovant-setup backup list
lunovant-setup backup restore ID
lunovant-setup backup original
lunovant-setup uninstall --dry-run
lunovant-setup uninstall
```

Lệnh gỡ cài đặt (`uninstall`) sẽ đưa các file cấu hình về trạng thái ban đầu, gỡ bỏ cài đặt Lunovant và chỉ xóa key khi bạn xác nhận. Tuyệt đối không xóa dữ liệu trò chuyện của bạn.

---

## Cam kết quyền riêng tư

- Khóa API chỉ được gửi duy nhất đến địa chỉ máy chủ Lunovant (`https://api.lunovant.tech`).
- Tuyệt đối không thu thập dữ liệu người dùng (no telemetry, no analytics).
- Thông tin đăng nhập cá nhân của ChatGPT (`auth.json`) và Claude (`.credentials.json`, kho khóa) **không bao giờ** bị đọc, gửi đi hay ghi log. Ứng dụng chỉ kiểm tra xem file đăng nhập có tồn tại hay không để phục vụ tính năng chuyển chế độ.
- Mọi khóa API và dữ liệu nhạy cảm đều được tự động ẩn (che sao `****`) khi hiển thị trên màn hình dòng lệnh.

---

## Tự build từ mã nguồn

Yêu cầu máy cài Python 3.11 trở lên.

```bash
pip install -e ".[dev]"
pytest
python scripts/build.py --smoke
```

---

## Giấy phép mã nguồn

Phát hành theo giấy phép mã nguồn mở MIT, xem chi tiết tại [LICENSE](LICENSE).
