"""Centralized theme for Voice Type - light/dark palettes + QSS + vector icons.

Provides:
- :class:`Palette` dataclass with :data:`DARK_PALETTE` / :data:`LIGHT_PALETTE`
- Active-palette switching: :func:`get_palette`, :func:`apply_theme_mode`
- :func:`settings_qss` / :func:`apply_dialog_theme` for settings-style dialogs
- Vector icons (gear/close/refresh/eye) cached per palette so they regenerate
  automatically when the theme switches

The palette is resolved dynamically (``theme.ACCENT`` reads the active palette
via module ``__getattr__``), so code that reads colors at call time sees theme
switches. Code that needs to react to a switch should call :func:`get_palette`
inside its paint/refresh path rather than capturing a constant at import.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    """All colors the UI needs, as hex strings.

    Fields are grouped: surfaces, borders, text, accent (primary action),
    and semantic state colors (danger=stop/recording, success=level,
    warning=processing/busy).
    """

    # Surfaces
    bg_dialog: str
    bg_card: str
    bg_input: str
    bg_hover: str
    # Borders
    border: str
    border_hover: str
    border_focus: str
    # Text
    text_primary: str
    text_secondary: str
    text_disabled: str
    text_title: str
    # Accent (primary CTA / idle)
    accent: str
    accent_hover: str
    accent_pressed: str
    # Semantic state
    danger: str
    danger_hover: str
    danger_light: str   # lighter hover variant for recording-stop button
    success: str
    warning: str
    warning_hover: str
    warning_pressed: str


DARK_PALETTE = Palette(
    bg_dialog="#1a1b26",
    bg_card="#24253a",
    bg_input="#16172a",
    bg_hover="#2e2f48",
    border="#3a3b52",
    border_hover="#5a5b72",
    border_focus="#7c8cff",
    text_primary="#e5e7eb",
    text_secondary="#9ca3af",
    text_disabled="#6b7280",
    text_title="#c7c9ff",
    accent="#7c8cff",
    accent_hover="#8b9aff",
    accent_pressed="#6366f1",
    danger="#ef4444",
    danger_hover="#dc2626",
    danger_light="#f87171",
    success="#22c55e",
    warning="#f59e0b",
    warning_hover="#fbbf24",
    warning_pressed="#d97706",
)

LIGHT_PALETTE = Palette(
    bg_dialog="#f8fafc",        # slate-50 - outer dialog
    bg_card="#ffffff",          # white cards on the slate backdrop
    bg_input="#ffffff",
    bg_hover="#f1f5f9",         # slate-100 hover lift
    border="#e2e8f0",           # slate-200
    border_hover="#cbd5e1",     # slate-300
    border_focus="#6366f1",     # indigo-600 (darker than dark mode for AA on white)
    text_primary="#1e293b",     # slate-800
    text_secondary="#64748b",   # slate-500 (>=4.5:1 on white)
    text_disabled="#cbd5e1",    # slate-300
    text_title="#4f46e5",       # indigo-600
    accent="#6366f1",           # indigo-600
    accent_hover="#4f46e5",     # indigo-700
    accent_pressed="#4338ca",   # indigo-800
    danger="#ef4444",
    danger_hover="#dc2626",
    danger_light="#f87171",
    success="#16a34a",          # green-600 (darker for light-bg contrast)
    warning="#d97706",          # amber-600 (#f59e0b is too pale on white)
    warning_hover="#b45309",    # amber-700
    warning_pressed="#92400e",  # amber-800
)


# ---------------------------------------------------------------------------
# Active palette
# ---------------------------------------------------------------------------

_active_palette: Palette = DARK_PALETTE


def get_palette() -> Palette:
    """Return the currently active palette."""
    return _active_palette


def set_active_palette(palette: Palette) -> None:
    """Set the active palette directly (used by :func:`apply_theme_mode`)."""
    global _active_palette
    _active_palette = palette


def system_uses_light() -> bool:
    """Detect whether the OS is in light mode.

    On Windows, reads ``AppsUseLightTheme`` from the personalization registry
    key. Defaults to ``False`` (dark) when the value can't be read (non-Windows,
    missing key, etc.) so the app stays on its native dark look rather than
    flashing white on an unknown environment.
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return bool(value)
    except (OSError, FileNotFoundError, ImportError):
        return False


def palette_for_mode(mode: str) -> Palette:
    """Resolve a theme mode (``dark``/``light``/``system``) to a Palette."""
    if mode == "light":
        return LIGHT_PALETTE
    if mode == "dark":
        return DARK_PALETTE
    # "system" (and any unknown value) follows the OS.
    return LIGHT_PALETTE if system_uses_light() else DARK_PALETTE


def apply_theme_mode(mode: str) -> Palette:
    """Set the active palette from a theme mode and return it.

    Icons are cached per-color (see ``_icon_cache``), so a palette change
    naturally produces fresh icons on the next ``*_icon()`` call - callers
    just need to re-``setIcon`` on their buttons.
    """
    palette = palette_for_mode(mode)
    set_active_palette(palette)
    return palette


# Backward-compatible dynamic color access. ``theme.ACCENT`` resolves to the
# active palette's ``accent`` field at access time, so code reading it at call
# time (paint events, stylesheet rebuilds) sees theme switches automatically.
# NOTE: ``from theme import ACCENT`` captures a snapshot at import - callers
# that must react to switches should use ``get_palette()`` instead.
#
# _CONST_NAMES is automatically derived from Palette fields to avoid manual sync.
_CONST_NAMES = frozenset(field.name.upper() for field in Palette.__dataclass_fields__.values())


def __getattr__(name: str):
    """Resolve UPPERCASE color names against the active palette dynamically."""
    if name in _CONST_NAMES:
        return getattr(get_palette(), name.lower())
    if name == "HINT_STYLESHEET":
        return hint_stylesheet()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def hint_stylesheet() -> str:
    """Secondary-text stylesheet for hint labels (reflects active palette)."""
    return f"color: {get_palette().text_secondary}; font-size: 12px;"


# ---------------------------------------------------------------------------
# Checkmark image for styled checkboxes
# ---------------------------------------------------------------------------
# Qt QSS can't draw a checkmark glyph on QCheckBox::indicator without an
# image, so we render a white check once to a temp PNG and reference it
# via url() in the stylesheet. Cached for the process lifetime. The white
# check works on the indigo accent in both light and dark mode, so a single
# image serves both palettes.

_checkmark_path: str | None = None


def _checkmark_image_path() -> str:
    """Generate (once) and return the path to a white checkmark PNG."""
    global _checkmark_path
    if _checkmark_path and Path(_checkmark_path).exists():
        return _checkmark_path

    size = 18
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(255, 255, 255), 2.4)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(3.5, 9.5)
    path.lineTo(7.5, 13)
    path.lineTo(14.5, 5)
    painter.drawPath(path)
    painter.end()

    fd, path_str = tempfile.mkstemp(suffix=".png", prefix="vt_check_")
    os.close(fd)
    pm.save(path_str, "PNG")
    _checkmark_path = path_str
    return path_str


# ---------------------------------------------------------------------------
# Vector icons (refresh, eye, eye-off, gear, close)
# ---------------------------------------------------------------------------
# Emoji like 🔄 / ⏳ / ⚙ are font-dependent and render inconsistently across
# platforms (violates the no-emoji-icons rule), so we draw clean vector glyphs
# with QPainter. Each icon is cached per (name, color) so a theme switch
# (which changes text_secondary) produces fresh icons automatically - callers
# just re-setIcon on their buttons.

_icon_cache: dict[tuple[str, str], QIcon] = {}


def _draw_refresh_pixmap(color: QColor) -> QPixmap:
    """Draw a circular refresh arrow (Lucide refresh-cw style)."""
    size = 18
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)

    cx = cy = size / 2.0
    r = (size - 5) / 2.0
    rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)

    start = 60.0
    sweep = -270.0
    path = QPainterPath()
    path.arcMoveTo(rect, start)
    path.arcTo(rect, start, sweep)
    p.drawPath(path)

    end_rad = math.radians(start + sweep)  # -210° == 150° (upper-left)
    ex = cx + r * math.cos(end_rad)
    ey = cy - r * math.sin(end_rad)
    tx = math.sin(end_rad)
    ty = math.cos(end_rad)
    back, half = 4.2, 2.8
    bcx, bcy = ex - tx * back, ey - ty * back
    nx, ny = -ty, tx
    tri = QPolygonF([
        QPointF(ex, ey),
        QPointF(bcx + nx * half, bcy + ny * half),
        QPointF(bcx - nx * half, bcy - ny * half),
    ])
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawPolygon(tri)
    p.end()
    return pm


def _draw_eye_pixmap(color: QColor, slashed: bool = False) -> QPixmap:
    """Draw an eye (open, or with a slash for the hidden state)."""
    size = 18
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 1.5)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    center = QPointF(size / 2.0, size / 2.0)
    p.drawEllipse(center, 6.0, 3.4)
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawEllipse(center, 1.7, 1.7)
    if slashed:
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawLine(QPointF(3.0, 3.0), QPointF(size - 3.0, size - 3.0))
    p.end()
    return pm


def _draw_gear_pixmap(color: QColor) -> QPixmap:
    """Draw a line-art gear (Lucide settings style) with 8 teeth."""
    size = 18
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    cx = cy = size / 2.0
    teeth = 8
    r_tip = 7.2
    r_root = 5.1
    tip_half = 7.0                       # half angular width of a tooth tip
    valley_half = 45.0 / 2 - tip_half    # half width of the gap between teeth

    path = QPainterPath()
    for i in range(teeth):
        c = i * 45.0
        # -90 so 0° points up (tooth at 12 o'clock first), screen y is down.
        a_left = math.radians(c - tip_half - 90)
        a_right = math.radians(c + tip_half - 90)
        a_valley = math.radians(c + tip_half + valley_half - 90)
        p_left = QPointF(cx + r_tip * math.cos(a_left), cy + r_tip * math.sin(a_left))
        p_right = QPointF(cx + r_tip * math.cos(a_right), cy + r_tip * math.sin(a_right))
        p_valley = QPointF(cx + r_root * math.cos(a_valley), cy + r_root * math.sin(a_valley))
        if i == 0:
            path.moveTo(p_left)
        else:
            path.lineTo(p_left)
        path.lineTo(p_right)
        path.lineTo(p_valley)
    path.closeSubpath()
    p.drawPath(path)
    p.drawEllipse(QPointF(cx, cy), 2.3, 2.3)  # axle hole
    p.end()
    return pm


def _draw_close_pixmap(color: QColor) -> QPixmap:
    """Draw an X close glyph with rounded caps."""
    size = 18
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 1.7)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(5.5, 5.5), QPointF(12.5, 12.5))
    p.drawLine(QPointF(12.5, 5.5), QPointF(5.5, 12.5))
    p.end()
    return pm


def _cached_icon(name: str, color_hex: str, painter) -> QIcon:
    """Return a cached QIcon for (name, color), rendering it on first use."""
    key = (name, color_hex)
    icon = _icon_cache.get(key)
    if icon is None:
        icon = QIcon(painter(QColor(color_hex)))
        _icon_cache[key] = icon
    return icon


def refresh_icon() -> QIcon:
    return _cached_icon("refresh", get_palette().text_secondary, _draw_refresh_pixmap)


def eye_icon() -> QIcon:
    return _cached_icon("eye", get_palette().text_secondary, _draw_eye_pixmap)


def eye_off_icon() -> QIcon:
    return _cached_icon("eye_off", get_palette().text_secondary,
                        lambda c: _draw_eye_pixmap(c, slashed=True))


def gear_icon() -> QIcon:
    return _cached_icon("gear", get_palette().text_secondary, _draw_gear_pixmap)


def close_icon() -> QIcon:
    return _cached_icon("close", get_palette().text_secondary, _draw_close_pixmap)


# ---------------------------------------------------------------------------
# Chevron arrow images for QSpinBox / QComboBox sub-controls
# ---------------------------------------------------------------------------
# QSS sub-controls (QSpinBox::up-arrow, QComboBox::down-arrow) can't use a
# QIcon - they need an ``image: url(...)`` file. We render crisp Lucide-style
# chevron arrows (a clear V/^ shape, not a border-trick triangle which reads
# as a wedge/dot) to temp PNGs, cached per (direction, color). On a theme
# switch the color changes so a fresh PNG is generated and settings_qss()
# re-issues the new path - Qt reloads the image.

_arrow_paths: dict[tuple[str, str], str] = {}


def _draw_chevron_pixmap(direction: str, color: QColor) -> QPixmap:
    """Draw a Lucide-style chevron arrow (``down`` = V, ``up`` = ^)."""
    size = 16
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(color, 2.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QPainterPath()
    if direction == "down":
        path.moveTo(3.5, 6.0)
        path.lineTo(8.0, 10.5)
        path.lineTo(12.5, 6.0)
    else:  # up
        path.moveTo(3.5, 10.5)
        path.lineTo(8.0, 6.0)
        path.lineTo(12.5, 10.5)
    p.drawPath(path)
    p.end()
    return pm


def _arrow_image_path(direction: str, color_hex: str) -> str:
    """Return the path to a chevron-arrow PNG in *color_hex* (cached per color).

    Called from :func:`settings_qss` so the arrows match the active palette;
    a theme switch produces a new color -> a new PNG -> a new url() in the
    re-applied QSS.
    """
    key = (direction, color_hex)
    path = _arrow_paths.get(key)
    if path and Path(path).exists():
        return path
    pm = _draw_chevron_pixmap(direction, QColor(color_hex))
    fd, path_str = tempfile.mkstemp(suffix=f"_arrow_{direction}.png", prefix="vt_")
    os.close(fd)
    pm.save(path_str, "PNG")
    _arrow_paths[key] = path_str
    return path_str


# ---------------------------------------------------------------------------
# QSS stylesheet
# ---------------------------------------------------------------------------

def settings_qss() -> str:
    """Return the QSS stylesheet for settings-style dialogs.

    Reads the active palette, so re-calling :func:`apply_dialog_theme` after a
    theme switch re-skins the whole dialog tree (popups and child dialogs
    included) without recreating widgets.
    """
    p = get_palette()
    chk = _checkmark_image_path().replace("\\", "/")
    # Chevron arrows for spinbox/combobox sub-controls, in the active palette's
    # text color (and a dimmed variant for the disabled state).
    arr_up = _arrow_image_path("up", p.text_primary).replace("\\", "/")
    arr_down = _arrow_image_path("down", p.text_primary).replace("\\", "/")
    arr_up_dis = _arrow_image_path("up", p.text_disabled).replace("\\", "/")
    arr_down_dis = _arrow_image_path("down", p.text_disabled).replace("\\", "/")
    return f"""
    /* ---- Dialog & containers ---- */
    QDialog {{
        background-color: {p.bg_dialog};
        color: {p.text_primary};
        font-size: 13px;
    }}

    QGroupBox {{
        background-color: {p.bg_card};
        border: 1px solid {p.border};
        border-radius: 10px;
        margin-top: 16px;
        padding: 18px 14px 12px 14px;
        font-weight: 600;
        color: {p.text_primary};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 0 8px;
        background-color: {p.bg_dialog};
        color: {p.text_title};
        font-size: 13px;
    }}

    QLabel {{
        color: {p.text_primary};
        background: transparent;
    }}
    QLabel:disabled {{
        color: {p.text_disabled};
    }}
    /* Hint labels - secondary text, set via objectName so a QSS refresh
       re-skins them without touching each label's inline stylesheet. */
    QLabel#hintLabel {{
        color: {p.text_secondary};
        font-size: 12px;
        background: transparent;
    }}
    QLabel#errorLabel {{
        color: {p.danger};
        font-size: 12px;
        background: transparent;
    }}

    /* ---- Tab widget (clean underline tabs) ---- */
    QTabWidget::pane {{
        border: none;
        background: transparent;
        top: -1px;
    }}
    QTabBar {{
        background: transparent;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p.text_secondary};
        padding: 8px 18px;
        border: none;
        border-bottom: 2px solid transparent;
        margin: 0 2px;
        font-weight: 500;
    }}
    QTabBar::tab:hover {{
        color: {p.text_primary};
    }}
    QTabBar::tab:selected {{
        color: {p.text_primary};
        border-bottom: 2px solid {p.accent};
    }}

    /* ---- Line edits ---- */
    QLineEdit {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 6px 10px;
        color: {p.text_primary};
        selection-background-color: {p.accent};
        selection-color: white;
    }}
    QLineEdit:hover {{
        border-color: {p.border_hover};
    }}
    QLineEdit:focus {{
        border: 1px solid {p.border_focus};
        background-color: {p.bg_card};
    }}
    QLineEdit:disabled {{
        background-color: {p.bg_dialog};
        color: {p.text_disabled};
        border-color: {p.border};
    }}
    QLineEdit[readOnly="true"] {{
        background-color: {p.bg_dialog};
        color: {p.text_secondary};
    }}

    /* ---- Combo boxes ---- */
    QComboBox {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 6px 10px;
        color: {p.text_primary};
        min-height: 24px;
    }}
    QComboBox:hover {{
        border-color: {p.border_hover};
    }}
    QComboBox:focus {{
        border: 1px solid {p.border_focus};
    }}
    QComboBox:disabled {{
        background-color: {p.bg_dialog};
        color: {p.text_disabled};
    }}
    /* The drop-down button is a distinct clickable zone: a left separator
       border + its own hover/pressed background make it obvious that the
       right edge opens the list (previously a tiny low-contrast triangle
       with no hover affordance). */
    QComboBox::drop-down {{
        border: none;
        border-left: 1px solid {p.border};
        width: 28px;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }}
    QComboBox::drop-down:hover {{
        background: {p.bg_hover};
    }}
    QComboBox::drop-down:pressed {{
        background: {p.border};
    }}
    QComboBox::down-arrow {{
        image: url({arr_down});
        width: 16px;
        height: 16px;
    }}
    QComboBox::down-arrow:disabled {{
        image: url({arr_down_dis});
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.bg_card};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 4px;
        selection-background-color: {p.accent};
        selection-color: white;
        outline: none;
    }}
    QComboBox QLineEdit {{
        background: transparent;
        border: none;
        padding: 0;
    }}

    /* ---- Spin boxes ---- */
    QSpinBox {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 6px 10px;
        color: {p.text_primary};
        min-height: 24px;
    }}
    QSpinBox:hover {{
        border-color: {p.border_hover};
    }}
    QSpinBox:focus {{
        border: 1px solid {p.border_focus};
    }}
    QSpinBox:disabled {{
        background-color: {p.bg_dialog};
        color: {p.text_disabled};
    }}
    /* Up/down buttons are widened to a comfortable hit area and given a
       separator border + hover/pressed backgrounds so they read as
       distinct clickable controls. The arrows are crisp chevron PNGs
       (see _arrow_image_path), not border-trick triangles. */
    QSpinBox::up-button, QSpinBox::down-button {{
        background: transparent;
        border: none;
        border-left: 1px solid {p.border};
        width: 26px;
    }}
    QSpinBox::up-button {{
        border-top-right-radius: 6px;
    }}
    QSpinBox::down-button {{
        border-bottom-right-radius: 6px;
        border-top: 1px solid {p.border};
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background: {p.bg_hover};
    }}
    QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {{
        background: {p.border};
    }}
    QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {{
        border-left-color: {p.border};
        border-top-color: {p.border};
    }}
    QSpinBox::up-arrow {{
        image: url({arr_up});
        width: 16px;
        height: 16px;
    }}
    QSpinBox::down-arrow {{
        image: url({arr_down});
        width: 16px;
        height: 16px;
    }}
    QSpinBox::up-arrow:disabled {{
        image: url({arr_up_dis});
    }}
    QSpinBox::down-arrow:disabled {{
        image: url({arr_down_dis});
    }}

    /* ---- Checkboxes ---- */
    QCheckBox {{
        color: {p.text_primary};
        spacing: 8px;
        background: transparent;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 2px solid {p.border};
        border-radius: 4px;
        background-color: {p.bg_input};
    }}
    QCheckBox::indicator:hover {{
        border-color: {p.border_focus};
    }}
    QCheckBox::indicator:checked {{
        background-color: {p.accent};
        border-color: {p.accent};
        image: url({chk});
    }}
    QCheckBox::indicator:disabled {{
        border-color: {p.border};
        background-color: {p.bg_dialog};
    }}

    /* ---- Buttons ---- */
    QPushButton {{
        background-color: {p.bg_hover};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 7px 16px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {p.border};
        border-color: {p.border_hover};
    }}
    QPushButton:pressed {{
        background-color: {p.bg_card};
    }}
    QPushButton:disabled {{
        color: {p.text_disabled};
        background-color: {p.bg_dialog};
        border-color: {p.border};
    }}

    QPushButton#primaryButton {{
        background-color: {p.accent};
        border: none;
        color: white;
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {p.accent_hover};
    }}
    QPushButton#primaryButton:pressed {{
        background-color: {p.accent_pressed};
    }}
    QPushButton#primaryButton:disabled {{
        background-color: {p.border};
        color: {p.text_disabled};
    }}

    QPushButton#dangerButton {{
        color: {p.danger};
        border-color: {p.danger_hover};
    }}
    QPushButton#dangerButton:hover {{
        background-color: rgba(239, 68, 68, 0.15);
        border-color: {p.danger};
    }}
    QPushButton#dangerButton:pressed {{
        background-color: rgba(239, 68, 68, 0.25);
    }}

    /* ---- Progress bar (mic level) ---- */
    QProgressBar {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 5px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: {p.success};
        border-radius: 4px;
    }}

    /* ---- Table (glossary) ---- */
    QTableWidget {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 6px;
        gridline-color: {p.border};
        color: {p.text_primary};
        selection-background-color: {p.accent};
        selection-color: white;
        outline: none;
    }}
    QTableWidget::item {{
        padding: 4px 8px;
        border: none;
    }}
    QTableWidget::item:selected {{
        background-color: {p.accent};
        color: white;
    }}
    QHeaderView::section {{
        background-color: {p.bg_card};
        color: {p.text_secondary};
        border: none;
        border-bottom: 1px solid {p.border};
        border-right: 1px solid {p.border};
        padding: 6px 10px;
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background-color: {p.bg_card};
        border: none;
        border-bottom: 1px solid {p.border};
    }}

    /* ---- List views (completer popup, history list, etc.) ---- */
    QListView {{
        background-color: {p.bg_card};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 4px;
        selection-background-color: {p.accent};
        selection-color: white;
        outline: none;
    }}
    QListView::item {{
        color: {p.text_primary};
    }}

    /* ---- Text edit (history preview) ---- */
    QTextEdit {{
        background-color: {p.bg_input};
        border: 1px solid {p.border};
        border-radius: 6px;
        color: {p.text_primary};
        selection-background-color: {p.accent};
        selection-color: white;
    }}

    /* ---- Scrollbars ---- */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {p.border};
        border-radius: 4px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p.border_hover};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {p.border};
        border-radius: 4px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {p.border_hover};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}

    /* ---- Dialog button box ---- */
    QDialogButtonBox QPushButton {{
        min-width: 80px;
    }}

    /* ---- Tooltips ---- */
    QToolTip {{
        background-color: {p.bg_card};
        color: {p.text_primary};
        border: 1px solid {p.border};
        border-radius: 4px;
        padding: 4px 8px;
    }}
    """


def apply_dialog_theme(dialog) -> None:
    """Apply the settings theme stylesheet to *dialog* and its children.

    Re-call after a theme switch to re-skin an already-visible dialog.
    """
    dialog.setStyleSheet(settings_qss())
