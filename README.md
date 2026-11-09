# Codex Setup Manager

English | [Tiếng Việt](README.vi.md)

Codex Setup Manager (`codex-setup`) configures OpenAI Codex (CLI and Desktop app) to use the Lunovant API. It edits your Codex `config.toml` safely, stores your API key in the operating system's secret store, tests the connection, and launches Codex with the key available.

## What it does

- Adds a Lunovant provider and a default model to `$CODEX_HOME/config.toml` (keeps your other settings and comments).
- Stores the API key in macOS Keychain, Windows Credential Manager or the Linux Secret Service. The key is never written to `config.toml`.
- Tests the connection step by step (reachability, key, model list, Responses API, streaming).
- Launches Codex CLI or Desktop with the key injected as an environment variable.
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

Run `codex-setup` with no arguments to open the menu:

```
1  Quick Setup
2  Change Model
3  API Settings
4  Test Connection
5  Windows Sandbox Fix   (Windows only)
6  Backup & Restore
7  Diagnostics
8  Profiles
9  Uninstall Configuration
0  Exit
L  Launch Codex (with key injected)
```

Choose 1 and follow the prompts: confirm the base URL, paste your API key (input is hidden), pick a model, review the diff, and confirm. Then choose 4 to test and L to launch Codex. Nothing is changed until you confirm, and a backup is made first.

## Command reference

Global options: `--codex-home PATH`, `--lang en|vi`. Write commands accept `--dry-run` (show the diff only) and `--yes` (skip confirmation).

| Command | Purpose |
| --- | --- |
| `status` | Show config, provider, model, key and Codex status |
| `setup [--base-url URL] [--model M] [--key-stdin] [--secret-backend auto\|keyring\|file\|session]` | Quick Setup |
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
codex-setup setup --dry-run              # preview the changes, write nothing
codex-setup model gpt-6.1-terra          # switch model
codex-setup test                         # test the connection
codex-setup sandbox unelevated           # Windows sandbox fallback
codex-setup launch cli                   # start Codex CLI with the key
codex-setup launch app                   # start Codex Desktop with the key (experimental)
echo "sk-..." | codex-setup api --key-stdin
```

Prefer the hidden prompt over `--key-stdin`: a key typed into a command line can stay in your shell history. Use `--key-stdin` only for automation, reading from a protected source.

## How the API key is stored

Storage order (`--secret-backend auto`):

1. OS secret store: macOS Keychain, Windows Credential Manager, or Linux Secret Service.
2. Session only: if no secret store is available, the key lives in memory until the program exits.
3. Plain-text file: only if you explicitly choose `--secret-backend file`. It is saved as `secrets.json` in the app folder with owner-only permissions. This is not encrypted; the tool warns you.

Codex reads the key from the environment variable `LUNOVANT_API_KEY` (the `env_key` in `config.toml`), not from the config file. So the variable must exist in the process that starts Codex:

- `codex-setup launch cli` / `launch app` starts Codex with the variable set for that process only. Nothing is written to disk.
- `codex-setup env install` stores the key as a persistent environment variable (Windows: user environment; macOS/Linux: a marked block in your shell rc file). This writes the key in plain text, so use it only if you accept that. `codex-setup env remove` undoes it.

The key is never put in `config.toml`, logs, or command-line arguments.

## Resulting config.toml

```toml
model = "gpt-6.1-sol"
model_provider = "lunovant"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
env_key = "LUNOVANT_API_KEY"
wire_api = "responses"
```

The file lives at `~/.codex/config.toml` (`%USERPROFILE%\.codex\config.toml` on Windows), or under `CODEX_HOME` if set. The built-in provider ids `openai`, `ollama`, `lmstudio`, `amazon-bedrock` and `gcp` are reserved; the tool never writes a table for them.

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
- The key never appears in `config.toml`, logs, or command-line arguments. Error output is redacted.

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
