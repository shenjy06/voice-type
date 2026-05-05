# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice Type is a Windows voice-to-text dictation tool with AI refinement. Workflow: record voice → STT (speech-to-text) → LLM text polishing → auto-paste to cursor position.

**Tech stack**: PySide6 (Qt 6), sounddevice, scipy, OpenAI SDK (compatible APIs), pyperclip, pynput (hotkeys), Windows ctypes (window management).

## Quick Start

```bash
pip install -r requirements.txt
python -m src
```

Or install as a package:

```bash
pip install -e .
voice-type
```

Config file lives at `%USERPROFILE%\.voice-type\config.json`, created automatically on first run.

## Architecture

The app follows a pipeline architecture with a central `Application` orchestrator in `src/__main__.py`:

```
[Hotkey/UI] → [AudioRecorder] → [WAV file] → [Transcriber] → [TextPolisher] → [TextTyper] → Cursor
```

### Core Modules

| Module | Responsibility |
|--------|---------------|
| `src/__main__.py` | `Application` class — wires all components together, manages Qt event loop, background processing thread, hotkey lifecycle |
| `src/api_client.py` | `ApiClient` — wraps OpenAI client creation with common defaults |
| `src/config.py` | Dataclass-based config with JSON persistence (`AppConfig`, `AsrConfig`, `PolishApiConfig`, `RecordingConfig`, `OutputConfig`, `WindowConfig`) |
| `src/audio.py` | `AudioRecorder` — sounddevice-based async recording, saves to temp OGG via soundfile |
| `src/asr.py` | `Transcriber` — OpenAI SDK `audio.transcriptions.create()` for STT |
| `src/polisher.py` | `TextPolisher` — OpenAI SDK `chat.completions.create()` with system prompt for text refinement |
| `src/typer.py` | `TextTyper` — clipboard copy + ctypes `keybd_event` Ctrl+V to inject text at cursor |
| `src/window_manager.py` | Windows foreground control — `SetForegroundWindow` strategies, thread attachment, Alt tap |
| `src/state.py` | `RecorderState` enum for recording workflow states |
| `src/network.py` | Network connectivity check with multiple probe endpoints |

### UI Modules

| Module | Responsibility |
|--------|---------------|
| `src/ui/main_window.py` | `FloatingRecordingWindow` — frameless, draggable, always-on-top window with pulsing dot animation and state machine. `Toast` — auto-dismissing notification |
| `src/ui/system_tray.py` | `TrayIcon` — system tray with context menu. `HotkeyManager` — pynput keyboard listener for global hotkeys |
| `src/ui/settings_dialog.py` | `SettingsDialog` — tabbed dialog (STT/Polish/Output/Hotkeys) with config load/save |
| `src/ui/icon_utils.py` | `make_circle_icon()` — shared circular icon creation with centered text |

### Threading Model

ASR + LLM processing runs in a `QThread` via `ProcessingWorker` to avoid blocking the UI. Audio recording uses a callback-based `sounddevice.InputStream` running on its own thread.

### State Machine

`FloatingRecordingWindow` has states: `idle → recording → processing → done/error → idle`. Hotkeys and UI buttons drive transitions. The `cancel` hotkey skips processing and deletes temp audio.

## Key Details

- **Windows-only**: Window management (`GetForegroundWindow`, `SetForegroundWindow`) uses Windows ctypes APIs. Hotkeys use `pynput` (cross-platform library).
- **Two separate API configs**: STT and Polish can use different providers/keys (e.g., SiliconFlow for STT, OpenAI for Polish)
- **Config migration**: `AppConfig.from_dict()` handles migration from old single hotkey format to toggle/cancel hotkey format
- **Temp audio lifecycle**: OGG file created in `tempfile.mktemp()`, deleted after STT or on cancel
- **Left Alt tap detection**: `HotkeyManager` uses pynput to distinguish Alt tap (toggle) from Alt+key combo (e.g., Alt+Tab). Tap = release without any other key pressed while Alt was held.
- **Centralized state transitions**: `FloatingRecordingWindow._transition_to()` handles signal emission and button updates in one place.
- **Shared icon creation**: `make_circle_icon()` in `icon_utils.py` eliminates duplicate QPixmap+QPainter code across UI modules.
- **State enum**: `RecorderState` in `state.py` replaces scattered string constants (`STATE_IDLE`, etc.).
