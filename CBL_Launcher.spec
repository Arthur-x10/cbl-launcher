# -*- mode: python ; coding: utf-8 -*-
"""CBL Cube Launcher 打包配置。

默认产出 onedir（目录版，启动快，不用把 PyQt6-WebEngine 解压到 %TEMP%）：

    pyinstaller CBL_Launcher.spec
    -> dist/CBL_Launcher/CBL_Launcher.exe
    -> dist/CBL_Launcher/_internal/...

需要单文件时切回 onefile：

    set CBL_ONEFILE=1
    pyinstaller CBL_Launcher.spec
    -> dist/CBL_Launcher.exe

发布页直链只支持单文件，构建投放请用 tools/build_release.py（内部固定
CBL_ONEFILE=1）。
"""

import os

# 产物形态：默认 onedir；CBL_ONEFILE=1 / true / yes / on 时生成单文件。
ONEFILE = os.environ.get("CBL_ONEFILE", "0").strip().lower() in {"1", "true", "yes", "on"}

# spec 所在目录（PyInstaller 注入），保证从任意 cwd 调用都能找到资源。
PROJECT_ROOT = SPECPATH

# 品牌图标：resources/cbl.ico，已重生成 16/32/48/64/128/256 六尺寸。
ICON = [os.path.join(PROJECT_ROOT, "resources", "cbl.ico")]

# Windows 版本资源：name="CBL Cube Launcher"，version="0.6.0"。
# versioninfo 依赖 pywin32/pefile，非 Windows 上导入失败时跳过版本资源。
try:
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )
except ImportError:  # pragma: no cover - 仅非 Windows 打包会走到
    VERSION_INFO = None
else:
    _VERSION = (0, 9, 0, 0)
    VERSION_INFO = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_VERSION,
            prodvers=_VERSION,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "080404b0",
                        [
                            StringStruct("CompanyName", "CBL Cube Launcher"),
                            StringStruct("FileDescription", "CBL Cube Launcher"),
                            StringStruct("FileVersion", "0.9.0"),
                            StringStruct("InternalName", "CBL_Launcher"),
                            StringStruct("LegalCopyright", "CBL Cube Launcher contributors"),
                            StringStruct("OriginalFilename", "CBL_Launcher.exe"),
                            StringStruct("ProductName", "CBL Cube Launcher"),
                            StringStruct("ProductVersion", "0.9.0"),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [2052, 1200])]),
        ],
    )


a = Analysis(
    [os.path.join(PROJECT_ROOT, "main.py")],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtWebEngineCore',
        # provider 是通过 importlib.import_module 动态加载的，静态分析看不到，
        # 少一个就会在打包后表现为「库页空白 / 产品缺失」。
        'core.providers.java',
        'core.providers.java.version',
        'core.providers.java.launch',
        'core.providers.java.loaders',
        'core.providers.java.packs',
        'core.providers.java.runtime',
        'core.providers.java.deps',
        'core.providers.bedrock',
        'core.providers.server',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if ONEFILE:
    # onefile：EXE 直接收 binaries/datas，产物是 dist/CBL_Launcher.exe。
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='CBL_Launcher',
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
        icon=ICON,
        version=VERSION_INFO,
    )
else:
    # onedir：EXE 只带脚本，依赖交给 COLLECT 放进 dist/CBL_Launcher/_internal/。
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='CBL_Launcher',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON,
        version=VERSION_INFO,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='CBL_Launcher',
    )
