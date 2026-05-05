"""Floating recording window — compact widget with record button."""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QCursor, QCloseEvent
from src.state import RecorderState

logger = logging.getLogger(__name__)

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

_BUTTON_TEXTS = {
    RecorderState.RECORDING: "Recording...",
    RecorderState.PROCESSING: "Processing...",
    RecorderState.IDLE: "Record",
    RecorderState.DONE: "Record",
    RecorderState.ERROR: "Record",
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
        color = QColor(239, 68, 68)
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self._SIZE, self._SIZE)


class FloatingRecordingWindow(QWidget):
    """Compact floating window for recording control."""

    recording_started = Signal()
    recording_stopped = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, always_on_top: bool = True):
        super().__init__()
        self._state = RecorderState.IDLE
        self._hotkey_manager = None
        self._init_ui()
        if always_on_top:
            self.setWindowFlag(Qt.WindowStaysOnTopHint)

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(240, 100)
        self.resize(240, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Top row
        top_row = QHBoxLayout()
        top_row.setSpacing(4)

        self.dot = PulsingDot(self)
        top_row.addWidget(self.dot)
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
        quit_btn.clicked.connect(self.quit_requested.emit)
        top_row.addWidget(quit_btn)

        layout.addLayout(top_row)

        # Record button
        self.record_btn = QPushButton()
        self.record_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.record_btn.setFixedHeight(40)
        self._update_record_button()
        self.record_btn.clicked.connect(self._toggle_recording)
        layout.addWidget(self.record_btn)

    def _update_record_button(self):
        style = _BUTTON_STYLES.get(self._state)
        text = _BUTTON_TEXTS.get(self._state, "Record")
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

    def _transition_to(self, new_state: RecorderState):
        """Centralized state transition — updates button and emits signals."""
        old_state = self._state
        self._state = new_state

        if old_state == RecorderState.RECORDING and new_state == RecorderState.IDLE:
            self.dot.stop()
            self.recording_stopped.emit()
        elif new_state == RecorderState.RECORDING:
            self.dot.start()
            self.recording_started.emit()

        self._update_record_button()

    def _toggle_recording(self):
        if self._state == RecorderState.RECORDING:
            self._transition_to(RecorderState.IDLE)
        else:
            self._transition_to(RecorderState.RECORDING)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(31, 41, 55))
        painter.setPen(QColor(55, 65, 81))
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
        self._state = RecorderState.PROCESSING
        self._update_record_button()

    def set_done(self):
        self._state = RecorderState.DONE
        self._update_record_button()

    def set_error(self, msg: str = "Error"):
        self._state = RecorderState.ERROR
        self._update_record_button()

    def closeEvent(self, event: QCloseEvent):
        self.quit_requested.emit()
        event.accept()

    def set_hotkey_manager(self, manager):
        self._hotkey_manager = manager


class Toast(QWidget):
    """A brief toast-style notification that appears at screen bottom center and auto-dismisses."""

    _FONT_FAMILY = "Microsoft YaHei"
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
        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        fm = QFontMetrics(QFont(self._FONT_FAMILY, self._FONT_SIZE))
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
        color = QColor(31, 41, 55)
        painter.setBrush(color)
        painter.setPen(QColor(75, 85, 99))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)
        painter.setPen(QColor(229, 231, 235))
        painter.setFont(QFont(self._FONT_FAMILY, self._FONT_SIZE))
        painter.drawText(self.rect(), Qt.AlignCenter, self._text)
