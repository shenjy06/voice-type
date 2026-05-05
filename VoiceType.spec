# -*- mode: python ; coding: utf-8 -*-
"""
Optimized spec: manually collect ONLY the PySide6 modules we actually use.
This avoids the massive bloat from collect_all('PySide6').
"""
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    get_hook_config,
)

# ============================================================
# Only the Qt modules actually used by voice-type
# ============================================================
_qt_modules = ['QtCore', 'QtGui', 'QtWidgets']

datas = [('voice_type', 'voice_type')]

# Collect data files for each Qt module (translations excluded by default)
for mod in _qt_modules:
    datas += collect_data_files(f'PySide6.{mod}', include_py_files=False)

# Collect essential binaries (Qt platform plugin + core DLLs)
binaries = collect_dynamic_libs('PySide6.QtCore')
binaries += collect_dynamic_libs('PySide6.QtGui')
binaries += collect_dynamic_libs('PySide6.QtWidgets')

# Also collect shiboken6 binaries (required by PySide6)
binaries += collect_dynamic_libs('shiboken6')

# Build hiddenimports manually for only the Qt modules we need
hiddenimports = [
    'voice_type.__main__',
    'voice_type.audio',
    'voice_type.asr',
    'voice_type.polisher',
    'voice_type.typer',
    'voice_type.config',
    'voice_type.network',
    'voice_type.ui.main_window',
    'voice_type.ui.settings_dialog',
    'voice_type.ui.system_tray',
]
for mod in _qt_modules:
    hiddenimports += collect_submodules(f'PySide6.{mod}')

# Add shiboken6
hiddenimports += collect_submodules('shiboken6')

# Add openai + sounddevice (much smaller, collect_all is acceptable here)
_tmp = collect_submodules('openai')
hiddenimports += _tmp
datas += collect_data_files('openai', include_py_files=False)
_tmp = collect_submodules('sounddevice')
hiddenimports += _tmp
datas += collect_data_files('soundfile', include_py_files=False)
datas += collect_data_files('sounddevice', include_py_files=False)

# Add required platform plugin
datas += collect_data_files('PySide6.plugins.platforms', include_py_files=False)

# ============================================================
# Build
# ============================================================
a = Analysis(
    ['voice_type\\__main__.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'PIL',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'PySide6.Qt3DCore',
        'PySide6.Qt3DRender',
        'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic',
        'PySide6.Qt3DAnimation',
        'PySide6.Qt3DExtras',
        'PySide6.QtWebEngineCore',
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineQuick',
        'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets',
        'PySide6.QtQml',
        'PySide6.QtQuick',
        'PySide6.QtQuickWidgets',
        'PySide6.QtQuick3D',
        'PySide6.QtDesigner',
        'PySide6.QtSql',
        'PySide6.QtTest',
        'PySide6.QtXml',
        'PySide6.QtOpenGL',
        'PySide6.QtOpenGLWidgets',
        'PySide6.QtPositioning',
        'PySide6.QtLocation',
        'PySide6.QtSensors',
        'PySide6.QtSerialPort',
        'PySide6.QtStateMachine',
        'PySide6.QtBluetooth',
        'PySide6.QtConcurrent',
        'PySide6.QtDBus',
        'PySide6.QtHelp',
        'PySide6.QtNfc',
        'PySide6.QtRemoteObjects',
        'PySide6.QtScxml',
        'PySide6.QtSvg',
        'PySide6.QtSvgWidgets',
        'PySide6.QtUiTools',
        'PySide6.QtTextToSpeech',
        'PySide6.QtCharts',
        'PySide6.QtDataVisualization',
        'PySide6.QtVirtualKeyboard',
        'PySide6.QtWebChannel',
        'PySide6.QtWebSockets',
        'PySide6.QtPdf',
        'PySide6.QtPdfWidgets',
        'PySide6.QtAxContainer',
        'PySide6.QtNetwork',
        'PySide6.QtPrintSupport',
        'PySide6.QtSerialBus',
        'PySide6.QtSpatialAudio',
        'PySide6.QtGraphs',
        'PySide6.QtGraphsWidgets',
        'PySide6.QtHttpServer',
        'PySide6.QtCanvasPainter',
        'PySide6.QtWebView',
        'PySide6.QtAsyncio',
    ],
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
