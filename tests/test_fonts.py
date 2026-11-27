# -*- coding: utf-8 -*-
"""Tests for interface-font handling (issue #2).

Spyder calls the plugin's update_font() at registration and again on every
font change in Preferences → Appearance, so the panel must request the
Interface font and set it on both text areas. The logic lives in module-level
pure functions (update_panel_font, apply_font_to_areas) because the mocked
spyder base classes cannot be instantiated headlessly; the class methods are
one-line delegations to them.
"""

from unittest.mock import MagicMock

from spyder.api.fonts import SpyderFontType

from spyder_claude.plugin import update_panel_font
from spyder_claude.widget.main_widget import apply_font_to_areas


class TestUpdatePanelFont:
    def test_requests_interface_font_and_applies_to_widget(self):
        widget = MagicMock()
        get_font = MagicMock()

        update_panel_font(widget, get_font)

        get_font.assert_called_once_with(SpyderFontType.Interface)
        widget.apply_fonts.assert_called_once_with(get_font.return_value)


class TestApplyFontToAreas:
    def test_font_set_on_both_areas(self):
        response_area = MagicMock()
        input_area = MagicMock()
        font = MagicMock()

        apply_font_to_areas(response_area, input_area, font)

        response_area.setFont.assert_called_once_with(font)
        input_area.setFont.assert_called_once_with(font)
