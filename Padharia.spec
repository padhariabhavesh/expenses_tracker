# ── Padharia.spec ─────────────────────────────────────────────────────────
# PyInstaller spec for Padharia Expense Tracker (with Auth + Admin Panel)
# ──────────────────────────────────────────────────────────────────────────
from PyInstaller.utils.hooks import collect_all
import os
import sys

# ── Data files bundled into the exe ──────────────────────────────────────
datas = [
    ('frontend/templates', 'templates'),   # login, register, dashboard, admin
    ('static',             'static'),      # style.css, script.js, rupee.png/.ico
]

binaries      = []
hiddenimports = []

# ── PyQt5 (full collection) ───────────────────────────────────────────────
tmp_ret = collect_all('PyQt5')
datas       += tmp_ret[0]
binaries    += tmp_ret[1]
hiddenimports += tmp_ret[2]

hiddenimports += [
    'PyQt5.QtWidgets',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtNetwork',
]

# ── Flask / Werkzeug hidden imports ──────────────────────────────────────
hiddenimports += [
    'flask',
    'flask_cors',
    'werkzeug',
    'werkzeug.security',
    'werkzeug.utils',
    'pymongo',
    'pymongo.uri_parser',
    'pymongo.ssl_support',
    'bson',
    'bson.objectid',
    'dns',
    'dns.resolver',
    'openpyxl',
    'dotenv',
]

# ── PyQt5 DLLs (auto-detect install location) ────────────────────────────
for _base in [
    os.path.expanduser(r'~\AppData\Local\Programs\Python\Python311\Lib\site-packages\PyQt5\Qt5\bin'),
    os.path.expanduser(r'~\AppData\Local\Programs\Python\Python312\Lib\site-packages\PyQt5\Qt5\bin'),
    os.path.expanduser(r'~\AppData\Local\Programs\Python\Python310\Lib\site-packages\PyQt5\Qt5\bin'),
    r'C:\Python311\Lib\site-packages\PyQt5\Qt5\bin',
    r'C:\Python312\Lib\site-packages\PyQt5\Qt5\bin',
]:
    if os.path.isdir(_base):
        binaries += [(os.path.join(_base, '*.dll'), 'PyQt5/Qt5/bin')]
        break

# ── Icon path (relative, so it works on any machine) ─────────────────────
_icon = os.path.join('static', 'rupee.ico')

# ─────────────────────────────────────────────────────────────────────────
a = Analysis(
    ['backend\\main.py'],
    pathex=['backend'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas', 'scipy'],
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
    console=False,                     # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)
