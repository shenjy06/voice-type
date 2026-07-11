"""Tests for StreamingTranscriber — DashScope Realtime API (OpenAI protocol)."""

import base64
import json

from voicetype.streaming_asr import StreamingTranscriber


class TestStreamingTranscriber:
    def test_start_without_api_key_reports_error(self):
        """start() returns False and reports an error when no API key is set."""
        errors = []
        transcriber = StreamingTranscriber(
            api_key="",
            model="qwen3-asr-flash-realtime-2026-02-10",
            on_error=errors.append,
        )
        assert transcriber.start() is False
        assert errors and "No API key" in errors[0]

    def test_start_connects_and_sends_session_update(self, mocker):
        """start() opens the WebSocket and sends a session.update JSON frame."""
        mock_ws = mocker.MagicMock()
        mocker.patch(
            "voicetype.streaming_asr.websocket.create_connection",
            return_value=mock_ws,
        )
        transcriber = StreamingTranscriber(
            api_key="sk-test",
            model="qwen3-asr-flash-realtime-2026-02-10",
            language="zh",
            sample_rate=16000,
        )
        try:
            # Simulate session.updated so start() doesn't time out.
            transcriber._session_ready.set()
            assert transcriber.start() is True

            # The first send() call is session.update.
            assert mock_ws.send.called
            sent = json.loads(mock_ws.send.call_args[0][0])
            assert sent["type"] == "session.update"
            session = sent["session"]
            assert session["modalities"] == ["text"]
            assert session["input_audio_format"] == "pcm"
            assert session["sample_rate"] == 16000
            assert session["input_audio_transcription"]["language"] == "zh"
            assert session["turn_detection"]["type"] == "server_vad"
            assert session["turn_detection"]["silence_duration_ms"] == 800
            mock_ws.settimeout.assert_called_once_with(1.0)
        finally:
            transcriber._finished.set()
            transcriber._send_queue.put(None)
            transcriber._close_ws()

    def test_start_sends_no_language_when_auto(self, mocker):
        """auto language omits the language field in session.update."""
        mock_ws = mocker.MagicMock()
        mocker.patch(
            "voicetype.streaming_asr.websocket.create_connection",
            return_value=mock_ws,
        )
        transcriber = StreamingTranscriber(
            api_key="sk-test", model="m", language="auto",
        )
        try:
            transcriber._session_ready.set()
            transcriber.start()
            sent = json.loads(mock_ws.send.call_args[0][0])
            iat = sent["session"]["input_audio_transcription"]
            assert "language" not in iat or not iat.get("language")
        finally:
            transcriber._finished.set()
            transcriber._send_queue.put(None)
            transcriber._close_ws()

    def test_start_connection_failure_reports_error(self, mocker):
        """A connection failure reports an error and returns False."""
        mocker.patch(
            "voicetype.streaming_asr.websocket.create_connection",
            side_effect=OSError("refused"),
        )
        errors = []
        transcriber = StreamingTranscriber(
            api_key="sk-test",
            model="m",
            on_error=errors.append,
        )
        assert transcriber.start() is False
        assert errors and "refused" in errors[0]

    def test_send_audio_before_start_is_noop(self):
        """send_audio() before start() is a silent no-op."""
        transcriber = StreamingTranscriber(api_key="sk-test", model="m")
        transcriber.send_audio(b"\x00\x01")  # must not raise

    def test_handle_session_updated_sets_ready(self):
        """session.updated sets the _session_ready latch."""
        transcriber = StreamingTranscriber(api_key="sk", model="m")
        assert transcriber._session_ready.is_set() is False
        transcriber._handle_message(json.dumps({"type": "session.updated"}))
        assert transcriber._session_ready.is_set() is True

    def test_handle_audio_transcript_done_updates_text(self):
        """response.audio_transcript.done updates the live text callback."""
        texts = []
        transcriber = StreamingTranscriber(
            api_key="sk", model="m", on_text_update=texts.append,
        )
        transcriber._handle_message(json.dumps({
            "type": "response.audio_transcript.done",
            "transcript": "hello world",
        }))
        assert texts == ["hello world"]
        assert transcriber._final_text == "hello world"

    def test_handle_conversation_item_created_updates_text(self):
        """conversation.item.created carries the input audio transcript."""
        texts = []
        transcriber = StreamingTranscriber(
            api_key="sk", model="m", on_text_update=texts.append,
        )
        transcriber._handle_message(json.dumps({
            "type": "conversation.item.created",
            "item": {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_audio", "transcript": "recognized text"}
                ],
            },
        }))
        assert transcriber._final_text == "recognized text"
        assert transcriber._finished.is_set()

    def test_handle_transcription_text_overwrites_with_stash(self):
        """conversation.item.input_audio_transcription.text carries the full
        current transcript in 'stash' — overwrite, not accumulate."""
        texts = []
        transcriber = StreamingTranscriber(
            api_key="sk", model="m", on_text_update=texts.append,
        )
        transcriber._handle_message(json.dumps({
            "type": "conversation.item.input_audio_transcription.text",
            "text": "",
            "stash": "hello",
        }))
        transcriber._handle_message(json.dumps({
            "type": "conversation.item.input_audio_transcription.text",
            "text": "",
            "stash": "hello world",
        }))
        assert transcriber._final_text == "hello world"
        assert texts == ["hello", "hello world"]

    def test_handle_transcription_completed_sets_finished(self):
        """conversation.item.input_audio_transcription.completed finishes."""
        texts = []
        transcriber = StreamingTranscriber(
            api_key="sk", model="m", on_text_update=texts.append,
        )
        transcriber._handle_message(json.dumps({
            "type": "conversation.item.input_audio_transcription.completed",
            "text": "final transcript",
        }))
        assert transcriber._final_text == "final transcript"
        assert transcriber._finished.is_set()

    def test_handle_response_done_sets_finished(self):
        """response.done sets the _finished latch."""
        transcriber = StreamingTranscriber(api_key="sk", model="m")
        transcriber._handle_message(json.dumps({"type": "response.done"}))
        assert transcriber._finished.is_set()

    def test_handle_error_reports_error(self):
        """error event reports an error."""
        errors = []
        transcriber = StreamingTranscriber(
            api_key="sk", model="m", on_error=errors.append,
        )
        transcriber._handle_message(json.dumps({
            "type": "error",
            "error": {"message": "bad model"},
        }))
        assert errors and "bad model" in errors[0]

    def test_handle_malformed_json_ignored(self):
        """Malformed JSON messages are silently ignored."""
        transcriber = StreamingTranscriber(api_key="sk", model="m")
        transcriber._handle_message("not json")  # must not raise

    def test_finalize_returns_transcript(self, mocker):
        """finalize() waits for response.done and returns the transcript."""
        mock_ws = mocker.MagicMock()
        mocker.patch(
            "voicetype.streaming_asr.websocket.create_connection",
            return_value=mock_ws,
        )
        transcriber = StreamingTranscriber(api_key="sk-test", model="m")
        transcriber._session_ready.set()
        assert transcriber.start() is True
        transcriber._final_text = "final text"
        transcriber._finished.set()
        result = transcriber.finalize(timeout=1.0)
        assert result == "final text"
        mock_ws.close.assert_called_once()

    def test_sender_base64_encodes_audio(self, mocker):
        """The sender loop base64-encodes raw PCM before sending."""
        mock_ws = mocker.MagicMock()
        mocker.patch(
            "voicetype.streaming_asr.websocket.create_connection",
            return_value=mock_ws,
        )
        transcriber = StreamingTranscriber(api_key="sk", model="m")
        transcriber._session_ready.set()
        transcriber.start()
        transcriber.send_audio(b"\x00\x01\xff\xfe")
        transcriber._send_queue.put(None)  # stop the sender
        transcriber._sender_thread.join(timeout=2.0)
        # Find the audio event among all send() calls.
        sent_events = []
        for call in mock_ws.send.call_args_list:
            try:
                sent_events.append(json.loads(call.args[0]))
            except (json.JSONDecodeError, IndexError):
                pass
        audio_events = [e for e in sent_events if e.get("type") == "input_audio_buffer.append"]
        assert len(audio_events) >= 1
        expected = base64.b64encode(b"\x00\x01\xff\xfe").decode("utf-8")
        assert audio_events[0]["audio"] == expected
