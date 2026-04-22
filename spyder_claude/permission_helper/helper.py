#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""
MCP permission-prompt server for spyder-claude.

Speaks MCP JSON-RPC 2.0 over stdin/stdout so the `claude` CLI can invoke it
via `--permission-prompt-tool mcp__spyder_claude_perm__permission_prompt`.
When Claude asks for permission we forward the request to the Spyder plugin
over a localhost TCP socket, wait for the user's decision, and return it.

This script is intentionally stdlib-only so the host-side Python interpreter
that `claude` uses doesn't need any extra packages installed. It is shipped
with the plugin and bootstrapped to a location readable from outside the
Flatpak sandbox (typically ~/.var/app/<app-id>/cache/spyder-claude/).

Environment variables:
    SPYDER_CLAUDE_PERM_PORT  — localhost TCP port of the approval server
                                (required)
    SPYDER_CLAUDE_PERM_TOKEN — shared secret sent with every request so the
                                server can reject stray connections (required)
    SPYDER_CLAUDE_PERM_DEBUG — if set to '1', log to stderr for troubleshooting

Protocol on the wire (line-delimited JSON, one object per line):
    helper → server : {"token": "...", "tool_use_id": "...",
                       "tool_name": "Bash", "input": { ... }}
    server → helper : {"behavior": "allow", "updatedInput": { ... }}
                  or {"behavior": "deny",  "message": "..."}

If anything goes wrong (server unreachable, bad reply, timeout) the helper
denies by default — safer than silently allowing.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import threading
from typing import Any, Dict, Optional

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "spyder_claude_perm"
SERVER_VERSION = "1.0.0"
TOOL_NAME = "permission_prompt"

# Generous ceiling — the user may take a moment to click. `claude` has its
# own internal timeout too; we just don't want to hang forever if the Spyder
# end vanished.
APPROVAL_TIMEOUT_SECONDS = 600

_DEBUG = os.environ.get("SPYDER_CLAUDE_PERM_DEBUG") == "1"


def _log(msg: str) -> None:
    if _DEBUG:
        # IMPORTANT: MCP stdio servers MUST NOT write to stdout except for
        # protocol messages. stderr is fine.
        print(f"[spyder-claude-perm] {msg}", file=sys.stderr, flush=True)


# ---- Transport: line-delimited JSON over TCP to the Spyder widget ----------


def _ask_spyder(tool_use_id: str, tool_name: str, tool_input: Any) -> Dict[str, Any]:
    """Send an approval request to the Spyder plugin and block until answered.

    Returns an MCP-formatted decision dict:
        {"behavior": "allow", "updatedInput": <input>}  or
        {"behavior": "deny",  "message": "..."}
    On any error, returns a deny response (fail-closed).
    """
    port_str = os.environ.get("SPYDER_CLAUDE_PERM_PORT", "")
    token = os.environ.get("SPYDER_CLAUDE_PERM_TOKEN", "")

    if not port_str or not token:
        return {
            "behavior": "deny",
            "message": (
                "spyder-claude permission helper is missing environment "
                "configuration (SPYDER_CLAUDE_PERM_PORT / _TOKEN). "
                "This is a plugin bug — please report it."
            ),
        }

    try:
        port = int(port_str)
    except ValueError:
        return {
            "behavior": "deny",
            "message": f"Invalid SPYDER_CLAUDE_PERM_PORT: {port_str!r}",
        }

    request = {
        "token": token,
        "tool_use_id": tool_use_id,
        "tool_name": tool_name,
        "input": tool_input,
    }

    try:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            sock.settimeout(APPROVAL_TIMEOUT_SECONDS)
            sock.sendall((json.dumps(request) + "\n").encode("utf-8"))

            # Read a single line response (the server writes exactly one).
            buf = bytearray()
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf.extend(chunk)
                if b"\n" in buf:
                    break

            line, _, _ = bytes(buf).partition(b"\n")
            if not line:
                return {
                    "behavior": "deny",
                    "message": "Spyder approval server closed the connection without responding.",
                }

            reply = json.loads(line.decode("utf-8"))
    except socket.timeout:
        return {
            "behavior": "deny",
            "message": "Approval request timed out (no response from Spyder).",
        }
    except (OSError, ConnectionError) as exc:
        return {
            "behavior": "deny",
            "message": f"Could not reach Spyder approval server: {exc}",
        }
    except json.JSONDecodeError as exc:
        return {
            "behavior": "deny",
            "message": f"Malformed reply from Spyder approval server: {exc}",
        }

    # Normalise / validate the reply.
    behavior = reply.get("behavior")
    if behavior == "allow":
        out: Dict[str, Any] = {"behavior": "allow"}
        if "updatedInput" in reply:
            out["updatedInput"] = reply["updatedInput"]
        else:
            out["updatedInput"] = tool_input
        return out
    if behavior == "deny":
        return {
            "behavior": "deny",
            "message": reply.get("message", "Denied by user."),
        }
    return {
        "behavior": "deny",
        "message": f"Unknown 'behavior' in Spyder reply: {behavior!r}",
    }


# ---- MCP JSON-RPC 2.0 stdio server -----------------------------------------


_write_lock = threading.Lock()


def _send(message: Dict[str, Any]) -> None:
    """Write one JSON-RPC message as a single line to stdout."""
    data = json.dumps(message, ensure_ascii=False)
    with _write_lock:
        sys.stdout.write(data + "\n")
        sys.stdout.flush()


def _send_result(msg_id: Any, result: Any) -> None:
    _send({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _send_error(msg_id: Any, code: int, message: str) -> None:
    _send(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }
    )


# --- Method handlers ---------------------------------------------------------


def _handle_initialize(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
    }


def _tool_schema() -> Dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Handle permission requests from the Claude Code CLI. "
            "Forwards to the spyder-claude IDE panel for user approval."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool_use_id": {"type": "string"},
                "tool_name": {"type": "string"},
                "input": {"type": "object"},
            },
            "required": ["tool_use_id", "tool_name", "input"],
        },
    }


def _handle_tools_list(_params: Dict[str, Any]) -> Dict[str, Any]:
    return {"tools": [_tool_schema()]}


def _handle_tools_call(params: Dict[str, Any]) -> Dict[str, Any]:
    name = params.get("name")
    if name != TOOL_NAME:
        # Return a tool error (not a JSON-RPC error) per MCP conventions.
        return {
            "content": [
                {"type": "text", "text": json.dumps({
                    "behavior": "deny",
                    "message": f"Unknown tool: {name}",
                })}
            ],
            "isError": True,
        }

    args = params.get("arguments") or {}
    tool_use_id = args.get("tool_use_id", "")
    tool_name = args.get("tool_name", "")
    tool_input = args.get("input", {})

    _log(f"permission request: {tool_name} (id={tool_use_id})")
    decision = _ask_spyder(tool_use_id, tool_name, tool_input)
    _log(f"decision: {decision.get('behavior')}")

    return {
        "content": [
            {"type": "text", "text": json.dumps(decision)}
        ]
    }


METHODS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}


def _dispatch(message: Dict[str, Any]) -> None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    # Notifications (no "id") don't get a response.
    is_notification = "id" not in message

    if method is None:
        # Probably a response to something we didn't send — ignore.
        return

    handler = METHODS.get(method)
    if handler is None:
        if is_notification:
            return  # Silently drop unknown notifications (e.g. notifications/initialized).
        _send_error(msg_id, -32601, f"Method not found: {method}")
        return

    try:
        result = handler(params)
    except Exception as exc:  # noqa: BLE001 — top-level safety net
        _log(f"handler error: {exc!r}")
        if not is_notification:
            _send_error(msg_id, -32603, f"Internal error: {exc}")
        return

    if not is_notification:
        _send_result(msg_id, result)


def main() -> int:
    _log(f"starting; PID={os.getpid()}")
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _log(f"bad JSON from stdin: {exc}")
            continue
        if isinstance(message, dict):
            _dispatch(message)
    _log("stdin closed; exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
