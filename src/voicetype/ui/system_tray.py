"""System tray icon with menu and global hotkeys."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from pynput import keyboard

from voicetype.constants import PASTE_MODES, ASR_LANGUAGES, POLISH_STYLES
from voicetype.i18n import t
from voicetype.ui.icon_utils import make_circle_icon


class TrayIcon(QObject):
    """System tray icon with context menu."""

    show_window_requested = Signal()
    history_requested = Signal()
    settings_requested = Signal()
    recording_toggled = Signal()
    auto_paste_toggled = Signal(bool)
    polish_toggled = Signal(bool)
    polish_style_changed = Signal(str)
    paste_mode_changed = Signal(str)
    asr_language_changed = Signal(str)
    quit_requested = Signal()

    # Backward-compatible aliases — prefer importing from voicetype.constants directly
    PASTE_MODES = PASTE_MODES
    ASR_LANGUAGES = ASR_LANGUAGES
    POLISH_STYLES = POLISH_STYLES

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_recording = False
        self._init_icon()
        self._init_menu()

    def _init_icon(self):
        """Create a simple microphone-style tray icon."""
        self._icon = make_circle_icon("T", (37, 99, 235))
        # Pre-build the recording icon once and reuse it instead of
        # reallocating/painting a QPixmap every recording start.
        self._recording_icon = make_circle_icon("S", (220, 38, 38))
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

        menu.addSeparator()

        self.auto_paste_action = QAction(t("tray.auto_paste"), menu)
        self.auto_paste_action.setCheckable(True)
        self.auto_paste_action.toggled.connect(self.auto_paste_toggled.emit)
        menu.addAction(self.auto_paste_action)

        self.polish_action = QAction(t("tray.polish"), menu)
        self.polish_action.setCheckable(True)
        self.polish_action.toggled.connect(self.polish_toggled.emit)
        menu.addAction(self.polish_action)

        self.polish_style_menu = QMenu(t("tray.polish_style"), menu)
        self.polish_style_actions = {}
        for label_key, value in self.POLISH_STYLES:
            action = QAction(t(label_key), self.polish_style_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, s=value: self.polish_style_changed.emit(s))
            self.polish_style_menu.addAction(action)
            self.polish_style_actions[value] = action
        menu.addMenu(self.polish_style_menu)

        self.paste_mode_menu = QMenu(t("tray.paste_mode"), menu)
        self.paste_mode_actions = {}
        for label_key, value in self.PASTE_MODES:
            action = QAction(t(label_key), self.paste_mode_menu)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, mode=value: self.paste_mode_changed.emit(mode))
            self.paste_mode_menu.addAction(action)
            self.paste_mode_actions[value] = action
        menu.addMenu(self.paste_mode_menu)

        self.asr_language_menu = QMenu(t("tray.asr_language"), menu)
        self.asr_language_actions = {}
        for code in self.ASR_LANGUAGES:
            label = t("settings.lang_auto") if code == "auto" else code
            action = QAction(label, self.asr_language_menu)
            action.setCheckable(True)
            action.triggered.connect(
                lambda checked=False, lang=code: self.asr_language_changed.emit(lang)
            )
            self.asr_language_menu.addAction(action)
            self.asr_language_actions[code] = action
        menu.addMenu(self.asr_language_menu)

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

    def apply_config(self, config):
        """Reflect current runtime config in quick toggle actions."""
        self._set_action_checked(self.auto_paste_action, config.output.auto_paste)
        self._set_action_checked(self.polish_action, config.polish.enabled)
        self._check_action_group(self.paste_mode_actions, config.output.paste_mode, "auto")
        self._check_action_group(self.polish_style_actions, config.polish.style, "default")
        self._check_action_group(self.asr_language_actions, config.asr.language, "auto")

    def _set_action_checked(self, action: QAction, checked: bool):
        old = action.blockSignals(True)
        action.setChecked(checked)
        action.blockSignals(old)

    def _check_action_group(self, actions: dict[str, QAction], selected: str, fallback: str):
        if selected not in actions:
            selected = fallback
        for value, action in actions.items():
            self._set_action_checked(action, value == selected)

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
            self._tray.setIcon(self._recording_icon)
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
        self.auto_paste_action.setText(t("tray.auto_paste"))
        self.polish_action.setText(t("tray.polish"))
        self.polish_style_menu.setTitle(t("tray.polish_style"))
        for label_key, value in self.POLISH_STYLES:
            self.polish_style_actions[value].setText(t(label_key))
        self.paste_mode_menu.setTitle(t("tray.paste_mode"))
        for label_key, value in self.PASTE_MODES:
            self.paste_mode_actions[value].setText(t(label_key))
        self.asr_language_menu.setTitle(t("tray.asr_language"))
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
    """Global hotkeys using Right Shift as toggle and Right Shift+C as cancel.

    A quick tap of Right Shift toggles recording start/stop. Holding Right
    Shift together with any other key (e.g. Right Shift+C) is treated as a
    combo and does NOT toggle — Right Shift+C cancels an in-progress recording
    instead. Left Shift is ignored entirely so it stays free for normal typing.
    """

    toggle_recording = Signal()
    cancel_recording = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._listener = None
        self._toggle_key_pressed = False
        self._combo_used = False
        self._running = False
        self._last_toggle_key = None

    def start(self):
        """Start monitoring global hotkeys."""
        if self._running:
            return
        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
            daemon=True,  # Allow process to exit even if listener is running
        )
        self._listener.start()

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._toggle_key_pressed = False
        self._combo_used = False
        self._last_toggle_key = None

    def _on_press(self, key):
        """Handle key press event."""
        is_shift_r = key == keyboard.Key.shift_r
        is_shift = key == keyboard.Key.shift
        if is_shift_r or is_shift:
            # Only Right Shift (shift_r) starts a toggle. A bare generic
            # Key.shift press is treated as left-shift and ignored so
            # left-shift keeps working as a normal modifier.
            if is_shift_r and not self._toggle_key_pressed:
                self._toggle_key_pressed = True
                self._combo_used = False
                self._last_toggle_key = "shift_r"
            return

        try:
            if (
                self._toggle_key_pressed
                and hasattr(key, "char")
                and key.char
                and key.char.lower() == "c"
            ):
                self._combo_used = True
                self.cancel_recording.emit()
                return
        except AttributeError:
            pass

        if self._toggle_key_pressed:
            self._combo_used = True

    def _on_release(self, key):
        """Handle key release event and detect Right Shift tap vs combo."""
        is_shift_r = key == keyboard.Key.shift_r
        is_shift = key == keyboard.Key.shift

        # On Windows pynput often delivers the Right-Shift release as
        # generic Key.shift rather than Key.shift_r. Only accept the
        # generic shift on release when the matching press was shift_r
        # (otherwise true left-shift presses would also toggle).
        matching_toggle = (
            (is_shift_r and self._last_toggle_key == "shift_r")
            or (is_shift and self._last_toggle_key == "shift_r")
        )

        if matching_toggle:
            if not self._toggle_key_pressed:
                return
            self._toggle_key_pressed = False
            self._last_toggle_key = None

            if self._combo_used:
                return

            self.toggle_recording.emit()
            return

        if self._toggle_key_pressed:
            self._combo_used = True
