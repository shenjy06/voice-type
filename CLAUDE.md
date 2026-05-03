# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice Type is a Windows voice-to-text dictation tool with AI refinement. Workflow: record voice → STT (speech-to-text) → LLM text polishing → auto-paste to cursor position.

**Tech stack**: PySide6 (Qt 6), sounddevice, scipy, OpenAI SDK (compatible APIs), pyperclip, Windows ctypes for hotkeys and window management.

## Quick Start

```bash
pip install -r requirements.txt
python -m voice_type
```

Or install as a package:

```bash
pip install -e .
voice-type
```

Config file lives at `%USERPROFILE%\.voice-type\config.json`, created automatically on first run.

## Architecture

The app follows a pipeline architecture with a central `Application` orchestrator in `voice_type/__main__.py`:

```
[Hotkey/UI] → [AudioRecorder] → [WAV file] → [Transcriber] → [TextPolisher] → [TextTyper] → Cursor
```

### Core Modules

| Module | Responsibility |
|--------|---------------|
| `voice_type/__main__.py` | `Application` class — wires all components together, manages Qt event loop, background processing thread, hotkey lifecycle |
| `voice_type/config.py` | Dataclass-based config with JSON persistence (`AppConfig`, `AsrConfig`, `PolishApiConfig`, `RecordingConfig`, `OutputConfig`, `WindowConfig`) |
| `voice_type/audio.py` | `AudioRecorder` — sounddevice-based async recording, saves to temp WAV via scipy |
| `voice_type/asr.py` | `Transcriber` — OpenAI SDK `audio.transcriptions.create()` for STT |
| `voice_type/polisher.py` | `TextPolisher` — OpenAI SDK `chat.completions.create()` with system prompt for text refinement |
| `voice_type/typer.py` | `TextTyper` — clipboard copy + ctypes `keybd_event` Ctrl+V to inject text at cursor |

### UI Modules

| Module | Responsibility |
|--------|---------------|
| `voice_type/ui/main_window.py` | `FloatingRecordingWindow` — frameless, draggable, always-on-top window with pulsing dot animation and state machine (idle/recording/processing/done/error). `Toast` — auto-dismissing notification |
| `voice_type/ui/system_tray.py` | `TrayIcon` — system tray with context menu. `HotkeyManager` — Windows `RegisterHotKey` API for global hotkeys |
| `voice_type/ui/settings_dialog.py` | `SettingsDialog` — tabbed dialog (STT/Polish/Output/Hotkeys) with config load/save |

### Threading Model

ASR + LLM processing runs in a `QThread` via `ProcessingWorker` to avoid blocking the UI. Audio recording uses a callback-based `sounddevice.InputStream` running on its own thread.

### State Machine

`FloatingRecordingWindow` has states: `idle → recording → processing → done/error → idle`. Hotkeys and UI buttons drive transitions. The `cancel` hotkey skips processing and deletes temp audio.

## Key Details

- **Windows-only**: Global hotkeys (`RegisterHotKey`) and window management (`GetForegroundWindow`, `SetForegroundWindow`) use Windows ctypes APIs
- **Two separate API configs**: STT and Polish can use different providers/keys (e.g., SiliconFlow for STT, OpenAI for Polish)
- **Config migration**: `AppConfig.from_dict()` handles migration from old single hotkey format to start/stop/cancel hotkey format
- **Temp audio lifecycle**: WAV file created in `tempfile.mktemp()`, deleted after STT or on cancel
