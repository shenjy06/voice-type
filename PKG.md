# Voice Type 打包指南

将程序打包为 Windows 安装程序，分两个阶段：**PyInstaller 打包** + **Inno Setup 制作安装包**。

## 第一阶段：PyInstaller 打包成独立 .exe

### 安装

```bash
pip install pyinstaller
```

### 打包命令

```bash
pyinstaller voice_type/__main__.py \
  --name "VoiceType" \
  --onedir \
  --windowed \
  --hidden-import sounddevice \
  --hidden-import scipy
```

### 参数说明

| 参数 | 作用 |
|------|------|
| `--name` | 输出目录/文件名 |
| `--onedir` | 输出一个文件夹（包含 .exe 和依赖 dll），适合制作安装包 |
| `--windowed` | 隐藏命令行控制台窗口（GUI 应用不需要） |
| `--hidden-import` | PyInstaller 可能漏掉动态导入的包，需手动指定 |

### 注意事项

- PySide6 的 Qt 插件（`platforms/qwindows.dll` 等）通常会自动收集。如果打包后启动闪退，检查 `dist/VoiceType/PySide6/plugins/platforms/` 是否存在 `qwindows.dll`
- 打包完成后产物在 `dist/VoiceType/` 目录

### 快速出包（单文件）

如果只需要一个独立 .exe，不需要安装包：

```bash
pyinstaller voice_type/__main__.py \
  --name "VoiceType" \
  --onefile \
  --windowed \
  --hidden-import sounddevice \
  --hidden-import scipy
```

产物：`dist/VoiceType.exe`（体积较大，启动稍慢）

### 替代方案：auto-py-to-exe

```bash
pip install auto-py-to-exe
auto-py-to-exe
```

提供 GUI 界面，填好入口脚本和参数，一键生成 .exe。适合快速出包。

## 第二阶段：Inno Setup 制作安装程序

### 安装

下载 [Inno Setup](https://jrsoftware.org/isdl.php) 并安装。

### 创建打包脚本

在项目根目录创建 `installer.iss`：

```iss
[Setup]
AppName=Voice Type
AppVersion=0.1.0
DefaultDirName={autopf}\VoiceType
DefaultGroupName=Voice Type
OutputBaseFilename=VoiceType-Setup
OutputDir=installer-output

[Files]
Source: "dist\VoiceType\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Voice Type"; Filename: "{app}\__main__.exe"
Name: "{commondesktop}\Voice Type"; Filename: "{app}\__main__.exe"
```

### 编译安装包

1. 用 Inno Setup 打开 `installer.iss`
2. 点击 **Build → Compile**
3. 生成的安装程序位于 `installer-output/VoiceType-Setup.exe`

## 方案对比

| 场景 | 方案 |
|------|------|
| 快速出包自己用 | PyInstaller `--onefile --windowed`，直接给 .exe |
| 正式分发 / 安装包 | PyInstaller `--onedir` + Inno Setup |
| 持续集成打包 | PyInstaller + GitHub Actions (windows-latest runner) |
