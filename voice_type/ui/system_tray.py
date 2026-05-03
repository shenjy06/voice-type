"""System tray icon with menu and global hotkey."""

import logging
import ctypes
from ctypes import wintypes
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtCore import Qt, Signal, QObject
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction

logger = logging.getLogger(__name__)

# Windows API constants
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

MOD_MAP = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "super": MOD_WIN,
    "win": MOD_WIN,
}

# Virtual key codes
VK_MAP = {
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59,
    "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
    "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "f11": 0x7A, "f12": 0x7B,
}

user32 = ctypes.windll.user32


class TrayIcon(QObject):
    """System tray icon with context menu."""

    show_window_requested = Signal()
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
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(37, 99, 235))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.setPen(QColor(255, 255, 255))
        from PySide6.QtGui import QFont
        font = QFont("Arial", 16, QFont.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "T")
        painter.end()
        self._icon = QIcon(pixmap)
        self._tray = QSystemTrayIcon(self._icon)
        self._tray.setToolTip("Voice Type")
        self._tray.activated.connect(self._on_activated)

    def _init_menu(self):
        menu = QMenu()

        self.show_action = QAction("Show Window", menu)
        self.show_action.triggered.connect(self.show_window_requested.emit)
        menu.addAction(self.show_action)

        menu.addSeparator()

        self.record_action = QAction("Start Recording", menu)
        self.record_action.triggered.connect(self.recording_toggled.emit)
        menu.addAction(self.record_action)

        self.settings_action = QAction("Settings...", menu)
        self.settings_action.triggered.connect(self.settings_requested.emit)
        menu.addAction(self.settings_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

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
            self.record_action.setText("Stop Recording")
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(220, 38, 38))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 28, 28)
            painter.setPen(QColor(255, 255, 255))
            from PySide6.QtGui import QFont
            font = QFont("Arial", 16, QFont.Bold)
            painter.setFont(font)
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "■")
            painter.end()
            self._tray.setIcon(QIcon(pixmap))
            self._tray.setToolTip("Voice Type — Recording...")
        else:
            self.record_action.setText("Start Recording")
            self._tray.setIcon(self._icon)
            self._tray.setToolTip("Voice Type")

    def show_message(self, title: str, message: str, icon=QSystemTrayIcon.Information):
        """Show a system tray notification."""
        self._tray.showMessage(title, message, icon, 3000)

    def hide(self):
        self._tray.hide()


class HotkeyManager(QObject):
    """Global hotkey using Windows RegisterHotKey API."""

    start_recording = Signal()
    stop_recording = Signal()
    cancel_recording = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hotkey_id = 0  # counter for unique hotkey IDs
        self._registered: list[tuple] = []  # (id, modifiers, vk)

    def register(self, modifiers: list[str], key: str, callback: str):
        """Register a hotkey. callback is 'start', 'stop', or 'cancel'."""
        self._hotkey_id += 1
        mod_value = 0
        for m in modifiers:
            m = m.lower()
            if m in MOD_MAP and m != "none":
                mod_value |= MOD_MAP[m]
        vk = VK_MAP.get(key.lower(), 0)
        if vk == 0:
            logger.warning("Unknown hotkey key: %s", key)
            return
        self._registered.append((self._hotkey_id, mod_value, vk, callback))

    def start(self):
        """Register all hotkeys with Windows."""
        # Get HWND from parent widget
        if self.parent() and hasattr(self.parent(), "winId"):
            hwnd = int(self.parent().winId())
        else:
            logger.error("HotkeyManager needs a QWidget parent to register hotkeys")
            return

        for hid, mods, vk, cb in self._registered:
            result = user32.RegisterHotKey(hwnd, hid, mods, vk)
            if result:
                logger.info("Hotkey registered: id=%d, mods=%d, vk=%d -> %s", hid, mods, vk, cb)
            else:
                logger.error("Failed to register hotkey id=%d, mods=%d, vk=%d", hid, mods, vk)

    def stop(self):
        """Unregister all hotkeys."""
        if self.parent() and hasattr(self.parent(), "winId"):
            hwnd = int(self.parent().winId())
            for hid, _, _, cb in self._registered:
                user32.UnregisterHotKey(hwnd, hid)
                logger.info("Hotkey unregistered: id=%d -> %s", hid, cb)
        self._registered.clear()
        self._hotkey_id = 0

    def update(self):
        """Re-register hotkeys (after config change)."""
        self.stop()
        # Re-registration is handled by the caller who re-creates the manager
        # or re-registers. For now, just log.
        logger.info("Hotkey update called (need to re-register from config)")

    def handle_hotkey(self, hotkey_id: int):
        """Called when a WM_HOTKEY is received."""
        for hid, _, _, cb in self._registered:
            if hid == hotkey_id:
                if cb == "start":
                    self.start_recording.emit()
                elif cb == "stop":
                    self.stop_recording.emit()
                elif cb == "cancel":
                    self.cancel_recording.emit()
                break
