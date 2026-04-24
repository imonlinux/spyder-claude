# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/imonlinux/spyder-claude/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/imonlinux/spyder-claude/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/imonlinux/spyder-claude/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/imonlinux/spyder-claude/releases/tag/v0.2.0
