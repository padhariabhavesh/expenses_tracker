from PyInstaller.utils.hooks import collect_all

datas = [('frontend/templates', 'templates'), ('static', 'static')]
binaries = []
hiddenimports = []

# Collect all PyQt5 hooks
tmp_ret = collect_all('PyQt5')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Add specific submodules to be safe
hiddenimports += ['PyQt5.QtWidgets', 'PyQt5.QtWebEngineWidgets', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtNetwork']

# Manual fix for missing DLLs
import os
qt5_bin = r'C:\Users\Bhavesh\AppData\Local\Programs\Python\Python311\Lib\site-packages\PyQt5\Qt5\bin'
if os.path.exists(qt5_bin):
    # Add all DLLs from bin to the bundle
    binaries += [(os.path.join(qt5_bin, '*.dll'), 'PyQt5/Qt5/bin')]


a = Analysis(
    ['backend\\main.py'],
    pathex=['backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Padharia',
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
    icon='d:\\Freelance\\expenses_tracker\\static\\rupee.ico',
)
