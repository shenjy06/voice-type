"""Floating recording window - compact widget with record button."""

import collections
import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QApplication, QLabel,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QElapsedTimer
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QCursor, QCloseEvent
from voicetype.state import RecorderState
from voicetype.i18n import t
from voicetype.ui.theme import get_palette, gear_icon, close_icon

# Default font family - fall back to a platform-appropriate list if unavailable
_DEFAULT_FONT_FAMILIES = ("Segoe UI", "Microsoft YaHei", "Helvetica", "Arial")

logger = logging.getLogger(__name__)


def _default_font(size: int) -> QFont:
    """Return a font using the application default family when available."""
    base = QApplication.font()
    if base.family():
        return QFont(base.family(), size)
    for family in _DEFAULT_FONT_FAMILIES:
        font = QFont(family, size)
        if font.exactMatch() or QFontMetrics(font).height() > 0:
            return font
    return QFont("", size)


# Record button style per state. The button cycles indigo (idle CTA) ->
# red (recording = stop) -> amber (processing = busy), matching the semantic
# state colors used everywhere else in the app. Reads the active palette so a
# theme switch takes effect on the next _update_record_button() call.
def _button_style(state: RecorderState, p) -> str | None:
    """Return the record-button stylesheet for *state*, or None for idle.

    Idle falls back to the accent stylesheet applied by _update_record_button.
    """
    if state == RecorderState.RECORDING:
        return (
            f"QPushButton {{ background: {p.danger}; color: white; "
            f"border: none; border-radius: 8px; font-size: 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: #f87171; }}"
            f"QPushButton:pressed {{ background: {p.danger_hover}; }}"
        )
    if state == RecorderState.PROCESSING:
        return (
            f"QPushButton {{ background: {p.warning}; color: white; "
            f"border: none; border-radius: 8px; font-size: 14px; font-weight: 600; }}"
            f"QPushButton:hover {{ background: {p.warning_hover}; }}"
            f"QPushButton:pressed {{ background: {p.warning_pressed}; }}"
        )
    return None


_BUTTON_TEXT_KEYS = {
    RecorderState.RECORDING: "btn.recording",
    RecorderState.PROCESSING: "btn.polishing",
    RecorderState.IDLE: "btn.record",
    RecorderState.DONE: "btn.record",
    RecorderState.ERROR: "btn.record",
}


class PulsingDot(QWidget):
    """A small red dot that pulses when recording."""

    _OPAQUE = 1.0
    _TRANSPARENT = 0.3
    _STEP = 0.05
    _TIMER_MS = 50
    _SIZE = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)
        self._opacity = self._OPAQUE
        self._growing = True
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._pulse)
        self._recording = False

    def start(self):
        self._recording = True
        self._timer.start(self._TIMER_MS)

    def stop(self):
        self._recording = False
        self._timer.stop()
        self._opacity = self._OPAQUE
        self.update()

    def _pulse(self):
        if self._growing:
            self._opacity -= self._STEP
            if self._opacity <= self._TRANSPARENT:
                self._growing = False
        else:
            self._opacity += self._STEP
            if self._opacity >= self._OPAQUE:
                self._growing = True
        self.update()

    def paintEvent(self, event):
        if not self._recording and self._opacity == self._OPAQUE:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(get_palette().danger)
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self._SIZE, self._SIZE)


class MicrophoneIcon(QWidget):
    """Small microphone mark for the floating window header."""

    _SIZE = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self._SIZE, self._SIZE)

    def paintEvent(self, event):
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(p.accent))
        painter.drawRoundedRect(5, 1, 6, 9, 3, 3)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(p.accent_hover))
        painter.drawArc(3, 5, 10, 7, 180 * 16, 180 * 16)
        painter.drawLine(8, 12, 8, 14)
        painter.drawLine(5, 14, 11, 14)


class AudioLevelWaveform(QWidget):
    """Compact level meter using recent microphone levels."""

    _BAR_COUNT = 18
    _MIN_BAR_HEIGHT = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(22)
        # deque(maxlen=...) gives O(1) bounded append vs. rebuilding an
        # 18-element list every 100ms; iteration/indexing still work.
        self._levels = collections.deque([0.0] * self._BAR_COUNT, maxlen=self._BAR_COUNT)

    def reset(self):
        self._levels = collections.deque([0.0] * self._BAR_COUNT, maxlen=self._BAR_COUNT)
        self.update()

    def add_level(self, level: float):
        level = max(0.0, min(1.0, float(level)))
        # Skip repaint when level is unchanged - avoids unconditional
        # QPainter redraw of all 18 bars on every 100ms tick.
        if level == self._levels[-1]:
            self._levels.append(level)
            return
        self._levels.append(level)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._levels:
            return

        p = get_palette()
        active = QColor(p.success)
        # border_hover is visible in both themes (plain border is too pale on
        # white in light mode); low alpha keeps idle bars subtle.
        idle = QColor(p.border_hover)

        gap = 3
        width = self.width()
        height = self.height()
        bar_w = max(2, (width - gap * (self._BAR_COUNT - 1)) / self._BAR_COUNT)

        for index, level in enumerate(self._levels):
            bar_h = self._MIN_BAR_HEIGHT + level * (height - self._MIN_BAR_HEIGHT)
            x = int(index * (bar_w + gap))
            y = int((height - bar_h) / 2)
            color = QColor(active if level > 0.02 else idle)
            color.setAlphaF(0.35 + min(0.65, level))
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(x, y, int(bar_w), int(bar_h), 2, 2)


class FloatingRecordingWindow(QWidget):
    """Compact floating window for recording control."""

    recording_started = Signal()
    recording_stopped = Signal()
    settings_requested = Signal()
    hide_requested = Signal()

    def __init__(self, always_on_top: bool = True):
        super().__init__()
        self._state = RecorderState.IDLE
        self._hotkey_manager = None
        self._elapsed = QElapsedTimer()
        self._pending_audio_level = 0.0
        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_QuitOnClose, False)
        self.setMinimumSize(260, 156)
        self.resize(260, 156)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        # Top row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.app_icon = MicrophoneIcon(self)
        top_row.addWidget(self.app_icon)
        self.app_name_label = QLabel(t("app.name"))
        top_row.addWidget(self.app_name_label)
        top_row.addStretch()

        # Settings button - vector gear icon. Emoji glyphs (⚙) are
        # font-dependent and render inconsistently across platforms, so we
        # use the themed vector icon from theme.py (no-emoji-icons rule).
        self._settings_btn = QPushButton()
        self._settings_btn.setIcon(gear_icon())
        self._settings_btn.setFixedSize(26, 26)
        self._settings_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._settings_btn.clicked.connect(self.settings_requested.emit)
        top_row.addWidget(self._settings_btn)

        # Quit (hide) button - vector close icon; a red tint on hover
        # signals the dismiss intent without changing the icon glyph.
        self._quit_btn = QPushButton()
        self._quit_btn.setIcon(close_icon())
        self._quit_btn.setFixedSize(26, 26)
        self._quit_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._quit_btn.clicked.connect(self.hide_requested.emit)
        top_row.addWidget(self._quit_btn)

        layout.addLayout(top_row)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.dot = PulsingDot(self)
        self.duration_label = QLabel("00:00")
        self.duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        status_row.addWidget(self.dot)
        status_row.addStretch()
        status_row.addWidget(self.duration_label)
        layout.addLayout(status_row)

        self.waveform = AudioLevelWaveform(self)
        layout.addWidget(self.waveform)

        # Record button
        self.record_btn = QPushButton()
        self.record_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.record_btn.setFixedHeight(40)
        self._update_record_button()
        self.record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_btn)

        # Apply the initial palette-derived stylesheets now that all widgets
        # exist (also used by apply_theme() on a theme switch).
        self.apply_theme()

    def _settings_btn_stylesheet(self, p) -> str:
        return (
            f"QPushButton {{ background: transparent; border: none; border-radius: 6px; }}"
            f"QPushButton:hover {{ background: {p.bg_hover}; }}"
            f"QPushButton:pressed {{ background: {p.border}; }}"
        )

    def _quit_btn_stylesheet(self, p) -> str:
        return (
            f"QPushButton {{ background: transparent; border: none; border-radius: 6px; }}"
            f"QPushButton:hover {{ background: rgba(239, 68, 68, 0.18); }}"
            f"QPushButton:pressed {{ background: rgba(239, 68, 68, 0.30); }}"
        )

    def _update_record_button(self):
        p = get_palette()
        style = _button_style(self._state, p)
        text = t(_BUTTON_TEXT_KEYS.get(self._state, "btn.record"))
        enabled = self._state != RecorderState.PROCESSING

        if style:
            self.record_btn.setStyleSheet(style)
        else:
            self.record_btn.setStyleSheet(
                f"QPushButton {{ background: {p.accent}; color: white; "
                f"border: none; border-radius: 8px; font-size: 14px; font-weight: 600; }}"
                f"QPushButton:hover {{ background: {p.accent_hover}; }}"
                f"QPushButton:pressed {{ background: {p.accent_pressed}; }}"
            )
        self.record_btn.setText(text)
        self.record_btn.setEnabled(enabled)

    def apply_theme(self) -> None:
        """Re-apply the active palette to all inline stylesheets and repaint.

        Called on construction and after a light/dark theme switch. QPainter
        widgets (PulsingDot, waveform, MicrophoneIcon, the window, Toast,
        StatusBubble) read :func:`get_palette` inside paintEvent, so a
        ``self.update()`` repaint picks up the new colors; only the
        stylesheet-driven widgets (labels, header buttons, record button)
        need an explicit re-set here.
        """
        p = get_palette()
        self.app_name_label.setStyleSheet(
            f"color: {p.text_primary}; font-size: 12px; font-weight: 700;"
        )
        self.duration_label.setStyleSheet(
            f"color: {p.text_secondary}; font-size: 12px;"
        )
        self._settings_btn.setStyleSheet(self._settings_btn_stylesheet(p))
        self._settings_btn.setIcon(gear_icon())  # fresh icon for new palette
        self._quit_btn.setStyleSheet(self._quit_btn_stylesheet(p))
        self._quit_btn.setIcon(close_icon())
        self._update_record_button()
        self.update()

    def _set_state(self, new_state: RecorderState) -> None:
        """Centralized state setter - updates the state and refreshes the button."""
        self._state = new_state
        self._update_record_button()

    def _transition_to(self, new_state: RecorderState):
        """Centralized state transition - updates button, indicators, and emits signals."""
        old_state = self._state
        if old_state != new_state:
            logger.debug("State transition: %s -> %s", old_state.name, new_state.name)
        self._set_state(new_state)

        if old_state == RecorderState.RECORDING and new_state == RecorderState.IDLE:
            self.dot.stop()
            self.duration_label.setText("00:00")
            self.waveform.reset()
            self.recording_stopped.emit()
        elif new_state == RecorderState.RECORDING:
            self.dot.start()
            self._elapsed.restart()
            self._pending_audio_level = 0.0
            self.waveform.reset()
            self.duration_label.setText("00:00")
            self.recording_started.emit()
        else:
            # Any other transition (PROCESSING/DONE/ERROR) stops background indicators
            self.dot.stop()
            if new_state in (RecorderState.DONE, RecorderState.ERROR):
                self.duration_label.setText("00:00")
                self.waveform.reset()

    def refresh_recording_indicators(self, level: float):
        """Update duration + waveform from the latest mic level.

        Called by Application's single audio-level sync timer - do not
        call directly from UI code.
        """
        if self._state != RecorderState.RECORDING:
            return
        self._pending_audio_level = max(0.0, min(1.0, float(level)))
        elapsed_seconds = max(0, self._elapsed.elapsed() // 1000)
        minutes = elapsed_seconds // 60
        seconds = elapsed_seconds % 60
        self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")
        self.waveform.add_level(self._pending_audio_level)

    def _toggle_recording(self):
        if self._state == RecorderState.RECORDING:
            self._transition_to(RecorderState.IDLE)
        else:
            self._transition_to(RecorderState.RECORDING)

    def paintEvent(self, event):
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(p.bg_card))
        painter.setPen(QColor(p.border))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def start_recording(self):
        if self._state != RecorderState.RECORDING:
            self._transition_to(RecorderState.RECORDING)

    def stop_recording(self):
        if self._state == RecorderState.RECORDING:
            self._transition_to(RecorderState.IDLE)

    def is_recording(self) -> bool:
        return self._state == RecorderState.RECORDING

    def is_processing(self) -> bool:
        return self._state == RecorderState.PROCESSING

    def set_processing(self):
        self._transition_to(RecorderState.PROCESSING)

    def set_done(self):
        self._transition_to(RecorderState.DONE)

    def set_error(self, msg: str = ""):
        """Transition to ERROR state.

        ``msg`` is reserved for future UI use (e.g. showing the error text
        in a tooltip).  Currently only the state transition is needed.
        """
        _ = msg  # reserved, not yet displayed
        self._transition_to(RecorderState.ERROR)

    def closeEvent(self, event: QCloseEvent):
        self.hide_requested.emit()
        event.ignore()

    def set_hotkey_manager(self, manager):
        self._hotkey_manager = manager

    def retranslate(self):
        """Retranslate all user-facing text after a language change."""
        self.app_name_label.setText(t("app.name"))
        self._update_record_button()

    def set_audio_level(self, level: float):
        """Receive latest microphone level from the recorder (no-op).

        Kept for backwards compatibility; the actual UI updates happen in
        ``refresh_recording_indicators`` which is driven by the Application
        timer and reads the level directly.
        """
        self._pending_audio_level = max(0.0, min(1.0, float(level)))


class StatusBubble(QWidget):
    """A persistent status bubble shown at screen bottom during recording/processing."""

    _FONT_SIZE = 13
    _TARGET_OPACITY = 0.9
    _BOTTOM_MARGIN = 60
    _H_PADDING = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._fade_out = None
        self._font = _default_font(self._FONT_SIZE)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_QuitOnClose, False)

    def show_status(self, text: str):
        """Show or update the bubble with the given text."""
        self._text = text
        self._resize_and_repaint()
        self.setWindowOpacity(self._TARGET_OPACITY)
        self.show()
        self.raise_()

    def _resize_and_repaint(self):
        fm = QFontMetrics(self._font)
        text_w = fm.horizontalAdvance(self._text)
        w = text_w + self._H_PADDING
        h = 40
        self.setFixedSize(w, h)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.center().x() - w // 2
            y = geo.bottom() - h - self._BOTTOM_MARGIN
            self.move(x, y)
        self.update()

    def dismiss(self):
        """Hide the status bubble immediately."""
        if not self.isVisible():
            return
        self.hide()

    def paintEvent(self, event):
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(p.bg_card))
        painter.setPen(QColor(p.border))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        painter.setPen(QColor(p.text_primary))
        painter.setFont(self._font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)


class Toast(QWidget):
    """A brief toast-style notification that appears at screen bottom center and auto-dismisses."""

    _FONT_SIZE = 13
    _FADE_IN_MS = 150
    _FADE_OUT_MS = 200
    _TARGET_OPACITY = 0.9
    _BOTTOM_MARGIN = 60
    _H_PADDING = 48

    def __init__(self, text: str, duration_ms: int = 1500, parent=None):
        super().__init__(parent)
        self._text = text
        self._duration_ms = duration_ms
        self._font = _default_font(self._FONT_SIZE)
        self._fade_in = None  # keep reference to avoid premature GC
        self._fade_out = None
        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_QuitOnClose, False)

        fm = QFontMetrics(self._font)
        text_w = fm.horizontalAdvance(self._text)
        w = text_w + self._H_PADDING
        h = 40
        self.setFixedSize(w, h)

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.center().x() - w // 2
            y = geo.bottom() - h - self._BOTTOM_MARGIN
            self.move(x, y)

        self.setWindowOpacity(0)
        self._fade_in = QPropertyAnimation(self, b"windowOpacity")
        self._fade_in.setDuration(self._FADE_IN_MS)
        self._fade_in.setStartValue(0)
        self._fade_in.setEndValue(self._TARGET_OPACITY)
        self._fade_in.setEasingCurve(QEasingCurve.OutQuad)
        self._fade_in.start()

        QTimer.singleShot(self._duration_ms, self._fade_out_and_close)

    def _fade_out_and_close(self):
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(self._FADE_OUT_MS)
        anim.setStartValue(self._TARGET_OPACITY)
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.InQuad)
        anim.finished.connect(self.close)
        anim.start()
        self._fade_out = anim

    def paintEvent(self, event):
        p = get_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(p.bg_card))
        painter.setPen(QColor(p.border))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        painter.setPen(QColor(p.text_primary))
        painter.setFont(self._font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
