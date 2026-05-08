# -*- mode: python ; coding: utf-8 -*-

datas = []
binaries = []

# Keep the bundled dependency surface explicit. PyInstaller can otherwise follow
# optional hooks from the global Python environment and pull in large packages
# such as pandas, scipy, torch, and pyarrow.
hiddenimports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "sounddevice",
    "soundfile",
    "numpy",
    "openai",
    "pyperclip",
    "pynput",
    "pynput.keyboard",
]

excluded_optional_modules = [
    "IPython",
    "PIL",
    "cv2",
    "matplotlib",
    "notebook",
    "pandas",
    "pyarrow",
    "pytest",
    "scipy",
    "scikit-learn",
    "sklearn",
    "tensorflow",
    "torch",
    "torchaudio",
    "torchvision",
]


a = Analysis(
    ['src\\__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_optional_modules,
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
