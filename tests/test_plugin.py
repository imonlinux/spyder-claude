# -*- coding: utf-8 -*-
"""Test SpyderClaude plugin class."""

from unittest.mock import MagicMock, patch

import pytest

from spyder_claude.plugin import SpyderClaude


class TestSpyderClaudePlugin:
    """Test SpyderClaude plugin initialization and configuration."""

    def test_plugin_can_be_imported(self):
        """Test that SpyderClaude plugin can be imported."""
        assert SpyderClaude is not None

    def test_plugin_module_structure(self):
        """Test that plugin module has correct structure."""
        from spyder_claude import plugin

        # Check that the module has the expected content
        assert hasattr(plugin, "SpyderClaude")
        assert hasattr(plugin, "logger")
