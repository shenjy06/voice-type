"""Tests for voice_type.audio — AudioRecorder."""

import numpy as np
import pytest
from pathlib import Path
from voicetype.audio import AudioRecorder, MicrophoneMonitor, get_default_input_device_name


class TestAudioRecorderDefaults:
    def test_default_sample_rate(self):
        recorder = AudioRecorder()
        assert recorder.sample_rate == 16000

    def test_custom_sample_rate(self):
        recorder = AudioRecorder(sample_rate=44100)
        assert recorder.sample_rate == 44100

    def test_denoise_disabled_by_default(self):
        recorder = AudioRecorder()
        assert recorder.denoise_enabled is False
        assert recorder.denoise_strength == "medium"

    def test_denoise_params_accepted(self):
        recorder = AudioRecorder(denoise_enabled=True, denoise_strength="high")
        assert recorder.denoise_enabled is True
        assert recorder.denoise_strength == "high"

    def test_initially_not_recording(self):
        recorder = AudioRecorder()
        assert recorder.is_recording is False

    def test_initial_audio_path_is_none(self):
        recorder = AudioRecorder()
        assert recorder.audio_path is None


class TestAudioRecorderStartStop:
    def test_start_creates_stream(self, mocker):
        """start() creates and starts an InputStream."""
        mock_stream = mocker.MagicMock()
        mock_sd = mocker.patch("voicetype.audio.sd")
        mock_sd.InputStream.return_value = mock_stream

        recorder = AudioRecorder()
        recorder.start()

        mock_sd.InputStream.assert_called_once()
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["channels"] == 1
        assert call_kwargs["dtype"] == np.float32
        mock_stream.start.assert_called_once()
        assert recorder.is_recording is True

    def test_start_when_already_recording_is_noop(self, mocker):
        """start() while recording does nothing."""
        mock_stream = mocker.MagicMock()
        mocker.patch("voicetype.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))

        recorder = AudioRecorder()
        recorder.start()
        original_stream = recorder._stream
        recorder.start()
        assert recorder._stream is original_stream

    def test_stop_stops_and_closes_stream(self, mocker):
        """stop() stops and closes the stream."""
        mock_stream = mocker.MagicMock()
        mocker.patch("voicetype.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))

        recorder = AudioRecorder()
        recorder.start()
        recorder.stop()

        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert recorder.is_recording is False
        assert recorder._stream is None

    def test_stop_when_not_recording_is_noop(self, mocker):
        """stop() while not recording does nothing."""
        mock_stream = mocker.MagicMock()
        mocker.patch("voicetype.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))

        recorder = AudioRecorder()
        recorder.stop()

        mock_stream.stop.assert_not_called()


class TestAudioRecorderSave:
    def test_save_with_frames_writes_ogg(self, mocker):
        """save() with audio frames writes a WAV file via soundfile."""
        mock_sf = mocker.patch("voicetype.audio.sf")
        mocker.patch("voicetype.audio.tempfile.gettempdir", return_value="/tmp")
        mocker.patch("voicetype.audio.uuid.uuid4", return_value=mocker.MagicMock(hex="abc123"))
        mock_mkdir = mocker.patch("voicetype.audio.Path.mkdir")

        recorder = AudioRecorder()
        recorder._frames = [np.array([0.1, 0.2, 0.3], dtype=np.float32)]
        recorder.save()

        mock_sf.write.assert_called_once()
        args, kwargs = mock_sf.write.call_args
        assert Path(str(args[0])).as_posix() == "/tmp/.voice_type/recording_abc123.wav"
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
        assert args[2] == recorder.sample_rate
        assert kwargs["format"] == "WAV"
        assert kwargs["subtype"] == "PCM_16"

    def test_save_without_frames_raises(self):
        """save() with no frames raises ValueError."""
        recorder = AudioRecorder()
        with pytest.raises(ValueError, match="No audio data"):
            recorder.save()

    def test_save_passes_float32_data(self, mocker):
        """save() passes float32 audio data directly to soundfile."""
        mock_sf = mocker.patch("voicetype.audio.sf")
        mocker.patch("voicetype.audio.tempfile.gettempdir", return_value="/tmp")
        mocker.patch("voicetype.audio.uuid.uuid4", return_value=mocker.MagicMock(hex="abc123"))
        mocker.patch("voicetype.audio.Path.mkdir")

        recorder = AudioRecorder()
        recorder._frames = [np.array([-1.0, 0.0, 1.0], dtype=np.float32)]
        recorder.save()

        data_arg = mock_sf.write.call_args[0][1]
        assert data_arg.dtype == np.float32
        assert data_arg[0] == -1.0
        assert data_arg[1] == 0.0
        assert data_arg[2] == 1.0

    def test_save_returns_path(self, mocker):
        """save() returns the Path to the saved WAV file."""
        mocker.patch("voicetype.audio.sf")
        mocker.patch("voicetype.audio.tempfile.gettempdir", return_value="/tmp")
        mocker.patch("voicetype.audio.uuid.uuid4", return_value=mocker.MagicMock(hex="def456"))
        mocker.patch("voicetype.audio.Path.mkdir")

        recorder = AudioRecorder()
        recorder._frames = [np.array([0.1], dtype=np.float32)]
        result = recorder.save()

        assert isinstance(result, Path)
        assert Path(str(result)).as_posix() == "/tmp/.voice_type/recording_def456.wav"
        assert recorder.audio_path is not None

    def test_save_skips_denoise_when_disabled(self, mocker):
        """Denoise is not called when denoise_enabled is False."""
        mock_sf = mocker.patch("voicetype.audio.sf")
        mocker.patch("voicetype.audio.tempfile.gettempdir", return_value="/tmp")
        mocker.patch("voicetype.audio.uuid.uuid4", return_value=mocker.MagicMock(hex="abc"))
        mocker.patch("voicetype.audio.Path.mkdir")
        mock_denoise = mocker.patch("voicetype.audio.denoise")

        recorder = AudioRecorder(denoise_enabled=False)
        recorder._frames = [np.array([0.1, 0.2], dtype=np.float32)]
        recorder.save()

        mock_denoise.assert_not_called()
        # Original data is written as-is.
        data_arg = mock_sf.write.call_args[0][1]
        np.testing.assert_array_equal(data_arg, np.array([0.1, 0.2], dtype=np.float32))

    def test_save_applies_denoise_when_enabled(self, mocker):
        """Denoise is called and its output is written when enabled."""
        mock_sf = mocker.patch("voicetype.audio.sf")
        mocker.patch("voicetype.audio.tempfile.gettempdir", return_value="/tmp")
        mocker.patch("voicetype.audio.uuid.uuid4", return_value=mocker.MagicMock(hex="abc"))
        mocker.patch("voicetype.audio.Path.mkdir")
        mock_denoise = mocker.patch("voicetype.audio.denoise")

        denoised = np.array([0.9, 0.8, 0.7], dtype=np.float32)
        mock_denoise.return_value = denoised

        recorder = AudioRecorder(denoise_enabled=True, denoise_strength="high")
        recorder._frames = [np.array([0.1, 0.2, 0.3], dtype=np.float32)]
        recorder.save()

        mock_denoise.assert_called_once()
        args, kwargs = mock_denoise.call_args
        # Second positional arg is sample_rate; strength passed as kwarg.
        assert kwargs.get("strength") == "high"
        # Denoised data is what gets written to WAV.
        data_arg = mock_sf.write.call_args[0][1]
        np.testing.assert_array_equal(data_arg, denoised)


class TestAudioRecorderCallback:
    def test_callback_appends_frames(self):
        """_callback() appends a copy of the input data."""
        recorder = AudioRecorder()
        recorder._recording = True
        data = np.array([[0.1]], dtype=np.float32)
        recorder._callback(data, 1, None, None)

        assert len(recorder._frames) == 1
        assert np.array_equal(recorder._frames[0], data)
        assert recorder.input_level > 0.0

    def test_callback_updates_normalized_input_level(self):
        """_callback() stores a clamped microphone level for UI meters."""
        recorder = AudioRecorder()
        recorder._recording = True
        data = np.array([[10.0], [10.0]], dtype=np.float32)
        recorder._callback(data, 2, None, None)

        assert recorder.input_level == 1.0

    def test_callback_when_not_recording_does_not_append(self):
        """_callback() does not append when _recording is False."""
        recorder = AudioRecorder()
        recorder._recording = False
        recorder._input_level = 0.5
        data = np.array([[0.1]], dtype=np.float32)
        recorder._callback(data, 1, None, None)

        assert len(recorder._frames) == 0
        assert recorder.input_level == 0.0


class TestAudioRecorderCleanup:
    def test_cleanup_deletes_temp_file(self, mocker):
        """cleanup() deletes the temp file if it exists."""
        mock_path = mocker.MagicMock()
        mock_path.exists.return_value = True

        recorder = AudioRecorder()
        recorder._temp_file = mock_path
        recorder.cleanup()

        mock_path.unlink.assert_called_once()

    def test_cleanup_noop_when_no_file(self):
        """cleanup() does nothing when _temp_file is None."""
        recorder = AudioRecorder()
        recorder._temp_file = None
        recorder.cleanup()

    def test_cleanup_noop_when_file_missing(self, mocker):
        """cleanup() does nothing when file doesn't exist."""
        mock_path = mocker.MagicMock()
        mock_path.exists.return_value = False

        recorder = AudioRecorder()
        recorder._temp_file = mock_path
        recorder.cleanup()

        mock_path.unlink.assert_not_called()

    def test_cleanup_ignores_os_error(self, mocker):
        """cleanup() silently ignores OSError on delete."""
        mock_path = mocker.MagicMock()
        mock_path.exists.return_value = True
        mock_path.unlink.side_effect = OSError("Permission denied")

        recorder = AudioRecorder()
        recorder._temp_file = mock_path
        recorder.cleanup()


class TestAudioRecorderCancel:
    def test_cancel_stops_and_deletes(self, mocker):
        """cancel() stops recording and deletes the audio file."""
        mock_stream = mocker.MagicMock()
        mocker.patch("voicetype.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))
        mock_path = mocker.MagicMock()
        mock_path.exists.return_value = True

        recorder = AudioRecorder()
        recorder.start()
        recorder._temp_file = mock_path
        recorder.cancel()

        assert recorder.is_recording is False
        mock_path.unlink.assert_called_once()
        assert recorder._temp_file is None

    def test_cancel_without_recording(self, mocker):
        """cancel() when not recording just clears state."""
        recorder = AudioRecorder()
        recorder._temp_file = None
        recorder.cancel()

        assert recorder._temp_file is None


class TestAudioRecorderVAD:
    """Voice Activity Detection — auto-stop on sustained silence."""

    def test_disabled_never_triggers(self):
        """VAD off → _update_vad always returns False."""
        recorder = AudioRecorder()
        recorder.on_silence = lambda: None
        assert recorder._update_vad(0.5) is False
        assert recorder._update_vad(0.0) is False

    def test_no_silence_callback_no_trigger(self):
        """on_silence None → VAD never triggers even when enabled."""
        recorder = AudioRecorder(vad_enabled=True)
        assert recorder._update_vad(0.5) is False
        assert recorder._update_vad(0.0) is False

    def test_silence_before_speech_does_not_trigger(self, mocker):
        """Silence before first speech is ignored — no early stop."""
        mocker.patch("voicetype.audio.time.monotonic", return_value=0.0)
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1000)
        recorder.on_silence = lambda: None
        assert recorder._update_vad(0.0) is False
        assert recorder._vad_speech_detected is False

    def test_speech_then_silence_below_duration_no_trigger(self, mocker):
        """Silence shorter than the threshold does not trigger."""
        t = mocker.patch("voicetype.audio.time.monotonic")
        t.return_value = 0.0
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1500)
        recorder.on_silence = lambda: None
        assert recorder._update_vad(0.5) is False  # speech
        t.return_value = 1.0
        assert recorder._update_vad(0.0) is False  # silence begins
        t.return_value = 2.0  # elapsed = 1000ms < 1500ms
        assert recorder._update_vad(0.0) is False

    def test_speech_then_silence_above_duration_triggers(self, mocker):
        """Silence past the duration triggers exactly once."""
        t = mocker.patch("voicetype.audio.time.monotonic")
        t.return_value = 0.0
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1000)
        recorder.on_silence = lambda: None
        assert recorder._update_vad(0.5) is False  # speech
        t.return_value = 1.0
        assert recorder._update_vad(0.0) is False  # silence begins
        t.return_value = 2.5  # elapsed = 1500ms >= 1000ms
        assert recorder._update_vad(0.0) is True

    def test_trigger_latches_no_repeat(self, mocker):
        """After triggering, subsequent callbacks don't fire again."""
        t = mocker.patch("voicetype.audio.time.monotonic")
        t.return_value = 0.0
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1000)
        recorder.on_silence = lambda: None
        recorder._update_vad(0.5)  # speech
        t.return_value = 1.0
        recorder._update_vad(0.0)  # silence begins
        t.return_value = 2.5
        assert recorder._update_vad(0.0) is True  # trigger
        t.return_value = 5.0
        assert recorder._update_vad(0.0) is False  # latched

    def test_speech_resets_silence_timer_then_triggers(self, mocker):
        """After speech resets the timer, a fresh silence window must elapse."""
        t = mocker.patch("voicetype.audio.time.monotonic")
        t.return_value = 0.0
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1000)
        recorder.on_silence = lambda: None
        recorder._update_vad(0.5)        # speech
        t.return_value = 1.0
        recorder._update_vad(0.0)        # silence begins at 1.0
        t.return_value = 1.2
        recorder._update_vad(0.5)        # speech interrupts — resets
        t.return_value = 1.3
        assert recorder._update_vad(0.0) is False  # new silence begins at 1.3
        t.return_value = 2.0             # 700ms < 1000ms
        assert recorder._update_vad(0.0) is False
        t.return_value = 2.5             # 1200ms >= 1000ms
        assert recorder._update_vad(0.0) is True

    def test_start_resets_vad_state(self, mocker):
        """start() clears speech-detected + trigger latch + silence timer."""
        mock_stream = mocker.MagicMock()
        mocker.patch("voicetype.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))
        t = mocker.patch("voicetype.audio.time.monotonic")
        t.return_value = 0.0
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1000)
        recorder.on_silence = lambda: None
        recorder._update_vad(0.5)  # speech
        t.return_value = 1.0
        recorder._update_vad(0.0)  # silence begins
        t.return_value = 2.5
        recorder._update_vad(0.0)  # trigger
        assert recorder._vad_triggered is True
        recorder.start()
        assert recorder._vad_triggered is False
        assert recorder._vad_speech_detected is False
        assert recorder._vad_silence_start is None

    def test_callback_fires_on_silence_outside_lock(self, mocker):
        """_callback invokes on_silence when VAD triggers."""
        mock_time = mocker.patch("voicetype.audio.time.monotonic")
        mock_time.return_value = 0.0
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1000)
        fired = []
        recorder.on_silence = lambda: fired.append(True)
        recorder._recording = True
        # Speech
        recorder._callback(np.array([[0.5]], dtype=np.float32), 1, None, None)
        # Silence begins
        mock_time.return_value = 1.0
        recorder._callback(np.array([[0.0]], dtype=np.float32), 1, None, None)
        # Silence past duration — triggers callback
        mock_time.return_value = 2.5
        recorder._callback(np.array([[0.0]], dtype=np.float32), 1, None, None)
        assert fired == [True]

    def test_callback_swallows_callback_exception(self, mocker):
        """A raising on_silence must not propagate out of _callback."""
        mock_time = mocker.patch("voicetype.audio.time.monotonic")
        mock_time.return_value = 0.0
        recorder = AudioRecorder(vad_enabled=True, vad_silence_duration_ms=1000)
        recorder.on_silence = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        recorder._recording = True
        recorder._callback(np.array([[0.5]], dtype=np.float32), 1, None, None)
        mock_time.return_value = 1.0
        recorder._callback(np.array([[0.0]], dtype=np.float32), 1, None, None)
        mock_time.return_value = 2.5
        # Must not raise.
        recorder._callback(np.array([[0.0]], dtype=np.float32), 1, None, None)


class TestMicrophoneMonitor:
    def test_start_creates_stream(self, mocker):
        mock_stream = mocker.MagicMock()
        mock_sd = mocker.patch("voicetype.audio.sd")
        mock_sd.InputStream.return_value = mock_stream

        monitor = MicrophoneMonitor(sample_rate=44100)
        assert monitor.start() is True

        mock_sd.InputStream.assert_called_once()
        call_kwargs = mock_sd.InputStream.call_args[1]
        assert call_kwargs["samplerate"] == 44100
        assert call_kwargs["channels"] == 1
        assert call_kwargs["dtype"] == np.float32
        mock_stream.start.assert_called_once()
        assert monitor.is_running is True

    def test_start_failure_sets_error(self, mocker):
        mocker.patch("voicetype.audio.sd.InputStream", side_effect=RuntimeError("denied"))

        monitor = MicrophoneMonitor()

        assert monitor.start() is False
        assert monitor.is_running is False
        assert "denied" in monitor.error

    def test_stop_closes_stream_and_resets_level(self, mocker):
        mock_stream = mocker.MagicMock()
        mocker.patch("voicetype.audio.sd.InputStream", return_value=mock_stream)

        monitor = MicrophoneMonitor()
        monitor.start()
        monitor._input_level = 0.5
        monitor.stop()

        mock_stream.stop.assert_called_once()
        mock_stream.close.assert_called_once()
        assert monitor.is_running is False
        assert monitor.input_level == 0.0

    def test_callback_updates_input_level(self):
        monitor = MicrophoneMonitor()
        data = np.array([[0.1], [0.1]], dtype=np.float32)
        monitor._callback(data, 2, None, None)

        assert monitor.input_level > 0.0

    def test_get_default_input_device_name(self, mocker):
        mocker.patch("voicetype.audio.sd.query_devices", return_value={"name": "Microphone Array"})

        assert get_default_input_device_name() == "Microphone Array"

    def test_get_default_input_device_name_handles_error(self, mocker):
        mocker.patch("voicetype.audio.sd.query_devices", side_effect=RuntimeError("no device"))

        assert get_default_input_device_name() == ""
