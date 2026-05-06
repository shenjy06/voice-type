# VoiceType 构建指南

本文档说明如何在 Windows 环境下构建 VoiceType 为独立可执行的 EXE 文件。

## 环境要求

| 项目 | 最低版本 | 说明 |
|------|---------|------|
| 操作系统 | Windows 10/11 (64-bit) | 仅支持 Windows |
| Python | 3.10+ | 推荐 3.12+ |
| pip | 23.0+ | 随 Python 一起安装 |
| 磁盘空间 | 至少 2 GB | 构建过程需要 |

## 第一步：安装 Python

1. 访问 [Python 官网](https://www.python.org/downloads/) 下载最新版 Python
2. 运行安装程序，**务必勾选 "Add Python to PATH"** 选项
3. 安装完成后打开命令行验证：

```cmd
python --version
pip --version
```

## 第二步：克隆项目

```cmd
git clone https://github.com/shenjy06/voice-type.git
cd voice-type
```

如果没有安装 Git，也可以从 GitHub 下载 ZIP 压缩包并解压到本地目录。

## 第三步：安装项目依赖

```cmd
pip install -r requirements.txt
```

这会安装以下核心依赖：
- `PySide6` — Qt GUI 框架
- `sounddevice` — 音频录制
- `numpy` — 音频数据处理
- `soundfile` — OGG 音频编码
- `openai` — OpenAI 兼容 API 客户端
- `pyperclip` — 剪贴板操作

## 第四步：安装构建工具

```cmd
pip install pyinstaller
```

PyInstaller 是将 Python 项目打包为独立 EXE 的工具。

## 第五步：构建 EXE

### 方式一：使用 spec 文件构建（推荐）

```cmd
pyinstaller VoiceType.spec
```

项目采用白名单打包策略，只收集必需的 Qt 模块（QtCore/QtGui/QtWidgets），排除全局环境中的大包（torch、pandas 等），体积约 73 MB。

### 方式二：一键构建

双击运行：

```
build.bat
```

该脚本会自动检查 Python 和 PyInstaller 是否安装，安装缺失的依赖，然后完成构建。

## 构建输出

构建成功后，EXE 文件位于：

```
dist\VoiceType.exe
```

文件大小约 73 MB（白名单优化后，原方案约 270 MB）。

## 测试构建结果

双击 `dist\VoiceType.exe` 启动程序，验证：
1. 浮动窗口是否正常显示
2. 系统托盘图标是否正常
3. 设置页面是否可以打开
4. 热键是否可以正常注册

## 可选：运行单元测试

构建前建议先运行测试确保代码正确性：

```cmd
pip install -e ".[dev]"
pytest tests/ -v
```

## 常见问题

### 1. `python` 命令找不到

确保安装 Python 时勾选了 "Add Python to PATH"。如果已经安装但未添加到 PATH，可以手动添加：
- 控制面板 → 系统 → 高级系统设置 → 环境变量 → Path → 编辑 → 添加 Python 安装目录

### 2. `sounddevice` 安装失败

确保已安装 Visual C++ 运行库：
- 下载 [VC++ Redistributable](https://learn.microsoft.com/zh-cn/cpp/windows/latest-supported-vc-redist)

### 3. 构建后 EXE 启动闪退

用命令行方式运行 EXE 查看错误信息：

```cmd
dist\VoiceType.exe
```

根据输出的错误信息排查问题。

### 4. 杀毒软件拦截

由于 PyInstaller 打包的特性，部分杀毒软件可能误报。可将 `dist\VoiceType.exe` 添加到杀毒软件白名单。
