# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Main dockable widget for spyder-claude."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from anthropic import Anthropic
from qtpy.QtCore import QMutex, QMutexLocker, QObject, QThread, Qt, Signal, Slot
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

from .approval_dialog import ALLOW_ALWAYS, ALLOW_ONCE, DENY, ApprovalDialog
from .approval_server import ApprovalServer
from ..session import SessionManager
from ..secure_storage import create_secure_storage
from ..api_key_security import APIKeySecurity, SECURE_PLACEHOLDER

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper-script bootstrap
# ---------------------------------------------------------------------------

# Packaged location of the MCP permission helper. We ship it as regular module
# source so it's always available from the installed plugin.
_HELPER_PACKAGE_PATH = (
    Path(__file__).resolve().parent.parent / "permission_helper" / "helper.py"
)


def _bootstrap_helper_script() -> Path:
    """Copy the bundled helper script to a location the host side can read.

    Inside a Flatpak sandbox, paths under the sandbox's private site-packages
    are NOT reachable from the host side where `claude` runs. But
    ``~/.var/app/<app-id>/cache/`` is bind-mounted readable from the host, and
    ``$XDG_CACHE_HOME`` inside the sandbox resolves there. Outside Flatpak we
    just use the normal user cache dir.

    The script is copied (rather than referenced by its import path) so the
    host's python interpreter can execute it with no dependency on Spyder's
    Python environment.
    """
    cache_root = Path(
        os.environ.get("XDG_CACHE_HOME")
        or (Path.home() / ".cache")
    ) / "spyder-claude"
    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / "permission_helper.py"

    try:
        src_mtime = _HELPER_PACKAGE_PATH.stat().st_mtime
        if (
            not target.exists()
            or target.stat().st_mtime < src_mtime
            or target.stat().st_size != _HELPER_PACKAGE_PATH.stat().st_size
        ):
            shutil.copyfile(_HELPER_PACKAGE_PATH, target)
            os.chmod(target, 0o755)
    except OSError:
        logger.exception("Failed to install permission helper to %s", target)
        raise
    return target


def _running_in_flatpak() -> bool:
    return os.path.exists("/.flatpak-info") or "FLATPAK_ID" in os.environ


def _host_visible_path(inside_path: Path) -> str:
    """Translate a sandbox path to one the host can see, if possible.

    Inside Flatpak, $XDG_CACHE_HOME resolves to ``~/.var/app/$FLATPAK_ID/cache``
    from the host's viewpoint. Outside Flatpak this is a no-op.
    """
    if not _running_in_flatpak():
        return str(inside_path)

    flatpak_id = os.environ.get("FLATPAK_ID", "")
    # $XDG_CACHE_HOME in-sandbox should be ~/.var/app/<id>/cache, which is
    # also the path the host sees — but we compute it robustly.
    home = os.environ.get("HOME", str(Path.home()))
    host_cache = Path(home) / ".var" / "app" / flatpak_id / "cache"

    try:
        # If the path lives under $XDG_CACHE_HOME inside the sandbox, map it.
        cache_inside = Path(
            os.environ.get("XDG_CACHE_HOME")
            or (Path.home() / ".cache")
        )
        rel = inside_path.relative_to(cache_inside)
        return str(host_cache / rel)
    except ValueError:
        # Not under XDG_CACHE_HOME — hand it back unchanged and hope.
        return str(inside_path)


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------


class _ClaudeAPIWorker(QObject):
    """Worker for direct Anthropic API calls using the SDK.

    Does not use the CLI, so the approval-prompt machinery does not apply.
    """

    sig_chunk = Signal(str)
    sig_error = Signal(str)
    sig_finished = Signal()
    sig_tool_use = Signal(str, dict)
    sig_tool_result = Signal(str, bool)  # text, is_error
    sig_session_id = Signal(str)
    sig_prompt = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._prompt = ""
        self._api_key = ""
        self._base_url = "https://api.anthropic.com"
        self._model = "claude-sonnet-4-6"
        self._system_prompt = ""
        self._cancelled = False

    def configure(
        self,
        prompt: str,
        api_key: str,
        base_url: str,
        model: str,
        system_prompt: str,
    ) -> None:
        self._prompt = prompt
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._system_prompt = system_prompt

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True

    @Slot()
    def run(self) -> None:
        self._cancelled = False
        if not self._api_key:
            self.sig_error.emit("API key is required for API mode")
            self.sig_finished.emit()
            return
        try:
            client = (
                Anthropic(api_key=self._api_key, base_url=self._base_url)
                if self._base_url
                else Anthropic(api_key=self._api_key)
            )
            messages = [{"role": "user", "content": self._prompt}]
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "max_tokens": 4096,
            }
            if self._system_prompt:
                kwargs["system"] = self._system_prompt
            with client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    if self._cancelled:
                        break
                    self.sig_chunk.emit(text)
        except Exception as exc:  # noqa: BLE001
            self.sig_error.emit(str(exc))
        finally:
            self.sig_finished.emit()


class _ClaudeWorker(QObject):
    """Runs a claude CLI call in a background QThread.

    On top of the basic stream, this worker:
      - wires an MCP permission-prompt helper so approval requests surface in
        the Spyder UI (via ``--permission-prompt-tool``);
      - reports ``tool_use`` blocks with their input, so the user sees *what*
        Claude is about to do;
      - reports ``tool_result`` blocks so errors (including permission denials
        that slip through static rules) are visible instead of silent.
    """

    sig_chunk = Signal(str)
    sig_error = Signal(str)
    sig_finished = Signal()
    sig_tool_use = Signal(str, dict)        # tool name, input
    sig_tool_result = Signal(str, bool)     # text, is_error
    sig_session_id = Signal(str)
    sig_prompt = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._prompt = ""
        self._api_key = ""
        self._base_url = "https://api.anthropic.com"
        self._claude_path = ""
        self._model = "sonnet"
        self._system_prompt = ""
        self._session_id = ""
        self._perm_config: Optional[Dict[str, Any]] = None
        self._allowed_tools: list = []
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = False
        self._mcp_config_path: Optional[Path] = None

    def configure(
        self,
        prompt: str,
        api_key: str,
        base_url: str,
        claude_path: str,
        model: str,
        system_prompt: str,
        session_id: str = "",
        perm_config: Optional[Dict[str, Any]] = None,
        allowed_tools: Optional[list] = None,
    ) -> None:
        self._prompt = prompt
        self._api_key = api_key
        self._base_url = base_url
        self._claude_path = claude_path
        self._model = model
        self._system_prompt = system_prompt
        self._session_id = session_id
        self._perm_config = perm_config
        self._allowed_tools = list(allowed_tools or [])

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass

    @Slot()
    def run(self) -> None:
        self._cancelled = False
        claude = self._claude_path.strip() or "claude"

        if _running_in_flatpak():
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

        # --- permission-prompt-tool wiring ------------------------------------
        # Write an mcp-config JSON to a host-visible tempfile and reference it.
        if self._perm_config is not None:
            try:
                mcp_cfg = self._build_mcp_config_file(self._perm_config)
                cmd.extend(["--mcp-config", str(mcp_cfg)])
                cmd.extend([
                    "--permission-prompt-tool",
                    "mcp__spyder_claude_perm__permission_prompt",
                ])
            except Exception:  # noqa: BLE001
                logger.exception("Failed to configure permission-prompt tool")
                # Fall through without approvals — the user will see silent
                # denials surfaced as tool_result errors.

        if self._allowed_tools:
            cmd.extend(["--allowedTools", ",".join(self._allowed_tools)])

        if self._session_id:
            cmd.extend(["--resume", self._session_id])
        if self._model:
            cmd.extend(["--model", self._model])
        if self._system_prompt:
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
                def _drain_stderr() -> None:
                    while True:
                        line = proc.stderr.readline()
                        if not line:
                            break
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

                for _ in range(300):
                    if proc.poll() is not None:
                        break
                    if self._cancelled:
                        try:
                            proc.kill()
                        except OSError:
                            pass
                        break
                    time.sleep(0.1)

                stderr_thread.join(timeout=5)

                if proc.returncode != 0 and not self._cancelled:
                    self.sig_error.emit(
                        f"claude exited with code {proc.returncode}"
                    )
        except FileNotFoundError:
            if prefix:
                self.sig_error.emit(
                    f"Cannot find '{claude}' via flatpak-spawn. "
                    "Check the claude path in Preferences → Claude and "
                    "ensure Spyder has the org.freedesktop.Flatpak permission:\n"
                    "flatpak override --user "
                    "--talk-name=org.freedesktop.Flatpak org.spyder_ide.spyder"
                )
            else:
                self.sig_error.emit(
                    f"Cannot find '{claude}'. "
                    "Set the correct path to the claude binary in "
                    "Preferences → Claude."
                )
        except Exception as exc:  # noqa: BLE001
            self.sig_error.emit(str(exc))
        finally:
            self._proc = None
            # Clean up the temp mcp-config file.
            if self._mcp_config_path is not None:
                try:
                    self._mcp_config_path.unlink()
                except OSError:
                    pass
                self._mcp_config_path = None
            self.sig_finished.emit()

    def _build_mcp_config_file(
        self, perm_config: Dict[str, Any]
    ) -> Path:
        """Write the MCP config JSON to a host-readable tempfile.

        perm_config must contain at least {python, script, port, token} where
        ``python`` and ``script`` are host-visible paths.
        """
        cfg = {
            "mcpServers": {
                "spyder_claude_perm": {
                    "command": perm_config["python"],
                    "args": [perm_config["script"]],
                    "env": {
                        "SPYDER_CLAUDE_PERM_PORT": str(perm_config["port"]),
                        "SPYDER_CLAUDE_PERM_TOKEN": perm_config["token"],
                    },
                }
            }
        }

        # Place the mcp-config file in the same host-visible dir as the helper.
        cache_root = Path(
            os.environ.get("XDG_CACHE_HOME")
            or (Path.home() / ".cache")
        ) / "spyder-claude"
        cache_root.mkdir(parents=True, exist_ok=True)

        fd, inside_path = tempfile.mkstemp(
            prefix="mcp-", suffix=".json", dir=str(cache_root)
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh)

        inside = Path(inside_path)
        self._mcp_config_path = inside
        # For claude (on the host), the mcp-config path must be host-visible.
        host_path = _host_visible_path(inside)
        return Path(host_path)

    # ---- Stream-json event handling ---------------------------------------

    def _handle_event(self, line: str) -> None:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return

        etype = event.get("type")

        if etype == "stream_event":
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
                    self.sig_tool_use.emit(
                        block.get("name", "tool"),
                        block.get("input") or {},
                    )

        elif etype == "assistant":
            # Fallback: some content blocks (notably tool_use) arrive fully
            # formed on the "assistant" message rather than via stream_event.
            message = event.get("message", {})
            for block in message.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    # Avoid duplicating a tool_use we already announced from
                    # content_block_start — but announcing twice is harmless
                    # and better than silently losing it on providers that
                    # don't emit low-level stream events.
                    pass

        elif etype == "user":
            # Tool results come back as a user message with tool_result blocks.
            message = event.get("message", {})
            for block in message.get("content", []) or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    content = block.get("content", "")
                    if isinstance(content, list):
                        parts = [
                            str(c.get("text", ""))
                            for c in content
                            if isinstance(c, dict)
                        ]
                        text = "\n".join(p for p in parts if p)
                    else:
                        text = str(content or "")
                    is_error = bool(block.get("is_error"))
                    if text:
                        self.sig_tool_result.emit(text, is_error)

        elif etype == "result":
            if event.get("is_error"):
                self.sig_error.emit(event.get("result", "Unknown error"))
            session_id = event.get("session_id", "")
            if session_id:
                self.sig_session_id.emit(session_id)


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------


class ClaudeMainWidget(PluginMainWidget):
    """Dockable panel for querying Claude via the claude CLI or API."""

    sig_editor_content_requested = Signal()

    # ---- PluginMainWidget API ----------------------------------------------

    def get_title(self) -> str:
        return _("Claude")

    def get_focus_widget(self):
        return self._input_area

    def setup(self) -> None:
        # --- Response area ---
        self._response_area = QTextEdit(self)
        self._response_area.setReadOnly(True)
        self._response_area.setPlaceholderText(
            _("Claude's response will appear here…")
        )

        # --- Input area ---
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
        self._current_worker: Optional[QObject] = None
        self._current_thread: Optional[QThread] = None
        self._query_mutex = QMutex()

        # --- Per-conversation "always allow" set (resets on New Chat) ---
        self._session_allowed_tools: Set[str] = set()

        # --- Session persistence ---
        # Initialize session manager for cross-restart conversation continuity
        try:
            secure_storage = create_secure_storage()
            self.session_manager = SessionManager(secure_storage)
            self.api_key_security = APIKeySecurity(secure_storage)
            self._restore_session()  # Restore previous session if available
        except Exception as e:
            logger.warning(f"Failed to initialize session manager: {e}")
            self.session_manager = None
            self.api_key_security = None

        # --- Approval server ---
        # Lazily started on first query so a broken network stack doesn't
        # prevent the widget from loading entirely.
        self._approval_server: Optional[ApprovalServer] = None
        self._approval_port: Optional[int] = None
        self._helper_script_host_path: Optional[str] = None

    def update_actions(self) -> None:
        pass

    # ---- Public API (called by plugin) -------------------------------------

    def inject_editor_content(self, content: str, filename: str) -> None:
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

    def shutdown(self) -> None:
        """Stop any running query and tear down the approval server."""
        with QMutexLocker(self._query_mutex):
            thread = self._current_thread
            worker = self._current_worker
            self._current_thread = None
            self._current_worker = None

        if thread is not None:
            if thread.isRunning():
                if worker is not None:
                    worker.cancel()
                thread.quit()
                if not thread.wait(3000):
                    logger.warning(
                        "Worker thread did not finish cleanly during shutdown, "
                        "forcing termination"
                    )
                    thread.terminate()
                    thread.wait(1000)
            thread.deleteLater()

        if self._approval_server is not None:
            self._approval_server.stop()
            self._approval_server = None

    # ---- Approval-server bootstrap ----------------------------------------

    def _ensure_approval_server(self) -> Optional[Dict[str, Any]]:
        """Start the approval server + install the helper, once. Returns the
        config dict to pass to the worker, or None if anything failed (in
        which case we fall back to no-permission-prompt-tool mode).
        """
        if self._approval_server is not None and self._helper_script_host_path:
            return {
                "python": self._host_python_path(),
                "script": self._helper_script_host_path,
                "port": self._approval_port,
                "token": self._approval_server.token,
            }

        try:
            helper_path = _bootstrap_helper_script()
            self._helper_script_host_path = _host_visible_path(helper_path)

            server = ApprovalServer(self)
            self._approval_port = server.start()
            server.sig_request.connect(self._on_approval_request)
            self._approval_server = server
        except Exception:  # noqa: BLE001
            logger.exception("Failed to set up approval server; continuing without it")
            self._approval_server = None
            self._approval_port = None
            self._helper_script_host_path = None
            return None

        return {
            "python": self._host_python_path(),
            "script": self._helper_script_host_path,
            "port": self._approval_port,
            "token": self._approval_server.token,
        }

    @staticmethod
    def _host_python_path() -> str:
        """A Python 3 interpreter reachable from the host side.

        Inside Flatpak, ``claude`` runs on the host and spawns the MCP helper
        on the host, so we must name an interpreter that exists *outside* the
        sandbox. Assuming ``python3`` is on the host PATH is the least-bad
        default — the only dependency is the stdlib. (`sys.executable` would
        point into the sandbox and would not work.)
        """
        return "python3"

    # ---- Approval request → dialog ----------------------------------------

    @Slot(dict, object)
    def _on_approval_request(
        self, payload: Dict[str, Any], reply: Callable[[Dict[str, Any]], None]
    ) -> None:
        tool_name = str(payload.get("tool_name", ""))
        tool_input = payload.get("input", {})

        # Session-level "allow always" short-circuit.
        if tool_name in self._session_allowed_tools:
            reply({"behavior": "allow", "updatedInput": tool_input})
            self._append_text(
                _("\n[auto-allowed: {tool}]").format(tool=tool_name)
            )
            return

        decision, original_input = ApprovalDialog.ask(
            tool_name, tool_input, parent=self
        )

        if decision == DENY:
            reply({
                "behavior": "deny",
                "message": "User denied the request in Spyder.",
            })
            self._append_text(
                _("\n[denied: {tool}]").format(tool=tool_name)
            )
            return

        if decision == ALLOW_ALWAYS:
            self._session_allowed_tools.add(tool_name)

        reply({"behavior": "allow", "updatedInput": original_input})
        self._append_text(
            _("\n[allowed: {tool}]").format(tool=tool_name)
        )

    # ---- Worker plumbing --------------------------------------------------

    def _connect_worker_signals(self, worker: QObject) -> None:
        worker.sig_chunk.connect(self._on_chunk)
        worker.sig_error.connect(self._on_error)
        worker.sig_finished.connect(self._on_worker_finished)

        if hasattr(worker, "sig_tool_use"):
            worker.sig_tool_use.connect(self._on_tool_use)
        if hasattr(worker, "sig_tool_result"):
            worker.sig_tool_result.connect(self._on_tool_result)
        if hasattr(worker, "sig_session_id"):
            worker.sig_session_id.connect(self._on_session_id)
        if hasattr(worker, "sig_prompt"):
            worker.sig_prompt.connect(self._on_prompt)

    # ---- Private helpers ---------------------------------------------------

    def _on_send_clicked(self) -> None:
        prompt = self._input_area.toPlainText().strip()
        if prompt:
            self._run_query(prompt)

    def _on_send_with_file_clicked(self) -> None:
        prompt = self._input_area.toPlainText().strip()
        if not prompt:
            return
        self._pending_prompt = prompt
        self.sig_editor_content_requested.emit()

    def _on_new_chat(self) -> None:
        """Start fresh conversation."""
        self._session_id = ""
        self._session_allowed_tools.clear()
        self._response_area.clear()

        # Clear persisted session
        if self.session_manager:
            try:
                self.session_manager.clear_session()
                logger.debug("Cleared persisted session for new chat")
            except Exception as e:
                logger.warning(f"Failed to clear persisted session: {e}")

    def _load_api_key(self, config_value: str) -> str:
        """Load API key from config or secure storage.

        Args:
            config_value: Value from Spyder config (may be SECURE:stored placeholder)

        Returns:
            Actual API key string
        """
        # If we have secure storage and the config contains the placeholder
        if self.api_key_security and config_value == SECURE_PLACEHOLDER:
            try:
                secure_key = self.api_key_security.retrieve_api_key()
                if secure_key:
                    return secure_key
                else:
                    logger.warning("Secure storage placeholder found but no key in storage")
                    return ""
            except Exception as e:
                logger.error(f"Failed to load API key from secure storage: {e}")
                return ""

        # Otherwise return the config value as-is (plaintext or empty)
        return config_value

    def _run_query(self, prompt: str) -> None:
        with QMutexLocker(self._query_mutex):
            if (
                self._current_thread is not None
                and self._current_thread.isRunning()
            ):
                # Give visible feedback instead of silently dropping the click.
                self._append_text(
                    _("\n[busy — wait for the current query to finish or click Cancel]\n")
                )
                return

            if self._current_thread is not None:
                self._current_thread.deleteLater()
                self._current_thread = None
                self._current_worker = None

            use_cli = self.get_conf("use_cli", default=True)
            api_key_config = self.get_conf("api_key", default="")
            api_key = self._load_api_key(api_key_config)  # Load from secure storage if needed
            base_url = self.get_conf(
                "base_url", default="https://api.anthropic.com"
            )
            claude_path = self.get_conf("claude_path", default="")
            model = self.get_conf("model", default="sonnet")
            system_prompt = self.get_conf("system_prompt", default="")

            if use_cli:
                perm_config = self._ensure_approval_server()
                worker: QObject = _ClaudeWorker()
                worker.configure(
                    prompt,
                    api_key,
                    base_url,
                    claude_path,
                    model,
                    system_prompt,
                    self._session_id,
                    perm_config=perm_config,
                )
            else:
                worker = _ClaudeAPIWorker()
                worker.configure(
                    prompt, api_key, base_url, model, system_prompt
                )

            thread = QThread()
            worker.moveToThread(thread)
            self._connect_worker_signals(worker)
            thread.started.connect(worker.run)

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

            self._input_area.clear()
            self._set_busy(True)
            thread.start()

    def _append_text(self, text: str) -> None:
        cursor = self._response_area.textCursor()
        cursor.movePosition(cursor.End)
        cursor.insertText(text)
        self._response_area.setTextCursor(cursor)
        self._response_area.ensureCursorVisible()

    # ---- Slots from the worker --------------------------------------------

    @Slot(str)
    def _on_chunk(self, text: str) -> None:
        self._append_text(text)

    @Slot(str, dict)
    def _on_tool_use(self, tool_name: str, tool_input: Any) -> None:
        preview = self._summarize_tool_input(tool_name, tool_input)
        if preview:
            self._append_text(f"\n[tool: {tool_name} — {preview}]")
        else:
            self._append_text(f"\n[tool: {tool_name}]")

    @staticmethod
    def _summarize_tool_input(tool_name: str, tool_input: Any) -> str:
        if not isinstance(tool_input, dict):
            return ""
        for key in ("command", "file_path", "path", "url", "pattern", "query"):
            val = tool_input.get(key)
            if isinstance(val, str) and val:
                if len(val) > 80:
                    return val[:77] + "…"
                return val
        return ""

    @Slot(str, bool)
    def _on_tool_result(self, text: str, is_error: bool) -> None:
        label = "tool error" if is_error else "tool result"
        truncated = text if len(text) < 800 else text[:780] + "…[truncated]"
        self._append_text(f"\n[{label}] {truncated}\n")

    @Slot(str)
    def _on_session_id(self, session_id: str) -> None:
        """Handle new session ID from Claude CLI/API."""
        self._session_id = session_id

        # Save session for persistence across IDE restarts
        if self.session_manager and session_id:
            try:
                use_cli = self.get_conf("use_cli", default=True)
                model = self.get_conf("model", default="sonnet")
                mode = "cli" if use_cli else "api"

                self.session_manager.create_session(
                    session_id=session_id,
                    model=model,
                    mode=mode,
                    metadata={"created_at": self._get_current_time()}
                )
                logger.debug(f"Saved session for persistence: {session_id}")
            except Exception as e:
                logger.warning(f"Failed to save session: {e}")

    def _restore_session(self) -> None:
        """Restore previous session if available and valid."""
        if not self.session_manager:
            return

        try:
            session = self.session_manager.load_session()
            if session and self.session_manager.is_session_valid():
                self._session_id = session.session_id
                self._append_text(
                    _("\n[previous conversation restored — session continued]\n")
                )
                logger.info(f"Restored previous session: {session.session_id}")
            else:
                logger.debug("No valid previous session to restore")
        except Exception as e:
            logger.warning(f"Failed to restore session: {e}")

    def _get_current_time(self) -> str:
        """Get current time as ISO format string."""
        from datetime import datetime
        return datetime.now().isoformat()

    @Slot(str)
    def _on_prompt(self, prompt_text: str) -> None:
        self._append_text(f"\n{prompt_text}")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._append_text(f"\n[Error] {message}")

    @Slot()
    def _on_worker_finished(self) -> None:
        with QMutexLocker(self._query_mutex):
            thread = self._current_thread
            worker = self._current_worker
            self._current_thread = None
            self._current_worker = None

        if thread is not None:
            thread.quit()
            if not thread.wait(5000):
                logger.warning(
                    "Worker thread did not finish cleanly, forcing termination"
                )
                thread.terminate()
                thread.wait(1000)
            thread.deleteLater()

        self._set_busy(False)

    @Slot()
    def _on_cancel_clicked(self) -> None:
        with QMutexLocker(self._query_mutex):
            if self._current_worker is not None:
                self._current_worker.cancel()

    def _set_busy(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)
        self._send_file_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(busy)
        self._send_btn.setText(_("Running…") if busy else _("Send"))
