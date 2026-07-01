"""Floating recording window — compact widget with record button."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QApplication, QLabel,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve, QElapsedTimer
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QCursor, QCloseEvent
from voicetype.state import RecorderState
from voicetype.i18n import t

# Shared color constants
_COLOR_BG = QColor(31, 41, 55)
_COLOR_BORDER_WINDOW = QColor(55, 65, 81)
_COLOR_BORDER_BUBBLE = QColor(75, 85, 99)
_COLOR_TEXT = QColor(229, 231, 235)
_COLOR_DOT = QColor(239, 68, 68)
_COLOR_WAVE_ACTIVE = QColor(34, 197, 94)
_COLOR_WAVE_IDLE = QColor(75, 85, 99)

# Default font family — fall back to a platform-appropriate list if unavailable
_DEFAULT_FONT_FAMILIES = ("Segoe UI", "Microsoft YaHei", "Helvetica", "Arial")


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


# Button style descriptors keyed by RecorderState
_BUTTON_STYLES = {
    RecorderState.RECORDING: (
        "QPushButton { background: #dc2626; color: white; "
        "border: none; border-radius: 8px; font-size: 14px; font-weight: bold; }"
        "QPushButton:hover { background: #ef4444; }"
        "QPushButton:pressed { background: #b91c1c; }"
    ),
    RecorderState.PROCESSING: (
        "QPushButton { background: #d97706; color: white; "
        "border: none; border-radius: 8px; font-size: 14px; font-weight: bold; }"
        "QPushButton:hover { background: #f59e0b; }"
        "QPushButton:pressed { background: #b45309; }"
    ),
}

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
        color = QColor(_COLOR_DOT)
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(96, 165, 250))
        painter.drawRoundedRect(5, 1, 6, 9, 3, 3)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QColor(147, 197, 253))
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
        self._levels = [0.0] * self._BAR_COUNT

    def reset(self):
        self._levels = [0.0] * self._BAR_COUNT
        self.update()

    def add_level(self, level: float):
        level = max(0.0, min(1.0, float(level)))
        self._levels = self._levels[1:] + [level]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self._levels:
            return

        gap = 3
        width = self.width()
        height = self.height()
        bar_w = max(2, (width - gap * (self._BAR_COUNT - 1)) / self._BAR_COUNT)

        for index, level in enumerate(self._levels):
            bar_h = self._MIN_BAR_HEIGHT + level * (height - self._MIN_BAR_HEIGHT)
            x = int(index * (bar_w + gap))
            y = int((height - bar_h) / 2)
            color = QColor(_COLOR_WAVE_ACTIVE if level > 0.02 else _COLOR_WAVE_IDLE)
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
        self._level_timer = QTimer(self)
        self._level_timer.setInterval(100)
        self._level_timer.timeout.connect(self._refresh_recording_indicators)
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
        self.setMinimumSize(260, 152)
        self.resize(260, 152)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        # Top row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.app_icon = MicrophoneIcon(self)
        top_row.addWidget(self.app_icon)
        self.app_name_label = QLabel(t("app.name"))
        self.app_name_label.setStyleSheet("color: #e5e7eb; font-size: 12px; font-weight: 700;")
        top_row.addWidget(self.app_name_label)
        top_row.addStretch()

        # Settings button
        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(22, 22)
        settings_btn.setCursor(QCursor(Qt.PointingHandCursor))
        settings_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af; "
            "border: none; font-size: 13px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.1); color: #e5e7eb; }"
        )
        settings_btn.clicked.connect(self.settings_requested.emit)
        top_row.addWidget(settings_btn)

        # Quit button
        quit_btn = QPushButton("✕")
        quit_btn.setFixedSize(22, 22)
        quit_btn.setCursor(QCursor(Qt.PointingHandCursor))
        quit_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #9ca3af; "
            "border: none; font-size: 13px; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(239,68,68,0.3); color: #f87171; }"
        )
        quit_btn.clicked.connect(self.hide_requested.emit)
        top_row.addWidget(quit_btn)

        layout.addLayout(top_row)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.dot = PulsingDot(self)
        self.duration_label = QLabel("00:00")
        self.duration_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.duration_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
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

    def _update_record_button(self):
        style = _BUTTON_STYLES.get(self._state)
        text = t(_BUTTON_TEXT_KEYS.get(self._state, "btn.record"))
        enabled = self._state != RecorderState.PROCESSING

        if style:
            self.record_btn.setStyleSheet(style)
        else:
            self.record_btn.setStyleSheet(
                "QPushButton { background: #2563eb; color: white; "
                "border: none; border-radius: 8px; font-size: 14px; font-weight: bold; }"
                "QPushButton:hover { background: #3b82f6; }"
                "QPushButton:pressed { background: #1d4ed8; }"
            )
        self.record_btn.setText(text)
        self.record_btn.setEnabled(enabled)

    def _set_state(self, new_state: RecorderState) -> None:
        """Centralized state setter — updates the state and refreshes the button."""
        self._state = new_state
        self._update_record_button()

    def _transition_to(self, new_state: RecorderState):
        """Centralized state transition — updates button, indicators, and emits signals."""
        old_state = self._state
        self._set_state(new_state)

        if old_state == RecorderState.RECORDING and new_state == RecorderState.IDLE:
            self.dot.stop()
            self._level_timer.stop()
            self.duration_label.setText("00:00")
            self.waveform.reset()
            self.recording_stopped.emit()
        elif new_state == RecorderState.RECORDING:
            self.dot.start()
            self._elapsed.restart()
            self._pending_audio_level = 0.0
            self.waveform.reset()
            self.duration_label.setText("00:00")
            self._level_timer.start()
            self.recording_started.emit()
        else:
            # Any other transition (PROCESSING/DONE/ERROR) stops background indicators
            self.dot.stop()
            self._level_timer.stop()
            if new_state in (RecorderState.DONE, RecorderState.ERROR):
                self.duration_label.setText("00:00")
                self.waveform.reset()

    def _refresh_recording_indicators(self):
        if self._state != RecorderState.RECORDING:
            return
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(_COLOR_BG)
        painter.setPen(_COLOR_BORDER_WINDOW)
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

    def set_processing(self):
        self._transition_to(RecorderState.PROCESSING)

    def set_done(self):
        self._transition_to(RecorderState.DONE)

    def set_error(self, msg: str = "Error"):
        # The error message is optional UI context; state machine is what matters.
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
        """Receive latest microphone level from the recorder."""
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(_COLOR_BG)
        painter.setPen(_COLOR_BORDER_BUBBLE)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        painter.setPen(_COLOR_TEXT)
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(_COLOR_BG)
        painter.setPen(_COLOR_BORDER_BUBBLE)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        painter.setPen(_COLOR_TEXT)
        painter.setFont(self._font)
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
