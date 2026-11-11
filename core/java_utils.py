"""Java 检测与管理模块"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional


def find_java_in_path() -> Optional[str]:
    """从 PATH 环境变量中查找 java"""
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True, text=True, timeout=10
        )
        # java -version 输出到 stderr
        output = result.stderr or result.stdout
        if "version" in output.lower():
            # 尝试获取 java.exe 的完整路径
            where_result = subprocess.run(
                ["where", "java"], capture_output=True, text=True, timeout=5
            )
            if where_result.returncode == 0:
                first_line = where_result.stdout.strip().split("\n")[0].strip()
                if os.path.isfile(first_line):
                    return first_line
            return "java"  # 在 PATH 中但无法确定完整路径
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def find_java_in_common_locations() -> list[dict]:
    """扫描常见的 Java 安装位置，返回 [{path, version}]"""
    found = []
    search_dirs = []

    # Windows 常见 Java 安装路径
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local_appdata = os.environ.get("LOCALAPPDATA", "")

    for base in [program_files, program_files_x86]:
        for sub in ["Java", "Eclipse Adoptium", "AdoptOpenJDK", "Zulu", "Microsoft",
                     "BellSoft", "Amazon Corretto", "Semeru"]:
            d = os.path.join(base, sub)
            if os.path.isdir(d):
                search_dirs.append(d)

    # Minecraft 自带 Runtime
    if local_appdata:
        runtime_dir = os.path.join(local_appdata, "Packages",
                                    "Microsoft.4297127D64EC6_8wekyb3d8bbwe",
                                    "LocalCache", "Local", "runtime")
        if os.path.isdir(runtime_dir):
            search_dirs.append(runtime_dir)

    # .minecraft/runtime (Mojang 官方 Runtime) — 系统默认位置
    mc_runtime = os.path.join(os.environ.get("APPDATA", ""), ".minecraft", "runtime")
    if os.path.isdir(mc_runtime):
        search_dirs.append(mc_runtime)

    # 启动器自身目录下的 .minecraft/runtime（便携模式）
    try:
        from core.config import LAUNCHER_DIR
        portable_rt = os.path.join(str(LAUNCHER_DIR), ".minecraft", "runtime")
        if os.path.isdir(portable_rt) and portable_rt != mc_runtime:
            search_dirs.append(portable_rt)
    except ImportError:
        pass

    for search_dir in search_dirs:
        for root, dirs, files in os.walk(search_dir):
            if "javaw.exe" in files:
                javaw_path = os.path.join(root, "javaw.exe")
                version = get_java_version(javaw_path)
                found.append({"path": javaw_path, "version": version or "未知版本"})
            elif "java.exe" in files and "javaw.exe" not in files:
                java_path = os.path.join(root, "java.exe")
                version = get_java_version(java_path)
                found.append({"path": java_path, "version": version or "未知版本"})

    # 去重
    seen = set()
    unique = []
    for item in found:
        norm = os.path.normpath(item["path"]).lower()
        if norm not in seen:
            seen.add(norm)
            unique.append(item)
    return unique


def get_java_version(java_path: str) -> Optional[str]:
    """获取指定 Java 的版本号"""
    try:
        result = subprocess.run(
            [java_path, "-version"],
            capture_output=True, text=True, timeout=10
        )
        output = result.stderr or result.stdout
        match = re.search(r'version\s+"([\d._]+)"', output)
        if match:
            return match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_major_java_version(java_path: str) -> Optional[int]:
    """获取 Java 主版本号 (8, 11, 17, 21...)"""
    ver = get_java_version(java_path)
    if not ver:
        return None
    parts = ver.split(".")
    if parts[0] == "1":
        return int(parts[1]) if len(parts) > 1 else None
    return int(parts[0])


def auto_detect_java() -> Optional[str]:
    """自动检测最合适的 Java，优先返回 javaw.exe"""
    # 优先从常见位置查找
    javas = find_java_in_common_locations()
    if javas:
        # 优先 Java 17+（现代 MC 版本需要）
        for j in javas:
            major = get_major_java_version(j["path"])
            if major and major >= 17:
                return j["path"]
        # 否则返回第一个
        return javas[0]["path"]

    # 最后尝试 PATH
    return find_java_in_path()


def validate_java(java_path: str) -> bool:
    """验证 Java 路径是否有效"""
    if not java_path:
        return False
    if java_path == "java":
        return find_java_in_path() is not None
    return os.path.isfile(java_path) and get_java_version(java_path) is not None
