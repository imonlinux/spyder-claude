# -*- coding: utf-8 -*-
"""Tests for the direct keyring interop layer (secure_conf)."""

import sys
import types

import pytest

from spyder_claude.secure_conf import keyring_backend_available, keyring_write


def _install_keyring(monkeypatch, backend=None, set_password=None):
    fake = types.ModuleType("keyring")
    if backend is not None:
        fake.get_keyring = lambda: backend
    if set_password is not None:
        fake.set_password = set_password
    monkeypatch.setitem(sys.modules, "keyring", fake)
    return fake


class _Backend:
    def __init__(self, priority=5.0):
        self._priority = priority

    @property
    def priority(self):
        return self._priority


class _RaisingPriorityBackend:
    @property
    def priority(self):
        raise RuntimeError("broken backend")


class TestKeyringBackendAvailable:
    def test_true_with_real_backend(self, monkeypatch):
        _install_keyring(monkeypatch, backend=_Backend(priority=4.5))
        assert keyring_backend_available() is True

    def test_false_with_fail_backend(self, monkeypatch):
        # keyring's no-backend sentinel has priority 0
        _install_keyring(monkeypatch, backend=_Backend(priority=0))
        assert keyring_backend_available() is False

    def test_false_when_priority_raises(self, monkeypatch):
        _install_keyring(monkeypatch, backend=_RaisingPriorityBackend())
        assert keyring_backend_available() is False

    def test_false_when_keyring_missing(self, monkeypatch):
        # None in sys.modules makes `import keyring` raise ImportError
        monkeypatch.setitem(sys.modules, "keyring", None)
        assert keyring_backend_available() is False


class TestKeyringWrite:
    def test_writes_with_section_option_convention(self, monkeypatch):
        calls = []
        _install_keyring(
            monkeypatch,
            set_password=lambda svc, user, pw: calls.append((svc, user, pw)),
        )
        keyring_write("spyder_claude", "api_key", "sk-test")
        assert calls == [("spyder_claude", "api_key", "sk-test")]

    def test_raises_on_failure(self, monkeypatch):
        def boom(svc, user, pw):
            raise RuntimeError("no backend")

        _install_keyring(monkeypatch, set_password=boom)
        with pytest.raises(RuntimeError):
            keyring_write("spyder_claude", "api_key", "sk-test")
