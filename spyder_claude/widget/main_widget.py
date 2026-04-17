# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Main dockable widget for spyder-claude."""

import json
import os
import subprocess

from qtpy.QtCore import QObject, QThread, Qt, Signal, Slot
from qtpy.QtGui import QKeySequence
from qtpy.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QShortcut,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from spyder.api.translations import _
from spyder.api.widgets.main_widget import PluginMainWidget


class _ClaudeWorker(QObject):
    """Runs a claude CLI call in a background QThread via flatpak-spawn.

    Uses --output-format stream-json so we can stream text incrementally,
    surface tool calls (e.g. Phantom MCP), and capture the session ID for
    conversation continuity.
    """

    sig_chunk = Signal(str)       # incremental text to append to response area
    sig_error = Signal(str)       # error message
    sig_finished = Signal()       # run complete
    sig_tool_use = Signal(str)    # tool name each time Claude calls a tool
    sig_session_id = Signal(str)  # session ID from the result event

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prompt = ""
        self._api_key = ""
        self._claude_path = ""
        self._model = "sonnet"
        self._system_prompt = ""
        self._session_id = ""

    def configure(
        self,
        prompt: str,
        api_key: str,
        claude_path: str,
        model: str,
        system_prompt: str,
        session_id: str = "",
    ):
        self._prompt = prompt
        self._api_key = api_key
        self._claude_path = claude_path
        self._model = model
        self._system_prompt = system_prompt
        self._session_id = session_id

    @Slot()
    def run(self):
        claude = self._claude_path.strip() or "claude"

        # Inside a Flatpak sandbox the claude binary lives on the host, so we
        # must use flatpak-spawn --host to reach it.  Outside Flatpak (pip,
        # conda, standalone Spyder) we invoke claude directly.
        if os.path.exists("/.flatpak-info") or "FLATPAK_ID" in os.environ:
            prefix = ["flatpak-spawn", "--host"]
        else:
            prefix = []

        cmd = [
            *prefix,
            claude, "-p",
            "--verbose",
            "--output-format", "stream-json",
            "--include-partial-messages",
        ]

        if self._session_id:
            cmd.extend(["--resume", self._session_id])
        if self._model:
            cmd.extend(["--model", self._model])
        if self._system_prompt:
            # append- preserves Claude's default context instead of replacing it
            cmd.extend(["--append-system-prompt", self._system_prompt])
        cmd.append(self._prompt)

        env = os.environ.copy()
        if self._api_key:
            env["ANTHROPIC_API_KEY"] = self._api_key

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )
            with proc:
                buf = b""

                while True:
                    chunk = proc.stdout.read(256)
                    if not chunk:
                        break
                    buf += chunk
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if line:
                            self._handle_event(
                                line.decode("utf-8", errors="replace")
                            )

                proc.wait()
                if proc.returncode != 0:
                    err = proc.stderr.read().decode("utf-8", errors="replace").strip()
                    self.sig_error.emit(
                        err or f"claude exited with code {proc.returncode}"
                    )

        except FileNotFoundError:
            if prefix:
                self.sig_error.emit(
                    f"Cannot find '{claude}' via flatpak-spawn. "
                    "Check the claude path in Preferences → Claude and ensure "
                    "Spyder has the org.freedesktop.Flatpak permission:\n"
                    "flatpak override --user "
                    "--talk-name=org.freedesktop.Flatpak org.spyder_ide.spyder"
                )
            else:
                self.sig_error.emit(
                    f"Cannot find '{claude}'. "
                    "Set the correct path to the claude binary in "
                    "Preferences → Claude."
                )
        except Exception as exc:
            self.sig_error.emit(str(exc))
        finally:
            self.sig_finished.emit()

    def _handle_event(self, line: str):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return

        etype = event.get("type")

        if etype == "stream_event":
            # Low-level API events: use these for true token-by-token streaming
            # and immediate tool-call notification.
            inner = event.get("event", {})
            itype = inner.get("type")

            if itype == "content_block_delta":
                delta = inner.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        self.sig_chunk.emit(text)

            elif itype == "content_block_start":
                block = inner.get("content_block", {})
                if block.get("type") == "tool_use":
                    self.sig_tool_use.emit(block.get("name", "tool"))

        elif etype == "result":
            if event.get("is_error"):
                self.sig_error.emit(event.get("result", "Unknown error"))
            session_id = event.get("session_id", "")
            if session_id:
                self.sig_session_id.emit(session_id)


class ClaudeMainWidget(PluginMainWidget):
    """Dockable panel for querying Claude via the claude CLI."""

    sig_editor_content_requested = Signal()

    # ---- PluginMainWidget API ----------------------------------------------

    def get_title(self):
        return _("Claude")

    def get_focus_widget(self):
        return self._input_area

    def setup(self):
        """Build the UI and wire up the background worker thread."""

        # --- Response area (top) ---
        self._response_area = QTextEdit(self)
        self._response_area.setReadOnly(True)
        self._response_area.setPlaceholderText(
            _("Claude's response will appear here…")
        )

        # --- Input area (bottom) ---
        self._input_area = QTextEdit(self)
        self._input_area.setPlaceholderText(_("Ask Claude something…"))
        self._input_area.setMaximumHeight(120)

        self._send_btn = QPushButton(_("Send"), self)
        self._send_file_btn = QPushButton(_("Send with current file"), self)
        self._new_chat_btn = QPushButton(_("New Chat"), self)
        self._clear_btn = QPushButton(_("Clear"), self)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._send_btn)
        btn_row.addWidget(self._send_file_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._new_chat_btn)
        btn_row.addWidget(self._clear_btn)

        input_container = QWidget(self)
        input_vlayout = QVBoxLayout(input_container)
        input_vlayout.setContentsMargins(0, 0, 0, 0)
        input_vlayout.addWidget(QLabel(_("Query:"), self))
        input_vlayout.addWidget(self._input_area)
        input_vlayout.addLayout(btn_row)

        splitter = QSplitter(Qt.Vertical, self)
        splitter.addWidget(self._response_area)
        splitter.addWidget(input_container)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)
        self.setLayout(layout)

        # --- Button connections ---
        self._send_btn.clicked.connect(self._on_send_clicked)
        self._send_file_btn.clicked.connect(self._on_send_with_file_clicked)
        self._new_chat_btn.clicked.connect(self._on_new_chat)
        self._clear_btn.clicked.connect(self._response_area.clear)

        # --- Keyboard shortcuts ---
        send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self._input_area)
        send_shortcut.activated.connect(self._on_send_clicked)

        # --- Session state ---
        self._session_id = ""
        self._pending_prompt = ""

        # --- Background worker ---
        self._worker = _ClaudeWorker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.sig_chunk.connect(self._on_chunk)
        self._worker.sig_error.connect(self._on_error)
        self._worker.sig_tool_use.connect(self._on_tool_use)
        self._worker.sig_session_id.connect(self._on_session_id)
        self._worker.sig_finished.connect(self._thread.quit)
        self._worker.sig_finished.connect(lambda: self._set_busy(False))

    def update_actions(self):
        pass

    # ---- Public API (called by plugin) -------------------------------------

    def inject_editor_content(self, content: str, filename: str):
        """Called by the plugin with the active editor's file content."""
        if content:
            prompt = (
                f"File: {filename}\n"
                f"```\n{content}\n```\n\n"
                f"{self._pending_prompt}"
            )
        else:
            prompt = self._pending_prompt
        self._pending_prompt = ""
        self._run_query(prompt)

    # ---- Private helpers ---------------------------------------------------

    def _on_send_clicked(self):
        prompt = self._input_area.toPlainText().strip()
        if prompt:
            self._run_query(prompt)
            self._input_area.clear()

    def _on_send_with_file_clicked(self):
        prompt = self._input_area.toPlainText().strip()
        if not prompt:
            return
        self._pending_prompt = prompt
        self._input_area.clear()
        self.sig_editor_content_requested.emit()

    def _on_new_chat(self):
        """Start a fresh conversation — clears display and drops session ID."""
        self._session_id = ""
        self._response_area.clear()

    def _run_query(self, prompt: str):
        if self._thread.isRunning():
            return
        self._thread.wait()  # ensure fully stopped before restarting

        api_key = self.get_conf("api_key", default="")
        claude_path = self.get_conf("claude_path", default="")
        model = self.get_conf("model", default="sonnet")
        system_prompt = self.get_conf("system_prompt", default="")

        self._worker.configure(
            prompt, api_key, claude_path, model, system_prompt, self._session_id
        )

        preview = prompt[:120].replace("\n", " ")
        if len(prompt) > 120:
            preview += "…"

        header = f"\n{'─' * 40}\n"
        if self._session_id:
            header += _("[continuing conversation]\n")
        header += f"> {preview}\n\n"
        self._response_area.append(header)

        self._set_busy(True)
        self._thread.start()

    @Slot(str)
    def _on_chunk(self, text: str):
        """Append a streaming text chunk to the response area."""
        cursor = self._response_area.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self._response_area.setTextCursor(cursor)
        self._response_area.ensureCursorVisible()

    @Slot(str)
    def _on_tool_use(self, tool_name: str):
        """Show a tool-call indicator when Claude calls an MCP tool."""
        self._response_area.append(f"\n[tool: {tool_name}]")

    @Slot(str)
    def _on_session_id(self, session_id: str):
        """Store session ID so the next query resumes this conversation."""
        self._session_id = session_id

    @Slot(str)
    def _on_error(self, message: str):
        self._response_area.append(f"\n[Error] {message}")

    def _set_busy(self, busy: bool):
        self._send_btn.setEnabled(not busy)
        self._send_file_btn.setEnabled(not busy)
        self._send_btn.setText(_("Running…") if busy else _("Send"))
