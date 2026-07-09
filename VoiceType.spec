# -*- mode: python ; coding: utf-8 -*-
#
# VoiceType PyInstaller spec.
#
# Strategy: only the runtime dependencies declared in pyproject.toml need to
# land in the bundle (PySide6 GUI, sounddevice/soundfile/numpy for audio,
# openai, pydantic, pyperclip, pynput). Everything else that PyInstaller
# may otherwise drag in from the global Python environment is explicitly
# excluded below.

datas = []
binaries = []

# soundfile ships libsndfile.dll (+ libvorbis/libogg dependencies) via its
# Python package. collect_all ensures every DLL/data file ships in the
# bundle. (Historically the default hook missed native deps on some setups;
# keeping the explicit collect is a safety net.)
from PyInstaller.utils.hooks import collect_all

_sf_datas, _sf_binaries, _sf_hiddenimports = collect_all("soundfile")
datas += _sf_datas
binaries += _sf_binaries

# cryptography ships Rust C extensions and OpenSSL bindings. collect_all
# pulls in the native deps (cryptography._rust, bundled OpenSSL) so that
# encrypted config export/import works in the frozen bundle. Listing only
# the top-level module name in hiddenimports is NOT enough - the native
# extension would fail to load at runtime.
_crypto_datas, _crypto_binaries, _crypto_hiddenimports = collect_all("cryptography")
datas += _crypto_datas
binaries += _crypto_binaries

# These modules MUST end up in the PYZ even when other parts of the same
# package are otherwise excluded. Keep this list minimal — only add a name
# here when the app actually imports it at runtime.
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
    "pynput.keyboard._win32",
    "websocket",
]
# Append transitive hidden imports collected above (soundfile, cryptography)
# so the linker sees every module they may load at runtime.
hiddenimports += _sf_hiddenimports + _crypto_hiddenimports

# Explicit deny list. PyInstaller treats `excludes` as a tree: excluding
# `pandas` also drops `pandas.core`, `pandas.io`, etc. Keep names here
# narrow enough to avoid surprising PyInstaller's own hooks.

# ---------------------------------------------------------------------------
# Heavy data / ML / scientific stack (none are required by voicetype)
# ---------------------------------------------------------------------------
excluded_optional_modules = [
    # Numerics / data
    "IPython",
    "PIL",
    "PIL.ImageQt",            # sometimes picked up via indirect imports
    "PIL.ImageTk",
    "cv2",
    "matplotlib",
    "matplotlib.backends",
    "notebook",
    "pandas",
    "pandas.core",
    "pandas.io",
    "pyarrow",
    "scipy",
    "scipy.spatial",
    "scipy.signal",
    "scipy.special",
    "scikit-learn",
    "sklearn",
    "tensorflow",
    "torch",
    "torchvision",
    "torchaudio",
    "tensorflow_io",
    # Jupyter / notebook
    "jupyter",
    "jupyter_client",
    "jupyter_core",
    "IPython.extensions",
    "nbconvert",
    "nbformat",
    # Testing / dev (the bundled EXE never runs tests)
    "pytest",
    "pytestqt",
    "_pytest",
    # Tk / wx widget toolkits (we only use Qt)
    "tkinter",
    "tkinter.ttk",
    "wx",
    # Other risky-to-ship optionals
    "lxml",
    "xmlrpc",
    "xmlrpc.client",
    "xmlrpc.server",
    "unittest",
    "unittest.mock",
    "pydoc_data",
    "doctest",
]

# ---------------------------------------------------------------------------
# PySide6 submodules we never use — excluding them keeps the bundle small
# without breaking the three we do use (QtCore/QtGui/QtWidgets).
# ---------------------------------------------------------------------------
pyside6_unused_submodules = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDBus",
    "PySide6.QtDesigner",
    "PySide6.QtGamepad",
    "PySide6.QtHelp",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetwork",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtXml",
]

# ---------------------------------------------------------------------------
# numpy sub-modules the app does NOT use — drop them to shrink the bundle.
# `numpy` itself, plus `numpy.core` pieces actually used at runtime, stay.
# ---------------------------------------------------------------------------
numpy_unused_submodules = [
    # NOTE: Do NOT exclude numpy._distributor_init or numpy.matrixlib —
    # numpy's __init__.py imports them unconditionally at startup.
    "numpy.distutils",
    "numpy.testing",
    "numpy.f2py",
    "numpy.compat",
    "numpy.core.tests",
    "numpy.lib.tests",
    "numpy.fft.tests",
    "numpy.linalg.tests",
    "numpy.random.tests",
    "numpy.tests",
]

# Merge all exclusion lists into the one PyInstaller consumes.
excluded_optional_modules = (
    excluded_optional_modules
    + pyside6_unused_submodules
    + numpy_unused_submodules
)


a = Analysis(
    ['src/voicetype/__main__.py'],
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
    # UPX disabled: it can corrupt native C-extension DLLs (numpy, soundfile)
    # causing hard-to-diagnose native crashes. Even though UPX isn't currently
    # installed on the build machine, keeping upx=False is a safety default.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
