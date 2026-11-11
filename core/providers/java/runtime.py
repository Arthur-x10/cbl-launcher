"""Java 运行时 —— 检测/安装 Mojang 官方 JRE，并按游戏版本挑选兼容的 Java。

为什么需要「ASCII 运行时根」：
    Java 8（jre-legacy）在 Windows 上无法从含中文的路径启动。它的 native 库
    搜索把 java.home 按 ANSI 编码处理，zip.dll 会加载失败，报
        Error occurred during initialization of VM
        java.lang.UnsatisfiedLinkError: no zip in java.library.path
    实测同一份 jre-legacy：
        C:\\Users\\ethan\\Desktop\\minecraft启动器\\...\\bin\\java.exe -version -> rc=1（失败）
        复制到 %LOCALAPPDATA%\\CBL\\runtime 后                                  -> rc=0（1.8.0_51）
    Java 17/21 没有这个问题。所以当 .minecraft 路径含非 ASCII 时，运行时统一
    装到 %LOCALAPPDATA%\\CBL\\runtime；检测时两个位置都找，旧位置会自动迁移。
"""

import os
import shutil
import sys
import threading
from typing import Optional

import minecraft_launcher_lib

from core import paths

# 覆盖 MC 1.0 ~ 最新版的三个 Mojang 官方运行时
RUNTIMES: list[tuple[str, int, str, str]] = [
    ("jre-legacy", 8, "Java 8", "MC 1.0 ~ 1.16"),
    ("java-runtime-gamma", 17, "Java 17", "MC 1.17 ~ 1.20.4"),
    ("java-runtime-delta", 21, "Java 21", "MC 1.20.5+"),
]

_EXE_NAMES = ("javaw.exe", "java.exe") if os.name == "nt" else ("java",)


# ═══════════════════ 路径策略 ═══════════════════

def _is_ascii(path: str) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def needs_ascii_root(mc_dir: str) -> bool:
    """Java 8 在 Windows 上不能从含非 ASCII 的路径运行，这种目录需要 ASCII 根。"""
    return paths.IS_WINDOWS and not _is_ascii(os.path.abspath(mc_dir))


def ascii_runtime_root() -> str:
    """%LOCALAPPDATA%\\CBL（Windows 上通常是纯 ASCII）。"""
    return os.path.join(paths.local_appdata(), "CBL")


def runtime_roots(mc_dir: str) -> list[str]:
    """[首选根] 或 [首选根, 旧位置]。

    首选根：mc_dir 含非 ASCII 时用 %LOCALAPPDATA%\\CBL，否则就是 mc_dir 自己。
    旧位置用于兼容"运行时已经下在中文目录里"的存量，读取时仍然能找到。
    """
    mc_abs = os.path.abspath(mc_dir)
    if needs_ascii_root(mc_abs):
        primary = os.path.abspath(ascii_runtime_root())
        roots = [primary]
        if primary.lower() != mc_abs.lower():
            roots.append(mc_abs)
        return roots
    return [mc_abs]


def runtime_dir(mc_dir: str, runtime_name: str) -> str:
    return os.path.join(runtime_roots(mc_dir)[0], "runtime", runtime_name)


# ═══════════════════ 检测 ═══════════════════

def get_runtime_status(mc_dir: str) -> list[dict]:
    """检查每个运行时的安装状态。"""
    result = []
    for name, major, label, covers in RUNTIMES:
        java_path = find_runtime_exe(mc_dir, name)
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
    for name, _major, label, covers in RUNTIMES:
        if not find_runtime_exe(mc_dir, name):
            missing.append((name, label, covers))
    return missing


def find_runtime_exe(mc_dir: str, runtime_name: str) -> Optional[str]:
    """在候选根下的 runtime/{name}/ 里找 javaw.exe（找不到再退 java.exe）。"""
    for root in runtime_roots(mc_dir):
        base = os.path.join(root, "runtime", runtime_name)
        if not os.path.isdir(base):
            continue
        found = paths.find_java_binary(base)
        if found:
            return found
    return None


def is_runtime_installed(mc_dir: str, runtime_name: str) -> bool:
    return find_runtime_exe(mc_dir, runtime_name) is not None


# ═══════════════════ 迁移 ═══════════════════

def migrate_to_ascii(mc_dir: str, cb=None) -> int:
    """把旧位置（含中文的 .minecraft/runtime）里的运行时复制到 ASCII 根。

    返回迁移的运行时个数。复制 150 MB 在本地 SSD 上约 0.2 秒。
    """
    roots = runtime_roots(mc_dir)
    if len(roots) < 2:
        return 0
    primary, legacy = roots[0], roots[1]
    src_base = os.path.join(legacy, "runtime")
    dst_base = os.path.join(primary, "runtime")
    if not os.path.isdir(src_base):
        return 0
    moved = 0
    try:
        names = sorted(os.listdir(src_base))
    except OSError:
        return 0
    for name in names:
        src = os.path.join(src_base, name)
        dst = os.path.join(dst_base, name)
        if not os.path.isdir(src) or os.path.isdir(dst):
            continue
        if cb:
            try:
                cb(f"正在把 {name} 迁移到英文路径（Java 8 不支持中文路径）…")
            except Exception:
                pass
        try:
            os.makedirs(dst_base, exist_ok=True)
            shutil.copytree(src, dst)
            moved += 1
        except OSError as e:
            print(f"[runtime] 迁移 {name} 失败: {e}", file=sys.stderr)
    return moved


# ═══════════════════ 安装 ═══════════════════

_redirect_installed = False
_redirect_lock = threading.Lock()


def ensure_install_redirect() -> bool:
    """让库把 JRE 装到 ASCII 根。

    库内部固定用 minecraft_directory/runtime/，而 install_minecraft_version
    会顺手把 JRE 装到 .minecraft 下 —— 那正好是含中文的路径。
    这里把库的两个 install_jvm_runtime 名字换成"先换成 ASCII 根"的包装。
    """
    global _redirect_installed
    if not paths.IS_WINDOWS:
        return False
    with _redirect_lock:
        if _redirect_installed:
            return True
        try:
            import minecraft_launcher_lib.install as mll_install
            import minecraft_launcher_lib.runtime as mll_runtime
        except Exception:
            return False
        orig = getattr(mll_runtime, "install_jvm_runtime", None)
        if orig is None or getattr(orig, "_cbl_ascii_root", False):
            _redirect_installed = True
            return True

        def wrapper(runtime_name, minecraft_directory, callback=None):
            target = runtime_roots(minecraft_directory)[0]
            return orig(runtime_name, target, callback=callback)

        wrapper._cbl_ascii_root = True  # type: ignore[attr-defined]
        mll_runtime.install_jvm_runtime = wrapper
        if hasattr(mll_install, "install_jvm_runtime"):
            mll_install.install_jvm_runtime = wrapper
        _redirect_installed = True
        return True


def install_runtime(mc_dir: str, runtime_name: str, cb: Optional[dict] = None):
    """安装指定的 Mojang 运行时。cb 语义同 minecraft-launcher-lib。"""
    if runtime_name not in {name for name, _m, _l, _c in RUNTIMES}:
        raise ValueError(f"未知的 Java 运行时: {runtime_name!r}")
    if cb and "setStatus" in cb:
        cb["setStatus"](f"正在下载 {runtime_label(runtime_name)}…")
    ensure_install_redirect()
    minecraft_launcher_lib.runtime.install_jvm_runtime(runtime_name, mc_dir, callback=cb)


def install_all_missing(mc_dir: str, cb: Optional[dict] = None):
    """安装所有缺失的运行时；cb["setStatus"] 显示当前进度。

    进度条由库按单个运行时的文件数推进，所以这里只用状态文字标出第几个，
    不去覆盖 setMax，避免 3 个运行时的进度条来回跳。
    """
    missing = get_missing_runtimes(mc_dir)
    if not missing:
        return
    total = len(missing)
    for i, (name, label, covers) in enumerate(missing):
        if cb and "setStatus" in cb:
            cb["setStatus"](f"正在下载 {label} ({i + 1}/{total})… 用于 {covers}")
        install_runtime(mc_dir, name, cb)
    if cb and "setStatus" in cb:
        cb["setStatus"](f"Java 环境准备完成（共 {total} 个运行时）")


# ═══════════════════ 挑选 ═══════════════════

def runtime_for_required(required_major: int) -> str:
    """按版本要求给出「应该有」的运行时名（用于提示用户下载哪一个）。"""
    if required_major <= 8:
        return "jre-legacy"
    if required_major <= 17:
        return "java-runtime-gamma"
    return "java-runtime-delta"


def runtime_label(runtime_name: str) -> str:
    for name, _major, label, _covers in RUNTIMES:
        if name == runtime_name:
            return label
    return runtime_name


def find_java_for_version(mc_dir: str, required_major: int) -> Optional[str]:
    """根据版本要求找到最合适的已安装运行时。

    required <= 8（1.16 及更老）只认 Java 8。以前 required=8 时 Java 17/21 也
    算合格，一旦 jre-legacy 缺失就会把 17 塞给 1.7.10，崩在 ASM/Mixin 初始化里，
    错误信息离原因很远。
    """
    if required_major <= 8:
        for name, major, _label, _covers in RUNTIMES:
            if major != 8:
                continue
            path = find_runtime_exe(mc_dir, name)
            if path:
                return path
        return None

    best = None
    best_major = None
    for name, major, _label, _covers in RUNTIMES:
        path = find_runtime_exe(mc_dir, name)
        if not path:
            continue
        if major >= required_major and (best_major is None or major < best_major):
            best = path
            best_major = major
    return best
