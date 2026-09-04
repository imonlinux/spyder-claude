# -*- coding: utf-8 -*-
"""Unmocked platform smoke tests (Windows + macOS).

The regular suite patches sys.platform, so it exercises logic but never a
real platform environment. These classes run only on their matching OS in
CI and verify the actual failure modes from issue #1:

1. the cache directory is actually created in the platform cache location
2. the helper script is actually installed there
3. the interpreter _host_python_command() picks actually exists and can
   run the installed helper (the old hardcoded "python3" could not on
   Windows)
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from spyder_claude.widget.main_widget import (
    _bootstrap_helper_script,
    _get_cache_root,
    _host_python_command,
)

windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="Windows-only smoke test"
)
macos_only = pytest.mark.skipif(
    sys.platform != "darwin", reason="macOS-only smoke test"
)


def _interpreter_command(ban_python3: bool) -> list:
    cmd, args = _host_python_command()
    if ban_python3:
        assert cmd != "python3", (
            "Windows must never select 'python3' (App Execution Alias stub)"
        )
    return [cmd, *args]


@windows_only
class TestRealWindowsCache:
    """Real %LOCALAPPDATA% behavior, no mocks."""

    def test_cache_root_uses_localappdata(self):
        root = _get_cache_root()
        assert "spyder-claude" in str(root)
        assert Path(root).is_absolute()
        localappdata = os.environ.get("LOCALAPPDATA")
        if localappdata:
            assert root == Path(localappdata) / "spyder-claude"

    def test_cache_root_directory_creates(self):
        root = _get_cache_root()
        root.mkdir(parents=True, exist_ok=True)
        assert root.is_dir()

    def test_helper_script_installs(self):
        target = _bootstrap_helper_script()
        assert target.exists()
        assert target.parent == _get_cache_root()
        assert target.stat().st_size > 0


@windows_only
class TestRealWindowsInterpreter:
    """The chosen interpreter must actually work on this machine."""

    def test_selected_interpreter_runs(self):
        command = _interpreter_command(ban_python3=True)
        proc = subprocess.run(
            [*command, "-c", "import sys; print(sys.version_info[0])"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "3", proc.stdout

    def test_selected_interpreter_can_parse_helper(self):
        command = _interpreter_command(ban_python3=True)
        helper = _bootstrap_helper_script()
        proc = subprocess.run(
            [*command, "-m", "py_compile", str(helper)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr


@macos_only
class TestRealMacosCache:
    """Real ~/Library/Caches behavior, no mocks."""

    def test_cache_root_uses_library_caches(self):
        root = _get_cache_root()
        assert root == Path.home() / "Library" / "Caches" / "spyder-claude"

    def test_cache_root_directory_creates(self):
        root = _get_cache_root()
        root.mkdir(parents=True, exist_ok=True)
        assert root.is_dir()

    def test_helper_script_installs(self):
        target = _bootstrap_helper_script()
        assert target.exists()
        assert target.parent == _get_cache_root()
        assert target.stat().st_size > 0


@macos_only
class TestRealMacosInterpreter:
    """On macOS the helper interpreter is plain python3, which must exist."""

    def test_python3_is_selected(self):
        assert _host_python_command() == ("python3", [])

    def test_selected_interpreter_runs(self):
        command = _interpreter_command(ban_python3=False)
        proc = subprocess.run(
            [*command, "-c", "import sys; print(sys.version_info[0])"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == "3", proc.stdout

    def test_selected_interpreter_can_parse_helper(self):
        command = _interpreter_command(ban_python3=False)
        helper = _bootstrap_helper_script()
        proc = subprocess.run(
            [*command, "-m", "py_compile", str(helper)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
