# -*- coding: utf-8 -*-
# Copyright © spyder-claude contributors
# Licensed under the terms of the MIT License

"""SpyderClaude dockable plugin."""

from qtpy.QtGui import QIcon

from spyder.api.plugin_registration.decorators import (
    on_plugin_available,
    on_plugin_teardown,
)
from spyder.api.plugins import Plugins, SpyderDockablePlugin
from spyder.api.translations import _

from .config import CONF_DEFAULTS, CONF_SECTION, CONF_VERSION
from .widget.main_widget import ClaudeMainWidget
from .widget.preferences import ClaudeConfigPage


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
        return QIcon()

    def on_initialize(self):
        widget = self.get_widget()
        # Widget asks the plugin for editor content so the plugin can reach the
        # Editor plugin (widgets don't have direct access to sibling plugins).
        widget.sig_editor_content_requested.connect(
            self._provide_editor_content
        )

    @on_plugin_available(plugin=Plugins.Preferences)
    def on_preferences_available(self):
        preferences = self.get_plugin(Plugins.Preferences)
        preferences.register_plugin_preferences(self)

    @on_plugin_teardown(plugin=Plugins.Preferences)
    def on_preferences_teardown(self):
        preferences = self.get_plugin(Plugins.Preferences)
        preferences.deregister_plugin_preferences(self)
        widget = self.get_widget()
        if widget is not None and widget._thread.isRunning():
            widget._thread.quit()
            widget._thread.wait(3000)

    # ---- Private API -------------------------------------------------------

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
                pass

        self.get_widget().inject_editor_content(content, filename)
