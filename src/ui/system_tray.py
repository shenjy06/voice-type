"""System tray icon with menu and global hotkeys."""

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from pynput import keyboard

from src.i18n import t
from src.ui.icon_utils import make_circle_icon

logger = logging.getLogger(__name__)


class TrayIcon(QObject):
    """System tray icon with context menu."""

    show_window_requested = Signal()
    history_requested = Signal()
    settings_requested = Signal()
    recording_toggled = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_recording = False
        self._init_icon()
        self._init_menu()

    def _init_icon(self):
        """Create a simple microphone-style tray icon."""
        self._icon = make_circle_icon("T", (37, 99, 235))
        self._tray = QSystemTrayIcon(self._icon)
        self._tray.setToolTip(t("tray.tooltip"))
        self._tray.activated.connect(self._on_activated)

    def _init_menu(self):
        menu = QMenu()

        self.show_action = QAction(t("tray.show_window"), menu)
        self.show_action.triggered.connect(self.show_window_requested.emit)
        menu.addAction(self.show_action)

        menu.addSeparator()

        self.record_action = QAction(t("tray.start_recording"), menu)
        self.record_action.triggered.connect(self.recording_toggled.emit)
        menu.addAction(self.record_action)

        self.settings_action = QAction(t("tray.settings"), menu)
        self.settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(self.settings_action)

        self.history_action = QAction(t("tray.history"), menu)
        self.history_action.triggered.connect(self.history_requested.emit)
        menu.addAction(self.history_action)

        menu.addSeparator()

        self._quit_action = QAction(t("tray.quit"), menu)
        self._quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(self._quit_action)

        self._tray.setContextMenu(menu)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window_requested.emit()

    def show(self):
        self._tray.show()

    def set_recording(self, recording: bool):
        """Update tray menu based on recording state."""
        self._is_recording = recording
        if recording:
            self.record_action.setText(t("tray.stop_recording"))
            self._tray.setIcon(make_circle_icon("S", (220, 38, 38)))
            self._tray.setToolTip(t("tray.tooltip_recording"))
        else:
            self.record_action.setText(t("tray.start_recording"))
            self._tray.setIcon(self._icon)
            self._tray.setToolTip(t("tray.tooltip"))

    def retranslate(self):
        """Retranslate all menu texts after a language change."""
        self.show_action.setText(t("tray.show_window"))
        self.record_action.setText(
            t("tray.stop_recording") if self._is_recording else t("tray.start_recording")
        )
        self.history_action.setText(t("tray.history"))
        self.settings_action.setText(t("tray.settings"))
        self._quit_action.setText(t("tray.quit"))
        self._tray.setToolTip(
            t("tray.tooltip_recording") if self._is_recording else t("tray.tooltip")
        )

    def show_message(self, title: str, message: str, icon=QSystemTrayIcon.Information):
        """Show a system tray notification."""
        self._tray.showMessage(title, message, icon, 3000)

    def hide(self):
        self._tray.hide()


class HotkeyManager(QObject):
    """Global hotkeys using Right Shift as toggle and Right Shift+C as cancel."""

    toggle_recording = Signal()
    cancel_recording = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None
        self._toggle_key_pressed = False
        self._combo_used = False
        self._running = False

    def start(self):
        """Start monitoring global hotkeys."""
        if self._running:
            return
        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()
        logger.info("Right Shift hotkey monitoring started")

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._toggle_key_pressed = False
        self._combo_used = False
        logger.info("Right Shift hotkey monitoring stopped")

    def _on_press(self, key):
        """Handle key press event."""
        if key == keyboard.Key.shift_r:
            self._toggle_key_pressed = True
            self._combo_used = False
            return

        try:
            if (
                self._toggle_key_pressed
                and hasattr(key, "char")
                and key.char
                and key.char.lower() == "c"
            ):
                self._combo_used = True
                logger.info("Right Shift+C cancel triggered")
                self.cancel_recording.emit()
                return
        except AttributeError:
            pass

        if self._toggle_key_pressed:
            self._combo_used = True

    def _on_release(self, key):
        """Handle key release event and detect Right Shift tap vs combo."""
        if key != keyboard.Key.shift_r:
            if self._toggle_key_pressed:
                self._combo_used = True
            return

        if not self._toggle_key_pressed:
            return
        self._toggle_key_pressed = False

        if self._combo_used:
            return

        logger.info("Right Shift toggle triggered")
        self.toggle_recording.emit()
