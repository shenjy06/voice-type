# Voice Type 打包指南

将程序打包为 Windows 独立 .exe。

## 打包

### 安装

```bash
pip install pyinstaller
```

### 打包命令

```bash
pyinstaller VoiceType.spec
```

产物：`dist/VoiceType.exe`（约 73 MB 单文件）

## 体积优化

`VoiceType.spec` 采用白名单打包策略，只收集明确需要的模块：

| 优化项 | 说明 |
|--------|------|
| **白名单 Qt 模块** | 只收集 QtCore/QtGui/QtWidgets，不使用 collect_all |
| **黑名单排除大包** | 排除 torch、pandas、scipy、matplotlib 等全局环境大包 |
| **optimize=1** | 移除 docstrings（-O 编译） |
| **UPX 压缩** | 对二进制文件加壳压缩 |

实际体积约 **73 MB**（从 collect_all 方案的 ~270 MB 降至 ~73 MB）。

## 快速出包（单文件）

如果不需要优化体积，可直接用命令行：

```bash
pyinstaller --clean --noconfirm VoiceType.spec
```

产物：`dist/VoiceType.exe`

## 替代方案：auto-py-to-exe

```bash
pip install auto-py-to-exe
auto-py-to-exe
```

提供 GUI 界面，填好入口脚本和参数，一键生成 .exe。适合快速出包。

## 制作安装程序（可选）

如需制作安装包，可使用 Inno Setup：

1. 下载 [Inno Setup](https://jrsoftware.org/isdl.php) 并安装
2. 在项目根目录创建 `installer.iss`：

```iss
[Setup]
AppName=Voice Type
AppVersion=0.1.0
DefaultDirName={autopf}\VoiceType
DefaultGroupName=Voice Type
OutputBaseFilename=VoiceType-Setup
OutputDir=installer-output

[Files]
Source: "dist\VoiceType.exe"; DestDir: "{app}"

[Icons]
Name: "{commondesktop}\Voice Type"; Filename: "{app}\VoiceType.exe"
```

3. 用 Inno Setup 打开 `installer.iss` → Build → Compile
4. 生成的安装程序位于 `installer-output/VoiceType-Setup.exe`
