# Voice Type

Windows 语音转文字速记工具。录制语音 → 语音识别 → 文本润色 → 自动粘贴到光标位置。

采用 [GPL-3.0](LICENSE) 许可证开源。

## 功能特性

- **语音录制**: 全局热键一键录制/停止/取消，不抢占目标应用焦点
- **语音识别 (STT)**: 将录制的音频转录为文本（支持 OpenAI 兼容协议）
- **智能润色**: LLM 自动去除语气词、修正语法、提升表达清晰度
- **词库修正**: 在润色前自动替换常见误识别的人名、项目名和技术名词
- **文本注入**: 恢复原始焦点窗口，将润色后的文本粘贴到光标位置
- **本地历史记录**: 使用本地 SQLite 保留最近识别文本，可从托盘菜单复制或重新粘贴
- **浮动控制窗口**: 始终置顶的迷你窗口，支持拖拽移动，带脉冲红点动画
- **状态气泡**: 录制时显示"录制中..."，润色时显示"润色中..."，完成后自动消失
- **系统托盘**: 点击 X 最小化到托盘，托盘菜单提供录制切换、设置、退出功能
- **全局热键**: 使用 pynput 监听键盘，在任何应用中均可响应
- **网络检测**: 保存设置时自动检测网络可用性，避免无效配置
- **启动检查**: 首次启动时自动检测 API 配置，未配置时弹出设置引导
- **中英文界面**: 支持中文/英文双语 UI，可在设置中切换语言，重启生效

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

点击浮动窗口右上角的齿轮图标打开设置页面，或通过系统托盘菜单进入设置。设置页面分为五个标签页：STT、Polish、Glossary、Output、Hotkeys。

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

### 输出配置

| 字段 | 说明 | 默认值 |
|------|------|--------|
| Paste Delay | 粘贴前延迟（毫秒） | `300 ms` |
| Paste Mode | 自动检测目标窗口、强制 `Ctrl+V`、强制 `Ctrl+Shift+V` 或仅复制 | 自动 |
| Auto-paste | 是否自动粘贴到光标位置 | 开启 |

如果自动粘贴失败，识别文本会保留在剪贴板中，可手动粘贴。

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
7. 如需放弃本次录制，按 `Right Alt + C` 取消（音频将被丢弃）
8. 点击窗口 X 按钮最小化到托盘，通过托盘菜单 "Quit" 完全退出

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
│       ├── asr.py                   # 语音识别：OpenAI 兼容 API
│       ├── glossary.py              # 词库修正：ASR 后专有名词替换
│       ├── polisher.py              # 文本润色：LLM API + 系统提示词
│       ├── typer.py                 # 文本注入：窗口管理 + 剪贴板
│       ├── window_manager.py        # Windows 窗口控制：ctypes API
│       ├── network.py               # 网络检测：HTTP 连通性检查
│       ├── state.py                 # 应用状态枚举 (RecorderState)
│       ├── i18n.py                  # 国际化：中英文翻译
│       └── ui/
│           ├── history_dialog.py    # 最近文本历史查看/复制/重新粘贴
│           ├── main_window.py       # 浮动录制窗口 + 脉冲红点动画 + 状态气泡 + Toast
│           ├── settings_dialog.py   # 设置对话框（STT/Polish/Glossary/Output/Hotkeys）
│           ├── system_tray.py       # 系统托盘 + 全局热键管理
│           └── icon_utils.py        # 共享图标创建（圆形 + 居中文字）
├── tests/                       # 单元测试（243 项，覆盖全部模块）
│   ├── conftest.py
│   ├── test_audio.py
│   ├── test_asr.py
│   ├── test_config.py
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
├── build.bat                    # 一键构建脚本
├── requirements.txt
├── pyproject.toml
└── README.md
```

## 运行测试

```bash
# 安装测试依赖（在已激活的 venv 中执行）
pip install -e ".[dev]"
pytest tests/ -v
```

## 配置文件

用户配置（包括词库词条）存储在 `%USERPROFILE%\.voice-type\config.json`。本地历史记录存储在 `%USERPROFILE%\.voice-type\history.sqlite3`。首次启动时如果未检测到配置，会自动弹出设置页面引导配置。

## 注意事项

- 语音识别需要网络连接和有效的 API 密钥
- 全局热键仅在 Windows 系统上可用
- 保存设置时会自动检测网络连通性，网络不可用时不会保存
- 录制时建议保持浮动窗口可见，避免在安全敏感应用（如密码管理器）中使用
- 文本注入依赖剪贴板，请勿在粘贴期间复制其他内容
