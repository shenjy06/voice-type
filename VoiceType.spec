# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# 白名单：只收集项目明确需要的 PySide6 模块
# 不再列"不需要的模块"，而是列"需要的模块"
needed_binaries = []
needed_datas = []
needed_imports = []

for qt_module in ['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets']:
    datas, binaries, hiddenimports = collect_all(qt_module)
    needed_binaries.extend(binaries)
    needed_datas.extend(datas)
    needed_imports.extend(hiddenimports)

# 排除全局环境中的无关大包
excludes = [
    'torch', 'torchvision', 'torchaudio',
    'pandas', 'pyarrow', 'scipy',
    'sklearn', 'scikit-learn', 'matplotlib',
]

a = Analysis(
    ['src\\__main__.py'],
    pathex=[],
    binaries=needed_binaries,
    datas=needed_datas,
    hiddenimports=needed_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VoiceType',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
