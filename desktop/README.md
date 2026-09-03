# VoiceType Desktop (Electron)

VoiceType 的 Electron + TypeScript + React 实现，功能对齐仓库根目录的 Python/PySide6 版本（谱减法降噪除外）。仅支持 Windows（文本注入、全局热键依赖 Win32 API）。

## 功能

- **语音识别**：任意 OpenAI 兼容 `/v1/audio/transcriptions` 端点（批量）+ OpenAI Realtime / DashScope WebSocket 协议（流式，含实时字幕面板）
- **文本润色**：任意 OpenAI 兼容 `chat/completions`，支持 4 种风格、上下文感知（光标前后文本）、语言提示
- **词库替换**：正则一次替换，CSV 导入/导出（UTF-8 BOM，与 Python 版互通）
- **输出**：剪贴板粘贴（终端自动 Ctrl+Shift+V）、失败保留音频供托盘重试、连续口述
- **录音**：设备选择、采样率、RMS VAD 静音自动停止
- **配置**：命名档案、加密导出/导入（信封格式 `voice-type-config-enc-v1` 与 Python 版**双向互通**）、API key 本机 safeStorage(DPAPI) 保护
- **系统集成**：托盘全功能菜单、全局热键（默认右 Alt 轻点，Right Alt+C 取消）、单实例、开机自启
- **界面**：light/dark/system 主题、中英双语、悬浮录音窗（电平波形）/状态气泡/实时字幕/Toast

## 开发

```cmd
cd desktop
npm install
npm run dev        # 启动开发版
npm test           # vitest 单元测试（45 个）
npm run typecheck  # 主进程 + 渲染层 TS 检查
```

若 Electron 二进制下载失败，使用镜像：

```cmd
set ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
node node_modules\electron\install.js
```

## 打包

```cmd
npm run dist        # 两个产物 (dist/)
                    #   VoiceType-Setup-<版本>.exe     NSIS 安装版
                    #   VoiceType-<版本>-portable.zip  绿色便携版
npm run dist:dir    # 免安装目录 (dist/win-unpacked/VoiceType.exe)
```

便携版用法：用 7-Zip 等解压工具把 zip 解压到任意目录，直接运行其中的 `VoiceType.exe`。NSIS 构建工具下载卡住时，加镜像环境变量（见上方开发一节）后重试。

## 架构

```
src/main/      主进程：状态机、ASR/润色、Win32 注入(koffi)、配置、托盘、热键
src/preload/   contextBridge 类型化 API（全部窗口共用）
src/renderer/  5 个入口：floating(悬浮窗) overlay(气泡+字幕+Toast)
               settings(7 个标签页) history(历史) audio(隐藏采集窗口)
src/shared/    配置 schema(与 Python config.json 同构)、i18n、主题 token
tests/         vitest：词库/配置/加密互操作/WAV/VAD/热键解析/润色 prompt
```

数据流：隐藏 audio 窗口 getUserMedia + AudioWorklet 采集 PCM16 → IPC → 主进程缓冲（批量 WAV）+ 流式 WebSocket 双路分发 → ASR → 词库 → 润色 → 历史记录 → koffi keybd_event 粘贴回原前台窗口。

## 与 Python 版的兼容性

- `config.json` 字段名完全一致，可互相导入导出；Electron 额外使用 `recording.device_id`（WebRTC 设备 ID），忽略 Python 的 sounddevice `device` 整数索引
- 加密导出信封双向互通（tests/fernet-interop.test.ts 用 Python cryptography 生成的真实信封验证）
- API key 在本机配置文件中经 safeStorage 加密（`v1:` 前缀，DPAPI），与 Python 版 `v0:` base64 降级策略同构

## 已知差异

- 谱减法降噪未移植（设置项置灰）；浏览器采集链路默认关闭 AGC/降噪
- 右 Alt 轻点检测依赖 `uiohook-napi`（N-API 预编译）；加载失败时单键热键回退 Electron globalShortcut，右 Alt 不可用
- 历史记录为 JSON 文件（上限 20 条，同 Python 语义），不与 `history.sqlite3` 共享

## 加密互操作测试夹具

`tests/fixtures/python-envelope.json` 由 Python 版 `voicetype.crypto` 生成。重新生成：

```python
import json, base64, os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
salt = os.urandom(16)
kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000)
key = base64.urlsafe_b64encode(kdf.derive(b'test-password'))
token = Fernet(key).encrypt('中英 mixed 内容 123'.encode())
envelope = {'format': 'voice-type-config-enc-v1', 'kdf': 'pbkdf2-sha256',
            'iterations': 600_000, 'salt': base64.b64encode(salt).decode(),
            'ciphertext': base64.b64encode(token).decode()}
open('tests/fixtures/python-envelope.json', 'w', encoding='utf-8').write(json.dumps(envelope))
```
