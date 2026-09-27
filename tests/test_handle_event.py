# -*- coding: utf-8 -*-
"""Tests for _parse_stream_event (claude CLI stream-json parsing).

The parser is a pure module-level function: recorded event shapes go in,
(signal, args) emissions come out. These cases mirror the event types the
claude CLI emits in --output-format stream-json mode.
"""

import json

import pytest

from spyder_claude.widget.main_widget import _parse_stream_event


def _parse(event):
    return _parse_stream_event(json.dumps(event))


class TestTextStreaming:
    def test_text_delta_emits_chunk(self):
        events = _parse({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "hello"},
            },
        })
        assert events == [("sig_chunk", ("hello",))]

    def test_non_text_delta_ignored(self):
        events = _parse({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "input_json_delta", "partial_json": "{}"},
            },
        })
        assert events == []

    def test_empty_text_delta_ignored(self):
        events = _parse({
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": ""},
            },
        })
        assert events == []

    def test_event_without_type_ignored(self):
        assert _parse({"event": {"type": "content_block_delta"}}) == []


class TestToolUse:
    def test_tool_use_block_announced(self):
        events = _parse({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "ls -la"},
                },
            },
        })
        assert events == [("sig_tool_use", ("Bash", {"command": "ls -la"}))]

    def test_tool_use_with_missing_input(self):
        events = _parse({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {"type": "tool_use", "name": "Read"},
            },
        })
        assert events == [("sig_tool_use", ("Read", {}))]

    def test_text_block_start_not_announced_as_tool(self):
        events = _parse({
            "type": "stream_event",
            "event": {
                "type": "content_block_start",
                "content_block": {"type": "text", "text": "hi"},
            },
        })
        assert events == []


class TestToolResult:
    def test_string_content(self):
        events = _parse({
            "type": "user",
            "message": {"content": [
                {"type": "tool_result", "content": "file contents"}
            ]},
        })
        assert events == [("sig_tool_result", ("file contents", False))]

    def test_list_content_joined(self):
        events = _parse({
            "type": "user",
            "message": {"content": [
                {
                    "type": "tool_result",
                    "content": [
                        {"type": "text", "text": "line one"},
                        {"type": "text", "text": "line two"},
                    ],
                }
            ]},
        })
        assert events == [("sig_tool_result", ("line one\nline two", False))]

    def test_error_result_flagged(self):
        events = _parse({
            "type": "user",
            "message": {"content": [
                {
                    "type": "tool_result",
                    "content": "permission denied",
                    "is_error": True,
                }
            ]},
        })
        assert events == [("sig_tool_result", ("permission denied", True))]

    def test_non_dict_blocks_skipped(self):
        events = _parse({
            "type": "user",
            "message": {"content": ["not a dict"]},
        })
        assert events == []

    def test_empty_text_not_emitted(self):
        events = _parse({
            "type": "user",
            "message": {"content": [{"type": "tool_result", "content": ""}]},
        })
        assert events == []


class TestResultEvent:
    def test_session_id_emitted(self):
        events = _parse({
            "type": "result",
            "is_error": False,
            "session_id": "abc-123",
            "result": "done",
        })
        assert events == [("sig_session_id", ("abc-123",))]

    def test_error_result_emits_error_then_session(self):
        events = _parse({
            "type": "result",
            "is_error": True,
            "session_id": "abc-123",
            "result": "overloaded",
        })
        assert events == [
            ("sig_error", ("overloaded",)),
            ("sig_session_id", ("abc-123",)),
        ]

    def test_result_without_session_id(self):
        assert _parse({"type": "result", "is_error": False}) == []


class TestMalformedInput:
    @pytest.mark.parametrize("line", [
        "not json at all",
        "",
        "   ",
        "[1, 2, 3]",          # valid JSON, wrong shape
        '"just a string"',    # valid JSON, wrong shape
    ])
    def test_no_crash_and_no_events(self, line):
        assert _parse_stream_event(line) == []
