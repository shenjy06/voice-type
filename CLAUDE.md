# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice Type is a Windows voice-to-text dictation tool with AI refinement. Workflow: record voice → STT (speech-to-text) → LLM text polishing → auto-paste to cursor position.

**Tech stack**: PySide6 (Qt 6), sounddevice, scipy, OpenAI SDK (compatible APIs), pyperclip, pynput (hotkeys), Windows ctypes (window management).

## Quick Start

```bash
pip install -r requirements.txt
python -m voicetype
```

Or install as a package:

```bash
pip install -e .
voice-type
```

Config file lives at `%USERPROFILE%\.voice-type\config.json`, created automatically on first run.

## Architecture

The app follows a pipeline architecture with a central `Application` orchestrator in `voicetype/__main__.py`:

```
[Hotkey/UI] → [AudioRecorder] → [WAV file] → [Transcriber] → [TextPolisher] → [TextTyper] → Cursor
```

### Core Modules

| Module | Responsibility |
|--------|---------------|
| `voicetype/__main__.py` | `Application` class — wires all components together, manages Qt event loop, background processing thread, hotkey lifecycle |
| `voicetype/api_client.py` | `ApiClient` — wraps OpenAI client creation with common defaults |
| `voicetype/config.py` | Dataclass-based config with JSON persistence (`AppConfig`, `AsrConfig`, `PolishApiConfig`, `RecordingConfig`, `OutputConfig`, `GlossaryEntry`, `WindowConfig`) |
| `voicetype/audio.py` | `AudioRecorder` — sounddevice-based async recording, saves to temp OGG via soundfile |
| `voicetype/asr.py` | `Transcriber` — OpenAI SDK `audio.transcriptions.create()` for STT |
| `voicetype/glossary.py` | `apply_glossary()` — user-defined term replacements applied after STT and before polishing |
| `voicetype/polisher.py` | `TextPolisher` — OpenAI SDK `chat.completions.create()` with system prompt for text refinement, supports context-aware polishing |
| `voicetype/context.py` | `get_cursor_context()` — captures text before/after cursor via Shift+Home/End + Ctrl+C clipboard trick, restores original clipboard |
| `voicetype/typer.py` | `TextTyper` — clipboard copy + ctypes `keybd_event` Ctrl+V to inject text at cursor |
| `voicetype/window_manager.py` | Windows foreground control — `SetForegroundWindow` strategies, thread attachment, Alt tap |
| `voicetype/state.py` | `RecorderState` enum for recording workflow states |
| `voicetype/network.py` | Network connectivity check with multiple probe endpoints |

### UI Modules

| Module | Responsibility |
|--------|---------------|
| `voicetype/ui/main_window.py` | `FloatingRecordingWindow` — frameless, draggable, always-on-top window with pulsing dot animation and state machine. `Toast` — auto-dismissing notification |
| `voicetype/ui/system_tray.py` | `TrayIcon` — system tray with context menu. `HotkeyManager` — pynput keyboard listener for global hotkeys |
| `voicetype/ui/settings_dialog.py` | `SettingsDialog` — tabbed dialog (STT/Polish/Glossary/Output/Hotkeys) with config load/save |
| `voicetype/ui/icon_utils.py` | `make_circle_icon()` — shared circular icon creation with centered text |

### Threading Model

ASR + LLM processing runs in a `QThread` via `ProcessingWorker` to avoid blocking the UI. Audio recording uses a callback-based `sounddevice.InputStream` running on its own thread.

### State Machine

`FloatingRecordingWindow` has states: `idle → recording → processing → done/error → idle`. Hotkeys and UI buttons drive transitions. The `cancel` hotkey skips processing and deletes temp audio.

## Key Details

- **Windows-only**: Window management (`GetForegroundWindow`, `SetForegroundWindow`) uses Windows ctypes APIs. Hotkeys use `pynput` (cross-platform library).
- **Two separate API configs**: STT and Polish can use different providers/keys (e.g., SiliconFlow for STT, OpenAI for Polish)
- **Config migration**: `AppConfig.from_dict()` handles migration from old single hotkey format to toggle/cancel hotkey format
- **Temp audio lifecycle**: OGG file created in `tempfile.mktemp()`, deleted after STT or on cancel
- **Right Alt tap detection**: `HotkeyManager` uses pynput to distinguish Right Alt tap (toggle) from Right Alt+key combo (e.g., Right Alt+C for cancel). Tap = release without any other key pressed while Right Alt was held.
- **Centralized state transitions**: `FloatingRecordingWindow._transition_to()` handles signal emission and button updates in one place.
- **Shared icon creation**: `make_circle_icon()` in `icon_utils.py` eliminates duplicate QPixmap+QPainter code across UI modules.
- **State enum**: `RecorderState` in `state.py` replaces scattered string constants (`STATE_IDLE`, etc.).
- **Context-aware polishing**: When polish is enabled, `get_cursor_context()` captures text before/after the cursor at recording start. The polisher uses this context to add connecting punctuation (commas, periods) to the new text, but only outputs the new portion — the existing text is not modified.

## Building & Packaging

### PyInstaller whitelist build strategy

The project packs only the modules it explicitly needs, pulling in a small set from PyInstaller.utils.hooks.collect_all so unrelated packages in the user's Python environment (torch, pandas, etc.) are not dragged into the bundle.

**Core rule**: declare what you need via a whitelist collect_all, then add a conservative denylist as a safety net.

`python
# VoiceType.spec core logic
from PyInstaller.utils.hooks import collect_all

# 1. Whitelist: only collect the PySide6 modules we use
needed_binaries = []
needed_datas = []
needed_imports = []
for qt_module in ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets']:
    datas, binaries, hiddenimports = collect_all(qt_module)
    needed_binaries.extend(binaries)
    needed_datas.extend(datas)
    needed_imports.extend(hiddenimports)

# 2. Exclude heavy unrelated packages from the global environment
excludes = [
    'torch', 'torchvision', 'torchaudio',
    'pandas', 'pyarrow', 'scipy',
    'sklearn', 'scikit-learn', 'matplotlib',
]

a = Analysis(
    ['voicetype\\__main__.py'],
    pathex=[],
    binaries=needed_binaries,
    datas=needed_datas,
    hiddenimports=needed_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
`

**Result**: bundle size dropped from ~178MB to ~80MB (~55% reduction).

Notes:
- When adding new PySide6 modules, add the module name to the collect_all loop.
- excludes only blocks known heavy global-environment packages; does not affect functionality.
- Build command: pyinstaller VoiceType.spec
- Output: dist/VoiceType.exe
- Output: `dist/VoiceType.exe`
