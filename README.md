# spyder-claude

A [Spyder IDE](https://www.spyder-ide.org/) plugin that lets you query Claude from a dockable panel inside the IDE.

Queries are handled by the [Claude Code CLI](https://claude.ai/code), so the plugin inherits your full Claude configuration — including any MCP servers you have connected.

## Requirements

- Spyder 6 (Flatpak, pip, conda, or standalone)
- [Claude Code CLI](https://claude.ai/code) installed on your system
- An Anthropic API key (or Claude Code login)

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
git clone https://github.com/YOUR_USERNAME/spyder-claude.git
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
| Path to claude binary | Full path to the `claude` executable, e.g. `/home/user/.npm-global/bin/claude` |
| Model | `sonnet` (default), `opus`, or `haiku` |
| System prompt | Optional text appended to Claude's default system prompt |

## Usage

The **Claude** panel appears as a dockable widget (find it under **View → Panes**).

- **Send** — query Claude with your typed prompt
- **Send with current file** — includes the active editor file as context
- **New Chat** — start a fresh conversation (clears display and session)
- **Clear** — clear the display only (conversation context is preserved)

Responses stream token-by-token. When Claude calls a tool (e.g. an MCP server), a `[tool: name]` indicator appears in the response area.

## How it works

Each query runs:

```
flatpak-spawn --host <claude_path> -p --verbose \
  --output-format stream-json --include-partial-messages \
  [--resume <session_id>] [--model <model>] \
  [--append-system-prompt <prompt>] \
  "<user prompt>"
```

The plugin parses the `stream-json` event stream to display text incrementally, surface tool calls, and capture the session ID for conversation continuity.

## License

MIT
