CBL Cube Launcher — 发行包投放目录
=====================================

这个目录就是发布页下载直链的目标：website/index.html 里
"下载 CBL_Launcher.exe" 按钮指向 ./downloads/CBL_Launcher.exe。

所以这里的文件名必须完全一致：

    CBL_Launcher.exe

从构建产物复制的命令（在项目根目录执行，cmd）：

    copy dist\CBL_Launcher.exe website\downloads\CBL_Launcher.exe

PowerShell 写法：

    Copy-Item dist\CBL_Launcher.exe website\downloads\CBL_Launcher.exe -Force

一条命令完成构建 + 投放（推荐）：

    python tools/build_release.py

只投放 dist 里已有的产物、不重新打包：

    python tools/build_release.py --no-build

目录说明
--------
* 当前可靠产物是 PyInstaller 构建的 Windows x64 便携包。onefile 模式产出单个
  dist\CBL_Launcher.exe（首启会把 PyQt6-WebEngine 解压到 %TEMP%，较慢）；
  onedir 模式产出 dist\CBL_Launcher\CBL_Launcher.exe 加 _internal\ 目录，
  启动更快，但必须整目录一起分发。
* 本页直链只对应单文件 CBL_Launcher.exe。onedir 版本请把整个目录打成 zip 另发。
* 目录为空时，发布页按钮点击后会提示缺少文件，并指回本说明。
* 不要把 exe 提交进公共仓库；发布包里通常只保留本说明。

构建细节见 CBL_Launcher.spec 与 tools/build_release.py。
