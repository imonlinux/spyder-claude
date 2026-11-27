# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""SpyderClaude dockable plugin."""

import logging

from spyder.api.fonts import SpyderFontType
from spyder.api.plugin_registration.decorators import (
    on_plugin_available,
    on_plugin_teardown,
)
from spyder.api.plugins import Plugins, SpyderDockablePlugin
from spyder.api.translations import _
from spyder.utils.icon_manager import ima

from .config import CONF_DEFAULTS, CONF_SECTION, CONF_VERSION, LEGACY_SECURE_PLACEHOLDER
from .secure_conf import keyring_backend_available, keyring_write
from .widget.main_widget import ClaudeMainWidget
from .widget.preferences import ClaudeConfigPage

logger = logging.getLogger(__name__)

# Keys of this length class are always API keys, never accidental matches.
_MIN_API_KEY_LENGTH = 20


def update_panel_font(widget, get_font) -> None:
    """Resolve Spyder's interface font and apply it to the plugin widget.

    Module-level so the delegation stays testable under the headless test
    suite (the mocked spyder base classes cannot be entered).
    """
    widget.apply_fonts(get_font(SpyderFontType.Interface))


def migrate_plaintext_api_key(
    get_conf_func, set_conf_func, remove_conf_func
) -> str:
    """Move a plaintext ``api_key`` config value into keyring storage.

    ``set_conf_func`` must raise on failure. The plaintext is removed only
    after the secure write has returned successfully, so a failed write can
    never delete the only copy of the key.

    Returns a status string: ``"migrated"``, ``"empty"``, ``"skipped"`` or
    ``"failed:<reason>"``. The ``skipped`` case covers the placeholder written
    by pre-0.3.2 builds, whose own secure-storage scheme never stored the key
    anywhere recoverable — the user must re-enter it.
    """
    value = get_conf_func() or ""
    if not value.strip():
        return "empty"
    if value == LEGACY_SECURE_PLACEHOLDER:
        logger.warning(
            "Config contains the obsolete %r placeholder, which was never "
            "backed by actual storage. Please re-enter your API key in "
            "Preferences → Claude.",
            LEGACY_SECURE_PLACEHOLDER,
        )
        return "skipped"
    if len(value.strip()) < _MIN_API_KEY_LENGTH:
        logger.warning(
            "Config api_key value is too short to be an API key; leaving it "
            "untouched."
        )
        return "skipped"
    try:
        set_conf_func(value)
        remove_conf_func()
    except Exception as exc:
        return f"failed:{exc}"
    return "migrated"


class SpyderClaude(SpyderDockablePlugin):
    """Dockable panel that lets users query Claude from within Spyder."""

    NAME = "spyder_claude"
    REQUIRES = [Plugins.Preferences]
    OPTIONAL = [Plugins.Editor]
    CONF_SECTION = CONF_SECTION
    CONF_DEFAULTS = CONF_DEFAULTS
    CONF_VERSION = CONF_VERSION
    CONF_FILE = True
    CONF_WIDGET_CLASS = ClaudeConfigPage
    WIDGET_CLASS = ClaudeMainWidget
    CAN_BE_DISABLED = True

    # ---- SpyderDockablePlugin API ------------------------------------------

    @staticmethod
    def get_name():
        return _("Claude")

    @staticmethod
    def get_description():
        return _("Interact with Claude AI from within Spyder")

    @staticmethod
    def get_icon():
        return ima.icon("comment")

    def on_initialize(self):
        widget = self.get_widget()
        # Widget asks the plugin for editor content so the plugin can reach the
        # Editor plugin (widgets don't have direct access to sibling plugins).
        widget.sig_editor_content_requested.connect(
            self._provide_editor_content
        )
        self._migrate_plaintext_api_key()

    @on_plugin_available(plugin=Plugins.Preferences)
    def on_preferences_available(self):
        preferences = self.get_plugin(Plugins.Preferences)
        preferences.register_plugin_preferences(self)

    @on_plugin_teardown(plugin=Plugins.Preferences)
    def on_preferences_teardown(self):
        preferences = self.get_plugin(Plugins.Preferences)
        preferences.deregister_plugin_preferences(self)

    def on_close(self, cancelable=False):
        widget = self.get_widget()
        if widget is not None:
            widget.shutdown()

    def update_font(self):
        """Apply Spyder's interface font to the panel's text areas.

        Called by Spyder at plugin registration and again whenever the user
        applies a font change in Preferences → Appearance, so the panel
        tracks the interface font live without a restart.
        """
        update_panel_font(self.get_widget(), self.get_font)

    # ---- Private API -------------------------------------------------------

    def _migrate_plaintext_api_key(self):
        """Move a plaintext API key from the config file into the keyring.

        Uses the keyring directly rather than ``set_conf(..., secure=True)``:
        Spyder's CONF only reports a missing keyring backend via a modal
        dialog and then continues, which would let the migration delete the
        plaintext key even though nothing was stored. Here a failed write
        raises, the migration aborts, and the key stays in the config file.
        """
        if not keyring_backend_available():
            logger.warning(
                "No system keyring backend is available; the API key stays "
                "in the config file and will still be used. Install a "
                "Secret Service provider (gnome-keyring/KWallet) or the "
                "keyrings.alt package to enable secure storage."
            )
            return

        status = migrate_plaintext_api_key(
            get_conf_func=lambda: self.get_conf("api_key", default=""),
            set_conf_func=lambda v: keyring_write(CONF_SECTION, "api_key", v),
            remove_conf_func=lambda: self.remove_conf("api_key"),
        )
        if status == "migrated":
            logger.info("Moved plaintext API key into the system keyring")
        elif status.startswith("failed:"):
            logger.warning(
                "Could not store the API key in the system keyring (%s); "
                "it has been left in the config file and will still be used.",
                status.split(":", 1)[1],
            )

    def _provide_editor_content(self):
        """Fetch the active editor file and hand it to the widget."""
        content = ""
        filename = ""

        editor = self.get_plugin(Plugins.Editor)
        if editor is not None:
            try:
                current_editor = editor.get_current_editor()
                if current_editor is not None:
                    content = current_editor.toPlainText()
                    filename = editor.get_current_filename()
            except Exception:
                logger.exception("Failed to fetch active editor content")

        self.get_widget().inject_editor_content(content, filename)
