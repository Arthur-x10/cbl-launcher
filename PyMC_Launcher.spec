# -*- mode: python ; coding: utf-8 -*-
# 历史产物配置：2026-10-27 用它构建出 dist/PyMC_Launcher.exe（改名前的品牌）。
# 当前构建请用 CBL_Launcher.spec（onedir，默认 / CBL_ONEFILE=1 切单文件）。
# 保留本文件是为了能复现那个旧产物，不参与日常构建。


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebEngineCore'],
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
    name='PyMC_Launcher',
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
