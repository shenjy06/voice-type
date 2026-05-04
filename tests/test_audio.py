"""Tests for voice_type.audio — AudioRecorder."""

import numpy as np
import pytest
from pathlib import Path
from voice_type.audio import AudioRecorder


class TestAudioRecorderDefaults:
    def test_default_sample_rate(self):
        recorder = AudioRecorder()
        assert recorder.sample_rate == 16000

    def test_custom_sample_rate(self):
        recorder = AudioRecorder(sample_rate=44100)
        assert recorder.sample_rate == 44100

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
        mock_sd = mocker.patch("voice_type.audio.sd")
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
        mocker.patch("voice_type.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))

        recorder = AudioRecorder()
        recorder.start()
        original_stream = recorder._stream
        recorder.start()
        assert recorder._stream is original_stream

    def test_stop_stops_and_closes_stream(self, mocker):
        """stop() stops and closes the stream."""
        mock_stream = mocker.MagicMock()
        mocker.patch("voice_type.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))

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
        mocker.patch("voice_type.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))

        recorder = AudioRecorder()
        recorder.stop()

        mock_stream.stop.assert_not_called()


class TestAudioRecorderSave:
    def test_save_with_frames_writes_ogg(self, mocker):
        """save() with audio frames writes an OGG file via soundfile."""
        mock_sf = mocker.patch("voice_type.audio.sf")
        mocker.patch("voice_type.audio.tempfile", mktemp=mocker.MagicMock(return_value="/tmp/voice_test.ogg"))

        recorder = AudioRecorder()
        recorder._frames = [np.array([0.1, 0.2, 0.3], dtype=np.float32)]
        recorder.save()

        mock_sf.write.assert_called_once()
        args, kwargs = mock_sf.write.call_args
        assert Path(str(args[0])).as_posix() == "/tmp/voice_test.ogg"
        assert args[2] == recorder.sample_rate
        assert kwargs["format"] == "OGG"
        assert kwargs["subtype"] == "VORBIS"

    def test_save_without_frames_raises(self):
        """save() with no frames raises ValueError."""
        recorder = AudioRecorder()
        with pytest.raises(ValueError, match="No audio data"):
            recorder.save()

    def test_save_passes_float32_data(self, mocker):
        """save() passes float32 audio data directly to soundfile."""
        mock_sf = mocker.patch("voice_type.audio.sf")
        mocker.patch("voice_type.audio.tempfile", mktemp=mocker.MagicMock(return_value="/tmp/t.ogg"))

        recorder = AudioRecorder()
        recorder._frames = [np.array([-1.0, 0.0, 1.0], dtype=np.float32)]
        recorder.save()

        data_arg = mock_sf.write.call_args[0][1]
        assert data_arg.dtype == np.float32
        assert data_arg[0] == -1.0
        assert data_arg[1] == 0.0
        assert data_arg[2] == 1.0

    def test_save_returns_path(self, mocker):
        """save() returns the Path to the saved OGG file."""
        mocker.patch("voice_type.audio.sf")
        mocker.patch("voice_type.audio.tempfile", mktemp=mocker.MagicMock(return_value="/tmp/test.ogg"))

        recorder = AudioRecorder()
        recorder._frames = [np.array([0.1], dtype=np.float32)]
        result = recorder.save()

        assert isinstance(result, Path)
        assert Path(str(result)).as_posix() == "/tmp/test.ogg"
        assert recorder.audio_path is not None


class TestAudioRecorderCallback:
    def test_callback_appends_frames(self):
        """_callback() appends a copy of the input data."""
        recorder = AudioRecorder()
        recorder._recording = True
        data = np.array([[0.1]], dtype=np.float32)
        recorder._callback(data, 1, None, None)

        assert len(recorder._frames) == 1
        assert np.array_equal(recorder._frames[0], data)

    def test_callback_when_not_recording_does_not_append(self):
        """_callback() does not append when _recording is False."""
        recorder = AudioRecorder()
        recorder._recording = False
        data = np.array([[0.1]], dtype=np.float32)
        recorder._callback(data, 1, None, None)

        assert len(recorder._frames) == 0


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
        mocker.patch("voice_type.audio.sd", InputStream=mocker.MagicMock(return_value=mock_stream))
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
