# -*- mode: python ; coding: utf-8 -*-


import os
import sys

# Keep unrelated DLLs on the host PATH out of the packaged Qt runtime.
os.environ['PATH'] = os.pathsep.join([
    sys.prefix,
    os.path.join(sys.prefix, 'Scripts'),
    sys.base_prefix,
    os.path.join(os.environ['SystemRoot'], 'System32'),
    os.environ['SystemRoot'],
])

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['schedule', 'pyzipper'],
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
    name='AutoBackup_v1.2.0',
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
