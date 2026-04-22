# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Preferences page for spyder-claude."""

import os

from qtpy.QtWidgets import QCheckBox, QGroupBox, QLineEdit, QVBoxLayout, QWidget

from spyder.api.preferences import PluginConfigPage
from spyder.api.translations import _


class ClaudeConfigPage(PluginConfigPage):
    """Spyder Preferences page for the Claude plugin."""

    def setup_page(self):
        # ---- Integration mode ----------------------------------------------
        mode_group = QGroupBox(_("Integration Mode"))

        use_cli_checkbox = self.create_checkbox(
            _("Use Claude Code CLI"),
            "use_cli",
            tip=_(
                "When checked, uses the claude CLI binary. "
                "When unchecked, uses the Anthropic API directly with SDK."
            ),
        )
        self.use_cli_checkbox = use_cli_checkbox

        mode_layout = QVBoxLayout()
        mode_layout.addWidget(use_cli_checkbox)
        mode_group.setLayout(mode_layout)

        # ---- Authentication (API mode) -------------------------------------
        auth_group = QGroupBox(_("API Configuration"))
        self.auth_group = auth_group

        api_key_widget = self.create_lineedit(
            _("Anthropic API key"),
            "api_key",
            tip=_(
                "Your Anthropic API key. "
                "Required when using API mode. "
                "WARNING: stored in plaintext in Spyder's local configuration "
                "file."
            ),
        )
        api_key_widget.textbox.setEchoMode(QLineEdit.Password)
        self.api_key_widget = api_key_widget

        base_url_widget = self.create_lineedit(
            _("API base URL"),
            "base_url",
            tip=_(
                "Base URL for the API endpoint. "
                "Default: https://api.anthropic.com. "
                "Use alternative providers like z.ai by changing this."
            ),
            validate_callback=lambda url: not url or url.startswith(
                ("http://", "https://")
            ),
            validate_reason=_("Base URL must start with http:// or https://"),
        )
        self.base_url_widget = base_url_widget

        auth_layout = QVBoxLayout()
        auth_layout.addWidget(api_key_widget)
        auth_layout.addWidget(base_url_widget)
        auth_group.setLayout(auth_layout)

        # ---- Claude CLI ----------------------------------------------------
        cli_group = QGroupBox(_("Claude CLI Configuration"))
        self.cli_group = cli_group

        claude_path_widget = self.create_lineedit(
            _("Path to claude binary"),
            "claude_path",
            tip=_(
                "Full path to the claude executable on the host system. "
                "Example: /home/user/.npm-global/bin/claude"
            ),
            validate_callback=lambda path: not path or os.path.isfile(path),
            validate_reason=_("No file found at this path"),
        )
        self.claude_path_widget = claude_path_widget

        cli_layout = QVBoxLayout()
        cli_layout.addWidget(claude_path_widget)
        cli_group.setLayout(cli_layout)

        # ---- Model selection -----------------------------------------------
        model_group = QGroupBox(_("Model"))
        self.model_group = model_group

        model_widget = self.create_lineedit(
            _("Model name"),
            "model",
            tip=_(
                "Model name to use for queries. "
                "For API mode: claude-sonnet-4-6, claude-opus-4-6, claude-haiku-4-5. "
                "For CLI mode: sonnet, opus, haiku, or provider models like zai:glm-5.1. "
                "Enter any model name supported by your API provider."
            ),
        )
        self.model_widget = model_widget

        model_layout = QVBoxLayout()
        model_layout.addWidget(model_widget)
        model_group.setLayout(model_layout)

        # ---- System prompt -------------------------------------------------
        prompt_group = QGroupBox(_("System prompt (optional)"))

        system_prompt_widget = self.create_textedit(
            _("System prompt"),
            "system_prompt",
            tip=_(
                "For API mode: this custom prompt replaces the default system prompt. "
                "For CLI mode: appended to Claude's default system prompt (--append-system-prompt). "
                "Leave blank to use Claude's default behaviour."
            ),
        )

        prompt_layout = QVBoxLayout()
        prompt_layout.addWidget(system_prompt_widget)
        prompt_group.setLayout(prompt_layout)

        # ---- Main layout ---------------------------------------------------
        main_layout = QVBoxLayout()
        main_layout.addWidget(mode_group)
        main_layout.addWidget(auth_group)
        main_layout.addWidget(cli_group)
        main_layout.addWidget(model_group)
        main_layout.addWidget(prompt_group)
        main_layout.addStretch(1)
        self.setLayout(main_layout)

        # ---- Connect signals ------------------------------------------------
        # create_checkbox returns a container, we need to find the actual checkbox
        # The checkbox is typically the first child of the container
        checkbox = None
        for child in use_cli_checkbox.children():
            if hasattr(child, 'toggled'):
                checkbox = child
                break

        if checkbox:
            checkbox.toggled.connect(self._on_mode_changed)

        # ---- Initial state -------------------------------------------------
        initial_state = self.get_option("use_cli")
        self._on_mode_changed(initial_state)

    def _on_mode_changed(self, use_cli: bool):
        """Show/hide fields based on integration mode."""
        if use_cli:
            # CLI mode: show CLI path, hide API and model fields
            self.cli_group.setVisible(True)
            self.auth_group.setVisible(False)
            self.model_group.setVisible(False)
        else:
            # API mode: show API fields and model, hide CLI path
            self.cli_group.setVisible(False)
            self.auth_group.setVisible(True)
            self.model_group.setVisible(True)
