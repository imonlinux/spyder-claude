# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.2] - 2026-09-27

### Fixed
- **Secure API key storage** — the v0.3.0 secure-storage scheme (migration
  manager, `SECURE:stored` placeholder, custom Fernet layer) was never wired
  into the plugin: keys typed into Preferences were still written to Spyder's
  config file as plaintext. The API key preference now uses the system
  keyring (`keyring` → Windows Credential Manager / macOS Keychain / Linux
  Secret Service), and on startup any plaintext key found in the config is
  moved into the keyring and removed from the config file.
  A key left behind by v0.3.0–0.3.1 as the `SECURE:stored` placeholder was
  never actually stored and must be re-entered (the plugin logs a warning).
- **Systems without a keyring backend** are handled gracefully instead of
  popping Spyder's "It was not possible to save a configuration setting
  securely" dialog on every startup: the migration checks for a usable
  backend first, writes to the keyring directly (so a failed write aborts
  instead of deleting the plaintext original), and falls back to keeping the
  key in the config file, where it is still used. The Preferences field
  likewise stores into the config file when no backend is available.
- Documentation drift: the README claimed API mode maintains conversation
  context and supports approval prompts — in reality each API query is an
  independent single-turn request with no tool use. Feature matrix corrected.

### Changed
- Preferences page: the API key, base URL, and model fields are shown in both
  CLI and API mode (all three are consumed by both code paths); only the
  claude binary path is CLI-specific.
- Removed dead code: the unused `--allowedTools` plumbing on the CLI worker,
  the no-op `assistant` branch of the stream-JSON parser, and the unused
  `api_key_security.py` / `migration.py` modules.

### Added
- README guide for enabling keyring access on Flatpak installs (Secret
  Service provider check, `flatpak override` grant, sandbox round-trip
  verification, and out-of-band key checks)
- Tests for the stream-JSON event parser (`_parse_stream_event`, 20 cases)
  and for the plaintext-key migration write path (7 cases)
- macOS keychain detection no longer probes `security -h`, which exits
  non-zero on current macOS and silently pushed users to the weak file
  storage fallback; it now checks for the binary's existence
- Windows DPAPI storage no longer creates a literal `~/` directory when
  `APPDATA` is unset; PyQt6 compatibility fixes for the approval dialog
  (`exec()`) and text-cursor enum access

## [0.3.1] - 2026-09-04

### Fixed
- Windows: the permission helper is now installed under
  `%LOCALAPPDATA%\spyder-claude` (with `%APPDATA%` and `~/AppData/Roaming`
  fallbacks), so the cache directory is actually created on Windows (#1)
- Windows: the generated mcp-config no longer hardcodes `python3` as the
  helper interpreter. On Windows `python3` is usually missing or is the
  Microsoft Store App Execution Alias stub, so the MCP server never started
  and approval prompts silently never appeared. The plugin now prefers the
  `py -3` launcher, then `python`, on Windows; Linux and macOS keep `python3`

### Added
- GitHub Actions CI: test matrix (Linux, Windows, macOS on Python 3.9 and
  3.13) plus unmocked Windows and macOS smoke jobs that verify
  cache-directory creation, helper installation, and interpreter selection
  on real operating systems
- CI badge in the README

## [0.3.0] - 2026-05-04

### Added
- **Session persistence** for CLI mode - conversations now continue across IDE restarts using Claude CLI's `--resume` parameter
- **Secure API key storage** - API keys encrypted using platform credential managers:
  - Windows: DPAPI via pywin32
  - macOS: Keychain Services (native)
  - Linux: Secret Service API (GNOME Keyring/KWallet)
  - Fallback: Encrypted file storage with system-specific key derivation
- **Automatic migration** - Existing plaintext API keys automatically migrated to secure storage on first startup
- **Session expiration** - Persisted sessions automatically expire after 7 days for security
- **Encryption module** - Fernet symmetric encryption (AES-128-CBC) with system-specific key derivation
- **Platform-specific secure storage** - Automatic platform detection with graceful fallbacks
- **Visual feedback** - Message displayed when previous conversation is restored

### Changed
- API keys now stored securely instead of plaintext in configuration files
- Configuration files use `"SECURE:stored"` placeholder for encrypted keys
- Enhanced error handling for encryption and secure storage operations

### Fixed
- Security vulnerability: API keys no longer stored in plaintext
- Session persistence now works correctly in CLI mode with proper encryption key derivation

### Technical Details
- Encryption: Fernet (AES-128-CBC) with base64-urlsafe encoded keys
- Key derivation: System-specific (hostname + user home directory) via SHA-256
- Platform detection: Automatic with graceful fallback to encrypted file storage
- Migration: Automatic detection of plaintext keys with rollback safety
- Session storage: JSON format with secure encryption, 7-day expiration
- Dependencies: Added `cryptography>=41.0.0` (automatically installed)

### Known Limitations
- Session persistence only available in CLI mode (API mode limited by Anthropic SDK architecture)
- API mode maintains conversation context during IDE session but doesn't persist across restarts

## [0.2.2] - 2026-04-24

### Added
- Comprehensive test suite with 25 tests covering:
  - Configuration defaults and validation
  - Platform detection (Flatpak, environment variables)
  - Helper script bootstrap functionality
  - Approval dialog and server components
  - Plugin module structure
- Pytest configuration and dev dependencies
- `tests/README.md` with test documentation and usage instructions

### Changed
- Updated `pyproject.toml` with pytest configuration
- Added optional dev dependencies for testing (pytest, pytest-cov, pytest-qt)

## [0.2.1] - 2026-04-22

### Added
- Dual mode operation (CLI mode vs API mode)
- Approval UI for tool call interactions
- Session whitelisting with "Allow always" option
- Thread safety fixes for multi-turn conversations
- Cross-platform support (Linux, macOS, Windows)
- Flatpak sandbox escape for helper script execution

### Fixed
- Critical thread safety issues in worker lifecycle
- State leakage between queries
- Race conditions in query execution

### Known Limitations
- API mode does not support MCP servers
- Session continuity in API mode requires explicit implementation
- API keys stored in plaintext (documented in preferences)

## [0.2.0] - 2026-04-XX

### Added
- Initial release of spyder-claude plugin
- Basic Claude integration within Spyder IDE
- Dockable Claude panel with query interface
- Support for including current editor file as context
- Multi-turn conversation support
- Streaming responses

[Unreleased]: https://github.com/imonlinux/spyder-claude/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/imonlinux/spyder-claude/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/imonlinux/spyder-claude/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/imonlinux/spyder-claude/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/imonlinux/spyder-claude/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/imonlinux/spyder-claude/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/imonlinux/spyder-claude/releases/tag/v0.2.0
