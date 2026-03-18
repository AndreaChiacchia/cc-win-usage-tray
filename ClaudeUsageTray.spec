# -*- mode: python ; coding: utf-8 -*-


import os
import winpty

winpty_dir = os.path.dirname(winpty.__file__)
winpty_binaries = [
    (os.path.join(winpty_dir, 'winpty.dll'), 'winpty'),
    (os.path.join(winpty_dir, 'winpty-agent.exe'), 'winpty'),
    (os.path.join(winpty_dir, 'conpty.dll'), 'winpty'),
    (os.path.join(winpty_dir, 'OpenConsole.exe'), 'winpty'),
]

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=winpty_binaries,
    datas=[('src/claude_icon.png', '.')],
    hiddenimports=['winotify'],
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
    name='ClaudeUsageTray',
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
    icon='NONE',
)
