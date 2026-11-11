#!/usr/bin/env python3
"""CBL Cube Launcher 发布链：构建 onefile 便携包并投放到 website/downloads/。

一条命令完成：备份旧产物 -> 调用 PyInstaller -> 复制到发布页直链目标 ->
打印产物路径、大小与 SHA-256。

只管理本项目两个目标：
    dist/CBL_Launcher.exe
    website/downloads/CBL_Launcher.exe
已存在的目标先改名为 *.bak-<时间戳>，不删除其他文件或目录。

示例：
    python tools/build_release.py
    python tools/build_release.py --no-build
    python tools/build_release.py --dist-dir build/dist

说明：发布页直链只支持单文件，所以这里固定用 CBL_ONEFILE=1 构建 onefile。
spec 默认的 onedir 目录版（dist/CBL_Launcher/）需要连 _internal 一起分发，
不适合直接放上发布页。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "CBL_Launcher.spec"
DEFAULT_DIST_DIR = ROOT / "dist"
DEFAULT_DOWNLOADS_DIR = ROOT / "website" / "downloads"
EXE_NAME = "CBL_Launcher.exe"
PAYLOAD_DIR_NAME = "CBL_Launcher"


def format_size(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB ({num_bytes} B)"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backup(path: Path) -> Path | None:
    """把已存在的目标改名为 *.bak-<时间戳>；不存在则返回 None。"""
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name(f"{path.name}.bak-{stamp}")
    index = 1
    while target.exists():
        target = path.with_name(f"{path.name}.bak-{stamp}-{index}")
        index += 1
    path.rename(target)
    return target


def resolve_dir(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (ROOT / path)


def pyinstaller_version() -> str | None:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or result.stderr).strip()


def find_artifact(dist_dir: Path) -> tuple[Path | None, str]:
    """返回 (可投放的单文件产物, 说明)。只有 onefile 的 dist/CBL_Launcher.exe 可投放。"""
    onefile = dist_dir / EXE_NAME
    if onefile.is_file():
        return onefile, ""
    onedir_exe = dist_dir / PAYLOAD_DIR_NAME / EXE_NAME
    if onedir_exe.is_file():
        return None, (
            f"dist 里只有 onedir 目录版：{onedir_exe}\n"
            "  目录版必须连 _internal/ 一起分发，不能作为发布页的单文件直链。\n"
            "  请运行 python tools/build_release.py（不带 --no-build）构建 onefile。"
        )
    return None, (
        f"没有找到构建产物。期望：{onefile}\n"
        "  请先运行 python tools/build_release.py（不带 --no-build）完成构建。"
    )


def build(dist_dir: Path) -> int:
    work_dir = ROOT / "build" / "build_release"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        str(SPEC_PATH),
    ]
    env = os.environ.copy()
    env["CBL_ONEFILE"] = "1"
    print("构建模式: onefile（环境变量 CBL_ONEFILE=1）")
    print(f"工作目录: {work_dir}")
    print("执行命令:")
    print("  " + subprocess.list2cmdline(command))
    print()
    started = time.perf_counter()
    result = subprocess.run(command, cwd=str(ROOT), env=env)
    elapsed = time.perf_counter() - started
    print()
    print(f"PyInstaller 退出码: {result.returncode}，耗时: {elapsed:.1f}s")
    if result.returncode != 0:
        print(f"错误：PyInstaller 构建失败（退出码 {result.returncode}）。", file=sys.stderr)
        return result.returncode if result.returncode > 0 else 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_release.py",
        description=(
            "构建 CBL Cube Launcher 的 Windows x64 onefile 便携包，并投放到 "
            "website/downloads/CBL_Launcher.exe。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python tools/build_release.py              构建并投放\n"
            "  python tools/build_release.py --no-build   只投放 dist 里已有的 CBL_Launcher.exe\n"
            "  python tools/build_release.py --dist-dir build/dist\n"
            "\n"
            "已存在的 dist/CBL_Launcher.exe 与 website/downloads/CBL_Launcher.exe\n"
            "会先改名为 *.bak-<时间戳>，不会删除。"
        ),
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="只投放 dist 里已有的 CBL_Launcher.exe，不调用 PyInstaller",
    )
    parser.add_argument(
        "--dist-dir",
        default=str(DEFAULT_DIST_DIR),
        metavar="PATH",
        help=f"构建产物目录（默认 {DEFAULT_DIST_DIR}）",
    )
    parser.add_argument(
        "--downloads-dir",
        default=str(DEFAULT_DOWNLOADS_DIR),
        metavar="PATH",
        help=f"投放目录（默认 {DEFAULT_DOWNLOADS_DIR}）",
    )
    args = parser.parse_args(argv)

    dist_dir = resolve_dir(args.dist_dir)
    downloads_dir = resolve_dir(args.downloads_dir)

    print("== CBL Cube Launcher 发布链 ==")
    print(f"项目根目录: {ROOT}")
    print(f"spec: {SPEC_PATH}")
    print(f"dist: {dist_dir}")
    print(f"投放目录: {downloads_dir}")
    print()

    if not SPEC_PATH.is_file():
        print(f"错误：找不到 spec 文件 {SPEC_PATH}", file=sys.stderr)
        return 2

    if args.no_build:
        print("模式: --no-build（跳过构建，直接投放现有产物）")
    else:
        version = pyinstaller_version()
        if not version:
            print(
                "错误：当前 Python 环境无法运行 PyInstaller"
                f"（{sys.executable} -m PyInstaller --version 失败）。\n"
                "  请先执行：python -m pip install pyinstaller",
                file=sys.stderr,
            )
            return 2
        print(f"PyInstaller 版本: {version}")

        dist_dir.mkdir(parents=True, exist_ok=True)
        saved_exe = backup(dist_dir / EXE_NAME)
        if saved_exe:
            print(f"已备份旧产物: {saved_exe}")
        saved_dir = backup(dist_dir / PAYLOAD_DIR_NAME)
        if saved_dir:
            print(f"已备份旧目录产物: {saved_dir}")
        print()
        code = build(dist_dir)
        if code != 0:
            return code

    artifact, detail = find_artifact(dist_dir)
    if artifact is None:
        print(f"错误：{detail}", file=sys.stderr)
        return 2

    size = artifact.stat().st_size
    print(f"产物: {artifact}")
    print(f"大小: {format_size(size)}")

    downloads_dir.mkdir(parents=True, exist_ok=True)
    target = downloads_dir / EXE_NAME
    saved_target = backup(target)
    if saved_target:
        print(f"已备份旧投放文件: {saved_target}")
    shutil.copy2(artifact, target)

    print(f"投放: {target}")
    print(f"投放大小: {format_size(target.stat().st_size)}")
    print(f"SHA-256: {sha256_of(target)}")
    print()
    print(f"完成。发布页下载按钮指向: {target}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:
        print(f"错误：文件操作失败：{exc}", file=sys.stderr)
        raise SystemExit(1)
