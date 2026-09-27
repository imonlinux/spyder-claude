# spyder-claude

[![CI](https://github.com/imonlinux/spyder-claude/actions/workflows/ci.yml/badge.svg)](https://github.com/imonlinux/spyder-claude/actions/workflows/ci.yml)
[![PyPI downloads](https://img.shields.io/pepy/dt/spyder-claude)](https://pepy.tech/projects/spyder-claude)

A [Spyder IDE](https://www.spyder-ide.org/) plugin that lets you query Claude from a dockable panel inside the IDE.

Queries are handled by the [Claude Code CLI](https://claude.ai/code), so the plugin inherits your full Claude configuration — including any MCP servers you have connected.

## Requirements

- Spyder 6 (Flatpak, pip, conda, or standalone)
- [Claude Code CLI](https://claude.ai/code) installed on your system (for CLI mode)
- An Anthropic API key (for API mode or Claude Code login)
- Python `cryptography` library (automatically installed with the plugin)

## Installation

### 1. Install the plugin

**Flatpak Spyder:**
```bash
flatpak run --command=python3 org.spyder_ide.spyder -m pip install spyder-claude
```

**pip/conda/standalone Spyder:**
```bash
pip install spyder-claude
```

**To install from the latest development version:**
```bash
pip install git+https://github.com/imonlinux/spyder-claude.git
```

To install from source, replace `spyder-claude` with the path to a cloned copy:
```bash
git clone https://github.com/imonlinux/spyder-claude.git
# then substitute the path above, e.g.:
flatpak run --command=python3 org.spyder_ide.spyder -m pip install -e ./spyder-claude
```

### 2. (Flatpak only) Grant the host-spawn permission

This one-time step allows the sandboxed Spyder to run the `claude` binary on the host.

```bash
flatpak override --user --talk-name=org.freedesktop.Flatpak org.spyder_ide.spyder
```

### 3. Restart Spyder

### 4. Configure the plugin

Open **Tools → Preferences → Claude** and set:

| Setting | Description |
|---|---|
| Anthropic API key | Your API key. Required for API mode; optional in CLI mode (leave blank to use `claude login`). Stored in your system credential manager via Spyder's secure storage — not in the config file. Keys saved by older versions are migrated automatically on startup. |
| API base URL | Base URL for the API endpoint. Default: `https://api.anthropic.com`. Use alternative providers like z.ai by changing this. Used in both CLI and API mode. |
| Path to claude binary | Full path to the `claude` executable, e.g. `/home/user/.npm-global/bin/claude` (CLI mode only) |
| Model name | Model name to use in both modes. Anthropic: `opus`, `sonnet`, `haiku`. z.ai: `zai:glm-5.1`, `zai:glm-4.5`. Enter any model name supported by your provider. |
| System prompt | Optional text appended to Claude's default system prompt |

## Usage

The **Claude** panel appears as a dockable widget (find it under **View → Panes**).

- **Send** — query Claude with your typed prompt
- **Send with current file** — includes the active editor file as context
- **New Chat** — start a fresh conversation (clears display and session)
- **Clear** — clear the display only (conversation context is preserved)

Responses stream token-by-token. When Claude calls a tool (e.g. an MCP server), a `[tool: name]` indicator appears in the response area.

### Session Persistence

In **CLI mode**, conversations automatically persist across Spyder restarts. When you restart Spyder and open the Claude panel, your previous conversation is restored and you can continue where you left off. Sessions are securely stored and expire after 7 days.

Click **New Chat** to start a fresh conversation when needed.

**Note:** Session persistence is only available in CLI mode. API mode is stateless: each query is an independent request with no memory of previous queries. Use CLI mode for multi-turn conversations.

## Platform Support

spyder-claude is cross-platform and works on:

| Platform | Status | Notes |
|---|---|---|
| **Linux** | ✅ Fully supported | Native CLI mode, Flatpak mode with host-spawn permission |
| **macOS** | ✅ Fully supported | Native CLI mode, approval prompts work correctly |
| **Windows** | ✅ Fully supported | Native CLI mode, approval prompts work correctly |

**All platforms:** API mode works identically across platforms using the Anthropic Python SDK.

### Troubleshooting

**"It was not possible to save a configuration setting securely"**

This Spyder dialog appears when no system keyring backend is reachable (most
commonly a Flatpak Spyder that cannot talk to the host's keyring daemon).
spyder-claude detects this and falls back to storing the API key in the
Spyder config file, so the plugin keeps working — but for real secure
storage, follow the steps below.

#### Enabling secret storage on Flatpak installs

On Linux, "the system keyring" means the **Secret Service** D-Bus API,
provided on the host by either **gnome-keyring** (GNOME and most desktop
spins) or **KWallet** (KDE/Plasma) — both implement the same API, and only
one can own it per session. A Flatpak sandbox must be explicitly allowed to
talk to it.

1. **Check the host provides the service:**

   ```bash
   busctl --user list | grep -i secrets
   ```

   No output means no provider is running. Install one:

   ```bash
   sudo dnf install gnome-keyring    # Fedora-family; usually preinstalled
   ```

   On KDE, `kwalletd` ships with Plasma and provides the same interface.
   The keyring must also be *unlocked* — with PAM integration it unlocks at
   login (default on Fedora desktops).

2. **Grant the Spyder Flatpak access (one-time):**

   ```bash
   flatpak override --user --talk-name=org.freedesktop.secrets org.spyder_ide.spyder
   ```

3. **Verify the round-trip inside the sandbox:**

   ```bash
   flatpak run --command=python3 org.spyder_ide.spyder -c \
     "import keyring; print(keyring.get_keyring()); keyring.set_password('spyder_claude','probe','ok'); print(keyring.get_password('spyder_claude','probe')); keyring.delete_password('spyder_claude','probe')"
   ```

   Success looks like `keyring.backends.SecretService.Keyring (priority: 5)`
   followed by `ok`. If you see `keyring.backends.fail.Keyring`, the daemon
   is missing (step 1) or locked — unlock it once (e.g. in seahorse under
   "Login") or log out and back in.

4. **Fully restart Spyder.** A plaintext API key saved earlier (while no
   backend was reachable) is migrated into the keyring automatically on
   startup and removed from the config file. Verify out of band, from the
   host:

   ```bash
   sudo dnf install libsecret    # provides secret-tool
   secret-tool lookup service spyder_claude username api_key   # prints the key
   grep -i api_key ~/.var/app/org.spyder_ide.spyder/config/spyder-py3/spyder.ini   # no match = clean
   ```

   (The key is stored under service `spyder_claude`, username `api_key`; in
   seahorse it appears in the "Login" keyring as "Password for 'api_key' on
   'spyder_claude'".)

As a last resort, installing `keyrings.alt` into the Flatpak environment
also provides a backend — but it is a non-recommended, file-based one (see
the note in the Spyder dialog) and is not advised for API keys.

### Platform-Specific Notes

**Linux (Flatpak):**
- One-time permission required: `flatpak override --user --talk-name=org.freedesktop.Flatpak org.spyder_ide.spyder`
- Approval helper script executes via `flatpak-spawn --host` to escape sandbox

**macOS:**
- Helper script cached in `~/Library/Caches/spyder-claude/`
- No special permissions required

**Windows:**
- Helper script cached in `%LOCALAPPDATA%\spyder-claude\`
- If approval prompts don't appear, verify `python` or `python3` is in PATH
- Graceful fallback: if helper script fails, prompts appear in terminal

## Feature Matrix

| Feature | CLI Mode | API Mode |
|---|---|---|
| Streaming responses | ✅ | ✅ |
| Multi-turn conversations | ✅ | ❌ (each query is independent) |
| Tool use | ✅ | ❌ |
| MCP server support | ✅ | ❌ (Planned) |
| Approval UI prompts | ✅ | ❌ (no tool use to approve) |
| Session-based whitelisting | ✅ | ❌ |
| Session persistence (across restarts) | ✅ | ❌ |
| Secure API key storage | ✅ | ✅ |
| Custom API base URL | ✅ | ✅ |
| Alternate model providers | ✅ | ✅ (e.g., z.ai) |
| System prompt customization | ✅ | ✅ |

**Key Differences:**
- **CLI Mode:** Uses your existing `claude` CLI configuration. Inherits all connected MCP servers, profiles, and settings. Conversations persist across IDE restarts using Claude CLI's `--resume` parameter.
- **API Mode:** Direct Anthropic API integration with SDK. Faster startup, no subprocess overhead. Each query is an independent single-turn request — no conversation memory, tool use, or MCP servers. Use CLI mode for multi-turn and MCP workflows.

## Release Notes

### Version 0.3.2 (2026-09-27)

**Fixed:**
- 🔒 **Secure API key storage now actually works:** the 0.3.0 secure-storage
  scheme was never wired up, so keys typed in Preferences were still saved as
  plaintext in the config file. The API key field now uses the system keyring
  (Windows Credential Manager / macOS Keychain / Linux Secret Service), and a
  startup migration moves any existing plaintext key into the keyring
  automatically.
- 🛡️ **Keyring-less systems handled safely:** without a keyring backend the
  migration skips cleanly (no more modal dialog at startup), a failed keyring
  write never deletes the plaintext key, and reads fall back to the config
  file so the key keeps working.
- 📖 Feature matrix and notes corrected: API mode is single-turn and has no
  tool use, approval prompts, or MCP servers

**Changed:**
- ⚙️ Preferences: the API key, base URL, and model fields are now visible in
  CLI mode too (they are used by both modes); only the CLI binary path is
  mode-specific
- 🧹 Removed dead code (unused `--allowedTools` plumbing, no-op parser branch,
  unused `api_key_security.py` / `migration.py`)

**Added:**
- 🧪 Tests for the stream-JSON parser and the key-migration write path
- 📖 README guide for enabling keyring access on Flatpak installs

### Version 0.3.1 (2026-09-04)

- 🪟 Windows: permission helper installed under `%LOCALAPPDATA%\spyder-claude`
  and the mcp-config no longer hardcodes `python3` (fixes approval prompts
  never appearing)
- 🤖 CI: test matrix (Linux/Windows/macOS, Python 3.9 & 3.13) plus unmocked
  Windows/macOS smoke jobs

### Version 0.3.0 (2026-05-04)

**New Features:**
- 🔒 **Secure API key storage:** API keys are now encrypted using platform credential managers (Windows DPAPI, macOS Keychain, Linux Secret Service) with fallback to encrypted file storage
- 💾 **Session persistence:** Conversations now persist across IDE restarts in CLI mode using Claude CLI's `--resume` parameter
- 🛡️ **Cross-platform security:** Automatic platform detection with graceful fallbacks ensures secure storage on all platforms
- 🔄 **Automatic migration:** Existing plaintext API keys are automatically migrated to secure storage on first startup
- 📅 **Session expiration:** Persisted sessions automatically expire after 7 days for security

**Improvements:**
- 🔧 Enhanced security architecture using Fernet encryption (AES-128-CBC)
- 🔧 System-specific key derivation prevents unauthorized access across machines
- 🔧 Visual feedback when previous conversation is restored
- 🔧 Better error handling for encryption failures

**Known Limitations:**
- Session persistence only available in CLI mode (API mode limited by Anthropic SDK architecture)
- API mode maintains conversation context during IDE session but doesn't persist across restarts
- Migration requires `cryptography` library (automatically installed)

**Technical Details:**
- Encryption: Fernet symmetric encryption (AES-128-CBC) with system-specific key derivation
- Platform storage: Native OS credential managers when available, encrypted file fallback otherwise
- Session storage: JSON format with secure encryption, 7-day expiration
- Migration: Automatic detection and migration of plaintext keys with rollback safety

### Version 0.2.2 (2026-04-24)

**New Features:**
- ✨ **Comprehensive test suite:** 25 tests covering configuration, platform detection, helper scripts, and plugin structure

**Improvements:**
- 🔧 Added pytest configuration and dev dependencies
- 🔧 Better test coverage for critical components

### Version 0.2.1 (2026-04-22)

**New Features:**
- ✨ **Dual mode operation:** Choose between Claude Code CLI or direct API mode
- ✨ **Approval UI:** Interactive modal dialogs for tool call approvals in both modes
- ✨ **Session whitelisting:** "Allow always" option for trusted tools within a conversation
- ✨ **Thread safety:** Fixed critical thread safety issues for stable multi-turn conversations
- ✨ **Cross-platform:** Fully tested on Linux, macOS, and Windows

**Improvements:**
- 🔧 Refactored worker lifecycle: fresh worker per query prevents state leakage
- 🔧 Mutex-protected query execution eliminates race conditions
- 🔧 Graceful shutdown and cancellation handling
- 🔧 Better error messages and status indicators

**Known Limitations:**
- API mode does not support MCP servers (use CLI mode for MCP workflows)
- Windows may need manual `python` command verification if approval prompts don't appear
- API keys stored in plaintext (resolved in v0.3.0)

**Technical Details:**
- Approval system uses 3-tier architecture: Qt UI → ApprovalServer (QTcpServer) → permission_helper (MCP stdio) → Claude CLI
- Flatpak sandbox escape via XDG_CACHE_HOME bind-mount for helper script execution
- Thread pattern: fresh QThread per query, no parent, QMutex-protected critical sections

## How it works

Each query runs:

```
flatpak-spawn --host <claude_path> -p --verbose \
  --output-format stream-json --include-partial-messages \
  [--resume <session_id>] [--model <model>] \
  [--append-system-prompt <prompt>] \
  "<user prompt>"
```

The plugin sets the `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` environment variables as needed, then parses the `stream-json` event stream to display text incrementally, surface tool calls, and capture the session ID for conversation continuity.

**Session Persistence:** In CLI mode, the session ID returned by Claude is securely stored and reused on subsequent queries, allowing conversations to continue across IDE restarts. The `--resume <session_id>` parameter automatically resumes previous conversations.

**Secure Storage:** API keys are encrypted using Fernet (AES-128-CBC) and stored using platform credential managers when available:
- **Windows:** DPAPI via pywin32
- **macOS:** Keychain Services (native)
- **Linux:** Secret Service API (GNOME Keyring/KWallet)
- **Fallback:** Encrypted file storage with system-specific key derivation

Existing plaintext keys are automatically migrated to secure storage on first startup.

## License

MIT
