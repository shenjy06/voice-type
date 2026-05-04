# Voice Type

Windows voice-to-text dictation tool. Record voice → Speech recognition → Text refinement → Auto-paste to cursor position.

## Features

- **Voice Recording**: One-key record/stop/cancel via global hotkeys without stealing focus from the target application
- **Speech Recognition (STT)**: Transcribe recorded audio to text (OpenAI-compatible protocol)
- **Smart Refinement**: LLM automatically removes filler words, fixes grammar, and improves clarity
- **Text Injection**: Restores the original foreground window and pastes the refined text at the cursor position
- **Floating Control Window**: Always-on-top mini window with drag support and pulsing red dot animation
- **System Tray**: Tray icon provides recording toggle, settings, and quit functions
- **Global Hotkeys**: Uses native Windows `RegisterHotKey` API, responsive in any application
- **Network Detection**: Automatically checks network availability on settings save to prevent invalid configurations
- **Startup Check**: Automatically detects API configuration on first launch and shows setup wizard if unconfigured

## Tech Stack

| Component | Technology |
|-----------|------------|
| GUI | PySide6 (Qt 6) |
| Audio Recording | sounddevice + numpy |
| Audio Encoding | soundfile (OGG/Vorbis) |
| Speech Recognition | OpenAI-compatible protocol (ASR API) |
| Text Refinement | OpenAI-compatible protocol (Chat Completions API) |
| Global Hotkeys | Windows RegisterHotKey (ctypes) |
| Text Injection | pyperclip (clipboard) + ctypes (window management) |

## Installation

```bash
# Clone the project
cd voice-type

# Install dependencies
pip install -r requirements.txt
```

### Dependencies

- `PySide6` — Qt GUI framework
- `sounddevice` — Cross-platform audio recording
- `numpy` — Audio data processing
- `soundfile` — OGG/Vorbis audio file encoding
- `openai` — Client for OpenAI-compatible STT and LLM services
- `pyperclip` — Cross-platform clipboard operations

> Note: Windows hotkeys and window management use the standard library `ctypes`, no extra dependencies required.

## Running

```bash
python -m voice_type
```

## Packaging as EXE

The project provides a one-click build script — just double-click to package:

```bash
build.bat
```

Or use the command line:

```bash
pyinstaller --clean --name="VoiceType" --windowed --noconfirm --onefile \
    --collect-all PySide6 \
    voice_type/__main__.py
```

The generated `dist/VoiceType.exe` is a standalone executable — no Python environment required.

## Settings

Click the gear icon in the upper-right corner of the floating window, or access settings via the system tray menu. The settings dialog has four tabs: STT, Polish, Output, and Hotkeys.

### STT (Speech-to-Text) Configuration

| Field | Description | Example |
|-------|-------------|---------|
| API Key | Authentication key for STT service | `sk-...` |
| Base URL | API address of STT service | `https://api.siliconflow.cn/v1` |
| Model | Speech recognition model | `FunAudioLLM/SenseVoiceSmall` |
| Language | Recognition language | `zh` / `en` / `auto` |
| Sample Rate | Recording sample rate | `16000` Hz |

### Polish (Text Refinement) Configuration

| Field | Description | Example |
|-------|-------------|---------|
| API Key | Authentication key for LLM service | `sk-...` |
| Base URL | API address of LLM service | `https://api.siliconflow.cn/v1` |
| Model | Text refinement model | `gpt-4o` / `deepseek-chat` / `qwen-plus` |

### Hotkey Configuration

You can separately configure the hotkeys for start recording, stop recording, and cancel recording in the settings:

| Hotkey | Default | Description |
|--------|---------|-------------|
| Start Recording | `Alt + S` | Start voice recording |
| Stop Recording | `Alt + E` | Stop recording and enter transcription/refinement pipeline |
| Cancel Recording | `Alt + C` | Stop recording and discard audio, skip subsequent processing |

Supports `alt`, `ctrl`, `shift`, `super`, `none` modifiers, with up to two modifier key combinations.

### Output Configuration

| Field | Description | Default |
|-------|-------------|---------|
| Paste Delay | Delay before pasting (milliseconds) | `300 ms` |
| Auto-paste | Whether to auto-paste to cursor position | Enabled |

## API Key Configuration

Voice Type uses OpenAI-compatible APIs and supports multiple providers. Below are common configuration examples:

### SiliconFlow

Register: https://cloud.siliconflow.cn

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
  }
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
  }
}
```

### Custom OpenAI-Compatible Providers

Any API that supports the OpenAI-compatible protocol can be used (DashScope, Volcano Engine, locally deployed Ollama/vLLM, etc.). Simply fill in the corresponding Base URL and API Key in the settings, and ensure the model name is correct.

## Usage

1. Launch the app — the setup wizard appears automatically on first run if no API key is configured
2. Configure your API Key and models in Settings
3. Place your cursor at the desired input position
4. Press `Alt + S` to start recording (the pulsing red dot lights up)
5. When finished speaking, press `Alt + E` to stop recording
6. Wait for processing — the refined text will automatically appear at the cursor position
7. To discard the current recording, press `Alt + C` to cancel (audio will be discarded)

## Project Structure

```
voice-type/
├── voice_type/
│   ├── __main__.py              # Entry point: Application class, wires all components
│   ├── config.py                # Config management: dataclass + JSON serialization/persistence
│   ├── audio.py                 # Audio recording: sounddevice async recording + soundfile OGG encoding
│   ├── asr.py                   # Speech recognition: OpenAI-compatible API
│   ├── polisher.py              # Text refinement: LLM API + system prompt
│   ├── typer.py                 # Text injection: window management + clipboard
│   ├── network.py               # Network detection: HTTP connectivity check
│   └── ui/
│       ├── main_window.py       # Floating recording window + pulsing red dot animation + Toast notifications
│       ├── settings_dialog.py   # Settings dialog (STT/Polish/Output/Hotkeys four-tab layout)
│       └── system_tray.py       # System tray + global hotkey management
├── tests/                       # Unit tests (178, covering all modules)
│   ├── conftest.py
│   ├── test_audio.py
│   ├── test_asr.py
│   ├── test_config.py
│   ├── test_main.py
│   ├── test_network.py
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
pip install -e ".[dev]"
pytest tests/ -v
```

## Configuration File

User configuration is stored at `%USERPROFILE%\.voice-type\config.json`. On first launch, if no configuration is detected, the settings dialog will automatically appear to guide the user through setup.

## Notes

- Speech recognition requires an internet connection and a valid API key
- Global hotkeys are only available on Windows
- Settings save automatically checks network connectivity and will not save if the network is unavailable
- Keep the floating window visible during recording; avoid using in security-sensitive applications (e.g., password managers)
- Text injection relies on the clipboard — do not copy other content during the paste operation
