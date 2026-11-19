# Lunovant Setup

English | [Tiếng Việt](README.vi.md)

Lunovant Setup (`lunovant-setup`) is an all-in-one configuration tool for **OpenAI Codex** and **Claude Code** to connect seamlessly to the Lunovant API. It safely configures your environment, stores credentials securely, verifies models, and allows side-by-side coexistence with your personal accounts.

The application automatically detects your key type:
- **Orion key**: configures OpenAI Codex (CLI and Desktop app).
- **Lyra key**: configures Claude Code (terminal and IDE extensions).
- **Combo key (both)**: configures both Codex and Claude Code in a single click!

*(Upgrading: if you used the old "Codex Setup" app, you can delete it after installing "Lunovant Setup.app". Your settings and saved keys are kept. The old `codex-setup` command still works as an alias.)*

---

## Quick start

1. **Download**: Download the release package for your operating system from GitHub Releases ([see links below](#download)).
2. **Open app**: Launch Lunovant Setup (`Lunovant Setup.app` on macOS, or double-click `lunovant-setup-windows-x64.exe` on Windows).
   > **Windows note**: On first launch, Windows SmartScreen will display **"Windows protected your PC"** because the executable is not yet code-signed. Click **More info**, then **Run anyway**. No administrator privileges are required.
3. **Paste key**: Paste your Lunovant API key (Orion, Lyra, or combo) into the **Paste your Lunovant key** field.
4. **Click "Install" & start working**: Click **Install** (**Cài đặt**). Lunovant Setup verifies your key, checks which product(s) your key supports, probes the working models, and writes the configuration safely with an automated backup. Once finished, launch your tool (Codex Desktop / CLI, or run `claude` in your terminal / IDE) and start coding!

---

## Claude Code

Lunovant Setup provides first-class support for Claude Code (CLI and VS Code / Cursor extensions).

### What is written

- **Configuration file**: Modifies `~/.claude/settings.json` (or `%USERPROFILE%\.claude\settings.json` on Windows).
- **Environment block**: Injects the following keys inside the `"env"` object:
  - `ANTHROPIC_BASE_URL`: Base origin URL (`https://api.lunovant.tech`)
  - `ANTHROPIC_AUTH_TOKEN`: Your Lunovant API key
  - `ANTHROPIC_MODEL`: Default model (`claude-opus-5-5`)
  - `ANTHROPIC_DEFAULT_OPUS_MODEL`: Opus 5.5 model ID (`claude-opus-5-5`)
  - `ANTHROPIC_DEFAULT_SONNET_MODEL`: Sonnet 5.5 model ID (`claude-sonnet-5-5`)
  - `ANTHROPIC_DEFAULT_HAIKU_MODEL`: Haiku 5.5 model ID (`claude-haiku-5-5`)
- **Preserves existing settings**: Any existing custom configurations or non-Lunovant settings in `settings.json` are preserved untouched.
- **Automated backup**: An automated backup of `settings.json` is created before any modifications are written.
- **Dedicated profile file (`~/.claude/lunovant-settings.json`)**: Created with strict `0600` permissions (read/write by owner only). This allows running Claude Code with Lunovant at any time via `claude --settings ~/.claude/lunovant-settings.json`.

### The 3 tested models & saving credits

Lunovant Setup configures three tested models across the Claude family:
- **Opus 5.5** (`claude-opus-5-5`, default): Maximum capability for complex reasoning, architectural tasks, and refactoring.
- **Sonnet 5.5** (`claude-sonnet-5-5`): Balanced speed and high intelligence for daily engineering.
- **Haiku 5.5** (`claude-haiku-5-5`): Ultra-fast and lightweight for routine updates and quick edits.

**Why only 3 models are tested**: Testing every model in the catalog consumes API credits. Lunovant Setup tests only the 3 specific models configured for your environment, saving your credits (💎).

### How to use Claude Code

- **Terminal (CLI)**:
  - `claude`: Starts Claude Code using your current default mode.
  - `claude --settings ~/.claude/lunovant-settings.json`: Always runs Claude Code using Lunovant, regardless of the active mode.
- **Save 💎 inside Claude Code**:
  - Switch to a lighter model on the fly by typing `/model sonnet` or `/model haiku` to conserve credits during routine tasks.
- **VS Code / Cursor (Claude Code extension)**:
  - The official Claude Code extension uses the exact same `~/.claude/settings.json`. No extra setup is required!
  - Reload your IDE window (**Developer: Reload Window**, `⌘⇧P` / `Ctrl+Shift+P`) after switching modes.
- **Claude desktop app limitation**:
  - The official Claude desktop chat application *cannot* connect to custom endpoints like Lunovant; only **Claude Code** (CLI and IDE extensions) is supported.

### Coexistence with personal Claude accounts

If you already have a personal Claude account login (e.g. Pro or Max) on your machine, Lunovant Setup lets you switch easily:
- **Two operational modes**:
  - **Lunovant**: Terminal `claude` and IDE extensions use Lunovant by default.
  - **Claude account (personal)**: Defaults to your personal Claude subscription. You can still use Lunovant at any time with `claude --settings ~/.claude/lunovant-settings.json`.
- **How to switch**:
  - In the GUI: Click the mode selector toggle under the Claude Code section.
  - In the CLI: Run `lunovant-setup mode lunovant --line claude` or `lunovant-setup mode personal --line claude`.
  - Restart your terminal or reload your IDE window after switching.
- **Privacy**:
  - The application only checks whether a personal login exists (by checking for `oauthAccount` in `~/.claude.json`). It **never** reads, stores, logs, or transmits your actual credentials, access tokens, passwords, or personal account details from `.credentials.json` or the OS keychain.

---

## OpenAI Codex

Lunovant Setup configures OpenAI Codex (CLI and Desktop app) to use the Lunovant API.

### Using alongside your own ChatGPT account

If you already use a personal ChatGPT account with Codex, you can use both side-by-side seamlessly:
- **Two operational modes**:
  - **Lunovant**: Everything (Codex Desktop app, VS Code / Cursor extensions, and the `codex` command) uses Lunovant by default.
  - **ChatGPT account**: Everything defaults to your personal ChatGPT account. Lunovant remains accessible anytime via `codex -p lunovant` in the terminal.
- **How to switch**:
  - In the GUI: Click the mode toggle (**Lunovant** / **ChatGPT account**) in the **Current mode** card.
  - In the CLI: Run `lunovant-setup mode lunovant --line codex` or `lunovant-setup mode personal --line codex`.
  - Restart the Codex Desktop app or reload VS Code (`⌘⇧P` / `Ctrl+Shift+P` → **Developer: Reload Window**) after switching modes.
- **Separate chat histories**:
  - Session history is separated by mode in Codex. Your personal ChatGPT conversations and Lunovant conversations do not mix; when you switch back to a mode, your previous chat threads in that mode reappear.
- **Cloud tasks and web search**:
  - Codex cloud tasks and web search require ChatGPT account mode.
- **Privacy**:
  - The tool never reads, logs, or transmits your ChatGPT login credentials (`auth.json`). It only checks whether a login file exists on your computer to allow switching modes.

### How to use Codex after setup

- **Codex Desktop / ChatGPT app**:
  - Open the app and start chatting. The model picker shows your default model (e.g. `gpt-6.1-sol`). Restart the app after switching modes.
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

### What it does for Codex

- Adds a Lunovant provider and a default model to `$CODEX_HOME/config.toml` (keeps your other settings and comments).
- One-click setup configures the API key in `config.toml` as `experimental_bearer_token` (file mode `0600` on macOS/Linux) and keeps it in the OS secret store (macOS Keychain, Windows Credential Manager or Linux Secret Service).
- Creates `$CODEX_HOME/lunovant.config.toml` so that `codex -p lunovant` always works regardless of the active default mode.
- Tests the connection step by step (reachability, key, model list, Responses API, streaming).
- Launches Codex CLI or Desktop directly or with the key injected.
- Fixes common Windows sandbox errors.
- Backs up the config before every change, and can restore or fully undo everything.
- Interface in English and Vietnamese (`--lang en|vi`).

Available Codex models: `gpt-6.1-sol` (default), `gpt-6.1-terra`, `gpt-6-sol`, `gpt-6-luna`, `gpt-6-astra`.
Base URL: `https://api.lunovant.tech`. API endpoint: `https://api.lunovant.tech/v1`.

---

### Model list in Codex

- The Codex model picker shows exactly the models Lunovant sells (a catalog file `lunovant-models.json` in `$CODEX_HOME`; Codex never asks the provider for its models).
- Opening the app refreshes the list: new models appear, and a list that a newer Codex cannot read is removed automatically. The command line does the same with `lunovant-setup refresh-catalog` (also run before `status` / `mode`; `--offline` skips the network and keeps the last known list).
- If Codex prints `failed to parse model_catalog_json ...`, open Lunovant Setup (it refreshes or removes the invalid list) or run `lunovant-setup refresh-catalog`.

## Supported systems

| OS | Architecture | Codex CLI / Desktop | Claude Code (CLI / IDE) | Lunovant Setup App |
| --- | --- | --- | --- | --- |
| Windows 10 / 11 | x64 | Yes / Yes | Yes / Yes | GUI window (.exe) |
| macOS (Apple Silicon) | arm64 | Yes / Yes | Yes / Yes | GUI window (.app) |
| macOS (Intel) | x64 | Yes / CLI only | Yes / Yes | GUI window (.app) |
| Ubuntu 24.04 | x64 | Yes / Preview | Yes / Yes | Text menu (TUI / CLI) |
| Ubuntu 22.04 | x64 | Yes / CLI only | Yes / Yes | Text menu (TUI / CLI) |

Lunovant Setup itself requires Codex and/or Claude Code to be installed separately.

---

## Desktop application

Lunovant Setup provides a user-friendly desktop window (no terminal needed) that opens directly onto **One-click setup** (**Cài đặt nhanh**):

- Paste your Lunovant key, then click **Install** (**Cài đặt**).
- The app checks the key (validates plan, 💎 remaining, and expiration date).
- It inspects the key permissions and detects the product lines:
  - If it contains `gpt-*` models → configures Codex.
  - If it contains `claude-*` models → configures Claude Code.
  - If it contains both → configures both seamlessly.
- It tests the models in parallel and displays latency or failure reasons.
- It safely writes configurations with automated backups.
- Once finished, it provides quick-launch buttons (**Open Codex Desktop**, **Open Codex CLI**, or **Open Terminal with Claude Code**) and model selectors.

All advanced configuration tabs for Codex (Model, API & key, Test connection, Windows Sandbox, Backup & Restore, Diagnostics, Launch Codex, Uninstall) remain accessible under **Codex advanced** (**Codex nâng cao**).

---

## Download

1. Open the [GitHub Releases page](https://github.com/lunovant/lunovant-setup/releases) and download the package for your system:
   - `lunovant-setup-windows-x64.exe` (Windows)
   - `lunovant-setup-macos-arm64-app.zip` (macOS Apple Silicon app)
   - `lunovant-setup-macos-x64-app.zip` (macOS Intel app)
   - `lunovant-setup-macos-arm64` / `lunovant-setup-macos-x64` (macOS standalone CLI)
   - `lunovant-setup-linux-x64` (Linux CLI / TUI)
2. Download the matching `.sha256` file and verify it:
   - macOS: `shasum -a 256 lunovant-setup-macos-arm64`
   - Linux: `sha256sum lunovant-setup-linux-x64`
   - Windows (PowerShell): `Get-FileHash .\lunovant-setup-windows-x64.exe -Algorithm SHA256`

---

## First run

### Windows

Double-click `lunovant-setup-windows-x64.exe` (or run it in a terminal).
Because release binaries are not yet code-signed, Windows SmartScreen will show:
> **"Windows protected your PC"**

Click **More info**, then click **Run anyway**. No administrator rights are needed.
*(Requires Microsoft Edge WebView2, preinstalled on Windows 10/11).*

### macOS

Download `lunovant-setup-macos-arm64-app.zip` (or Intel `x64`), unzip it, and drag **Lunovant Setup.app** to your `Applications` folder.

For standalone CLI binaries:
```bash
chmod +x ./lunovant-setup-macos-arm64
./lunovant-setup-macos-arm64
```

If Gatekeeper blocks an ad-hoc or unsigned CLI build:
```bash
chmod +x ./lunovant-setup-macos-arm64
xattr -d com.apple.quarantine ./lunovant-setup-macos-arm64 2>/dev/null; ./lunovant-setup-macos-arm64
```
Alternatively, in Finder, right-click the app/file, select **Open**, and confirm.

### Linux

```bash
chmod +x ./lunovant-setup-linux-x64
./lunovant-setup-linux-x64
```

---

## Command reference

Global options: `--codex-home PATH`, `--lang en|vi`. Write commands accept `--dry-run` (show diff only) and `--yes` (skip confirmation prompts).

| Command | Purpose |
| --- | --- |
| `status` | Show config, provider, model, key, and environment status |
| `setup --auto [--keep-personal] [--base-url URL]` | One-click automated setup for Codex and/or Claude Code (reads key from stdin). Use `--keep-personal` to keep personal logins as default |
| `setup [--base-url URL] [--model M] [--key-stdin] [--secret-backend auto\|keyring\|file\|session]` | Step-by-step setup for Codex |
| `mode [lunovant\|personal] [--line codex\|claude]` | Show or switch default mode between Lunovant and personal account for Codex, Claude Code, or both |
| `model [NAME]` | Show or change the Codex model |
| `api [--base-url URL] [--key-stdin \| --delete-key]` | Change Codex base URL or key, or delete stored key |
| `test [--model M]` | Test the Codex API connection |
| `sandbox [elevated\|unelevated\|remove]` | Configure Windows sandbox mode for Codex |
| `backup create\|list\|restore ID\|original` | Manage configuration backups |
| `diagnose [--text TEXT]` | Local diagnostics or explain Codex error messages |
| `profile list\|add\|use\|remove` | Manage Codex profiles |
| `launch [cli\|app] [-- codex args...]` | Launch Codex with injected key |
| `env install\|remove` | Persist key in user environment variables (opt-in) |
| `uninstall` | Remove configurations added by this tool |
| `--version` | Print the tool version |

### CLI examples

```bash
# Automated setup via stdin (never pass API keys as command arguments!)
pbpaste | lunovant-setup setup --auto

# Automated setup keeping personal account(s) as default
pbpaste | lunovant-setup setup --auto --keep-personal

# Switch default mode across both Codex and Claude Code
lunovant-setup mode lunovant
lunovant-setup mode personal

# Switch default mode for a specific product line
lunovant-setup mode lunovant --line claude    # Claude Code only
lunovant-setup mode lunovant --line codex     # Codex only
lunovant-setup mode                          # Show current modes

# Codex utilities
lunovant-setup model gpt-6.1-terra
lunovant-setup test
lunovant-setup sandbox unelevated
```

> **Security tip**: Never pass API keys as CLI flags (such as `-k` or `--key`), as they leak into shell history and system process listings (`ps`). Always pass keys via stdin: `pbpaste | lunovant-setup setup --auto` (macOS) or `Get-Clipboard | lunovant-setup setup --auto` (Windows PowerShell).

---

## Configuration files created

### Claude Code

**`~/.claude/settings.json`** (in Lunovant mode):
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.lunovant.tech",
    "ANTHROPIC_AUTH_TOKEN": "sk-...",
    "ANTHROPIC_MODEL": "claude-opus-5-5",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-5-5",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-5-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-5-5"
  }
}
```

**`~/.claude/lunovant-settings.json`** (profile file, mode `0600`):
Contains the same `env` block, allowing `claude --settings ~/.claude/lunovant-settings.json` to work in any mode.

### OpenAI Codex

**`~/.codex/config.toml`** (in Lunovant mode):
```toml
model = "gpt-6.1-sol"
model_provider = "lunovant"

[model_providers.lunovant]
name = "Lunovant"
base_url = "https://api.lunovant.tech/v1"
wire_api = "responses"
experimental_bearer_token = "sk-..."
```

**`~/.codex/lunovant.config.toml`** (profile file):
```toml
# Managed by Lunovant Setup: use with codex -p lunovant
model_provider = "lunovant"
model = "gpt-6.1-sol"
```

---

## Windows sandbox (Codex)

Codex on Windows executes commands inside a sandbox with two modes:
- `elevated`: requires a one-time administrator setup.
- `unelevated`: runs with a restricted token of your user account without requiring administrator rights.

If you encounter sandbox errors ("Couldn't check Windows setup" or "Unable to send message"), switch to `unelevated`:
```cmd
lunovant-setup sandbox unelevated
```

To restore Codex's default sandbox behavior: `lunovant-setup sandbox remove`.

---

## Troubleshooting

Run `lunovant-setup test` and `lunovant-setup diagnose` first.

- **401 Unauthorized**: Key is invalid or expired. Re-run setup or check key validity.
- **403 Forbidden**: Your key does not have access to this model. Check your plan at the Lunovant dashboard.
- **404 Not Found**: Incorrect URL endpoint or model name.
- **429 Too Many Requests**: Rate limit reached. Wait briefly and retry.
- **Claude desktop chat app does not use Lunovant**: The Claude desktop application cannot use custom endpoints. Use Claude Code in the terminal (`claude`) or within VS Code / Cursor.

---

## Backup, restore and uninstall

Backups are created before every modification:
```bash
lunovant-setup backup list
lunovant-setup backup restore ID
lunovant-setup backup original
lunovant-setup uninstall --dry-run
lunovant-setup uninstall
```

Uninstall restores modified configuration files, cleans up Lunovant provider settings, and only deletes stored keys upon confirmation. It never touches your conversation history.

---

## Privacy

- API keys are sent exclusively to the configured base URL (`https://api.lunovant.tech`).
- No telemetry, analytics, or user tracking.
- Personal credentials for ChatGPT (`auth.json`) and Claude (`.credentials.json`, keychain) are **never** read, transmitted, or logged. Detection logic only inspects whether a login profile exists.
- Sensitive values and keys are automatically masked in all CLI diffs and log outputs.

---

## Build from source

Requires Python 3.11+.

```bash
pip install -e ".[dev]"
pytest
python scripts/build.py --smoke
```

---

## License

MIT, see [LICENSE](LICENSE).
