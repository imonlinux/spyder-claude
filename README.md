# spyder-claude

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
| Anthropic API key | Your API key (securely stored using platform credential manager, masked in UI). Leave blank if you use `claude login`. |
| API base URL | Base URL for the API endpoint. Default: `https://api.anthropic.com`. Use alternative providers like z.ai by changing this. |
| Path to claude binary | Full path to the `claude` executable, e.g. `/home/user/.npm-global/bin/claude` |
| Model name | Model name to use. Anthropic: `opus`, `sonnet`, `haiku`. z.ai: `zai:glm-5.1`, `zai:glm-4.5`. Enter any model name supported by your provider. |
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

**Note:** Session persistence is only available in CLI mode. API mode maintains conversation context during the IDE session but does not persist across restarts due to Anthropic API SDK architecture.

## Platform Support

spyder-claude is cross-platform and works on:

| Platform | Status | Notes |
|---|---|---|
| **Linux** | ✅ Fully supported | Native CLI mode, Flatpak mode with host-spawn permission |
| **macOS** | ✅ Fully supported | Native CLI mode, approval prompts work correctly |
| **Windows** | ✅ Fully supported | Native CLI mode, approval prompts work correctly |

**All platforms:** API mode works identically across platforms using the Anthropic Python SDK.

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
| Multi-turn conversations | ✅ | ✅ |
| MCP server support | ✅ | ❌ (Planned) |
| Approval UI prompts | ✅ | ✅ |
| Session-based whitelisting | ✅ | ✅ |
| Session persistence (across restarts) | ✅ | ❌ |
| Secure API key storage | ✅ | ✅ |
| Custom API base URL | ✅ | ✅ |
| Alternate model providers | ✅ | ✅ (e.g., z.ai) |
| System prompt customization | ✅ | ✅ |

**Key Differences:**
- **CLI Mode:** Uses your existing `claude` CLI configuration. Inherits all connected MCP servers, profiles, and settings. Conversations persist across IDE restarts using Claude CLI's `--resume` parameter.
- **API Mode:** Direct Anthropic API integration with SDK. Faster startup, no subprocess overhead. Currently does not support MCP servers. Session persistence is limited to current IDE session (API SDK doesn't expose session IDs).

## Release Notes

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
