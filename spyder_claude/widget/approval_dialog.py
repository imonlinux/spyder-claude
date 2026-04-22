# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Modal approval dialog shown when Claude requests permission to use a tool."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from spyder.api.translations import _


# --- Decision constants -----------------------------------------------------

ALLOW_ONCE = "allow_once"
ALLOW_ALWAYS = "allow_always"
DENY = "deny"


def _summarize_input(tool_name: str, tool_input: Any) -> str:
    """Short human-readable summary of the tool call, shown prominently."""
    if not isinstance(tool_input, dict):
        return _("(no details)")

    # Common cases — pull out the most useful single field for each tool.
    if tool_name == "Bash":
        cmd = str(tool_input.get("command", "")).strip()
        return cmd or _("(empty command)")
    if tool_name in {"Write", "Edit", "MultiEdit", "NotebookEdit"}:
        return str(tool_input.get("file_path", "")) or _("(no path)")
    if tool_name == "Read":
        return str(tool_input.get("file_path", "")) or _("(no path)")
    if tool_name == "WebFetch":
        return str(tool_input.get("url", "")) or _("(no url)")
    if tool_name == "Grep":
        return str(tool_input.get("pattern", "")) or _("(no pattern)")
    if tool_name == "Glob":
        return str(tool_input.get("pattern", "")) or _("(no pattern)")

    # Fallback: the first non-trivial string value, if any.
    for key in ("command", "file_path", "path", "url", "pattern", "query"):
        if key in tool_input and tool_input[key]:
            return str(tool_input[key])
    return _("(see full details below)")


def _format_full_input(tool_input: Any) -> str:
    try:
        return json.dumps(tool_input, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(tool_input)


class ApprovalDialog(QDialog):
    """Modal dialog that asks the user to approve a Claude tool call."""

    def __init__(
        self,
        tool_name: str,
        tool_input: Any,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Claude — Tool Approval"))
        self.setModal(True)
        # Window-modal so it blocks just the Spyder window, not the app.
        self.setWindowModality(Qt.WindowModal)

        self._tool_name = tool_name
        self._decision: str = DENY  # default if dialog is closed with [X]

        layout = QVBoxLayout(self)

        # Top line: "Claude wants to use: <tool>"
        header = QLabel(
            _("Claude wants to use <b>{tool}</b>:").format(tool=tool_name),
            self,
        )
        header.setTextFormat(Qt.RichText)
        layout.addWidget(header)

        # Summary: the most important single string (command, path, url, …).
        summary = QLabel(_summarize_input(tool_name, tool_input), self)
        summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        summary.setWordWrap(True)
        summary.setStyleSheet(
            "QLabel { padding: 6px; border: 1px solid palette(mid); "
            "background: palette(base); font-family: monospace; }"
        )
        layout.addWidget(summary)

        # Full arguments, collapsed-ish. Read-only, selectable.
        details_label = QLabel(_("Full arguments:"), self)
        layout.addWidget(details_label)

        self._details = QPlainTextEdit(self)
        self._details.setReadOnly(True)
        self._details.setPlainText(_format_full_input(tool_input))
        self._details.setMaximumHeight(160)
        layout.addWidget(self._details)

        warning = QLabel(
            _(
                "Only allow if you trust the action. "
                "“Allow always” applies only to this conversation."
            ),
            self,
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("color: palette(mid);")
        layout.addWidget(warning)

        # Buttons.
        buttons = QDialogButtonBox(self)
        self._btn_deny = buttons.addButton(
            _("Deny"), QDialogButtonBox.RejectRole
        )
        self._btn_allow = buttons.addButton(
            _("Allow once"), QDialogButtonBox.AcceptRole
        )
        self._btn_always = buttons.addButton(
            _("Allow always (this session)"), QDialogButtonBox.AcceptRole
        )

        self._btn_deny.clicked.connect(self._on_deny)
        self._btn_allow.clicked.connect(self._on_allow)
        self._btn_always.clicked.connect(self._on_always)

        # Safer default: Deny is the default-focused button. Esc also denies.
        self._btn_deny.setDefault(True)
        self._btn_deny.setAutoDefault(True)

        layout.addWidget(buttons)

        self.resize(520, 380)

    # ---- Button slots -----------------------------------------------------

    def _on_deny(self) -> None:
        self._decision = DENY
        self.reject()

    def _on_allow(self) -> None:
        self._decision = ALLOW_ONCE
        self.accept()

    def _on_always(self) -> None:
        self._decision = ALLOW_ALWAYS
        self.accept()

    # ---- Public -----------------------------------------------------------

    @property
    def decision(self) -> str:
        return self._decision

    @classmethod
    def ask(
        cls,
        tool_name: str,
        tool_input: Any,
        parent: Optional[QWidget] = None,
    ) -> Tuple[str, Any]:
        """Run the dialog and return (decision, original_input).

        decision is one of ALLOW_ONCE, ALLOW_ALWAYS, DENY.
        """
        dlg = cls(tool_name, tool_input, parent)
        dlg.exec_()
        return dlg.decision, tool_input
