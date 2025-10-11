# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for KUKA GUI Editor
#
# Purpose: Create a standalone Windows executable that includes:
#   - All Python dependencies (numpy, matplotlib, tkinter)
#   - KUKA source parser module
#   - All required DLLs and data files
#
# Usage on Windows:
#   1. Install dependencies: pip install pyinstaller numpy matplotlib
#   2. Build executable: pyinstaller build_windows.spec
#   3. Find output in: dist/KUKAEditor.exe
#
# The resulting .exe is fully standalone and can be distributed without Python

block_cipher = None

a = Analysis(
    ['kuka_gui_editor.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Core dependencies
        'numpy',
        'numpy.core._multiarray_umath',
        'matplotlib',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg',
        'matplotlib.figure',
        'matplotlib.pyplot',
        'tkinter',
        'tkinter.filedialog',
        '_tkinter',

        # 3D plotting
        'mpl_toolkits.mplot3d',
        'mpl_toolkits.mplot3d.axes3d',
        'mpl_toolkits.mplot3d.proj3d',

        # Matplotlib widgets
        'matplotlib.widgets',

        # KUKA parser
        'kuka_src_parser',

        # Python standard library
        'copy',
        'enum',
        'dataclasses',
        'typing',
        'glob',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unnecessary packages to reduce size
        'pytest',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='KUKAEditor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # Compress executable with UPX (reduces file size)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI only). Set to True for debugging.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one: icon='icon.ico'
)
