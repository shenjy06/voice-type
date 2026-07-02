"""Widget for capturing a single global hotkey via pynput."""

import threading

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from pynput import keyboard

from voicetype.hotkey_parser import key_to_string, HotkeyBinding


class HotkeyRecorder(QWidget):
    """Read-only display of the current hotkey plus a button to record a new one.

    When recording, a temporary pynput listener captures the next physical key
    press. ``right_alt`` is returned for Right Alt / AltGr so the application
    keeps the special tap-vs-combo behavior. Pressing Escape or clicking Cancel
    aborts recording and restores the previous value.
    """

    hotkey_captured = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None
        self._current_hotkey = "right_alt"
        self._recording = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self._display)

        self._button = QPushButton()
        self._button.clicked.connect(self._on_button_clicked)
        layout.addWidget(self._button)

        # When a key is captured on the listener thread, marshal the UI update
        # back to the Qt UI thread via a queued connection.
        self.hotkey_captured.connect(self._apply_captured_hotkey, Qt.QueuedConnection)

        self._update_ui()

    def set_hotkey(self, hotkey: str):
        """Set the displayed hotkey without emitting the capture signal."""
        self._current_hotkey = hotkey or "right_alt"
        self._update_ui()

    def hotkey(self) -> str:
        """Return the currently displayed hotkey string."""
        return self._current_hotkey

    def is_recording(self) -> bool:
        return self._recording

    def stop_recording(self):
        """Stop the temporary listener if it is running."""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        self._recording = False
        self._update_ui()

    def _on_button_clicked(self):
        if self._recording:
            self.stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self._recording = True
        self._update_ui()
        self._listener = keyboard.Listener(on_press=self._on_capture_press)
        self._listener.start()

    def _on_capture_press(self, key):
        """Handle a key press while recording. Called on the listener thread."""
        if key == keyboard.Key.esc:
            self.hotkey_captured.emit(self._current_hotkey)
        else:
            self.hotkey_captured.emit(key_to_string(key))
        return False

    def _apply_captured_hotkey(self, hotkey: str):
        """Apply a captured hotkey on the Qt UI thread."""
        self.set_hotkey(hotkey)
        self.stop_recording()

    def _update_ui(self):
        if self._recording:
            self._display.setText("Press a key...")
            self._button.setText("Cancel")
        else:
            self._display.setText(_display_name(self._current_hotkey))
            self._button.setText("Change")


def _display_name(hotkey: str) -> str:
    """Return a human-readable label for a hotkey string."""
    normalized = (hotkey or "").strip().lower()
    if normalized == "right_alt":
        return "Right Alt"

    binding = HotkeyBinding.from_string(hotkey)
    if binding.kind == "right_alt":
        return "Right Alt"

    key = binding.key
    if key is None:
        return "Right Alt"

    if isinstance(key, keyboard.Key):
        return key.name.replace("_", " ").title()

    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return key.char.upper() if len(key.char) == 1 else key.char
        if key.vk is not None:
            return f"Key {key.vk}"

    return "Right Alt"
