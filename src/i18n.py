"""Simple dictionary-based internationalization (en/zh)."""

import locale
import logging

logger = logging.getLogger(__name__)

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app.name": "Voice Type",
        "btn.record": "Record",
        "btn.recording": "Recording...",
        "btn.polishing": "Polishing...",
        "settings.title": "Settings",
        "settings.general": "General",
        "settings.ui_language": "UI Language:",
        "settings.ui_language_auto": "Auto (System)",
        "settings.stt_api": "STT API",
        "settings.api_key": "API Key:",
        "settings.base_url": "Base URL:",
        "settings.model": "Model:",
        "settings.language": "Language:",
        "settings.recording_group": "Recording",
        "settings.sample_rate": "Sample Rate:",
        "settings.stt_tab": "STT",
        "settings.polish_api": "Polish API",
        "settings.polish_tab": "Polish",
        "settings.output": "Output",
        "settings.paste_delay": "Paste Delay:",
        "settings.paste_mode": "Paste Mode:",
        "settings.paste_mode_auto": "Auto",
        "settings.paste_mode_ctrl_v": "Ctrl+V",
        "settings.paste_mode_ctrl_shift_v": "Ctrl+Shift+V",
        "settings.paste_mode_clipboard": "Clipboard only",
        "settings.auto_paste": "Auto-paste to cursor position",
        "settings.hotkeys": "Hotkeys",
        "settings.hotkey_toggle": "Enable Right Shift toggle (tap to start/stop recording)",
        "settings.hotkey_hint": "Quickly tap Right Shift to toggle recording.\nHolding Right Shift with another key will not trigger it.",
        "settings.hotkey_cancel": "<b>Right Shift+C</b> — Cancel recording and discard audio.",
        "settings.save": "Save",
        "settings.cancel": "Cancel",
        "settings.network_error": "Network unavailable, settings not saved",
        "settings.api_key_required": "At least one API Key is required",
        "tray.tooltip": "Voice Type",
        "tray.tooltip_recording": "Voice Type — Recording...",
        "tray.show_window": "Show Window",
        "tray.start_recording": "Start Recording",
        "tray.stop_recording": "Stop Recording",
        "tray.history": "History...",
        "tray.settings": "Settings...",
        "tray.quit": "Quit",
        "history.title": "History",
        "history.empty": "No history yet",
        "history.copy": "Copy",
        "history.paste": "Paste",
        "history.clear": "Clear",
        "status.recording": "Recording...",
        "status.polishing": "Polishing...",
        "error.no_audio": "No audio recorded",
        "error.title": "Error",
        "error.no_audio_detail": "No audio was recorded",
        "msg.settings_saved": "Settings saved",
        "msg.error_format": "Error: {msg}",
        "msg.paste_failed_copied": "Auto-paste failed. The polished text remains on the clipboard; you can paste it manually.",
    },
    "zh": {
        "app.name": "语音输入",
        "btn.record": "录制",
        "btn.recording": "录制中...",
        "btn.polishing": "润色中...",
        "settings.title": "设置",
        "settings.general": "通用",
        "settings.ui_language": "界面语言：",
        "settings.ui_language_auto": "自动（跟随系统）",
        "settings.stt_api": "语音识别 API",
        "settings.api_key": "API 密钥：",
        "settings.base_url": "接口地址：",
        "settings.model": "模型：",
        "settings.language": "语言：",
        "settings.recording_group": "录音",
        "settings.sample_rate": "采样率：",
        "settings.stt_tab": "语音识别",
        "settings.polish_api": "润色 API",
        "settings.polish_tab": "润色",
        "settings.output": "输出",
        "settings.paste_delay": "粘贴延迟：",
        "settings.paste_mode": "粘贴模式：",
        "settings.paste_mode_auto": "自动",
        "settings.paste_mode_ctrl_v": "Ctrl+V",
        "settings.paste_mode_ctrl_shift_v": "Ctrl+Shift+V",
        "settings.paste_mode_clipboard": "仅复制到剪贴板",
        "settings.auto_paste": "自动粘贴到光标位置",
        "settings.hotkeys": "快捷键",
        "settings.hotkey_toggle": "启用右 Shift 切换（点击开始/停止录制）",
        "settings.hotkey_hint": "快速点击右 Shift 来切换录制。\n按住右 Shift 加其他键不会触发。",
        "settings.hotkey_cancel": "<b>Right Shift+C</b> — 取消录制并丢弃音频。",
        "settings.save": "保存",
        "settings.cancel": "取消",
        "settings.network_error": "网络不可用，设置未保存",
        "settings.api_key_required": "至少需要一个 API 密钥",
        "tray.tooltip": "语音输入",
        "tray.tooltip_recording": "语音输入 — 录制中...",
        "tray.show_window": "显示窗口",
        "tray.start_recording": "开始录制",
        "tray.stop_recording": "停止录制",
        "tray.history": "历史记录...",
        "tray.settings": "设置...",
        "tray.quit": "退出",
        "history.title": "历史记录",
        "history.empty": "暂无历史记录",
        "history.copy": "复制",
        "history.paste": "粘贴",
        "history.clear": "清空",
        "status.recording": "录制中...",
        "status.polishing": "润色中...",
        "error.no_audio": "未录制到音频",
        "error.title": "错误",
        "error.no_audio_detail": "未录制到音频",
        "msg.settings_saved": "设置已保存",
        "msg.error_format": "错误：{msg}",
        "msg.paste_failed_copied": "自动粘贴失败。润色内容已经保留在剪贴板中，可手动粘贴。",
    },
}

_current_lang: str = "en"


def _detect_system_language() -> str:
    """Detect system locale, return 'zh' or 'en'."""
    try:
        loc = locale.getlocale()[0]
        if loc and "chinese" in loc.lower():
            return "zh"
    except Exception:
        pass
    try:
        import ctypes
        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if (lang_id & 0xFF) == 0x04:
            return "zh"
    except Exception:
        pass
    return "en"


def init_language(lang: str = "auto") -> None:
    """Set the active language. 'auto' defers to system locale detection."""
    global _current_lang
    if lang == "auto":
        lang = _detect_system_language()
    if lang not in _TRANSLATIONS:
        lang = "en"
    _current_lang = lang


def t(key: str) -> str:
    """Translate a key to the current language."""
    return _TRANSLATIONS.get(_current_lang, {}).get(
        key, _TRANSLATIONS["en"].get(key, key)
    )
