"""Tests for voice_type.typer — TextTyper."""

import pyperclip
from src.typer import TextTyper, user32
from src.window_manager import (
    _tap_alt,
    _attach_thread_input,
    _detach_thread_input,
    get_foreground_window,
    set_foreground_window,
)
from tests.conftest import make_config


class TestTapAlt:
    def test_tap_alt_sends_two_inputs(self, mocker):
        """_tap_alt() calls SendInput."""
        # Don't mock KeyboardInput — it needs to be a real ctypes Structure for sizeof()
        mock_send = mocker.patch("src.window_manager.user32.SendInput")

        _tap_alt()

        mock_send.assert_called_once()


class TestAttachThreadInput:
    def test_attach_when_same_thread_noop(self, mocker):
        """No AttachThreadInput call when threads are the same."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.GetCurrentThreadId.return_value = 100
        mock_user32.GetWindowThreadProcessId.return_value = 100

        _attach_thread_input(123)

        mock_user32.AttachThreadInput.assert_not_called()

    def test_attach_when_different_thread(self, mocker):
        """AttachThreadInput(True) called when threads differ."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.GetCurrentThreadId.return_value = 100
        mock_user32.GetWindowThreadProcessId.return_value = 200

        _attach_thread_input(123)

        mock_user32.AttachThreadInput.assert_called_once_with(200, 100, True)


class TestDetachThreadInput:
    def test_detach_when_different_thread(self, mocker):
        """AttachThreadInput(False) called to detach."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.GetCurrentThreadId.return_value = 100
        mock_user32.GetWindowThreadProcessId.return_value = 200

        _detach_thread_input(123)

        mock_user32.AttachThreadInput.assert_called_once_with(200, 100, False)

    def test_detach_when_same_thread_noop(self, mocker):
        """No call when threads are the same."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.GetCurrentThreadId.return_value = 100
        mock_user32.GetWindowThreadProcessId.return_value = 100

        _detach_thread_input(123)

        mock_user32.AttachThreadInput.assert_not_called()


class TestGetForegroundWindow:
    def test_returns_hwnd(self, mocker):
        """get_foreground_window() returns user32.GetForegroundWindow()."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.GetForegroundWindow.return_value = 12345

        result = get_foreground_window()

        assert result == 12345
        mock_user32.GetForegroundWindow.assert_called_once()


class TestSetForegroundWindow:
    def test_returns_false_for_zero_hwnd(self):
        """set_foreground_window(0) returns False."""
        assert set_foreground_window(0) is False

    def test_returns_false_for_none_hwnd(self):
        """set_foreground_window(None) returns False."""
        assert set_foreground_window(None) is False

    def test_returns_false_when_window_not_exists(self, mocker):
        """IsWindow False -> returns False."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.IsWindow.return_value = False

        assert set_foreground_window(123) is False

    def test_strategy1_success(self, mocker):
        """Strategy 1 succeeds -> returns True."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.IsWindow.return_value = True
        mock_user32.GetCurrentThreadId.return_value = 100
        mock_user32.GetWindowThreadProcessId.return_value = 200
        mock_user32.SetForegroundWindow.return_value = True
        mocker.patch("src.window_manager.time.sleep")

        assert set_foreground_window(123) is True

    def test_strategy2_fallback_success(self, mocker):
        """Strategy 1 fails, Strategy 2 succeeds -> returns True."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.IsWindow.return_value = True
        mock_user32.SetForegroundWindow.side_effect = [False, True]  # S1 fails, S2 succeeds
        mocker.patch("src.window_manager.time.sleep")

        assert set_foreground_window(123) is True

    def test_strategy3_fallback(self, mocker):
        """All strategies fail -> returns False."""
        mock_user32 = mocker.patch("src.window_manager.user32")
        mock_user32.IsWindow.return_value = True
        mock_user32.SetForegroundWindow.return_value = False
        mock_user32.ShowWindow.return_value = 1
        mocker.patch("src.window_manager.time.sleep")

        result = set_foreground_window(123)
        assert result is False


class TestTextTyperOutputText:
    def test_empty_text_returns_false(self, mocker):
        """Empty string returns False."""
        cfg = make_config()
        typer = TextTyper(cfg)
        mocker.patch("src.typer.time.sleep")

        assert typer.output_text("") is False

    def test_calls_set_foreground_window_with_hwnd(self, mocker):
        """Non-zero saved_hwnd triggers set_foreground_window."""
        cfg = make_config()
        typer = TextTyper(cfg)
        mocker.patch("src.typer.time.sleep")
        mock_sfw = mocker.patch("src.typer.set_foreground_window", return_value=True)
        mocker.patch.object(typer, "_send_paste", return_value=True)
        mocker.patch("pyperclip.paste", return_value="")
        mocker.patch("pyperclip.copy")

        typer.output_text("hello", saved_hwnd=123)

        mock_sfw.assert_called_with(123)

    def test_paste_success_returns_true(self, mocker):
        """Successful paste returns True."""
        cfg = make_config()
        typer = TextTyper(cfg)
        mocker.patch("src.typer.time.sleep")
        mocker.patch("src.typer.set_foreground_window", return_value=True)
        mocker.patch.object(typer, "_send_paste", return_value=True)
        mocker.patch("pyperclip.paste", return_value="original")
        mock_copy = mocker.patch("pyperclip.copy")

        result = typer.output_text("hello", saved_hwnd=0)

        assert result is True
        mock_copy.assert_called_with("hello")

    def test_paste_failure_restores_clipboard(self, mocker):
        """Failed paste restores original clipboard content."""
        cfg = make_config()
        typer = TextTyper(cfg)
        mocker.patch("src.typer.time.sleep")
        mocker.patch("src.typer.set_foreground_window", return_value=True)
        mocker.patch.object(typer, "_send_paste", return_value=False)
        mocker.patch("pyperclip.paste", return_value="original clipboard")
        mock_copy = mocker.patch("pyperclip.copy")

        result = typer.output_text("hello", saved_hwnd=0)

        assert result is False
        mock_copy.assert_any_call("original clipboard")

    def test_clipboard_get_failure_uses_empty(self, mocker):
        """If pyperclip.paste() raises, uses empty string as original."""
        cfg = make_config()
        typer = TextTyper(cfg)
        mocker.patch("src.typer.time.sleep")
        mocker.patch("src.typer.set_foreground_window", return_value=True)
        mocker.patch.object(typer, "_send_paste", return_value=False)
        mocker.patch("pyperclip.paste", side_effect=Exception("clipboard error"))
        mock_copy = mocker.patch("pyperclip.copy")

        typer.output_text("hello", saved_hwnd=0)

        mock_copy.assert_any_call("")

    def test_paste_delay_respected(self, mocker):
        """sleep is called with paste_delay_ms / 1000."""
        mock_sleep = mocker.patch("src.typer.time.sleep")
        mocker.patch("src.typer.set_foreground_window", return_value=True)
        mocker.patch.object(TextTyper, "_send_paste", return_value=True)
        mocker.patch("pyperclip.paste", return_value="")
        mocker.patch("pyperclip.copy")

        cfg = make_config(output={"paste_delay_ms": 500})
        typer = TextTyper(cfg)
        typer.output_text("text")

        mock_sleep.assert_called_with(0.5)


class TestTextTyperSendPaste:
    def test_send_paste_success(self, mocker):
        """_send_paste() returns True on success."""
        mock_user32 = mocker.patch("src.typer.user32")
        mocker.patch("src.typer.time.sleep")

        cfg = make_config()
        typer = TextTyper(cfg)
        assert typer._send_paste() is True

        # Should have called keybd_event 4 times: Ctrl down, V down, V up, Ctrl up
        assert mock_user32.keybd_event.call_count == 4

    def test_send_paste_exception_returns_false(self, mocker):
        """_send_paste() returns False on exception."""
        mock_user32 = mocker.patch("src.typer.user32")
        mock_user32.keybd_event.side_effect = Exception("access denied")

        cfg = make_config()
        typer = TextTyper(cfg)
        assert typer._send_paste() is False
