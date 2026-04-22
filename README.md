# spyder-claude

A [Spyder IDE](https://www.spyder-ide.org/) plugin that lets you query Claude from a dockable panel inside the IDE.

Queries are handled by the [Claude Code CLI](https://claude.ai/code), so the plugin inherits your full Claude configuration — including any MCP servers you have connected.

## Requirements

- Spyder 6 (Flatpak, pip, conda, or standalone)
- [Claude Code CLI](https://claude.ai/code) installed on your system (for CLI mode)
- An Anthropic API key (for API mode or Claude Code login)

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
| Anthropic API key | Your API key (stored locally, masked in UI). Leave blank if you use `claude login`. |
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
| Custom API base URL | ✅ | ✅ |
| Alternate model providers | ✅ | ✅ (e.g., z.ai) |
| System prompt customization | ✅ | ✅ |

**Key Differences:**
- **CLI Mode:** Uses your existing `claude` CLI configuration. Inherits all connected MCP servers, profiles, and settings.
- **API Mode:** Direct Anthropic API integration with SDK. Faster startup, no subprocess overhead. Currently does not support MCP servers.

## Release Notes

### Version 0.2.0 (2026-04-22)

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
- Session continuity in API mode requires explicit implementation (planned for next release)
- Windows may need manual `python` command verification if approval prompts don't appear
- API keys stored in plaintext (documented in preferences with warning)

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

## License

MIT
