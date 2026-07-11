"""Streaming real-time ASR via DashScope — OpenAI Realtime API protocol.

Protocol (DashScope Realtime API, compatible with OpenAI Realtime API):
    1. Open ``wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model=<model>``
       with ``Authorization: Bearer <api_key>`` and ``OpenAI-Beta: realtime=v1``.
    2. Send ``session.update`` to configure audio format and server VAD.
    3. Send ``input_audio_buffer.append`` events with **base64-encoded** PCM.
    4. Server VAD detects silence and commits the audio buffer automatically.
    5. Receive ``response.audio_transcript.done`` for live transcript text.
    6. Receive ``response.done`` when processing is complete.
    7. Close the connection.

Threading:
    * ``send_audio`` is invoked on the sounddevice audio callback thread —
      it must NOT block on network I/O, so chunks are enqueued and a sender
      thread drains the queue, base64-encodes, and sends JSON text frames.
    * The WebSocket recv loop runs on its own thread; ``on_text_update`` is
      invoked from that thread (callers marshal to the UI thread via a Qt
      signal — see ``Application._StreamingTextBridge``).
    * ``finalize`` blocks the caller (the processing worker thread) until
      ``response.done`` arrives or the timeout elapses.
"""

import base64
import json
import logging
import queue
import threading
import uuid
from typing import Callable

import websocket

logger = logging.getLogger(__name__)

class StreamingTranscriber:
    """Streams PCM audio to DashScope realtime ASR (OpenAI Realtime API protocol).

    Uses server VAD (``turn_detection``) so the server automatically commits
    the audio buffer after detecting silence. ``finalize()`` stops sending
    audio and waits for ``response.done``.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        language: str = "auto",
        sample_rate: int = 16000,
        on_text_update: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._language = language
        self._sample_rate = sample_rate
        self._on_text_update = on_text_update
        self._on_error = on_error
        self._ws: websocket.WebSocket | None = None
        self._recv_thread: threading.Thread | None = None
        self._sender_thread: threading.Thread | None = None
        # Unbounded queue — audio chunks are small (~3KB per 0.1s);
        # a large backlog indicates network trouble, but we never want to
        # block the sounddevice callback thread.
        self._send_queue: queue.Queue[bytes | None] = queue.Queue()
        self._final_text = ""
        self._finished = threading.Event()
        self._session_ready = threading.Event()
        self._started = False

    def start(self) -> bool:
        """Open the WebSocket and send ``session.update``.

        Blocks briefly (up to 10s) waiting for ``session.updated``
        confirmation before returning. Returns True on success.
        """
        if self._started:
            return True
        if not self._api_key:
            self._report_error("No API key configured for streaming ASR")
            return False
        self._started = True

        url = f"{self._base_url}?model={self._model}"
        headers = [
            f"Authorization: Bearer {self._api_key}",
            "OpenAI-Beta: realtime=v1",
        ]
        try:
            self._ws = websocket.create_connection(url, header=headers, timeout=10)
            # Short recv timeout so the recv loop can react to _finished /
            # shutdown promptly instead of blocking until the next message.
            self._ws.settimeout(1.0)
        except Exception as e:
            self._report_error(f"Failed to connect to DashScope: {e}")
            return False

        # Send session.update to configure audio format + server VAD.
        try:
            self._ws.send(json.dumps(self._session_update_msg()))
        except Exception as e:
            self._report_error(f"Failed to send session.update: {e}")
            self._close_ws()
            return False

        # Start background threads.
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        self._sender_thread = threading.Thread(target=self._send_loop, daemon=True)
        self._sender_thread.start()

        # Wait for session.updated before returning (session is ready).
        if not self._session_ready.wait(timeout=10.0):
            self._report_error("Timeout waiting for session.updated")
            self._close_ws()
            return False

        logger.info(
            "Streaming ASR started (model=%s, sample_rate=%d)",
            self._model, self._sample_rate,
        )
        return True

    def send_audio(self, pcm: bytes) -> None:
        """Enqueue a PCM chunk for sending. Non-blocking.

        Called from the sounddevice audio callback thread. ``pcm`` must be
        16-bit signed little-endian mono PCM at the configured sample rate.
        The sender thread base64-encodes it and sends an
        ``input_audio_buffer.append`` JSON event.
        """
        if not self._started:
            return
        self._send_queue.put(pcm)

    def finalize(self, timeout: float = 10.0) -> str:
        """Stop sending audio and wait for the final transcript.

        With server VAD enabled, the server automatically commits the audio
        buffer after detecting silence and sends back a
        ``conversation.item.created`` event carrying the transcript — no
        explicit commit needed. We stop sending, wait for that event (or
        ``response.done``), and return the accumulated transcript. If the
        server doesn't respond within ``timeout``, we return whatever text
        was collected (may be empty).
        """
        # Stop the sender loop after it drains remaining audio chunks.
        self._send_queue.put(None)
        if not self._finished.wait(timeout=timeout):
            logger.warning(
                "Streaming ASR finalize timed out after %.1fs — returning partial text: %r",
                timeout, self._final_text,
            )
        self._close_ws()
        return self._final_text

    # ---- background threads -------------------------------------------------

    def _recv_loop(self) -> None:
        """Receive loop — parses JSON events until the socket closes."""
        while True:
            if self._finished.is_set():
                break
            ws = self._ws
            if ws is None:
                # _close_ws() set _ws to None on another thread; the
                # socket is gone — exit cleanly without spamming errors.
                break
            try:
                message = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e:
                if not self._finished.is_set():
                    self._report_error(f"Streaming ASR recv error: {e}")
                    self._finished.set()
                break
            if not message:
                if not self._finished.is_set():
                    self._finished.set()
                break
            self._handle_message(message)

    def _send_loop(self) -> None:
        """Drain the audio queue, base64-encode, and send JSON events.

        Terminates when ``None`` is enqueued (by ``finalize``).
        """
        while True:
            chunk = self._send_queue.get()
            if chunk is None:
                return
            ws = self._ws
            if ws is None:
                # Socket already closed (_close_ws ran in another thread);
                # drop the chunk (it arrived after the connection died).
                continue
            encoded = base64.b64encode(chunk).decode("utf-8")
            event = {
                "event_id": f"audio_{uuid.uuid4().hex[:12]}",
                "type": "input_audio_buffer.append",
                "audio": encoded,
            }
            try:
                ws.send(json.dumps(event))
            except Exception as e:
                logger.warning("Failed to send audio chunk: %s", e)

    # ---- message handling ---------------------------------------------------

    def _handle_message(self, message: str) -> None:
        """Parse a server event and update internal state."""
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return
        event_type = data.get("type", "")
        # Log every event type at debug level so protocol mismatches can be
        # diagnosed from the log when the provider's response format differs
        # from what we expect.
        logger.debug("Streaming ASR event: %s", event_type)

        if event_type == "session.updated":
            self._session_ready.set()

        elif event_type == "conversation.item.input_audio_transcription.text":
            # DashScope-specific: live transcript for the input audio. The
            # actual text is in the "stash" field (full text so far, updated
            # in place — NOT a delta); "text" is empty at this stage.
            text = (
                data.get("stash")
                or data.get("text")
                or data.get("delta")
                or ""
            )
            if text:
                # stash is the full current transcript — overwrite, not append.
                self._final_text = text
                logger.debug("Streaming ASR live text: %r", text)
                if self._on_text_update:
                    self._on_text_update(self._final_text)

        elif event_type == "conversation.item.input_audio_transcription.completed":
            # DashScope-specific: transcription for this item is complete.
            # The final text may be in "text" or "stash".
            text = (
                data.get("text")
                or data.get("stash")
                or data.get("transcript")
                or ""
            )
            if text:
                self._final_text = text
                logger.debug("Streaming ASR transcript completed: %r", text)
                if self._on_text_update:
                    self._on_text_update(self._final_text)
            else:
                # Keep whatever stash we already have — the completed event
                # may not carry the text itself.
                logger.debug("Streaming ASR .completed — no text field, keeping stash: %r",
                             self._final_text)
            self._finished.set()

        elif event_type == "conversation.item.created":
            # Fallback: some providers put the transcript directly in the
            # created item's content. Handle it in case the dedicated
            # transcription events above are not sent.
            item = data.get("item", {}) or {}
            for content in item.get("content", []) or []:
                transcript = content.get("transcript", "")
                if transcript:
                    if self._final_text:
                        self._final_text += " "
                    self._final_text += transcript
                    if self._on_text_update:
                        self._on_text_update(self._final_text)
                    self._finished.set()

        elif event_type == "response.audio_transcript.done":
            # Output audio transcript (assistant voice). Field is "transcript",
            # not "text", per the OpenAI Realtime API spec.
            transcript = data.get("transcript", "")
            if transcript:
                self._final_text = transcript
                if self._on_text_update:
                    self._on_text_update(transcript)
            self._finished.set()

        elif event_type == "response.done":
            self._finished.set()

        elif event_type == "error":
            err = data.get("error", {}).get("message", str(data))
            self._report_error(f"DashScope error: {err}")

    # ---- protocol messages ---------------------------------------------------

    def _session_update_msg(self) -> dict[str, object]:
        """Build the ``session.update`` event for DashScope realtime ASR.

        Uses server VAD so the server automatically commits the audio buffer
        after detecting silence (``silence_duration_ms: 800``). The transcript
        is delivered via ``response.audio_transcript.done``.
        """
        session = {
            "event_id": f"session_{uuid.uuid4().hex[:12]}",
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_format": "pcm",
                "sample_rate": self._sample_rate,
                "input_audio_transcription": {},
                "turn_detection": {
                    "type": "server_vad",
                    "threshold": 0.2,
                    "silence_duration_ms": 800,
                },
            },
        }
        # Set the recognition language when the user has selected one
        # explicitly (not "auto").
        if self._language and self._language != "auto":
            session["session"]["input_audio_transcription"]["language"] = self._language
        return session

    # ---- cleanup -----------------------------------------------------------

    def _close_ws(self) -> None:
        # Signal the sender thread to exit so it doesn't block on get() forever.
        # This is critical when start() fails (the sender thread is already
        # running but finalize() will never be called to enqueue the None
        # sentinel). Non-blocking put_nowait is safe here: the queue is
        # unbounded and the send loop is designed to consume sentinel values.
        try:
            self._send_queue.put_nowait(None)
        except queue.Full:
            pass
        ws = self._ws
        self._ws = None
        if ws is None:
            return
        try:
            ws.close()
        except Exception:
            pass

    def _report_error(self, msg: str) -> None:
        logger.error("Streaming ASR: %s", msg)
        if self._on_error:
            try:
                self._on_error(msg)
            except Exception:
                pass
