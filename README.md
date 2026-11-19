# Codex Setup Manager

English | [Tiếng Việt](README.vi.md)

Codex Setup Manager (`codex-setup`) configures OpenAI Codex (CLI and Desktop app) to use the Lunovant API. It edits your Codex `config.toml` safely, stores your API key in the operating system's secret store, tests the connection, and launches Codex with the key available.

## Quick start

1. **Download**: Download the release package for your operating system from GitHub Releases ([see links below](#download)).
2. **Open app**: Launch Codex Setup (`Codex Setup.app` on macOS, or double-click `codex-setup-windows-x64.exe` on Windows).
3. **Paste key**: Paste your Lunovant API key into the **Paste your Lunovant key** field.
4. **Click "Set up Codex" & open Codex**: Click **Set up Codex** (**Cài đặt Codex**), wait for the automated verification to complete, then click **Open Codex Desktop** (or open Codex in VS Code / terminal) to start working!

## Using it alongside your own ChatGPT account

If you already use a personal ChatGPT account with Codex, Codex Setup Manager lets you use both side-by-side seamlessly:

- **Two operational modes**:
  - **Lunovant**: Everything (Codex Desktop app, VS Code / Cursor extensions, and the `codex` command) uses Lunovant by default.
  - **ChatGPT account**: Everything defaults to your personal ChatGPT account. Lunovant remains accessible anytime via `codex -p lunovant` in the terminal.
- **How to switch**:
  - In the GUI: Click the mode toggle (**Lunovant** / **ChatGPT account**) in the **Current mode** card on the One-click setup screen.
  - In the CLI: Run `codex-setup mode lunovant` or `codex-setup mode personal`.
  - **Important**: After switching modes, restart the Codex Desktop app or reload VS Code (`⌘⇧P` / `Ctrl+Shift+P` → **Developer: Reload Window**) for the changes to take effect.
- **Separate chat histories**:
  - Session history is separated by mode in Codex. Your personal ChatGPT conversations and Lunovant conversations do not mix; when you switch back to a mode, your previous chat threads in that mode reappear.
- **Cloud tasks and web search**:
  - Codex cloud tasks and web search require ChatGPT account mode.
- **Privacy regarding your ChatGPT login**:
  - The tool never reads, logs, or transmits your ChatGPT login credentials (`auth.json`). It only checks whether a login file exists on your computer to allow switching modes.

## How to use after setup

After setup, you can use Codex across any environment:

- **Codex Desktop / ChatGPT app**:
  - Open the app and start chatting. The model picker will show your default model (e.g. `gpt-6.1-sol`). Restart the app after switching modes.
- **VS Code / Cursor (Codex extension)**:
  - Open the Codex panel in the right sidebar, or press `⌘⇧P` (macOS) / `Ctrl+Shift+P` (Windows/Linux) and run **Codex: Open Codex Sidebar**.
  - In Lunovant mode, you do not need to sign in with a ChatGPT account—start coding and asking questions immediately.
  - Reload the IDE window (**Developer: Reload Window**) after switching modes.
- **Terminal (CLI)**:
  - `codex`: Runs Codex using your current default mode.
  - `codex -p lunovant`: Always runs Codex with Lunovant (even when in ChatGPT personal mode).
  - Inside Codex, type `/model` to view available models or switch models on the fly.
- **Good to know**:
  - **Chat titling**: Each new chat thread in the app or IDE makes an extra call to a lightweight model to automatically generate a conversation title (costing just a few hundredths of a 💎).
  - **Check balance**: Check your remaining 💎 balance and plan details anytime at [https://ai.lunovant.tech/dashboard](https://ai.lunovant.tech/dashboard).

## What it does

- Adds a Lunovant provider and a default model to `$CODEX_HOME/config.toml` (keeps your other settings and comments).
- One-click setup configures the API key in `config.toml` as `experimental_bearer_token` (file mode `0600` on macOS/Linux) and keeps it in the OS secret store (macOS Keychain, Windows Credential Manager or Linux Secret Service).
- Tests the connection step by step (reachability, key, model list, Responses API, streaming).
- Launches Codex CLI or Desktop directly or with the key injected.
- Fixes common Windows sandbox errors.
- Backs up the config before every change, and can restore or fully undo everything.
- Interface in English and Vietnamese (`--lang en|vi`).

Models: `gpt-6.1-sol` (default), `gpt-6.1-terra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`.
Base URL: `https://api.lunovant.tech`. API endpoint: `https://api.lunovant.tech/v1`.

## Supported systems

| OS | Architecture | Codex CLI | Codex Desktop app |
| --- | --- | --- | --- |
| Windows 10 / 11 | x64 | Yes | Yes |
| macOS (Apple Silicon) | arm64 | Yes | Yes |
| macOS (Intel) | x64 | Yes | The documented Desktop download is for Apple Silicon; on Intel use the CLI |
| Ubuntu 24.04 | x64 | Yes | Linux app is a preview |
| Ubuntu 22.04 | x64 | Yes | No official Desktop app; use the CLI |

The Linux Desktop app is a preview, available for Ubuntu 24.04/26.04, Debian 13, Fedora 43/44 and Arch. Codex Setup Manager itself needs Codex to be installed separately.

## Desktop app

Codex Setup Manager provides a desktop window (no terminal needed) that opens directly onto **One-click setup** (**Cài đặt nhanh**):

- Paste your Lunovant key, then click **Set up Codex** (**Cài đặt Codex**).
- The app checks the key (validates plan, 💎 remaining, and expiration date).
- It fetches the models your key is authorized to use from the server.
- It tests each model in parallel (displaying ✓ with latency or ⚠ with the failure reason, with per-model retry support).
- It writes the configuration with an automatic backup and chooses `gpt-6.1-sol` as the default model (if working).
- Once completed, it offers buttons to **Open Codex Desktop** (**Mở Codex Desktop**) or **Open Codex CLI** (**Mở Codex CLI**), along with a default-model selector.

All detailed tabs (Model, API & key, Test connection, Windows Sandbox, Backup & Restore, Diagnostics, Launch Codex, Uninstall) are preserved under **Advanced** (**Nâng cao**).

Platform downloads:
- **macOS**: download `codex-setup-macos-arm64-app.zip` (Apple Silicon) or `codex-setup-macos-x64-app.zip` (Intel), unzip it, drag **Codex Setup.app** to Applications, then open it. The app is signed and notarized.
- **Windows**: double-click `codex-setup-windows-x64.exe`. It needs Microsoft Edge WebView2, which is preinstalled on Windows 10/11. If it is missing, install the [Evergreen runtime](https://developer.microsoft.com/microsoft-edge/webview2/).
- **Linux**: `codex-setup-linux-x64` uses the text menu (no desktop window yet: the GTK bindings could not be built on the Ubuntu 22.04 build runner). Every feature is available there and through the CLI commands.

The command line is still available: `codex-setup <command>`, or `codex-setup --tui` for the text menu.

## Download

1. Open the project's GitHub Releases page and download the file for your system:
   - `codex-setup-windows-x64.exe`
   - `codex-setup-macos-arm64` (Apple Silicon)
   - `codex-setup-macos-x64` (Intel Mac)
   - `codex-setup-linux-x64`
2. Download the matching `.sha256` file and verify it:
   - macOS: `shasum -a 256 codex-setup-macos-arm64` 
   - Linux: `sha256sum codex-setup-linux-x64`
   - Windows (PowerShell): `Get-FileHash .\codex-setup-windows-x64.exe -Algorithm SHA256`

   The printed hash must equal the one in the `.sha256` file.

## First run

Windows binaries are not code-signed, so SmartScreen shows a warning the first time.

### macOS

Release binaries are signed with a Developer ID and notarized by Apple when the maintainers' signing secrets are available, so this is enough:

```bash
chmod +x ./codex-setup-macos-arm64
./codex-setup-macos-arm64
```

If a build is unsigned and Gatekeeper blocks it, allow this one file only (`xattr -d` exits with 1 when the attribute is missing, so do not chain it with `&&`):

```bash
chmod +x ./codex-setup-macos-arm64
xattr -d com.apple.quarantine ./codex-setup-macos-arm64 2>/dev/null; ./codex-setup-macos-arm64
```

Alternative: in Finder, right-click the file, choose Open, then confirm Open. Do not turn Gatekeeper off for your whole Mac.

### Windows

Double-click the `.exe` (or run it in Terminal). If you see "Windows protected your PC", click More info, then Run anyway. No administrator rights are needed.

### Linux

```bash
chmod +x ./codex-setup-linux-x64
./codex-setup-linux-x64
```

For convenience, you can rename the file to `codex-setup` and put it on your `PATH`. The examples below use `codex-setup`.

## Quick Setup walkthrough

Codex Setup Manager opens directly on **One-click setup** (**Cài đặt nhanh**):

1. **Paste your key**: Enter your Lunovant key and click **Set up Codex** (**Cài đặt Codex**).
2. **Automated verification**: The app checks your key (plan, 💎 remaining, expiry), queries the models authorized for the key, and tests each model in parallel (showing ✓ with response latency or ⚠ with the reason, with per-model retry).
3. **Configuration**: Config is safely written with an automatic backup, setting `gpt-6.1-sol` as the default model (or the first working model).
4. **Launch & use**: Click **Open Codex Desktop** (**Mở Codex Desktop**) or **Open Codex CLI** (**Mở Codex CLI**) to start immediately, or change the default model using the selector.

> The classic step-by-step Quick Setup remains available under the **Advanced** (**Nâng cao**) section in the GUI and as option 1 in the text menu (`codex-setup --tui`).

## Command reference

Global options: `--codex-home PATH`, `--lang en|vi`. Write commands accept `--dry-run` (show the diff only) and `--yes` (skip confirmation).

| Command | Purpose |
| --- | --- |
| `status` | Show config, provider, model, key and Codex status |
| `setup --auto [--keep-personal] [--base-url URL]` | One-click automated setup (reads key from stdin, probes models, writes config). Use `--keep-personal` to keep your ChatGPT login default |
| `setup [--base-url URL] [--model M] [--key-stdin] [--secret-backend auto\|keyring\|file\|session]` | Quick Setup (step-by-step) |
| `mode [lunovant\|personal]` | Show or switch the active default mode between Lunovant and personal ChatGPT account |
| `model [NAME]` | Show or change the model |
| `api [--base-url URL] [--key-stdin \| --delete-key]` | Change base URL or key, or delete the stored key |
| `test [--model M]` | Test the connection |
| `sandbox [elevated\|unelevated\|remove]` | Windows sandbox mode (other systems: not applicable) |
| `backup create\|list\|restore ID\|original` | Manage backups |
| `diagnose [--text TEXT]` | Local checks, or explain an error message |
| `profile list\|add\|use\|remove` | Manage profiles |
| `launch [cli\|app] [-- codex args...]` | Launch Codex with the key injected |
| `env install\|remove` | Persist the key as an environment variable (opt-in) |
| `uninstall` | Remove what this tool added |
| `--version` | Print the version |

Examples:

```bash
# One-click setup via stdin (reads key from stdin; never pass the key as an argument)
pbpaste | codex-setup setup --auto

# One-click setup keeping your personal ChatGPT account as default
pbpaste | codex-setup setup --auto --keep-personal

# Switch default modes
codex-setup mode lunovant                # switch default to Lunovant
codex-setup mode personal                # switch default to personal ChatGPT account
codex-setup mode                         # show current active mode

codex-setup setup --dry-run              # preview the changes, write nothing
codex-setup model gpt-6.1-terra          # switch model
codex-setup test                         # test the connection
codex-setup sandbox unelevated           # Windows sandbox fallback
codex-setup launch cli                   # start Codex CLI with the key
codex-setup launch app                   # start Codex Desktop with the key (experimental)
echo "sk-..." | codex-setup api --key-stdin
```

Never pass an API key as a command-line argument: it leaks into shell history and process lists (`ps`). For automated setup, pass the key via stdin: `pbpaste | codex-setup setup --auto` (macOS) or `Get-Clipboard | codex-setup setup --auto` (Windows PowerShell).

## How the API key is stored

One-click setup writes the API key into `~/.codex/config.toml` (or `%USERPROFILE%\.codex\config.toml` on Windows) as `experimental_bearer_token`. This allows Codex Desktop and any new terminal session to work out-of-the-box without configuring environment variables.

- **File permissions**: On macOS and Linux, `config.toml` is written with strict `0600` permissions (read/write by owner only), and backups created by the tool also preserve `0600` mode.
- **OS Secret Store**: The key is also stored in the operating system's secret store (macOS Keychain, Windows Credential Manager, or Linux Secret Service) when available.
- **Security tradeoff**: The key is stored in plaintext within `config.toml`. While restricted to your user account (mode `0600`), any application or script running under your user account can read it.

If you prefer not to store the key in `config.toml`, the **Advanced** (**Nâng cao**) setup provides the environment variable workflow (`env_key = "LUNOVANT_API_KEY"`), where the key stays in the OS keychain and is injected via `codex-setup launch` or persisted with `codex-setup env install`.

The key is never printed in logs or passed via command-line arguments.

## Resulting config.toml

When in **Lunovant mode**:

```toml
model = "gpt-6.1-sol"
model_provider = "lunovant"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
wire_api = "responses"
experimental_bearer_token = "sk-…"
```

When in **ChatGPT account mode**:

The top-level `model_provider` line is absent (or restored to your personal settings), while the `[model_providers.lunovant]` table remains in `config.toml`:

```toml
model = "gpt-6.1-sol"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
wire_api = "responses"
experimental_bearer_token = "sk-…"
```

### Profile file (`lunovant.config.toml`)

In addition to `config.toml`, Codex Setup Manager creates `$CODEX_HOME/lunovant.config.toml` so that `codex -p lunovant` always works in both modes:

```toml
# Managed by Codex Setup Manager: use with  codex -p lunovant
model_provider = "lunovant"
model = "gpt-6.1-sol"
```

> **Note on legacy `profile = "..."` lines**: Newer versions of Codex refuse to start if a top-level `profile = "..."` line is present in `config.toml`. Codex Setup Manager automatically detects and removes any old top-level `profile = "..."` setting to ensure Codex starts normally, while preserving any existing `[profiles.*]` tables (which are simply ignored by newer Codex versions).

The files live under `~/.codex/` (`%USERPROFILE%\.codex\` on Windows), or under `CODEX_HOME` if set. On macOS and Linux, `config.toml` is created with permission mode `0600`. The built-in provider ids `openai`, `ollama`, `lmstudio`, `amazon-bedrock` and `gcp` are reserved; the tool never writes a table for them.

## Windows sandbox

Codex on Windows runs commands in a sandbox with two modes:

- `elevated`: needs a one-time setup approved by an administrator.
- `unelevated`: uses a restricted token of your own account. No admin approval needed.

Pick `unelevated` when the elevated setup is blocked (no admin rights, company policy, security software). Run:

```
codex-setup sandbox unelevated
```

Typical errors this fixes:

- "Couldn't check Windows setup"
- "Couldn't check agent sandbox status"
- "Unable to send message"

Never disable the sandbox; this tool does not offer that and does not touch Defender or UAC. `codex-setup sandbox remove` returns to Codex's default. Sandbox log: `%USERPROFILE%\.codex\.sandbox\sandbox.log` (`$CODEX_HOME/.sandbox/sandbox.log`). `codex-setup diagnose` reads its last lines with keys redacted.

## Troubleshooting

Run `codex-setup test` and `codex-setup diagnose` first. To explain a message you saw: `codex-setup diagnose --text "message"`.

- Provider mismatch ("model provider mismatch"): an old conversation stays bound to the provider it was created with. Start a new thread or session. The tool never edits Codex session files.
- 401 Unauthorized: the key is wrong, expired or has extra spaces. Set it again with `codex-setup api`.
- 403 Forbidden: the key has no access to this model or endpoint. Check your plan with Lunovant.
- 404 Not Found: wrong URL or model name. The URL should end with `/v1`; check the model name.
- 429 Too Many Requests: rate limit. Wait and retry.
- Variable `LUNOVANT_API_KEY` missing: start Codex with `codex-setup launch`, or use `env install`.

## Backup, restore and uninstall

Every change makes a backup first, and the first install also keeps a snapshot of your original config.

```bash
codex-setup backup list
codex-setup backup restore ID
codex-setup backup original
codex-setup uninstall --dry-run
codex-setup uninstall
```

Uninstall removes the provider tables this tool created, restores your original `model` / `model_provider` (or removes them), removes the sandbox setting only if this tool set it, and deletes the stored key only if you confirm. It never deletes backups or Codex data.

## Privacy

- The API key is sent only to the configured base URL (default `https://api.lunovant.tech`).
- No telemetry and no analytics.
- The key never appears in logs or command-line arguments. In `config.toml`, it is protected by user-only file permissions (`0600`). Error output is redacted.

## Build from source

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
pytest
python scripts/build.py --smoke
```

The binary and a `.sha256` file are written to `dist/`. Builds are for the current OS and architecture only.

## Signing (maintainers)

The macOS CI jobs sign with a Developer ID Application certificate and notarize the binary when `MACOS_CERT_P12` is set. Without it they build unsigned. Repository secrets:

- `MACOS_CERT_P12`: base64 of a Developer ID Application `.p12`
- `MACOS_CERT_PASSWORD`: password of that `.p12`
- `APPLE_API_KEY_P8`: content of the App Store Connect API key `.p8`
- `APPLE_API_KEY_ID`: key ID of that API key
- `APPLE_API_ISSUER_ID`: issuer ID of the App Store Connect team

Locally: `python scripts/build.py --codesign-identity "<identity>"` (or env `MACOS_SIGN_IDENTITY`). Use `-` for an ad-hoc signature. Notarize with `scripts/notarize_macos.sh <binary>`.

## Known limitations / not yet verified

- Launching the Desktop app with the key injected (`launch app`) is experimental. It is not verified that a Desktop app started this way always inherits the environment.
- Windows Desktop detection may miss Microsoft Store installs; "not detected" does not always mean not installed.
- Windows binaries are not signed (SmartScreen warning). macOS binaries are signed and notarized only when the signing secrets are configured.

## License

MIT, see [LICENSE](LICENSE).
