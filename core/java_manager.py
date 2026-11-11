"""Java 运行时自动管理 — 下载 Mojang 官方运行时，用户零配置。"""

import os
from typing import Optional

import minecraft_launcher_lib

# 需要的运行时列表：覆盖所有 MC 版本
RUNTIMES = [
    ("jre-legacy",          8,  "Java 8",  "MC 1.0 ~ 1.16"),
    ("java-runtime-gamma",  17, "Java 17", "MC 1.17 ~ 1.20.4"),
    ("java-runtime-delta",  21, "Java 21", "MC 1.20.5+"),
]


def get_runtime_status(mc_dir: str) -> list[dict]:
    """检查每个运行时的安装状态。"""
    result = []
    for name, major, label, covers in RUNTIMES:
        java_path = _find_runtime_exe(mc_dir, name)
        result.append({
            "name": name,
            "major": major,
            "label": label,
            "covers": covers,
            "installed": java_path is not None,
            "path": java_path or "",
        })
    return result


def get_missing_runtimes(mc_dir: str) -> list[tuple[str, str, str]]:
    """返回未安装的运行时 [(name, label, covers), ...]。"""
    missing = []
    for name, major, label, covers in RUNTIMES:
        if not _find_runtime_exe(mc_dir, name):
            missing.append((name, label, covers))
    return missing


def install_runtime(mc_dir: str, runtime_name: str,
                    callback: Optional[dict] = None):
    """安装指定的 Mojang 运行时。"""
    minecraft_launcher_lib.runtime.install_jvm_runtime(
        runtime_name, mc_dir, callback=callback
    )


def install_all_missing(mc_dir: str, callback: Optional[dict] = None):
    """安装所有缺失的运行时。callback.setStatus 会显示当前进度。"""
    missing = get_missing_runtimes(mc_dir)
    if not missing:
        return

    total = len(missing)
    for i, (name, label, covers) in enumerate(missing):
        if callback and "setStatus" in callback:
            callback["setStatus"](f"正在下载 {label} ({i+1}/{total})… 用于 {covers}")
        install_runtime(mc_dir, name, callback)

    if callback and "setStatus" in callback:
        callback["setStatus"](f"Java 环境准备完成（共 {total} 个运行时）")


def find_java_for_version(mc_dir: str, required_major: int) -> Optional[str]:
    """根据版本要求找到最合适的已安装运行时。

    required <= 8（1.16 及更老）只认 Java 8。以前 required=8 时 Java 17/21 也
    算合格，一旦 jre-legacy 缺失就会把 17 塞给 1.7.10，崩在 ASM/Mixin 初始化里，
    错误信息离原因很远。
    """
    if required_major <= 8:
        for name, major, label, covers in RUNTIMES:
            if major == 8:
                path = _find_runtime_exe(mc_dir, name)
                if path:
                    return path
        return None

    best = None
    best_major = None
    for name, major, label, covers in RUNTIMES:
        path = _find_runtime_exe(mc_dir, name)
        if not path:
            continue
        if major >= required_major and (best_major is None or major < best_major):
            best = path
            best_major = major

    return best


def _find_runtime_exe(mc_dir: str, runtime_name: str) -> Optional[str]:
    """在 .minecraft/runtime/{name}/ 下找 javaw.exe。"""
    base = os.path.join(mc_dir, "runtime", runtime_name)
    if not os.path.isdir(base):
        return None
    for root, dirs, files in os.walk(base):
        if "javaw.exe" in files:
            return os.path.join(root, "javaw.exe")
        if "java.exe" in files:
            return os.path.join(root, "java.exe")
    return None
