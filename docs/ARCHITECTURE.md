# Codex Setup Manager: architecture contract (source for docs/ARCHITECTURE.md)

Codex Setup Manager edits the user's Codex configuration (`$CODEX_HOME/config.toml`) so Codex
CLI / Desktop talk to a third-party OpenAI-compatible provider (default: Lunovant), stores the
provider API key in the OS secret store, and launches Codex with the key injected as an
environment variable. Python 3.11+, deps: rich, tomlkit, httpx, keyring (pyproject.toml exists).

## Verified Codex facts (Phase 1, checked 2026-11-09)

Sources: learn.chatgpt.com/docs/config-file/config-reference, /codex/windows/windows-sandbox,
/codex/app, /codex/linux/linux-app, and local `codex-cli 0.162.1 --help`.

- User config: `$CODEX_HOME/config.toml`, `CODEX_HOME` defaults to `~/.codex`
  (`%USERPROFILE%\.codex` on Windows).
- `model` (string), `model_provider` (string, default `openai`).
- `[model_providers.<id>]`: `name`, `base_url`, `env_key`, `wire_api`, `query_params`,
  `http_headers`, `env_http_headers`, `requires_openai_auth`, `env_key_instructions`.
  `wire_api = "responses"` is the only supported value (also the default).
- Built-in provider IDs `openai`, `ollama`, `lmstudio` are reserved and cannot be overridden.
  `amazon-bedrock` and `gcp` are also built in. The tool never writes a table for these ids.
- Profiles (v2): `$CODEX_HOME/<name>.config.toml` layered over the base config with
  `codex --profile <name>` / `-p <name>`. The old `[profiles.<name>]` table is not in the current
  reference; the tool does not write it.
- `[windows] sandbox = "mxc" | "elevated" | "unelevated"`. `elevated` needs an
  administrator-approved one-time setup; `unelevated` uses a restricted token of the current user
  and is the documented fallback when that setup is blocked. Sandbox log:
  `$CODEX_HOME/.sandbox/sandbox.log`. `[features] prefer_mxc = true` enables MXC.
- Desktop app: macOS (Apple Silicon download; bundle id `com.openai.codex`, installed as
  `ChatGPT.app` or `Codex.app`), Windows, Linux preview (`chatgpt` .deb/.rpm, executable
  `chatgpt`, Ubuntu 24.04/26.04, Debian 13, Fedora 43/44, Arch). Ubuntu 22.04: no official app.
- `codex app [PATH]` launches the Desktop app (opens the installer if missing; never call it to
  detect). `codex --version` prints `codex-cli X.Y.Z`.
- NOT verified: whether a GUI-launched Desktop app inherits environment from a launcher process
  (we launch the app executable directly with the env; marked experimental in the UI).

## Package layout (`src/codex_setup/`), every dir has __init__.py

```
main.py                   argparse CLI + entry point (no args -> TUI)
core/errors.py            exception hierarchy
core/paths.py             CODEX_HOME / config path / app state dir resolution
core/config_store.py      load/validate/backup/atomic write/rollback/diff of config.toml
core/codex_config.py      pure tomlkit edits (provider, active model, windows sandbox, status)
core/state.py             app state JSON (profiles, managed provider ids, original values)
core/backup.py            backup list / restore / original snapshot
providers/catalog.py      ProviderSpec + presets (Lunovant, OpenAI, custom)
security/redact.py        mask_key(), redact()
security/secrets.py       SecretStore (keyring, session-only fallback, opt-in 0600 file)
security/launcher.py      build env + launch Codex CLI / Desktop with the key injected
platforms/base.py         PlatformInfo, CodexInstall, detect_platform(), detect_codex()
platforms/windows.py      Desktop detection, persistent user env (winreg), opt-in
platforms/macos.py        Desktop detection (bundle id), app executable resolution
platforms/linux.py        Desktop detection (`chatgpt`), distro info, support matrix
platforms/shellrc.py      opt-in POSIX shell rc marker block
diagnostics/api_test.py   connection test steps + classification
diagnostics/checks.py     local diagnostics
diagnostics/knowledge.py  known error messages -> explanation + fix steps (en + vi)
ui/i18n.py                en/vi strings
ui/tui.py                 Rich menu UI
```

## Contracts

All public functions have type hints. Paths are `pathlib.Path`. Text files are UTF-8.
`env` parameters default to `os.environ`; tests pass dicts.

### core/errors.py
```python
class CodexSetupError(Exception): ...
class ConfigParseError(CodexSetupError):   # attrs .path, .line: int | None, .col: int | None
class ConfigWriteError(CodexSetupError):   # attr .path ; raised after rollback was attempted
class ReservedProviderError(CodexSetupError)
class SecretStoreError(CodexSetupError)
class ValidationError(CodexSetupError)      # bad URL / id / env var name / model name
```

### core/paths.py
```python
def codex_home(env: Mapping[str, str] | None = None) -> Path
    # CODEX_HOME if set and non-empty (expanduser), else Path.home() / ".codex"
def config_path(env=None) -> Path                       # codex_home() / "config.toml"
def profile_config_path(name: str, env=None) -> Path    # codex_home() / f"{name}.config.toml"
def app_state_dir(env=None) -> Path
    # override CODEX_SETUP_HOME. Windows: %APPDATA%/codex-setup-manager,
    # macOS: ~/Library/Application Support/codex-setup-manager,
    # else ($XDG_CONFIG_HOME or ~/.config)/codex-setup-manager
def backups_dir(env=None) -> Path                       # app_state_dir() / "backups"
```
Platform for app_state_dir comes from a `system: str | None = None` kwarg (default
`sys.platform`) so tests can simulate windows/macos/linux. Nothing here creates directories.

### core/config_store.py
```python
@dataclass
class LoadedConfig:
    path: Path
    doc: tomlkit.TOMLDocument
    original_text: str          # "" when the file did not exist
    existed: bool
@dataclass
class SaveResult:
    changed: bool; diff: str; backup: Path | None; dry_run: bool

def load_config(path: Path) -> LoadedConfig        # ConfigParseError on invalid TOML / bad UTF-8
def render(doc) -> str                              # tomlkit.dumps
def validate_text(text: str) -> None               # parse with tomllib; ConfigParseError
def diff_text(old: str, new: str, path: Path) -> str   # unified diff, "" if equal
def atomic_write_text(path: Path, text: str) -> None
    # mkdir parents; temp file in the same dir, write+flush+fsync, keep existing file mode,
    # os.replace; temp removed on failure; OSError -> ConfigWriteError
def save_config(loaded: LoadedConfig, *, dry_run: bool = False, reason: str = "", env=None) -> SaveResult
    # new_text = render(doc); validate_text(new_text); if equal -> SaveResult(changed=False,...)
    # dry_run -> SaveResult(changed=True, diff=..., backup=None, dry_run=True), disk untouched
    # else: backup.create_backup(path, reason, env) when the file existed; atomic write;
    # re-read + validate; on failure restore original_text atomically (or delete the new file
    # if it did not exist) and raise ConfigWriteError
```

### core/codex_config.py (pure, no I/O)
```python
RESERVED_PROVIDER_IDS = frozenset({"openai", "ollama", "lmstudio", "amazon-bedrock", "gcp"})
@dataclass
class ConfigStatus:
    model: str | None; model_provider: str | None; provider_ids: list[str]
    windows_sandbox: str | None; active_provider: dict | None   # plain dict of the active table
def get_status(doc) -> ConfigStatus
def upsert_provider(doc, spec: ProviderSpec) -> None
    # ReservedProviderError for reserved ids; updates only name/base_url/env_key/wire_api in an
    # existing [model_providers.<id>] (other keys and comments kept), else adds it. Never creates
    # a second table. Works when [model_providers] is absent, a super-table with other providers,
    # or the provider is written as a dotted/inline table.
def remove_provider(doc, provider_id: str) -> bool
def set_active(doc, provider_id: str, model: str) -> None
    # sets top-level model_provider and model. Top-level keys must stay top-level (inserted
    # before the first table, never appended into the last table). Verify by re-parsing.
def set_model(doc, model: str) -> None
def restore_top_level(doc, model: str | None, model_provider: str | None) -> None  # None removes
def set_windows_sandbox(doc, mode: Literal["elevated", "unelevated"] | None) -> None
    # None removes `sandbox` (and the [windows] table if empty). Other keys in [windows] kept.
    # "mxc" is reported by get_status but the tool never sets it.
```

### providers/catalog.py
```python
@dataclass(frozen=True)
class ProviderSpec:
    id: str              # ^[a-z0-9][a-z0-9_-]{0,63}$
    name: str
    base_url: str        # normalized, no trailing slash
    env_key: str | None  # ^[A-Z_][A-Z0-9_]*$ ; None only for builtin
    wire_api: str = "responses"
    builtin: bool = False
    def to_dict(self) -> dict ; @classmethod from_dict(d) -> ProviderSpec
LUNOVANT_ROOT_URL = "https://api.lunovant.tech"
LUNOVANT = ProviderSpec("lunovant", "Lunovant", "https://api.lunovant.tech/v1", "LUNOVANT_API_KEY")
LUNOVANT_MODELS = ("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna", "gpt-6-astra")
DEFAULT_MODEL = "gpt-6.1-sol"
OPENAI = ProviderSpec("openai", "OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", builtin=True)
def normalize_base_url(url: str) -> str   # strip, drop trailing "/", require http(s)+host, else ValidationError
def suggest_v1(url: str) -> str           # append "/v1" unless the path already ends with /v1
def validate_model_name(name: str) -> str # non-empty, no whitespace/quotes, <= 128 chars
def custom_provider(id, name, base_url, env_key) -> ProviderSpec   # validates; reserved id -> ReservedProviderError
```

### core/state.py
App-owned JSON at `app_state_dir()/state.json` (never secrets), written atomically.
```python
@dataclass
class Profile:
    name: str; provider: ProviderSpec; model: str; models: list[str]
@dataclass
class AppState:
    version: int = 1
    profiles: dict[str, Profile] = {}     # "lunovant" created by Quick Setup
    active_profile: str | None = None
    managed_provider_ids: list[str] = []  # provider tables this tool created
    original_top_level: dict | None = None  # {"model": .., "model_provider": ..} before 1st install
    original_snapshot: str | None = None    # path of the pre-install backup ("" = no file existed)
    secret_backend: str | None = None       # "keyring" | "file" | "session"
    last_test: dict | None = None           # {"when": iso, "overall": "ok|warn|fail", "model": ..}
def load_state(env=None) -> AppState      # missing -> default; corrupt -> renamed to state.json.bad, default
def save_state(state, env=None) -> None
```

### core/backup.py
```python
@dataclass
class BackupInfo: id: str; path: Path; created: str; reason: str; source: str; sha256: str; size: int
def create_backup(path: Path, reason: str = "", env=None) -> Path
    # copy to backups_dir()/f"config-{YYYYmmdd-HHMMSS-ffffff}.toml" + sidecar same-name .json
    # {source, created, reason, sha256}; id = file stem
def list_backups(env=None) -> list[BackupInfo]   # newest first, ignores files without sidecar
def find_backup(id_or_path: str, env=None) -> BackupInfo
def restore_backup(info: BackupInfo, target: Path, *, dry_run=False, env=None) -> SaveResult
    # validates the backup TOML first; backs up the current target; atomic write
def ensure_original_snapshot(path: Path, state: AppState, env=None) -> bool
    # first install only (state.original_snapshot is None): backup with reason="original";
    # if the config does not exist set state.original_snapshot = "" ; returns True if created
```

### security/redact.py
```python
def mask_key(key: str | None) -> str      # None/"" -> "(not set)"; len<=8 -> "****"; else first 3 + "…" + last 4
def redact(text: str, secrets: Iterable[str]) -> str   # every non-empty secret (len>=4) -> mask_key(secret)
                                                     # also masks "Bearer <token>" patterns
```

### security/secrets.py
```python
SERVICE = "codex-setup-manager"
class SecretStore:
    def __init__(self, backend: str = "auto", env=None, keyring_module=None)
        # auto -> keyring if usable else session ; "file" only when explicitly requested
    backend_name: str
    @staticmethod
    def keyring_usable(keyring_module=None) -> bool   # False for fail/null/chainer-without-backends
    def get(self, env_key: str) -> str | None
    def set(self, env_key: str, value: str) -> None   # SecretStoreError on backend failure
    def delete(self, env_key: str) -> bool
```
- keyring: `get_password(SERVICE, env_key)`.
- session: in-memory only (process lifetime).
- file (opt-in): `app_state_dir()/secrets.json`, created with mode 0600 on POSIX (os.open with
  0o600), atomic write; callers show a plaintext warning.
- Keys are never logged, printed in full, passed on argv, or written to config.toml.

### security/launcher.py
```python
def build_env(base: Mapping[str, str], env_key: str, secret: str) -> dict[str, str]
def launch_cli(args: list[str], env_key: str, secret: str, *, codex_path: str, run=subprocess.run) -> int
def launch_desktop(install: CodexInstall, platform: PlatformInfo, env_key: str, secret: str, *, popen=subprocess.Popen) -> None
    # starts the Desktop executable directly with env (no shell, no secret on argv), detached
```

### platforms
```python
@dataclass
class PlatformInfo:
    system: Literal["windows", "macos", "linux"]; release: str; machine: str
    distro_id: str | None = None; distro_version: str | None = None
@dataclass
class CodexInstall:
    cli_path: str | None; cli_version: str | None
    desktop_supported: bool; desktop_installed: bool
    desktop_path: str | None       # .app bundle / exe
    desktop_executable: str | None # binary to exec for launch
    desktop_note: str
def detect_platform() -> PlatformInfo
def detect_codex(platform: PlatformInfo, *, which=shutil.which, run=subprocess.run, env=None, roots=None) -> CodexInstall
```
- CLI: `which("codex")` then `[path, "--version"]` (timeout 5 s, errors -> version None).
  Never run `codex app`.
- macOS: `/Applications` and `~/Applications` `{ChatGPT,Codex}.app` whose Info.plist
  `CFBundleIdentifier == "com.openai.codex"`; executable `Contents/MacOS/<CFBundleExecutable>`.
- Windows: look for Codex/ChatGPT app executables under `%LOCALAPPDATA%\Programs\*`, and
  `%LOCALAPPDATA%\Microsoft\WindowsApps` aliases (`Codex.exe`, `ChatGPT.exe`). Not found ->
  desktop_installed False with note "not detected" (it may still be installed as a Store app).
  A `.codex` dir is never evidence of an install.
- Linux: `which("chatgpt")`; supported distros: ubuntu 24.04/26.04, debian 13, fedora 43/44,
  arch; others "not officially supported" (Ubuntu 22.04 explicitly: no official Desktop app).
- Persistent env (opt-in, user consent only):
  Windows `winreg` HKCU\Environment set/delete (REG_SZ) + WM_SETTINGCHANGE broadcast via ctypes;
  POSIX marker block `# >>> codex-setup-manager >>>` / `# <<< codex-setup-manager <<<` in the
  user's shell rc (zsh: ~/.zshrc, bash: ~/.bashrc, else ~/.profile), file mode kept, warning that
  the key is plaintext. Both have remove functions.

### diagnostics/api_test.py
```python
class Outcome(StrEnum): OK="ok"; WARN="warn"; FAIL="fail"; SKIP="skip"
class Problem(StrEnum): BAD_URL, DNS, TLS, NETWORK, TIMEOUT, UNAUTHORIZED, FORBIDDEN,
    MODEL_NOT_FOUND, RATE_LIMITED, RESPONSES_UNSUPPORTED, SERVER_ERROR, INCOMPATIBLE, UNKNOWN
@dataclass
class StepResult: step: str; outcome: Outcome; problem: Problem | None; detail: str; http_status: int | None = None
@dataclass
class ApiTestReport:
    steps: list[StepResult]; overall: Outcome
    # overall OK only if both responses steps passed; FAIL if any FAIL; else WARN
def run_api_test(base_url: str, api_key: str, model: str, *, client: httpx.Client | None = None, timeout: float = 30.0) -> ApiTestReport
```
Steps (stop after a FAIL in connect/auth; later steps SKIP):
1. `connect`: GET scheme://host/ ; any HTTP status = reachable. httpx.ConnectError whose cause
   is DNS (gaierror / "Name or service not known" / "nodename nor servname") -> DNS; ssl errors
   -> TLS; ConnectTimeout/ReadTimeout -> TIMEOUT; other transport errors -> NETWORK; invalid URL -> BAD_URL.
2. `models`: GET {base}/models with `Authorization: Bearer`. 401 -> UNAUTHORIZED (FAIL),
   403 -> FORBIDDEN (FAIL), 404 -> WARN (endpoint missing; also hint the URL may need /v1),
   200 with HTML/non-JSON -> FAIL BAD_URL ("this is a web page, not an API; try …/v1"), 200 JSON -> OK.
3. `model_listed`: WARN if the model is not in data[].id (SKIP when models unavailable).
4. `responses`: POST {base}/responses `{"model": m, "input": "Reply with OK", "max_output_tokens": 16}`.
   2xx + JSON with `output`/`output_text` or `object == "response"` -> OK; 2xx otherwise -> FAIL
   INCOMPATIBLE. 401/403 as above; 404/400 whose body mentions the model -> MODEL_NOT_FOUND;
   404/405 otherwise -> RESPONSES_UNSUPPORTED; 429 -> RATE_LIMITED; 5xx -> SERVER_ERROR.
5. `responses_stream`: same body + `"stream": true`; read SSE; OK when it sees
   `response.completed` (or `response.done`) after `response.created`/`response.output_text.delta`;
   otherwise FAIL INCOMPATIBLE (Codex requires streaming Responses).
Error details: body passed through redact([api_key]) and truncated to 300 chars. The key never
appears in any StepResult.

### diagnostics/checks.py
```python
@dataclass
class CheckResult: id: str; outcome: Outcome; title: str; detail: str; fix: str
@dataclass
class DiagnosticsContext: config_path: Path; env: Mapping[str, str]; platform: PlatformInfo;
    install: CodexInstall; state: AppState; secret_store: SecretStore
def run_checks(ctx) -> list[CheckResult]
```
Checks: config exists/parses (ConfigParseError line/col); model_provider set and its
[model_providers.<id>] defined (unless builtin); provider has env_key; env var present in the
current environment (WARN if missing but stored in the secret store: "use `codex-setup launch`"
or `env install`); secret stored; codex CLI found; Desktop status note; Windows: sandbox mode and
tail of `$CODEX_HOME/.sandbox/sandbox.log` scanned for errors (last 200 lines, redacted);
last API test result from state.

### diagnostics/knowledge.py
```python
@dataclass(frozen=True)
class KnownIssue: id: str; patterns: tuple[str, ...]; title: dict[str, str]; explanation: dict[str, str]; steps: dict[str, list[str]]  # keys "en","vi"
ISSUES: tuple[KnownIssue, ...]
def lookup(text: str) -> list[KnownIssue]   # case-insensitive substring/regex match
```
Issues: provider_mismatch ("model provider mismatch" etc.: old threads stay bound to the provider
they were created with; start a new thread/session; the tool never edits session files),
windows_setup ("couldn't check windows setup"), sandbox_status ("couldn't check agent sandbox
status"), unable_to_send ("unable to send message"), unauthorized (401), forbidden (403),
model_not_found (404 / "model not found" / "does not exist"), rate_limited (429),
responses_incompatible, invalid_config ("config.toml" + parse/invalid), env_missing ("environment
variable" + missing/not set, `LUNOVANT_API_KEY`), codex_not_found ("codex: command not found",
"not recognized as an internal or external command"). Windows sandbox issues: suggest
`codex-setup sandbox unelevated`, explain elevated vs unelevated, never disable the sandbox,
never touch Defender/UAC, mention `$CODEX_HOME/.sandbox/sandbox.log`.

## UI / CLI (main.py, ui/)

`codex-setup` with no args opens the Rich TUI: header panel (OS, Codex CLI version, Desktop
status, active model/provider, config status, last API test, masked key) and menu:
1 Quick Setup, 2 Change Model, 3 API Settings, 4 Test Connection, 5 Windows Sandbox Fix (only
shown on Windows), 6 Backup & Restore, 7 Diagnostics, 8 Profiles, 9 Uninstall Configuration,
0 Exit. Plus L Launch Codex (with key injected).
Subcommands (`--dry-run` on writes, `--yes` skips confirmation, global `--codex-home`, `--lang en|vi`):
`status`, `setup [--base-url URL] [--model M] [--key-stdin] [--secret-backend auto|keyring|file|session]`,
`model [NAME]`, `api [--base-url URL] [--key-stdin | --delete-key]`, `test [--model M]`,
`sandbox [elevated|unelevated|remove]` (non-Windows: "not applicable", exit 0),
`backup create|list|restore ID|original`, `diagnose [--text TEXT]`,
`profile list|add|use|remove`, `launch [cli|app] [-- codex args...]`, `env install|remove`,
`uninstall`, `--version`.
Keys only via getpass or stdin (`--key-stdin`). Every write: show diff, confirm (unless --yes),
back up, atomic write. Uninstall: remove managed provider tables, restore original top-level
model/model_provider (or remove them), remove sandbox only if the tool set it, delete stored
secret on confirmation, never delete backups or Codex data.
