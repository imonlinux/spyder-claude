# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Configuration defaults for the spyder-claude plugin."""

CONF_SECTION = "spyder_claude"

# (section, {option: default}) format required when CONF_FILE = True.
CONF_DEFAULTS = [
    (
        CONF_SECTION,
        {
            "use_cli": True,
            "api_key": "",
            "base_url": "https://api.anthropic.com",
            "claude_path": "",
            "model": "sonnet",
            "system_prompt": "",
        },
    )
]

CONF_VERSION = "1.0.0"

# Value older builds wrote into the config instead of the real key. Their
# secure-storage scheme was never wired up, so nothing is actually stored
# behind it and users seeing this must re-enter their key.
LEGACY_SECURE_PLACEHOLDER = "SECURE:stored"
