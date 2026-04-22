# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Main dockable widget for spyder-claude."""

import json
import os
import subprocess
import threading
from contextlib import contextmanager

from anthropic import Anthropic
from qtpy.QtCore import QObject, QMutex, QMutexLocker, QThread, Qt, Signal, Slot
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


class _ClaudeAPIWorker(QObject):
    """Worker for direct Anthropic API calls using the SDK."""

    sig_chunk = Signal(str)       # incremental text to append to response area
    sig_error = Signal(str)       # error message
    sig_finished = Signal()       # run complete
    sig_tool_use = Signal(str)    # tool name each time Claude calls a tool
    sig_session_id = Signal(str)  # session ID for conversation continuity
    sig_prompt = Signal(str)      # for consistency with CLI worker interface

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prompt = ""
        self._api_key = ""
        self._base_url = "https://api.anthropic.com"
        self._model = "claude-sonnet-4-6"
        self._system_prompt = ""
        self._cancelled = False
        self._client = None

    def configure(
        self,
        prompt: str,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str,
    ):
        self._prompt = prompt
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._system_prompt = system_prompt

    @Slot()
    def cancel(self):
        self._cancelled = True

    @Slot()
    def run(self):
        self._cancelled = False

        if not self._api_key:
            self.sig_error.emit("API key is required for API mode")
            self.sig_finished.emit()
            return

        try:
            # Initialize the Anthropic client
            if self._base_url:
                self._client = Anthropic(api_key=self._api_key, base_url=self._base_url)
            else:
                self._client = Anthropic(api_key=self._api_key)

            # Prepare messages
            messages = [{"role": "user", "content": self._prompt}]

            # Call the API with streaming
            kwargs = {
                "model": self._model,
                "messages": messages,
                "max_tokens": 4096,
            }

            if self._system_prompt:
                kwargs["system"] = self._system_prompt

            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if self._cancelled:
                        break
                    self.sig_chunk.emit(text)

        except Exception as exc:
            self.sig_error.emit(str(exc))
        finally:
            self._client = None
            self.sig_finished.emit()


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
    sig_prompt = Signal(str)      # approval prompts and other stderr output

    def __init__(self, parent=None):
        super().__init__(parent)
        self._prompt = ""
        self._api_key = ""
        self._base_url = "https://api.anthropic.com"
        self._claude_path = ""
        self._model = "sonnet"
        self._system_prompt = ""
        self._session_id = ""
        self._proc = None
        self._cancelled = False

    def configure(
        self,
        prompt: str,
        api_key: str,
        base_url: str,
        claude_path: str,
        model: str,
        system_prompt: str,
        session_id: str = "",
    ):
        self._prompt = prompt
        self._api_key = api_key
        self._base_url = base_url
        self._claude_path = claude_path
        self._model = model
        self._system_prompt = system_prompt
        self._session_id = session_id

    @Slot()
    def cancel(self):
        self._cancelled = True
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    @Slot()
    def run(self):
        self._cancelled = False
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
        if self._base_url:
            env["ANTHROPIC_BASE_URL"] = self._base_url

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                bufsize=0,
            )
            self._proc = proc
            with proc:
                def _drain_stderr():
                    """Stream stderr line-by-line for approval prompts."""
                    while True:
                        line = proc.stderr.readline()
                        if not line:
                            break
                        # Emit stderr lines as prompts (e.g., approval requests)
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded:
                            self.sig_prompt.emit(decoded)

                stderr_thread = threading.Thread(
                    target=_drain_stderr, daemon=True
                )
                stderr_thread.start()

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
                stderr_thread.join()
                if proc.returncode != 0 and not self._cancelled:
                    self.sig_error.emit(f"claude exited with code {proc.returncode}")

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
            self._proc = None
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
        self._cancel_btn = QPushButton(_("Cancel"), self)
        self._cancel_btn.setEnabled(False)
        self._new_chat_btn = QPushButton(_("New Chat"), self)
        self._clear_btn = QPushButton(_("Clear"), self)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._send_btn)
        btn_row.addWidget(self._send_file_btn)
        btn_row.addWidget(self._cancel_btn)
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
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._new_chat_btn.clicked.connect(self._on_new_chat)
        self._clear_btn.clicked.connect(self._response_area.clear)

        # --- Keyboard shortcuts ---
        send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self._input_area)
        send_shortcut.activated.connect(self._on_send_clicked)

        # --- Session state ---
        self._session_id = ""
        self._pending_prompt = ""
        self._current_worker = None  # Track active worker instance
        self._current_thread = None  # Track active thread instance
        self._query_mutex = QMutex()  # Prevent concurrent queries

    def _connect_worker_signals(self, worker):
        """Connect signals from a worker to the widget's handlers."""
        worker.sig_chunk.connect(self._on_chunk)
        worker.sig_error.connect(self._on_error)
        worker.sig_finished.connect(self._on_worker_finished)

        # Connect optional signals if they exist
        if hasattr(worker, 'sig_tool_use'):
            worker.sig_tool_use.connect(self._on_tool_use)
        if hasattr(worker, 'sig_session_id'):
            worker.sig_session_id.connect(self._on_session_id)
        if hasattr(worker, 'sig_prompt'):
            worker.sig_prompt.connect(self._on_prompt)

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

    def shutdown(self):
        """Stop any running query and clean up the worker thread."""
        with QMutexLocker(self._query_mutex):
            if self._current_thread is not None:
                if self._current_thread.isRunning():
                    if self._current_worker is not None:
                        self._current_worker.cancel()
                    self._current_thread.quit()
                    self._current_thread.wait(3000)

                # Clean up
                self._current_thread.deleteLater()
                self._current_thread = None
                self._current_worker = None

    # ---- Private helpers ---------------------------------------------------

    def _on_send_clicked(self):
        if self._current_thread is not None and self._current_thread.isRunning():
            return
        prompt = self._input_area.toPlainText().strip()
        if prompt:
            self._run_query(prompt)
            self._input_area.clear()

    def _on_send_with_file_clicked(self):
        if self._current_thread is not None and self._current_thread.isRunning():
            return
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
        # Use mutex to prevent concurrent queries
        with QMutexLocker(self._query_mutex):
            # Wait for any existing thread to finish
            if self._current_thread is not None and self._current_thread.isRunning():
                return

            # Clean up previous thread if it exists
            if self._current_thread is not None:
                self._current_thread.deleteLater()
                self._current_thread = None
                self._current_worker = None

            use_cli = self.get_conf("use_cli", default=True)
            api_key = self.get_conf("api_key", default="")
            base_url = self.get_conf("base_url", default="https://api.anthropic.com")
            claude_path = self.get_conf("claude_path", default="")
            model = self.get_conf("model", default="sonnet")
            system_prompt = self.get_conf("system_prompt", default="")

            # Create fresh worker instance
            if use_cli:
                worker = _ClaudeWorker()
                worker.configure(
                    prompt, api_key, base_url, claude_path, model, system_prompt, self._session_id
                )
            else:
                worker = _ClaudeAPIWorker()
                worker.configure(
                    prompt, api_key, base_url, model, system_prompt
                )

            # Create fresh thread without parent
            thread = QThread()
            worker.moveToThread(thread)

            # Connect signals
            self._connect_worker_signals(worker)
            thread.started.connect(worker.run)

            # Store references
            self._current_worker = worker
            self._current_thread = thread

            preview = prompt[:120].replace("\n", " ")
            if len(prompt) > 120:
                preview += "…"

            header = f"\n{'─' * 40}\n"
            if self._session_id:
                header += _("[continuing conversation]\n")
            header += f"> {preview}\n\n"
            self._append_text(header)

            self._set_busy(True)
            thread.start()

    def _append_text(self, text: str):
        cursor = self._response_area.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self._response_area.setTextCursor(cursor)
        self._response_area.ensureCursorVisible()

    @Slot(str)
    def _on_chunk(self, text: str):
        self._append_text(text)

    @Slot(str)
    def _on_tool_use(self, tool_name: str):
        self._append_text(f"\n[tool: {tool_name}]")

    @Slot(str)
    def _on_session_id(self, session_id: str):
        """Store session ID so the next query resumes this conversation."""
        self._session_id = session_id

    @Slot(str)
    def _on_prompt(self, prompt_text: str):
        """Display approval prompts and other stderr output from CLI."""
        self._append_text(f"\n{prompt_text}")

    @Slot(str)
    def _on_error(self, message: str):
        self._append_text(f"\n[Error] {message}")

    @Slot()
    def _on_worker_finished(self):
        """Clean up thread and worker after query completes."""
        with QMutexLocker(self._query_mutex):
            if self._current_thread is not None:
                self._current_thread.quit()
                self._current_thread.wait(5000)  # Wait up to 5 seconds for clean shutdown
                self._current_thread.deleteLater()
                self._current_thread = None
                self._current_worker = None
        self._set_busy(False)

    @Slot()
    def _on_cancel_clicked(self):
        """Cancel the currently running query."""
        with QMutexLocker(self._query_mutex):
            if self._current_worker is not None:
                self._current_worker.cancel()

    def _set_busy(self, busy: bool):
        self._send_btn.setEnabled(not busy)
        self._send_file_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(busy)
        self._send_btn.setText(_("Running…") if busy else _("Send"))
