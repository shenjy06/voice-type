# Voice Type

Windows 语音转文字速记工具。录制语音 → 语音识别 → 文本润色 → 自动粘贴到光标位置。

采用 [GPL-3.0](LICENSE) 许可证开源。

## 功能特性

- **语音录制**: 全局热键一键录制/停止/取消，不抢占目标应用焦点
- **语音识别 (STT)**: 将录制的音频转录为文本（支持 OpenAI 兼容协议）
- **智能润色**: LLM 自动去除语气词、修正语法、提升表达清晰度
- **文本注入**: 恢复原始焦点窗口，将润色后的文本粘贴到光标位置
- **浮动控制窗口**: 始终置顶的迷你窗口，支持拖拽移动，带脉冲红点动画
- **系统托盘**: 托盘图标提供录制切换、设置、退出等功能
- **全局热键**: 使用 Windows 原生热键 API，在任何应用中均可响应
- **网络检测**: 保存设置时自动检测网络可用性，避免无效配置
- **启动检查**: 首次启动时自动检测 API 配置，未配置时弹出设置引导

## 技术栈

| 组件 | 技术 |
|------|------|
| GUI | PySide6 (Qt 6) |
| 音频录制 | sounddevice + numpy |
| 音频编码 | soundfile (OGG/Vorbis) |
| 语音识别 | OpenAI 兼容协议 (ASR API) |
| 文本润色 | OpenAI 兼容协议 (Chat Completions API) |
| 全局热键 | Windows RegisterHotKey (ctypes) |
| 文本注入 | pyperclip (剪贴板) + ctypes (窗口管理) |

## 安装

```bash
# 克隆项目
cd voice-type

# 安装依赖
pip install -r requirements.txt
```

### 依赖说明

- `PySide6` — Qt GUI 框架
- `sounddevice` — 跨平台音频录制
- `numpy` — 音频数据处理
- `soundfile` — OGG/Vorbis 音频文件编码
- `openai` — 调用兼容 OpenAI API 协议的 STT 和 LLM 服务
- `pyperclip` — 跨平台剪贴板操作

> 注：Windows 热键和窗口管理使用标准库 `ctypes`，无需额外依赖。

## 运行

```bash
python -m voice_type
```

## 打包为 EXE

项目提供一键构建脚本，双击即可打包：

```bash
build.bat
```

或使用命令行：

```bash
pyinstaller --clean --name="VoiceType" --windowed --noconfirm --onefile \
    --collect-all PySide6 \
    voice_type/__main__.py
```

生成的 `dist/VoiceType.exe` 为独立可执行文件，无需安装 Python 环境。

## 设置

点击浮动窗口右上角的齿轮图标打开设置页面，或通过系统托盘菜单进入设置。设置页面分为四个标签页：STT、Polish、Output、Hotkeys。

### STT（语音识别）配置

| 字段 | 说明 | 示例 |
|------|------|------|
| API Key | STT 服务的认证密钥 | `sk-...` |
| Base URL | STT 服务的 API 地址 | `https://api.siliconflow.cn/v1` |
| Model | 语音识别模型 | `FunAudioLLM/SenseVoiceSmall` |
| Language | 识别语言 | `zh` / `en` / `auto` |
| Sample Rate | 录制采样率 | `16000` Hz |

### Polish（文本润色）配置

| 字段 | 说明 | 示例 |
|------|------|------|
| API Key | LLM 服务的认证密钥 | `sk-...` |
| Base URL | LLM 服务的 API 地址 | `https://api.siliconflow.cn/v1` |
| Model | 文本润色模型 | `gpt-4o` / `deepseek-chat` / `qwen-plus` |

### 热键配置

在设置中可以分别配置开始录制、停止录制和取消录制的热键：

| 热键 | 默认 | 说明 |
|------|------|------|
| 开始录制 | `Alt + S` | 开始录制语音 |
| 停止录制 | `Alt + E` | 停止录制并进入识别/润色流程 |
| 取消录制 | `Alt + C` | 停止录制并丢弃音频，不进行后续处理 |

支持 `alt`、`ctrl`、`shift`、`super`、`none` 修饰键，最多两个修饰键组合。

### 输出配置

| 字段 | 说明 | 默认值 |
|------|------|--------|
| Paste Delay | 粘贴前延迟（毫秒） | `300 ms` |
| Auto-paste | 是否自动粘贴到光标位置 | 开启 |

## API 密钥配置

Voice Type 使用 OpenAI 兼容协议的 API，支持多种服务商。以下是常用的配置示例：

### SiliconFlow（硅基流动）

注册地址: https://cloud.siliconflow.cn

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

注册地址: https://platform.openai.com

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

### 自定义兼容 OpenAI API 的服务商

任何支持 OpenAI 兼容协议的 API 均可使用（DashScope、火山引擎、本地部署的 Ollama/vLLM 等）。只需在设置中填写对应的 Base URL 和 API Key，并确保模型名称正确。

## 使用流程

1. 启动程序，首次运行时会自动弹出设置引导页面
2. 在设置中配置好 API Key 和模型
3. 将光标放在需要输入的位置
4. 按 `Alt + S` 开始录制（窗口保持显示，脉冲红点亮起）
5. 说话完毕后，按 `Alt + E` 停止录制
6. 等待处理完成，润色后的文本将自动出现在光标位置
7. 如需放弃本次录制，按 `Alt + C` 取消（音频将被丢弃）

## 项目结构

```
voice-type/
├── voice_type/
│   ├── __main__.py              # 入口：Application 类，连接所有组件
│   ├── config.py                # 配置管理：dataclass + JSON 序列化/持久化
│   ├── audio.py                 # 音频录制：sounddevice 异步录制 + soundfile 编码为 OGG
│   ├── asr.py                   # 语音识别：OpenAI 兼容 API
│   ├── polisher.py              # 文本润色：LLM API + 系统提示词
│   ├── typer.py                 # 文本注入：窗口管理 + 剪贴板
│   ├── network.py               # 网络检测：HTTP 连通性检查
│   └── ui/
│       ├── main_window.py       # 浮动录制窗口 + 脉冲红点动画 + Toast 通知
│       ├── settings_dialog.py   # 设置对话框（STT/Polish/Output/Hotkeys 四标签页）
│       └── system_tray.py       # 系统托盘 + 全局热键管理
├── tests/                       # 单元测试（178 项，覆盖全部模块）
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
├── build.bat                    # 一键构建脚本
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 运行测试

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## 配置文件

用户配置存储在 `%USERPROFILE%\.voice-type\config.json`。首次启动时如果未检测到配置，会自动弹出设置页面引导配置。

## 注意事项

- 语音识别需要网络连接和有效的 API 密钥
- 全局热键仅在 Windows 系统上可用
- 保存设置时会自动检测网络连通性，网络不可用时不会保存
- 录制时建议保持浮动窗口可见，避免在安全敏感应用（如密码管理器）中使用
- 文本注入依赖剪贴板，请勿在粘贴期间复制其他内容
