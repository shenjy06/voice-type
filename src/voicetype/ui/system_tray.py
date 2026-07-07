"""System tray icon with menu and global hotkeys."""

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from pynput import keyboard

from voicetype.constants import PASTE_MODES, ASR_LANGUAGES, POLISH_STYLES
from voicetype.hotkey_parser import HotkeyBinding
from voicetype.i18n import t
from voicetype.ui.icon_utils import make_circle_icon

logger = logging.getLogger(__name__)


class TrayIcon(QObject):
    """System tray icon with context menu."""

    show_window_requested = Signal()
    history_requested = Signal()
    settings_requested = Signal()
    recording_toggled = Signal()
    retry_requested = Signal()
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

        self._retry_action = QAction(t("tray.retry"), menu)
        # Enabled only when a previous processing cycle failed and its audio
        # file has been retained for retry.
        self._retry_action.setEnabled(False)
        self._retry_action.triggered.connect(self.retry_requested.emit)
        menu.addAction(self._retry_action)

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

    def set_retry_available(self, available: bool):
        """Enable/disable the 'Retry last' menu item."""
        self._retry_action.setEnabled(available)

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
        self._retry_action.setText(t("tray.retry"))
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
    """Global hotkeys for toggling and cancelling recording.

    The toggle shortcut is configurable via :class:`HotkeyBinding`:

    * ``right_alt`` — a quick tap of Right Alt toggles recording start/stop.
      Holding Right Alt with another key (e.g. Right Alt+C) is treated as a
      combo and does NOT toggle. Right Alt+C cancels an in-progress recording.
      Left Alt is ignored entirely so it stays free for normal typing.
    * ``key`` (e.g. F9) — pressing the bound key toggles recording. Releasing
      it does nothing, so holding the key does not repeat.

    Some keyboards/Windows layouts report the physical Right-Alt key as
    ``Key.alt_gr`` rather than ``Key.alt_r``. Both are accepted as the
    toggle key so the shortcut works regardless of how pynput labels it.
    """

    toggle_recording = Signal()
    cancel_recording = Signal()

    _RIGHT_ALT_TOGGLE_KEYS = ("alt_r", "alt_gr")

    def __init__(self, parent=None, binding: HotkeyBinding | None = None):
        super().__init__(parent)
        self._binding = binding or HotkeyBinding.right_alt()
        self._listener = None
        self._toggle_key_pressed = False
        self._combo_used = False
        self._running = False
        self._last_toggle_key = None
        self._single_key_pressed = False

    @property
    def binding(self) -> HotkeyBinding:
        return self._binding

    def set_binding(self, binding: HotkeyBinding):
        """Change the binding while the manager is stopped."""
        if self._running:
            raise RuntimeError("Cannot change binding while listener is running")
        self._binding = binding

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
        logger.info("Hotkey listener started (binding=%s)", self._binding)

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._listener:
            # pynput Listener.stop() signals the background thread to exit
            # but does NOT wait for it. Join the thread so the Win32 hook
            # is fully cleaned up before we continue — without this, the
            # daemon thread may still be unwinding when the process exits,
            # causing a non-deterministic access violation.
            self._listener.stop()
            try:
                self._listener.join(timeout=1.0)
            except RuntimeError:
                # join() raises RuntimeError if called from the listener's
                # own thread (e.g. hotkey triggers quit from within the
                # callback). In that case the thread will exit naturally
                # when the callback returns; skip the join.
                pass
            self._listener = None
        logger.info("Hotkey listener stopped")
        self._toggle_key_pressed = False
        self._combo_used = False
        self._last_toggle_key = None
        self._single_key_pressed = False

    def _on_press(self, key):
        """Handle key press event."""
        if self._binding.kind == "key":
            if key == self._binding.key and not self._single_key_pressed:
                self._single_key_pressed = True
                self.toggle_recording.emit()
            return

        self._on_press_right_alt(key)

    def _on_release(self, key):
        """Handle key release event."""
        if self._binding.kind == "key":
            if key == self._binding.key:
                self._single_key_pressed = False
            return

        self._on_release_right_alt(key)

    def _on_press_right_alt(self, key):
        """Handle Right-Alt-style press event."""
        is_alt_r = key == keyboard.Key.alt_r
        is_alt_gr = key == keyboard.Key.alt_gr
        is_alt = key == keyboard.Key.alt
        if is_alt_r or is_alt_gr or is_alt:
            # Only Right Alt (alt_r / alt_gr) starts a toggle. A bare generic
            # Key.alt press is treated as left-alt and ignored so
            # left-alt keeps working as a normal modifier. Clear any stale
            # toggle state so a later left-alt release does not toggle.
            if (is_alt_r or is_alt_gr) and not self._toggle_key_pressed:
                self._toggle_key_pressed = True
                self._combo_used = False
                self._last_toggle_key = "alt_r" if is_alt_r else "alt_gr"
            elif is_alt:
                self._last_toggle_key = None
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

    def _on_release_right_alt(self, key):
        """Handle Right-Alt-style release event and detect tap vs combo."""
        is_alt_r = key == keyboard.Key.alt_r
        is_alt_gr = key == keyboard.Key.alt_gr
        is_alt = key == keyboard.Key.alt

        # On Windows pynput often delivers the Right-Alt release as
        # generic Key.alt rather than Key.alt_r. Accept any alt release
        # when the matching press was one of the Right-Alt variants
        # (otherwise true left-alt presses would also toggle).
        matching_toggle = (
            (is_alt_r or is_alt_gr or is_alt)
            and self._last_toggle_key in self._RIGHT_ALT_TOGGLE_KEYS
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
