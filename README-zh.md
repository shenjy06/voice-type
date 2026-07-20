# Voice Type

[English](README.md) | 中文

Windows 语音转文字速记工具。录制语音 → 语音识别 → 文本润色 → 自动粘贴到光标位置。

采用 [GPL-3.0](LICENSE) 许可证开源。

## 功能特性

- **语音录制**: 全局热键一键录制/停止/取消，不抢占目标应用焦点
- **降噪**: 可选的谱门降噪，识别前去除稳态背景噪声（风扇、空调、电流声等）——纯 numpy 实现，无额外依赖。仅针对稳态噪声，瞬态声音（键盘敲击等）效果有限
- **静音自动停止 (VAD)**: 可选的静音自动停止，检测到持续静音后自动停止录音，无需手动按键。只有开口后才开始计静音，开口前的停顿不会误触发
- **流式实时转写**: 可选的实时语音转写，通过 WebSocket 将音频流式发送到服务端，说话时文字即时显示（OpenAI Realtime API 协议）
- **实时字幕面板**: 流式转写时，状态气泡上方会显示完整的实时字幕面板，不再只有 40 字符的截断预览；长文本自动从头部裁剪，保证最新内容始终可见
- **处理失败重试**: 批量处理失败（网络抖动、限流、API 超时）后保留音频文件，可从托盘菜单一键重试，无需重新录制
- **语音识别 (STT)**: 将录制的音频转录为文本（支持 OpenAI 兼容协议）
- **智能润色**: LLM 自动去除语气词、修正语法、提升表达清晰度
- **多语言润色提示**: 根据配置的 ASR 语言，在润色中英混合口述内容时保持 LLM 聚焦正确语言，避免语言漂移
- **词库修正**: 在润色前自动替换常见误识别的人名、项目名和技术名词
- **文本注入**: 恢复原始焦点窗口，将润色后的文本粘贴到光标位置
- **连续口述**: 每段处理并粘贴后自动重新开始录音，无需反复按切换热键即可口述长内容。按取消热键结束本次会话
- **本地历史记录**: 使用本地 SQLite 保留最近识别文本，可从托盘菜单复制或重新粘贴
- **浮动控制窗口**: 始终置顶的迷你窗口，支持拖拽移动，带脉冲红点动画
- **状态气泡**: 录制时显示"录制中..."，润色时显示"润色中..."，完成后自动消失
- **系统托盘**: 点击 X 最小化到托盘，托盘菜单提供录制切换、设置、退出功能
- **全局热键**: 使用 pynput 监听键盘，在任何应用中均可响应
- **网络检测**: 保存设置时自动检测网络可用性，避免无效配置
- **配置导入导出**: 将完整配置（含 API 密钥）导出为 JSON 文件，可备份或在多台机器间迁移；导入时显示配置预览，空配置文件会触发警告
- **启动检查**: 首次启动时自动检测 API 配置，未配置时弹出设置引导
- **中英文界面**: 支持中文/英文双语 UI，可在设置中切换语言，重启生效
- **明暗主题切换**: 支持深色、浅色、跟随系统三种主题模式，在设置中切换即实时预览。所有界面（对话框、浮动窗口、托盘、气泡、历史记录）统一配色，靛蓝强调色 + 矢量图标
- **模型自动发现**: 设置中点击刷新按钮可自动获取提供商的全部可用模型，无需手动复制模型名
- **命名配置档案**: 保存和切换多个命名配置方案（工作、个人等），在设置通用标签页管理
- **加密配置导出**: 支持密码加密导出配置文件，保护 API 密钥安全

## 技术栈

| 组件 | 技术 |
|------|------|
| GUI | PySide6 (Qt 6) |
| 音频录制 | sounddevice + numpy |
| 音频编码 | soundfile (OGG/Vorbis) |
| 语音识别 | OpenAI 兼容协议 (ASR API) |
| 文本润色 | OpenAI 兼容协议 (Chat Completions API) |
| 全局热键 | pynput 键盘监听 |
| 文本注入 | pyperclip (剪贴板) + ctypes (窗口管理) |

## 安装

建议使用虚拟环境运行本项目，将依赖与全局 Python 环境隔离。

### 使用 venv（推荐）

```bash
# 克隆项目
cd voice-type

# 创建虚拟环境（需要 Python 3.10+）
python -m venv .venv

# 激活虚拟环境
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (命令提示符):
.venv\Scripts\activate.bat
# Windows (Git Bash):
source .venv/Scripts/activate

# 安装依赖
pip install -r requirements.txt
```

### 直接安装（不使用 venv）

```bash
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
python -m voicetype
```

## 打包为 EXE

项目提供一键构建脚本，双击即可打包：

```bash
build.bat
```

或使用命令行：

```bash
pyinstaller --clean --noconfirm VoiceType.spec
```

`VoiceType.spec` 采用白名单打包策略，并排除全局 Python 环境中的大体积可选依赖。

生成的 `dist/VoiceType.exe` 为独立可执行文件，无需安装 Python 环境。

## 设置

点击浮动窗口右上角的齿轮图标打开设置页面，或通过系统托盘菜单进入设置。设置页面分为以下标签页：通用、录音、STT、润色、词库、输出、热键。

### 通用设置

| 字段 | 说明 | 默认值 |
|------|------|--------|
| 界面语言 | 界面显示语言 | 自动（跟随系统） |
| 主题 | 深色、浅色或跟随 Windows 系统主题 | 深色 |
| 开机自启动 | 是否随系统启动 | 关闭 |

### STT（语音识别）配置

| 字段 | 说明 | 示例 |
|------|------|------|
| API Key | STT 服务的认证密钥 | `sk-...` |
| Base URL | STT 服务的 API 地址 | `https://api.siliconflow.cn/v1` |
| Model | 语音识别模型（点击刷新按钮可获取提供商全部模型列表） | `FunAudioLLM/SenseVoiceSmall` |
| Language | 识别语言 | `zh` / `en` / `auto` |
| Sample Rate | 录制采样率 | `16000` Hz |
| Noise Reduction | 识别前是否启用谱门降噪 | `Off` / `On` |
| NR Strength | 降噪强度（越高抑制噪声越多，但可能影响语音） | `Low` / `Medium` / `High` |
| Auto-stop on silence | 检测到持续静音后自动停止录音（开口前的静音不计） | `Off` / `On` |
| Silence duration | 触发自动停止的静音时长 | `1500 ms` |
| Streaming | 将音频实时流式发送到服务端进行转写（使用上方的接口地址和 API 密钥） | `Off` / `On` |

### Polish（文本润色）配置

| 字段 | 说明 | 示例 |
|------|------|------|
| API Key | LLM 服务的认证密钥 | `sk-...` |
| Base URL | LLM 服务的 API 地址 | `https://api.siliconflow.cn/v1` |
| Model | 文本润色模型（点击刷新按钮可获取提供商全部模型列表） | `gpt-4o` / `deepseek-chat` / `qwen-plus` |

### Glossary（词库）配置

在 Glossary 标签页维护专有名词修正规则。规则会在语音识别完成后、文本润色前执行，适合修正常见误识别的人名、项目名、缩写和技术名词。

| 字段 | 说明 | 示例 |
|------|------|------|
| 识别文本 | ASR 返回的错误文本 | `派森` |
| 替换为 | 最终输出的正确词 | `Python` |

### 热键配置

| 热键 | 默认 | 说明 |
|------|------|------|
| 切换录制 | `Right Alt`（单击） | 第一次点击开始录制，第二次点击停止录制 |
| 取消录制 | `Right Alt + C` | 停止录制并丢弃音频，不进行后续处理 |

Right Alt 热键区分单击（切换录制）和组合键（按住它加其他键不触发录制）。左 Alt 不受影响，保留正常输入功能。

开启连续口述时，轻点切换热键会结束当前分段（处理并粘贴）并自动开始录制下一段。按 Right Alt+C 结束本次连续会话。

### 输出配置

| 字段 | 说明 | 默认值 |
|------|------|--------|
| Paste Delay | 粘贴前延迟（毫秒） | `120 ms` |
| Paste Mode | 自动检测目标窗口、强制 `Ctrl+V`、强制 `Ctrl+Shift+V` 或仅复制 | 自动 |
| Auto-paste | 是否自动粘贴到光标位置 | 开启 |
| 连续口述 | 每段粘贴后自动重新开始录音 | 关闭 |

如果自动粘贴失败，识别文本会保留在剪贴板中，可手动粘贴。

### 配置管理

设置对话框提供导出和导入按钮，用于备份或迁移配置：

- **导出** 将当前完整配置（含 API 密钥）保存到指定的 JSON 文件
- **导入** 加载配置文件，在确认前展示配置预览摘要；若文件为空/默认值将弹窗警告
- 导入后设置仅加载到对话框，需点击保存才生效——可先检查确认再保存

## API 密钥配置

Voice Type 使用 OpenAI 兼容协议的 API，支持多种服务商。以下是常用的配置示例：

### SiliconFlow（硅基流动）

注册地址: https://cloud.siliconflow.cn/i/BLu934tI

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
  },
  "glossary": [
    {"source": "派森", "replacement": "Python"}
  ]
}
```

### 自定义兼容 OpenAI API 的服务商

任何支持 OpenAI 兼容协议的 API 均可使用（DashScope、火山引擎、本地部署的 Ollama/vLLM 等）。只需在设置中填写对应的 Base URL 和 API Key，并确保模型名称正确。

## 使用流程

1. 启动程序，首次运行时会自动弹出设置引导页面
2. 在设置中配置好 API Key 和模型
3. 将光标放在需要输入的位置
4. 按 `Right Alt`（单击一次）开始录制（状态气泡显示"录制中..."）
5. 说话完毕后，按 `Right Alt`（单击一次）停止录制
6. 等待处理完成（状态气泡显示"润色中..."），润色后的文本将自动出现在光标位置
7. 如果处理失败（网络错误、限流等），通过托盘菜单"重试上次处理"使用同一份音频重新处理，无需重新录制
8. 如需放弃本次录制，按 `Right Alt + C` 取消（音频将被丢弃）
9. 点击窗口 X 按钮最小化到托盘，通过托盘菜单 "Quit" 完全退出

## 项目结构

```
voice-type/
├── src/
│   └── voicetype/
│       ├── __main__.py              # 入口：Application 类，连接所有组件
│       ├── api_client.py            # OpenAI 兼容 API 客户端封装
│       ├── config.py                # 配置管理：dataclass + JSON 序列化/持久化
│       ├── history.py               # SQLite 本地识别文本历史记录
│       ├── audio.py                 # 音频录制：sounddevice 异步录制 + soundfile 编码为 OGG
│       ├── denoise.py               # 谱门降噪（纯 numpy 实现）
│       ├── asr.py                   # 语音识别：OpenAI 兼容 API
│       ├── streaming_asr.py         # 流式实时转写：WebSocket（OpenAI Realtime 协议）
│       ├── glossary.py              # 词库修正：ASR 后专有名词替换
│       ├── polisher.py              # 文本润色：LLM API + 系统提示词
│       ├── processing.py            # 处理管线协调（STT + 词库 + 润色）
│       ├── processing_controller.py  # 处理线程协调
│       ├── recording_controller.py   # 录制线程协调
│       ├── typer.py                 # 文本注入：窗口管理 + 剪贴板
│       ├── window_manager.py        # Windows 窗口控制：ctypes API
│       ├── network.py               # 网络检测：HTTP 连通性检查
│       ├── state.py                 # 应用状态枚举 (RecorderState)
│       ├── i18n.py                  # 国际化：中英文翻译
│       ├── crypto.py                # 密码加密配置导出 (Fernet + PBKDF2)
│       └── ui/
│           ├── history_dialog.py    # 最近文本历史查看/复制/重新粘贴
│           ├── main_window.py       # 浮动录制窗口 + 脉冲红点动画 + 状态气泡 + Toast
│           ├── settings_dialog.py   # 设置对话框（STT/润色/词库/输出/热键）
│           ├── system_tray.py       # 系统托盘 + 全局热键管理
│           ├── theme.py             # 主题管理：明暗调色板、QSS、矢量图标
│           └── icon_utils.py        # 共享图标创建（圆形 + 居中文字）
├── tests/                       # 单元测试（495 项，23 个文件，覆盖全部模块）
├── run_tests.py                 # 内存友好的测试运行器（每个文件独立子进程）
│   ├── conftest.py
│   ├── test_audio.py
│   ├── test_asr.py
│   ├── test_config.py
│   ├── test_controllers.py
│   ├── test_denoise.py
│   ├── test_main.py
│   ├── test_network.py
│   ├── test_glossary.py
│   ├── test_i18n.py
│   ├── test_polisher.py
│   ├── test_streaming_asr.py
│   ├── test_typer.py
│   ├── test_crypto.py
│   └── ui/
│       ├── test_history_dialog.py
│       ├── test_hotkey_recorder.py
│       ├── test_main_window.py
│       ├── test_settings_dialog.py
│       ├── test_system_tray.py
│       └── test_theme.py
├── build.bat                    # 一键构建脚本
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 运行测试

```bash
# 安装测试依赖（在已激活的 venv 中执行）
pip install -e ".[dev]"
```

全套测试包含 495 个用例、23 个文件。在单个 `pytest` 进程内运行会持续积累内存（模块字节码、行缓存、Qt 图标缓存），峰值可达 500MB+。建议使用 `run_tests.py`，它会为每个测试文件启动独立的子进程，单个子进程内存控制在 ~150MB 以内，进程结束后操作系统自动回收全部内存：

```bash
python run_tests.py              # 运行全套测试
python run_tests.py tests/test_controllers.py  # 运行单个文件
```

日常开发中也可以直接运行单个文件：

```bash
pytest tests/test_foo.py -v
```

## 配置文件

用户配置（包括词库词条）存储在 `%USERPROFILE%\.voice-type\config.json`。本地历史记录存储在 `%USERPROFILE%\.voice-type\history.sqlite3`。首次启动时如果未检测到配置，会自动弹出设置页面引导配置。

## 注意事项

- 语音识别需要网络连接和有效的 API 密钥
- 全局热键仅在 Windows 系统上可用
- 保存设置时会自动检测网络连通性，网络不可用时不会保存
- 录制时建议保持浮动窗口可见，避免在安全敏感应用（如密码管理器）中使用
- 文本注入依赖剪贴板，请勿在粘贴期间复制其他内容
