# Voice Type

[中文](README-zh.md) | English

Windows voice-to-text dictation tool. Record voice → Speech recognition → Text refinement → Auto-paste to cursor position.

Licensed under [GPL-3.0](LICENSE).

## Features

- **Voice Recording**: One-key record/stop/cancel via global hotkeys without stealing focus from the target application
- **Noise Reduction**: Optional spectral-gate denoising removes steady background noise (fans, AC, hum) before recognition — pure numpy, no extra dependencies. Targets stationary noise; transient sounds (keyboard clicks) are not well suppressed.
- **Speech Recognition (STT)**: Transcribe recorded audio to text (OpenAI-compatible protocol)
- **Smart Refinement**: LLM automatically removes filler words, fixes grammar, and improves clarity
- **Glossary Corrections**: Replace frequently misrecognized names, project terms, and technical terms before refinement
- **Text Injection**: Restores the original foreground window and pastes the refined text at the cursor position
- **Local History**: Keeps recent recognized text in local SQLite for copy or re-paste from the tray menu
- **Floating Control Window**: Always-on-top mini window with drag support and pulsing red dot animation
- **Status Bubble**: Shows "录制中..." during recording, "润色中..." during processing, dismisses after paste
- **System Tray**: Click X to minimize to tray; tray menu provides recording toggle, settings, and quit
- **Global Hotkeys**: Uses `pynput` keyboard listener for global hotkey detection — responsive in any application
- **Network Detection**: Automatically checks network availability on settings save to prevent invalid configurations
- **Startup Check**: Automatically detects API configuration on first launch and shows setup wizard if unconfigured
- **Bilingual UI**: Supports Chinese and English interface, switchable in settings (requires restart)
- **Model Discovery**: Click the 🔄 button in settings to fetch all available models from your API provider — no need to copy model IDs manually

## Tech Stack

| Component | Technology |
|-----------|------------|
| GUI | PySide6 (Qt 6) |
| Audio Recording | sounddevice + numpy |
| Audio Encoding | soundfile (OGG/Vorbis) |
| Speech Recognition | OpenAI-compatible protocol (ASR API) |
| Text Refinement | OpenAI-compatible protocol (Chat Completions API) |
| Global Hotkeys | pynput keyboard listener |
| Text Injection | pyperclip (clipboard) + ctypes (window management) |

## Installation

It is recommended to use a virtual environment to keep dependencies isolated from your global Python installation.

### Using venv (recommended)

```bash
# Clone the project
cd voice-type

# Create a virtual environment (requires Python 3.10+)
python -m venv .venv

# Activate the virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (Command Prompt):
.venv\Scripts\activate.bat
# Windows (Git Bash):
source .venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt
```

### Direct install (without venv)

```bash
pip install -r requirements.txt
```

### Dependencies

- `PySide6` — Qt GUI framework
- `sounddevice` — Cross-platform audio recording
- `numpy` — Audio data processing
- `soundfile` — OGG/Vorbis audio file encoding
- `openai` — Client for OpenAI-compatible STT and LLM services
- `pyperclip` — Cross-platform clipboard operations
- `pynput` — Cross-platform keyboard/mouse listener for global hotkeys

> Note: Windows hotkeys and window management use the standard library `ctypes`, no extra dependencies required.

## Running

```bash
python -m voicetype
```

## Packaging as EXE

The project provides a one-click build script — just double-click to package:

```bash
build.bat
```

Or use the command line:

```bash
pyinstaller --clean --noconfirm VoiceType.spec
```

The spec file uses a whitelist build strategy and excludes large optional
packages from the global Python environment.

The generated `dist/VoiceType.exe` is a standalone executable — no Python environment required.

## Settings

Click the gear icon in the upper-right corner of the floating window, or access settings via the system tray menu. The settings dialog has five tabs: STT, Polish, Glossary, Output, and Hotkeys.

### STT (Speech-to-Text) Configuration

| Field | Description | Example |
|-------|-------------|---------|
| API Key | Authentication key for STT service | `sk-...` |
| Base URL | API address of STT service | `https://api.siliconflow.cn/v1` |
| Model | Speech recognition model (click 🔄 to fetch provider's full model list) | `FunAudioLLM/SenseVoiceSmall` |
| Language | Recognition language | `zh` / `en` / `auto` |
| Sample Rate | Recording sample rate | `16000` Hz |
| Noise Reduction | Enable spectral-gate denoising before recognition | `Off` / `On` |
| NR Strength | Denoising aggressiveness (higher suppresses more noise but may affect speech) | `Low` / `Medium` / `High` |

### Polish (Text Refinement) Configuration

| Field | Description | Example |
|-------|-------------|---------|
| API Key | Authentication key for LLM service | `sk-...` |
| Base URL | API address of LLM service | `https://api.siliconflow.cn/v1` |
| Model | Text refinement model (click 🔄 to fetch provider's full model list) | `gpt-4o` / `deepseek-chat` / `qwen-plus` |

### Glossary Configuration

Use the Glossary tab to define term corrections that run immediately after
speech recognition and before optional text refinement. This is useful for
names, project names, acronyms, and technical terms that ASR often
misrecognizes.

| Field | Description | Example |
|-------|-------------|---------|
| Recognized text | Text returned by ASR | `pai sen` / `派森` |
| Replace with | Correct term to output | `Python` |

### Hotkey Configuration

| Hotkey | Default | Description |
|--------|---------|-------------|
| Toggle Recording | `Right Alt` (tap) | Start recording on first tap, stop on second tap |
| Cancel Recording | `Right Alt + C` | Stop recording and discard audio, skip subsequent processing |

The Right Alt hotkey distinguishes between a tap (start/stop toggle) and modifier use (holding it with another key will not trigger recording). Left Alt is ignored so it stays free for normal typing.

### Output Configuration

| Field | Description | Default |
|-------|-------------|---------|
| Paste Delay | Delay before pasting (milliseconds) | `120 ms` |
| Paste Mode | Auto-detect target window, force `Ctrl+V`, force `Ctrl+Shift+V`, or copy only | Auto |
| Auto-paste | Whether to auto-paste to cursor position | Enabled |

If auto-paste fails, the recognized text remains on the clipboard so it can be pasted manually.

## API Key Configuration

Voice Type uses OpenAI-compatible APIs and supports multiple providers. Below are common configuration examples:

### SiliconFlow

Register: https://cloud.siliconflow.cn/i/BLu934tI

```json
{
  "asr": {
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "sk-...",
    "model": "FunAudioLLM/SenseVoiceSmall",
    "language": "zh"
  },
  "polish": {
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "sk-...",
    "model": "deepseek-ai/DeepSeek-V3"
  },
  "glossary": [
    {"source": "派森", "replacement": "Python"}
  ]
}
```

### OpenAI

Register: https://platform.openai.com

```json
{
  "asr": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "whisper-1",
    "language": "zh"
  },
  "polish": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "gpt-4o"
  },
  "glossary": [
    {"source": "派森", "replacement": "Python"}
  ]
}
```

### Custom OpenAI-Compatible Providers

Any API that supports the OpenAI-compatible protocol can be used (DashScope, Volcano Engine, locally deployed Ollama/vLLM, etc.). Simply fill in the corresponding Base URL and API Key in the settings, and ensure the model name is correct.

## Usage

1. Launch the app — the setup wizard appears automatically on first run if no API key is configured
2. Configure your API Key and models in Settings
3. Place your cursor at the desired input position
4. Press `Right Alt` (tap once) to start recording (status bubble shows "录制中...")
5. When finished speaking, press `Right Alt` (tap again) to stop recording
6. Wait for processing — status bubble shows "润色中...", then refined text automatically appears at the cursor position
7. To discard the current recording, press `Right Alt + C` to cancel (audio will be discarded)
8. Click window X button to minimize to tray; use tray menu "Quit" to fully exit

## Project Structure

```
voice-type/
├── src/
│   └── voicetype/
│       ├── __main__.py              # Entry point: Application orchestrator
│       ├── api_client.py            # Base OpenAI-compatible API client wrapper
│       ├── config.py                # Config management: dataclass + JSON persistence
│       ├── history.py               # SQLite local recognized text history storage
│       ├── audio.py                 # Audio recording: sounddevice + soundfile OGG encoding
│       ├── denoise.py               # Spectral-gate noise reduction (numpy-only)
│       ├── asr.py                   # Speech recognition: OpenAI-compatible transcriptions API
│       ├── glossary.py              # User glossary term replacement after ASR
│       ├── polisher.py              # Text refinement: LLM chat completions API
│       ├── typer.py                 # Text output: clipboard + Ctrl+V paste
│       ├── window_manager.py        # Windows foreground control: ctypes window/keyboard APIs
│       ├── network.py               # Network detection: HTTP connectivity check
│       ├── state.py                 # Application state enum (RecorderState)
│       ├── i18n.py                  # Internationalization: Chinese/English translations
│       └── ui/
│           ├── history_dialog.py    # Recent text history viewer/copy/re-paste dialog
│           ├── main_window.py       # Floating recording window + pulsing dot + StatusBubble + Toast
│           ├── settings_dialog.py   # Settings dialog (STT/Polish/Glossary/Output/Hotkeys)
│           ├── system_tray.py       # System tray icon + pynput hotkey manager
│           └── icon_utils.py        # Shared icon creation (circle + centered text)
├── tests/                       # Unit tests (375, covering all modules)
│   ├── conftest.py
│   ├── test_audio.py
│   ├── test_asr.py
│   ├── test_config.py
│   ├── test_denoise.py
│   ├── test_main.py
│   ├── test_network.py
│   ├── test_glossary.py
│   ├── test_i18n.py
│   ├── test_polisher.py
│   ├── test_typer.py
│   └── ui/
│       ├── test_main_window.py
│       ├── test_settings_dialog.py
│       └── test_system_tray.py
├── build.bat                    # One-click build script
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Running Tests

```bash
# Install with test dependencies (run in the activated venv)
pip install -e ".[dev]"
pytest tests/ -v
```

## Configuration File

User configuration, including glossary entries, is stored at `%USERPROFILE%\.voice-type\config.json`. Local history is stored at `%USERPROFILE%\.voice-type\history.sqlite3`. On first launch, if no configuration is detected, the settings dialog will automatically appear to guide the user through setup.

## Notes

- Speech recognition requires an internet connection and a valid API key
- Global hotkeys are only available on Windows
- Settings save automatically checks network connectivity and will not save if the network is unavailable
- Keep the floating window visible during recording; avoid using in security-sensitive applications (e.g., password managers)
- Text injection relies on the clipboard — do not copy other content during the paste operation
