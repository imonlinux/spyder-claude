# -*- coding: utf-8 -*-
"""Tests for the plaintext API key → keyring migration.

The migration is the write path that puts API keys into Spyder's secure
conf storage; it is deliberately a free function so it can be tested
without a running Spyder instance.
"""

from unittest.mock import MagicMock

import pytest

from spyder_claude.plugin import migrate_plaintext_api_key
from spyder_claude.widget.main_widget import resolve_api_key

VALID_KEY = "sk-ant-api03-0123456789abcdefghijklmnopqrstuvwxyz"


class Store:
    """Minimal stand-in for the (get, set, remove) conf triple."""

    def __init__(self, initial=""):
        self.plaintext = initial
        self.keyring_value = None
        self.set_called = False
        self.remove_called = False

    def get(self):
        return self.plaintext

    def set(self, value):
        self.set_called = True
        self.keyring_value = value

    def remove(self):
        self.remove_called = True
        self.plaintext = ""


class TestMigratePlaintextApiKey:
    def test_migrates_valid_key(self):
        store = Store(VALID_KEY)
        status = migrate_plaintext_api_key(store.get, store.set, store.remove)
        assert status == "migrated"
        assert store.set_called
        assert store.keyring_value == VALID_KEY
        assert store.remove_called
        assert store.plaintext == ""

    def test_empty_config_is_noop(self):
        store = Store("")
        status = migrate_plaintext_api_key(store.get, store.set, store.remove)
        assert status == "empty"
        assert not store.set_called
        assert not store.remove_called

    def test_legacy_placeholder_skipped(self):
        # 0.3.0-0.3.1 wrote this placeholder but never actually stored the
        # key anywhere; migrating a literal "SECURE:stored" into keyring
        # would be wrong, so the user must re-enter the key.
        store = Store("SECURE:stored")
        status = migrate_plaintext_api_key(store.get, store.set, store.remove)
        assert status == "skipped"
        assert not store.set_called
        assert not store.remove_called

    def test_short_value_skipped(self):
        store = Store("short")
        status = migrate_plaintext_api_key(store.get, store.set, store.remove)
        assert status == "skipped"
        assert not store.set_called

    def test_set_failure_reports_and_does_not_remove(self):
        def failing_set(value):
            raise RuntimeError("no keyring backend")

        status = migrate_plaintext_api_key(
            lambda: VALID_KEY, failing_set, lambda: pytest.fail("remove called")
        )
        assert status.startswith("failed:")
        assert "no keyring backend" in status


class TestPluginWiring:
    # NOTE: under tests/conftest.py the Spyder API is mocked, so the
    # `class SpyderClaude(SpyderDockablePlugin)` statement yields a MagicMock
    # rather than a real class and its methods cannot be invoked here. The
    # wiring is therefore asserted at source level; the behaviour itself is
    # covered by TestMigratePlaintextApiKey above.

    def test_on_initialize_calls_migration(self):
        import inspect

        import spyder_claude.plugin as plugin_module

        source = inspect.getsource(plugin_module)
        assert "_migrate_plaintext_api_key()" in source

    def test_migration_writes_keyring_directly_and_guards_backend(self):
        import inspect

        import spyder_claude.plugin as plugin_module

        source = inspect.getsource(plugin_module)
        # Write via keyring (raises on failure) — NOT via CONF's
        # secure set, which shows a dialog and then continues as if
        # the write had succeeded.
        assert 'keyring_write(CONF_SECTION, "api_key", v)' in source
        assert 'self.remove_conf("api_key")' in source
        assert 'self.get_conf("api_key", default="")' in source
        # Skip cleanly when no keyring backend exists.
        assert "keyring_backend_available()" in source

    def test_migration_never_removes_before_successful_write(self):
        import inspect

        source = inspect.getsource(migrate_plaintext_api_key)
        # The remove call must come textually after the set call inside the
        # same try block, so a failed set aborts before deletion.
        assert source.index("set_conf_func(value)") < source.index(
            "remove_conf_func()"
        )


class TestResolveApiKey:
    def test_secure_value_wins(self):
        assert resolve_api_key(
            secure_get=lambda: "sk-secure-key-1234567890",
            plain_get=lambda: "sk-plain-key-1234567890",
        ) == "sk-secure-key-1234567890"

    def test_plain_fallback_when_secure_empty(self):
        assert resolve_api_key(
            secure_get=lambda: "",
            plain_get=lambda: "sk-plain-key-1234567890",
        ) == "sk-plain-key-1234567890"

    def test_plain_fallback_when_secure_raises(self):
        # E.g. NoKeyringError on systems without a keyring backend.
        def broken_secure_get():
            raise RuntimeError("No recommended backend was available.")

        assert resolve_api_key(
            secure_get=broken_secure_get,
            plain_get=lambda: "sk-plain-key-1234567890",
        ) == "sk-plain-key-1234567890"

    def test_empty_everywhere(self):
        assert resolve_api_key(secure_get=lambda: "", plain_get=lambda: "") == ""
