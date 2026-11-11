"""跨平台系统集成：打开文件夹 / URI / 找 Java 可执行文件。"""

import os
import subprocess
import sys
from typing import Optional

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")


def open_folder(path: str) -> str:
    """在系统文件管理器中打开目录（不存在则创建）。"""
    os.makedirs(path, exist_ok=True)
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
    return path


def open_file(path: str) -> str:
    if IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])
    return path


def open_uri(uri: str):
    """打开 URL / 自定义协议（如 minecraft://）。"""
    if IS_WINDOWS:
        os.startfile(uri)  # type: ignore[attr-defined]
    elif IS_MAC:
        subprocess.Popen(["open", uri])
    else:
        subprocess.Popen(["xdg-open", uri])


def no_window_flags() -> int:
    """子进程不弹控制台窗口（仅 Windows 有效）。"""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def java_exec_names() -> tuple[str, ...]:
    return ("javaw.exe", "java.exe") if IS_WINDOWS else ("java",)


def find_java_binary(root: str) -> Optional[str]:
    """在目录树里找 Java 可执行文件。"""
    if not os.path.isdir(root):
        return None
    names = java_exec_names()
    for dirpath, _dirs, files in os.walk(root):
        for name in names:
            if name in files:
                return os.path.join(dirpath, name)
    return None


def local_appdata() -> str:
    return os.environ.get("LOCALAPPDATA", "") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")


def appx_packages_dir() -> str:
    """Windows AppX 包数据目录；非 Windows 返回空串。"""
    if not IS_WINDOWS:
        return ""
    return os.path.join(local_appdata(), "Packages")


def home() -> str:
    return os.path.expanduser("~")


def ascii_mirror(real_dir: str) -> str:
    """给含非 ASCII 的目录建一个 ASCII 目录联接（junction），返回可用于 JVM 的路径。

    为什么需要：Java 8 从中文路径既加载不了 native 库（lwjgl 报 "Can't find
    dependent libraries"），也打不开 classpath 里的 jar（同一个 1.7.10.jar，
    中文路径报「找不到主类」，换成 ASCII 路径就能正常加载类）。
    目录联接零拷贝、不需要管理员权限，Java 看到的就是纯 ASCII 路径。
    失败时原样返回，由调用方决定是否降级。
    """
    real = os.path.abspath(real_dir)
    if IS_WINDOWS is False or real.isascii():
        return real
    link = os.path.join(local_appdata(), "CBL", "mc")
    if os.path.isdir(link):
        try:
            if os.path.samefile(link, real):
                return link
        except OSError:
            pass
        try:
            os.rmdir(link)          # 删 junction 不会删目标目录
        except OSError:
            return real
    try:
        os.makedirs(os.path.dirname(link), exist_ok=True)
    except OSError:
        return real
    try:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", link, real],
                           capture_output=True, text=True, timeout=30)
    except Exception as e:
        print(f"[paths] 建立 ASCII 联接失败: {e}", file=sys.stderr)
        return real
    if r.returncode != 0 or not os.path.isdir(link):
        msg = ((r.stdout or "") + (r.stderr or "")).strip()
        print(f"[paths] 建立 ASCII 联接失败: {msg}", file=sys.stderr)
        return real
    return link


def user_data_dir(app_name: str = "CBL") -> str:
    """跨平台的用户级数据目录（非便携模式下备用）。"""
    if IS_WINDOWS:
        return os.path.join(os.environ.get("APPDATA", home()), app_name)
    if IS_MAC:
        return os.path.join(home(), "Library", "Application Support", app_name)
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.join(home(), ".config")), app_name)
