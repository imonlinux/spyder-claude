# Test Suite for spyder-claude

This directory contains the test suite for the spyder-claude plugin.

## Test Structure

- `test_config.py` - Tests for configuration defaults and loading
- `test_platform_utils.py` - Tests for platform detection and helper script bootstrap
- `test_plugin.py` - Tests for the main SpyderClaude plugin class
- `test_approval.py` - Tests for approval dialog and server components
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

3. **Plugin** (`test_plugin.py`)
   - Plugin metadata and dependencies
   - Initialization and configuration
   - Editor content integration
   - Shutdown handling

4. **Approval System** (`test_approval.py`)
   - Approval dialog constants
   - Dialog component initialization
   - Approval server component

## Notes

- Tests use mocking to avoid requiring a running Qt display
- Some tests may not run correctly without a full Spyder environment
- Integration tests for CLI mode and API mode require the actual `claude` binary

## Future Additions

Potential areas for more tests:
- Main widget query execution
- CLI mode subprocess invocation
- API mode Anthropic client integration
- Thread safety and mutex protection
- Cross-platform helper script execution
- Preference page widget
