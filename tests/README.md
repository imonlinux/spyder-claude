# Test Suite for spyder-claude

This directory contains the test suite for the spyder-claude plugin.

## Test Structure

- `test_config.py` - Tests for configuration defaults and loading
- `test_platform_utils.py` - Tests for platform detection and helper script bootstrap
- `test_plugin.py` - Tests for the main SpyderClaude plugin class
- `test_plugin_migration.py` - Tests for the plaintext API key → keyring migration
- `test_handle_event.py` - Tests for claude CLI stream-JSON event parsing
- `test_approval.py` - Tests for approval dialog and server components
- `test_smoke_platforms.py` - Unmocked platform tests (run on real Windows/macOS in CI)
- `conftest.py` - Pytest fixtures and configuration

## Running Tests

### Using pytest directly:
```bash
pytest
```

### Using the python_test MCP tool:
```bash
python_test --project=/path/to/spyder-claude
```

### With coverage:
```bash
pytest --cov=spyder_claude --cov-report=html
```

### Run specific test file:
```bash
pytest tests/test_config.py
```

### Run specific test:
```bash
pytest tests/test_config.py::TestConfig::test_conf_section_exists
```

## Test Coverage

The test suite covers:

1. **Configuration** (`test_config.py`)
   - Configuration section and defaults
   - Default values and types
   - Configuration version

2. **Platform Utilities** (`test_platform_utils.py`)
   - Flatpak detection
   - Path translation for sandbox escape
   - Helper script bootstrap

3. **Plugin / Migration** (`test_plugin.py`, `test_plugin_migration.py`)
   - Plugin metadata and dependencies
   - Plaintext API key → keyring migration (empty, placeholder, valid,
     failure cases) and its wiring into the plugin startup path

4. **Approval System** (`test_approval.py`)
   - Approval dialog constants
   - Dialog component initialization
   - Approval server component

5. **Stream-JSON parsing** (`test_handle_event.py`)
   - Text delta streaming, tool-use announcements, tool results
   - Session-id and error propagation from result events
   - Malformed / non-object JSON lines are ignored safely

## Notes

- Tests use mocking to avoid requiring a running Qt display. Because the
  Spyder API is mocked, classes whose bases come from Spyder/Qt (e.g.
  `ClaudeMainWidget`, the workers) become MagicMocks themselves; testable
  logic therefore lives in module-level functions (e.g. `_parse_stream_event`,
  `migrate_plaintext_api_key`) and is tested directly.
- Integration tests for CLI mode and API mode require the actual `claude` binary.

## Future Additions

Potential areas for more tests:
- Main widget query execution
- CLI mode subprocess invocation
- API mode Anthropic client integration
- Thread safety and mutex protection
- Cross-platform helper script execution
- Preference page widget
