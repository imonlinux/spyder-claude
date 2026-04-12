# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Preferences page for spyder-claude."""

from qtpy.QtWidgets import QGroupBox, QLineEdit, QVBoxLayout

from spyder.api.preferences import PluginConfigPage
from spyder.api.translations import _


class ClaudeConfigPage(PluginConfigPage):
    """Spyder Preferences page for the Claude plugin."""

    def setup_page(self):
        # ---- Authentication ------------------------------------------------
        auth_group = QGroupBox(_("Authentication"))

        api_key_widget = self.create_lineedit(
            _("Anthropic API key"),
            "api_key",
            tip=_(
                "Your Anthropic API key. "
                "Stored in Spyder's local configuration file."
            ),
        )
        api_key_widget.textbox.setEchoMode(QLineEdit.Password)

        auth_layout = QVBoxLayout()
        auth_layout.addWidget(api_key_widget)
        auth_group.setLayout(auth_layout)

        # ---- Claude CLI ----------------------------------------------------
        cli_group = QGroupBox(_("Claude CLI"))

        claude_path_widget = self.create_lineedit(
            _("Path to claude binary"),
            "claude_path",
            tip=_(
                "Full path to the claude executable on the host system. "
                "Example: /home/user/.npm-global/bin/claude"
            ),
        )

        cli_layout = QVBoxLayout()
        cli_layout.addWidget(claude_path_widget)
        cli_group.setLayout(cli_layout)

        # ---- Model selection -----------------------------------------------
        model_group = QGroupBox(_("Model"))

        model_widget = self.create_combobox(
            _("Claude model"),
            [
                ("Claude Opus 4.6 (most capable)", "opus"),
                ("Claude Sonnet 4.6 (balanced)", "sonnet"),
                ("Claude Haiku 4.5 (fastest)", "haiku"),
            ],
            "model",
            tip=_("Which Claude model to use for queries."),
        )

        model_layout = QVBoxLayout()
        model_layout.addWidget(model_widget)
        model_group.setLayout(model_layout)

        # ---- System prompt -------------------------------------------------
        prompt_group = QGroupBox(_("System prompt (optional)"))

        system_prompt_widget = self.create_textedit(
            _("System prompt"),
            "system_prompt",
            tip=_(
                "Appended to Claude's default system prompt (--append-system-prompt). "
                "Leave blank to use Claude's default behaviour."
            ),
        )

        prompt_layout = QVBoxLayout()
        prompt_layout.addWidget(system_prompt_widget)
        prompt_group.setLayout(prompt_layout)

        # ---- Main layout ---------------------------------------------------
        main_layout = QVBoxLayout()
        main_layout.addWidget(auth_group)
        main_layout.addWidget(cli_group)
        main_layout.addWidget(model_group)
        main_layout.addWidget(prompt_group)
        main_layout.addStretch(1)
        self.setLayout(main_layout)
