# Voice Type

用语音输入代替键盘打字。录制语音 → 语音识别 → 文本润色 → 自动粘贴到光标位置。

## 功能特性

- **语音录制**: 全局热键一键录制/停止，录制时自动隐藏浮动窗口，不抢占目标应用焦点
- **语音识别 (STT)**: 将录制的音频转录为文本
- **智能润色**: LLM 自动去除语气词、修正语法、提升表达清晰度
- **文本注入**: 恢复原始焦点窗口，将润色后的文本粘贴到光标位置
- **浮动控制窗口**: 始终置顶的迷你窗口，支持拖拽移动
- **系统托盘**: 托盘图标提供录制切换、设置、退出等功能
- **全局热键**: 使用 Windows 原生热键 API，在任何应用中均可响应

## 技术栈

| 组件 | 技术 |
|------|------|
| GUI | PySide6 (Qt 6) |
| 音频录制 | sounddevice + numpy + scipy |
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
- `numpy` + `scipy` — 音频数据处理和 WAV 文件生成
- `openai` — 调用兼容 OpenAI API 协议的 STT 和 LLM 服务
- `pyperclip` — 跨平台剪贴板操作
- `pywin32` — Windows 原生窗口操作（热键注册等）

## 运行

```bash
python -m voice_type
```

## 设置

点击浮动窗口右上角的齿轮图标打开设置页面，或通过系统托盘菜单进入设置。

### STT（语音识别）配置

| 字段 | 说明 | 示例 |
|------|------|------|
| API Key | STT 服务的认证密钥 | `sk-...` |
| Base URL | STT 服务的 API 地址 | `https://api.siliconflow.cn/v1` |
| Model | 语音识别模型 | `FunAudioLLM/SenseVoiceSmall` |
| Language | 识别语言 | `zh` / `en` / `auto` |

### Polish（文本润色）配置

| 字段 | 说明 | 示例 |
|------|------|------|
| API Key | LLM 服务的认证密钥 | `sk-...` |
| Base URL | LLM 服务的 API 地址 | `https://api.siliconflow.cn/v1` |
| Model | 文本润色模型 | `Qwen/Qwen2.5-7B-Instruct` |

### 热键配置

在设置中可以分别配置开始录制和停止录制的热键：

- **开始录制**: 默认 `Alt + S`
- **停止录制**: 默认 `Alt + E`

支持 `alt`、`ctrl`、`shift`、`super` 修饰键组合。

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
    "model": "Qwen/Qwen2.5-7B-Instruct"
  }
}
```

支持的 STT 模型：`FunAudioLLM/SenseVoiceSmall`（支持 OpenAI 兼容的 `/audio/transcriptions` 端点）

支持的 Polish 模型：`Qwen/Qwen2.5-7B-Instruct`、`THUDM/glm-4-9b-chat`、`deepseek-ai/DeepSeek-V3` 等

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

1. 启动程序，看到浮动的控制窗口
2. 在设置中配置好 API Key 和模型
3. 将光标放在需要输入的位置
4. 按 `Alt + S` 开始录制（窗口保持显示，按钮变为 "Recording..."）
5. 说话完毕后，按 `Alt + E` 停止录制
6. 等待处理完成，润色后的文本将自动出现在光标位置

## 项目结构

```
voice-type/
├── voice_type/
│   ├── __main__.py          # 入口：Application 类，连接所有组件
│   ├── config.py            # 配置管理：dataclass + JSON 序列化
│   ├── audio.py             # 音频录制：sounddevice start/stop/save
│   ├── asr.py               # 语音识别：OpenAI 兼容 API
│   ├── polisher.py          # 文本润色：LLM API + 系统提示词
│   ├── typer.py             # 文本注入：窗口管理 + 剪贴板
│   └── ui/
│       ├── main_window.py   # 浮动录制窗口 + 脉冲红点动画
│       ├── settings_dialog.py # 设置对话框（STT/Polish/热键）
│       └── system_tray.py   # 系统托盘 + 全局热键管理
├── requirements.txt
└── README.md
```

## 配置文件

用户配置存储在 `%USERPROFILE%\.voice-type\config.json`。首次运行时会自动创建默认配置。

## 注意事项

- 语音识别需要网络连接和有效的 API 密钥
- 全局热键仅在 Windows 系统上可用
- 录制时建议保持浮动窗口可见，避免在安全敏感应用（如密码管理器）中使用
- 文本注入依赖剪贴板，请勿在粘贴期间复制其他内容
