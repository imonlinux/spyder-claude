# -*- coding: utf-8 -*-
"""Pytest configuration and fixtures for spyder-claude tests."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add the package to the path
package_root = Path(__file__).parent.parent
sys.path.insert(0, str(package_root))

# Mock Qt modules BEFORE any imports happen
# This needs to be at module level in conftest.py to run before test collection
sys.modules["qtpy"] = MagicMock()
sys.modules["qtpy.QtCore"] = MagicMock()
sys.modules["qtpy.QtGui"] = MagicMock()
sys.modules["qtpy.QtWidgets"] = MagicMock()
sys.modules["qtpy.QtNetwork"] = MagicMock()
sys.modules["qtpy.QtSvg"] = MagicMock()

# Create mock objects for Spyder API that will be used by the real plugin
mock_plugins = MagicMock()
mock_plugins.Preferences = MagicMock()
mock_plugins.Editor = MagicMock()

mock_plugin_registration = MagicMock()
mock_plugin_registration.decorators = MagicMock()
mock_plugin_registration.on_plugin_available = MagicMock()
mock_plugin_registration.on_plugin_teardown = MagicMock()

# Mock Spyder API modules with proper structure
sys.modules["spyder"] = MagicMock()
sys.modules["spyder.api"] = MagicMock()
sys.modules["spyder.api.plugins"] = MagicMock()
sys.modules["spyder.api.plugins"].Plugins = mock_plugins
sys.modules["spyder.api.plugin_registration"] = mock_plugin_registration
sys.modules["spyder.api.plugin_registration.decorators"] = mock_plugin_registration.decorators
sys.modules["spyder.api.translations"] = MagicMock()
sys.modules["spyder.api.preferences"] = MagicMock()
sys.modules["spyder.utils"] = MagicMock()
sys.modules["spyder.utils.icon_manager"] = MagicMock()
sys.modules["spyder.api.widgets"] = MagicMock()
sys.modules["spyder.api.widgets.main_widget"] = MagicMock()
sys.modules["spyder.api.widgets.auxiliary_widgets"] = MagicMock()
sys.modules["spyder.api.widgets.mixins"] = MagicMock()
sys.modules["anthropic"] = MagicMock()


@pytest.fixture
def mock_qt():
    """Mock Qt components for headless testing."""
    """This fixture patches Qt components to allow testing without a display."""
    yield


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory for testing."""
    cache_dir = tmp_path / "cache" / "spyder-claude"
    cache_dir.mkdir(parents=True)
    return cache_dir


@pytest.fixture
def mock_editor():
    """Create a mock Spyder editor widget."""
    editor = MagicMock()
    mock_file = MagicMock()
    mock_file.toPlainText.return_value = "def test():\n    pass"
    editor.get_current_editor.return_value = mock_file
    editor.get_current_filename.return_value = "test_file.py"
    return editor


@pytest.fixture
def sample_config():
    """Provide sample configuration values."""
    return {
        "use_cli": True,
        "api_key": "",
        "base_url": "https://api.anthropic.com",
        "claude_path": "/usr/bin/claude",
        "model": "sonnet",
        "system_prompt": "",
    }
