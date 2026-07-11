"""Tests for voicetype.ui.theme - palettes, theme switching, vector icons.

Tests that touch QPixmap / QIcon need a QApplication; the ``qapp`` fixture
from pytest-qt provides one. Pure palette checks don't.
"""

from PySide6.QtGui import QColor, QIcon, QPixmap

from voicetype.ui import theme
from voicetype.ui.theme import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    Palette,
    apply_theme_mode,
    get_palette,
    palette_for_mode,
    set_active_palette,
)

import pytest


@pytest.fixture(autouse=True)
def _restore_palette():
    """Restore the active palette after each test so switches don't leak."""
    saved = get_palette()
    yield
    set_active_palette(saved)


class TestPalettes:
    """Both palettes are fully populated and semantically distinct."""

    def test_dark_palette_fields(self):
        p = DARK_PALETTE
        assert p.bg_dialog.startswith("#")
        assert p.accent.startswith("#")
        assert p.danger.startswith("#")
        assert p.warning.startswith("#")
        assert p.success.startswith("#")

    def test_light_palette_fields(self):
        p = LIGHT_PALETTE
        assert p.bg_dialog.startswith("#")
        assert p.accent.startswith("#")
        assert p.danger.startswith("#")
        assert p.warning.startswith("#")
        assert p.success.startswith("#")

    def test_light_and_dark_differ(self):
        """Light and dark must not be the same palette."""
        assert DARK_PALETTE.bg_dialog != LIGHT_PALETTE.bg_dialog
        assert DARK_PALETTE.text_primary != LIGHT_PALETTE.text_primary

    def test_dynamic_color_access_reads_active(self):
        """theme.ACCENT resolves to the active palette at access time."""
        set_active_palette(DARK_PALETTE)
        assert theme.ACCENT == DARK_PALETTE.accent
        set_active_palette(LIGHT_PALETTE)
        assert theme.ACCENT == LIGHT_PALETTE.accent

    def test_unknown_attribute_raises(self):
        with pytest.raises(AttributeError):
            _ = theme.NOT_A_COLOR


class TestThemeSwitching:
    def test_get_palette_returns_active(self):
        set_active_palette(LIGHT_PALETTE)
        assert get_palette() is LIGHT_PALETTE

    def test_apply_theme_mode_dark(self):
        assert apply_theme_mode("dark") is DARK_PALETTE
        assert get_palette() is DARK_PALETTE

    def test_apply_theme_mode_light(self):
        assert apply_theme_mode("light") is LIGHT_PALETTE
        assert get_palette() is LIGHT_PALETTE

    def test_palette_for_mode_system_falls_back(self):
        # "system" resolves to a real palette (either light or dark) without
        # raising, regardless of the host OS.
        assert palette_for_mode("system") in (LIGHT_PALETTE, DARK_PALETTE)

    def test_palette_for_mode_unknown_defaults_to_system(self):
        assert palette_for_mode("nonsense") in (LIGHT_PALETTE, DARK_PALETTE)


class TestSettingsQss:
    def test_qss_uses_active_palette(self, qapp):
        set_active_palette(DARK_PALETTE)
        dark_qss = theme.settings_qss()
        assert DARK_PALETTE.accent in dark_qss
        assert DARK_PALETTE.bg_dialog in dark_qss

        set_active_palette(LIGHT_PALETTE)
        light_qss = theme.settings_qss()
        assert LIGHT_PALETTE.accent in light_qss
        assert LIGHT_PALETTE.bg_dialog in light_qss
        # The two themes produce different stylesheets.
        assert dark_qss != light_qss

    def test_qss_has_hint_and_error_label_rules(self, qapp):
        """Hint/error labels are styled via objectName so a QSS refresh re-skins them."""
        qss = theme.settings_qss()
        assert "QLabel#hintLabel" in qss
        assert "QLabel#errorLabel" in qss

    def test_qss_spinbox_buttons_are_visible_and_interactive(self, qapp):
        """SpinBox up/down buttons have hover/pressed feedback and clear chevron arrows.

        Regression: the buttons used to be 18px-wide transparent zones with tiny
        border-trick triangles (read as wedges/dots). They now have a separator
        border, hover/pressed backgrounds, wider hit area, and crisp chevron
        arrow PNGs via image: url().
        """
        qss = theme.settings_qss()
        # Wider hit area (was 18px, then 24px, now 26px for 16px chevrons).
        assert "width: 26px" in qss
        # Hover + pressed feedback on the buttons.
        assert "QSpinBox::up-button:hover" in qss
        assert "QSpinBox::down-button:pressed" in qss
        # Separator between the input and the button zone.
        assert "border-left: 1px solid" in qss
        # Crisp chevron arrows via image (not border-trick triangles).
        assert "QSpinBox::up-arrow" in qss and "image: url(" in qss
        assert "QSpinBox::down-arrow" in qss
        # No leftover border-trick triangle rules.
        assert "border-bottom: 7px solid" not in qss

    def test_qss_combobox_dropdown_is_visible_and_interactive(self, qapp):
        """ComboBox drop-down has hover/pressed feedback and a clear chevron arrow."""
        qss = theme.settings_qss()
        assert "QComboBox::drop-down:hover" in qss
        assert "QComboBox::drop-down:pressed" in qss
        assert "width: 28px" in qss
        # Clear chevron arrow via image (not a border-trick triangle).
        assert "QComboBox::down-arrow" in qss and "image: url(" in qss
        assert "border-top: 7px solid" not in qss

    def test_qss_inputs_have_hover_state(self, qapp):
        """All text inputs give hover feedback (border brightens) for consistency."""
        qss = theme.settings_qss()
        assert "QLineEdit:hover" in qss
        assert "QSpinBox:hover" in qss

    def test_chevron_arrows_themed_per_palette(self, qapp):
        """Arrow PNGs are generated in the active palette's text color, so a
        theme switch produces a different image url in the re-applied QSS."""
        set_active_palette(DARK_PALETTE)
        dark_qss = theme.settings_qss()
        dark_path = theme._arrow_image_path("down", DARK_PALETTE.text_primary).replace("\\", "/")
        assert dark_path in dark_qss
        set_active_palette(LIGHT_PALETTE)
        light_qss = theme.settings_qss()
        light_path = theme._arrow_image_path("down", LIGHT_PALETTE.text_primary).replace("\\", "/")
        assert light_path in light_qss
        # Different palettes -> different arrow image files -> different urls.
        assert dark_path != light_path

    def test_chevron_pixmap_renders(self, qapp):
        pm = theme._draw_chevron_pixmap("down", QColor("#ffffff"))
        assert isinstance(pm, QPixmap)
        assert pm.width() == 16 and pm.height() == 16


class TestVectorIcons:
    """Vector icons are generated and cached per palette (no emoji)."""

    def test_gear_icon_valid(self, qapp):
        icon = theme.gear_icon()
        assert isinstance(icon, QIcon)
        assert not icon.isNull()

    def test_close_icon_valid(self, qapp):
        assert not theme.close_icon().isNull()

    def test_existing_icons_still_work(self, qapp):
        assert not theme.refresh_icon().isNull()
        assert not theme.eye_icon().isNull()
        assert not theme.eye_off_icon().isNull()

    def test_gear_pixmap_is_18px(self, qapp):
        pm = theme._draw_gear_pixmap(QColor("#9ca3af"))
        assert isinstance(pm, QPixmap)
        assert pm.width() == 18 and pm.height() == 18

    def test_icons_regenerate_on_theme_switch(self, qapp):
        """Icons are cached per color, so a palette switch yields a fresh icon."""
        set_active_palette(DARK_PALETTE)
        dark_gear = theme.gear_icon()
        set_active_palette(LIGHT_PALETTE)
        light_gear = theme.gear_icon()
        # Different text_secondary -> different cache entry -> different QIcon.
        assert not light_gear.isNull()
        # The dark icon is still valid (cached, not invalidated).
        assert not dark_gear.isNull()
