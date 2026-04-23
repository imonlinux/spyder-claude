# -*- coding: utf-8 -*-
"""Test configuration defaults and loading."""

import pytest

from spyder_claude.config import (
    CONF_DEFAULTS,
    CONF_SECTION,
    CONF_VERSION,
)


class TestConfig:
    """Test plugin configuration."""

    def test_conf_section_exists(self):
        """Test that CONF_SECTION is defined."""
        assert CONF_SECTION == "spyder_claude"

    def test_conf_defaults_structure(self):
        """Test that CONF_DEFAULTS has correct structure."""
        assert isinstance(CONF_DEFAULTS, list)
        assert len(CONF_DEFAULTS) == 1

        section, defaults = CONF_DEFAULTS[0]
        assert section == CONF_SECTION
        assert isinstance(defaults, dict)

    def test_conf_defaults_values(self):
        """Test that all default values are set correctly."""
        _, defaults = CONF_DEFAULTS[0]

        # Check all expected keys exist
        expected_keys = [
            "use_cli",
            "api_key",
            "base_url",
            "claude_path",
            "model",
            "system_prompt",
        ]
        for key in expected_keys:
            assert key in defaults

        # Check default values
        assert defaults["use_cli"] is True
        assert defaults["api_key"] == ""
        assert defaults["base_url"] == "https://api.anthropic.com"
        assert defaults["claude_path"] == ""
        assert defaults["model"] == "sonnet"
        assert defaults["system_prompt"] == ""

    def test_conf_version_exists(self):
        """Test that CONF_VERSION is defined."""
        assert CONF_VERSION == "1.0.0"

    def test_conf_types(self):
        """Test that config values have correct types."""
        _, defaults = CONF_DEFAULTS[0]

        assert isinstance(defaults["use_cli"], bool)
        assert isinstance(defaults["api_key"], str)
        assert isinstance(defaults["base_url"], str)
        assert isinstance(defaults["claude_path"], str)
        assert isinstance(defaults["model"], str)
        assert isinstance(defaults["system_prompt"], str)
