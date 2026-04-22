# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""Qt-side localhost approval server.

Listens on a random 127.0.0.1 port. The MCP permission helper (spawned by
`claude` on the host) connects here for every approval request, sends a
single JSON line, and blocks waiting for our single-line JSON reply.

The server is fully integrated with the Qt event loop via QTcpServer —
every read is signal-driven, so it cannot stall the UI thread. When a full
request arrives we emit `sig_request` and hand the caller a reply callable;
the widget displays its dialog and calls the callable when the user clicks.
"""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any, Callable, Dict

from qtpy.QtCore import QByteArray, QObject, Signal
from qtpy.QtNetwork import QHostAddress, QTcpServer, QTcpSocket

logger = logging.getLogger(__name__)


class ApprovalServer(QObject):
    """Accepts permission requests from the helper and forwards them to the UI.

    Signal:
        sig_request(dict, callable) — payload is {tool_use_id, tool_name,
            input}; the callable takes a decision dict
            {"behavior": "allow"|"deny", ...} and sends it back on the socket.
    """

    sig_request = Signal(dict, object)  # object = reply callable

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._token = secrets.token_urlsafe(32)
        self._server = QTcpServer(self)
        # One read buffer per connected socket, keyed by id(socket).
        self._buffers: Dict[int, QByteArray] = {}
        self._server.newConnection.connect(self._on_new_connection)

    # ---- Lifecycle ---------------------------------------------------------

    def start(self) -> int:
        """Start listening on a random localhost port and return it."""
        # QHostAddress.LocalHost == 127.0.0.1 — never binds to the outside world.
        if not self._server.listen(QHostAddress(QHostAddress.LocalHost), 0):
            raise RuntimeError(
                f"Could not start approval server: "
                f"{self._server.errorString()}"
            )
        port = int(self._server.serverPort())
        logger.info("spyder-claude approval server listening on 127.0.0.1:%d", port)
        return port

    def stop(self) -> None:
        if self._server.isListening():
            self._server.close()
        # Disconnect any lingering clients.
        for sock_id in list(self._buffers.keys()):
            self._buffers.pop(sock_id, None)

    @property
    def token(self) -> str:
        return self._token

    # ---- Connection handling ----------------------------------------------

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            if sock is None:
                return
            # Reject anything that didn't come from localhost, defence-in-depth
            # even though we only bound to 127.0.0.1.
            peer = sock.peerAddress()
            if not (peer.isLoopback() or peer == QHostAddress(QHostAddress.LocalHost)):
                logger.warning("Rejecting non-loopback connection from %s", peer.toString())
                sock.abort()
                sock.deleteLater()
                continue

            self._buffers[id(sock)] = QByteArray()
            sock.readyRead.connect(lambda s=sock: self._on_ready_read(s))
            sock.disconnected.connect(lambda s=sock: self._on_disconnected(s))

    def _on_ready_read(self, sock: QTcpSocket) -> None:
        buf = self._buffers.get(id(sock))
        if buf is None:
            return
        buf.append(sock.readAll())

        # Protocol is one JSON object per line. In practice the helper sends
        # exactly one request per connection, but handle multiple defensively.
        while True:
            data = bytes(buf)
            nl = data.find(b"\n")
            if nl < 0:
                break
            line = data[:nl]
            # Replace buffer with remainder.
            buf.clear()
            buf.append(data[nl + 1 :])
            self._handle_line(sock, line)

    def _on_disconnected(self, sock: QTcpSocket) -> None:
        self._buffers.pop(id(sock), None)
        sock.deleteLater()

    # ---- Request parsing / reply -----------------------------------------

    def _handle_line(self, sock: QTcpSocket, line: bytes) -> None:
        try:
            request = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning("Malformed approval request: %s", exc)
            self._reply_and_close(
                sock,
                {"behavior": "deny", "message": f"Malformed request: {exc}"},
            )
            return

        if not isinstance(request, dict):
            self._reply_and_close(
                sock,
                {"behavior": "deny", "message": "Request must be a JSON object"},
            )
            return

        if request.get("token") != self._token:
            logger.warning("Approval request with bad/missing token rejected.")
            self._reply_and_close(
                sock,
                {"behavior": "deny", "message": "Invalid token"},
            )
            return

        payload = {
            "tool_use_id": request.get("tool_use_id", ""),
            "tool_name": request.get("tool_name", ""),
            "input": request.get("input", {}),
        }

        # Build a one-shot reply callable. The UI will call this when the
        # user clicks Allow/Deny; it must only fire once.
        fired = {"done": False}

        def reply(decision: Dict[str, Any]) -> None:
            if fired["done"]:
                return
            fired["done"] = True
            self._reply_and_close(sock, decision)

        self.sig_request.emit(payload, reply)

    def _reply_and_close(self, sock: QTcpSocket, decision: Dict[str, Any]) -> None:
        if sock.state() == QTcpSocket.UnconnectedState:
            return
        try:
            data = (json.dumps(decision) + "\n").encode("utf-8")
            sock.write(data)
            sock.flush()
            # Half-close to signal end-of-response, then let the helper close.
            sock.disconnectFromHost()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send approval reply")
            sock.abort()
