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
            "api_key": "",
            "claude_path": "",
            "model": "sonnet",
            "system_prompt": "",
        },
    )
]

CONF_VERSION = "1.0.0"
