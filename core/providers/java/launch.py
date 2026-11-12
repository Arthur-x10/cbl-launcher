"""Java 版启动 —— 解析 Java 需求、拼 JVM 参数、注入 authlib-injector 并创建游戏进程。"""

import json
import os
import re
import shutil
import subprocess
import sys
import uuid as _uuid
from datetime import datetime
from typing import Optional

import minecraft_launcher_lib

from core import java_utils, log_manager, paths, performance, skin_local, yggdrasil
from core.providers.base import Instance, LaunchError, LaunchHandle
from core.providers.java import runtime

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_MODLOADER_KEYS = ("forge", "fabric", "quilt", "neoforge")
_MAX_INHERIT_DEPTH = 8


# ═══════════════════ Java 需求与挑选 ═══════════════════

def _java_compatible(required_major: int, major: Optional[int]) -> bool:
    """判断某个 Java 主版本能否跑这个 MC 版本。

    - 1.16 及更老（required <= 8）：只接受 Java 8~17。Java 18+ 会因反射/类版本
      直接崩，比"找不到 Java"更难排查。
    - 1.17+：主版本必须 >= 要求值。
    """
    if not major:
        return False
    if required_major <= 8:
        return 8 <= major <= 17
    return major >= required_major


def read_version_json(mc_dir: str, version_id: str) -> dict:
    """读取版本 JSON。文件缺失/损坏时抛 LaunchError（消息可直接给用户看）。"""
    path = os.path.join(mc_dir, "versions", version_id, f"{version_id}.json")
    if not os.path.isfile(path):
        raise LaunchError(f"版本文件不存在: {path}\n请先安装此版本。")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except Exception as e:
        raise LaunchError(f"版本文件损坏: {path}\n{e}") from e
    if not isinstance(data, dict):
        raise LaunchError(f"版本文件格式不对: {path}")
    return data


def required_java(mc_dir: str, version_id: str, _depth: int = 0) -> int:
    """该版本要求的 Java 主版本号；加载器版本沿 inheritsFrom 回溯到原版。"""
    if _depth > _MAX_INHERIT_DEPTH:
        return 8
    try:
        data = read_version_json(mc_dir, version_id)
    except LaunchError:
        return 8
    java_version = data.get("javaVersion") or {}
    major = java_version.get("majorVersion") if isinstance(java_version, dict) else None
    if isinstance(major, int) and major > 0:
        return major
    parent = data.get("inheritsFrom") or ""
    if parent:
        return required_java(mc_dir, parent, _depth + 1)
    return 8


def _major_from_version_text(text: str) -> Optional[int]:
    """从 java -version 的版本串（1.8.0_51 / 17.0.1）解析主版本号。"""
    match = re.match(r"v?(\d+)(?:\.(\d+))?", str(text or "").strip())
    if not match:
        return None
    first = int(match.group(1))
    if first == 1 and match.group(2) is not None:
        return int(match.group(2))
    return first


def _java_major(java_path: str) -> Optional[int]:
    """取 Java 主版本号；javaw.exe 问不出结果时退到同目录的 java.exe。

    某些 javaw/被裁剪的运行时会往不存在的控制台写版本信息，
    java_utils.get_major_java_version 于是拿到 None。这里再做一次兜底，
    让「实例里显式选的 Java」不会因为问不出版本就被判成不可用。
    """
    major = java_utils.get_major_java_version(java_path)
    if major:
        return major
    if os.path.basename(java_path).lower() == "javaw.exe":
        sibling = os.path.join(os.path.dirname(java_path), "java.exe")
        if os.path.isfile(sibling):
            return java_utils.get_major_java_version(sibling)
    return None


def _ensure_java_runnable(java_path: str, required_major: int) -> str:
    """Java 8 无法从含非 ASCII 的路径启动，提前给出可执行的提示。

    实测同一份 jre-legacy：放在含中文的目录里 `java -version` 直接
    "no zip in java.library.path"；复制到 %LOCALAPPDATA%\\CBL\\runtime 就正常。
    Java 17/21 没这个限制，所以只拦 required<=8 的情况。
    """
    if not paths.IS_WINDOWS or required_major > 8:
        return java_path
    try:
        os.path.abspath(java_path).encode("ascii")
        return java_path
    except UnicodeEncodeError:
        raise LaunchError(
            "Java 8（jre-legacy）无法在含中文的路径下运行。\n\n"
            f"当前 Java：{java_path}\n\n"
            "启动器会把 Mojang 运行时迁到英文路径（%LOCALAPPDATA%\\CBL\\runtime），"
            "重启启动器后自动完成；或在「设置 → Java 路径」里指定一个英文目录下的 Java 8。"
        )


def find_best_java(config, mc_dir: str, required_major: int) -> str:
    """按版本要求找到最合适的 Java（并对 Java 8 做路径可用性检查）。"""
    return _ensure_java_runnable(
        _find_best_java_impl(config, mc_dir, required_major), required_major)


def _find_best_java_impl(config, mc_dir: str, required_major: int) -> str:
    """按版本要求找到最合适的 Java。

    优先级:
    1. runtime.py 管理的 Mojang 运行时（最可靠）
    2. 用户手动配置的 Java（如果兼容）
    3. 系统扫描到的兼容 Java
    4. 抛 LaunchError
    """
    col = runtime.find_java_for_version(mc_dir, required_major)
    if col:
        return col

    user_java = config.get_java_path() if config is not None else ""
    if user_java and java_utils.validate_java(user_java):
        if _java_compatible(required_major, _java_major(user_java)):
            return user_java

    # 系统扫描：先把版本号问出来再排序，避免同一个 exe 被反复执行
    scanned = []
    for item in java_utils.find_java_in_common_locations():
        # 扫描结果里已经带了版本串，优先用它解析，避免每个 exe 再执行一遍
        major = _major_from_version_text(item.get("version")) or _java_major(item["path"])
        if major:
            scanned.append((item["path"], major))
    for path, major in sorted(scanned, key=lambda pair: pair[1]):
        # 必须过兼容性判断，绝不把 Java 21/26 塞给 1.7.10
        if _java_compatible(required_major, major):
            return path

    rt_name = runtime.runtime_for_required(required_major)
    raise LaunchError(
        f"未找到兼容的 Java。\n"
        f"此版本需要 Java {required_major}+（推荐 {runtime.runtime_label(rt_name)}）。\n"
        f"请先在首页等待 Java 环境自动下载完成，或在设置里手动指定 Java。"
    )


def resolve_java(config, mc_dir: str, version_id: str) -> str:
    """provider.resolve_java 的实现；没有可用 Java 时抛 LaunchError。"""
    return find_best_java(config, mc_dir, required_java(mc_dir, version_id))


# ═══════════════════ 参数拼装 ═══════════════════

def rewrite_root(command: list, old_root: str, new_root: str) -> list:
    """把命令里所有 old_root 前缀替换成 new_root。

    中文安装目录下 Java 8 打不开 classpath 里的 jar（实测同一个 1.7.10.jar：
    中文路径「找不到主类」，ASCII 路径正常加载），所以先生成 ASCII 目录联接，
    再把 classpath / library.path / gameDir 全部换成联接路径。
    """
    if not old_root or not new_root or os.path.normcase(old_root) == os.path.normcase(new_root):
        return command
    out = []
    for arg in command:
        if isinstance(arg, str) and old_root in arg:
            out.append(arg.replace(old_root, new_root))
        else:
            out.append(arg)
    return out


def prepare_ascii_natives(command: list, version_id: str) -> list:
    """Java 8 无法从含中文的目录加载 native 库，复制到英文目录并改写命令。

    实测同一个 lwjgl64.dll：
        中文目录  -> UnsatisfiedLinkError ... Can't find dependent libraries（JVM 里路径还是乱码）
        ASCII 目录 -> 加载成功
    Java 17/21 不需要这一步，但为了行为一致也一并处理（代价只是一次小拷贝）。
    """
    if not paths.IS_WINDOWS:
        return command
    for i, arg in enumerate(command):
        if not isinstance(arg, str) or not arg.startswith("-Djava.library.path="):
            continue
        raw = arg.split("=", 1)[1]
        if not raw or raw.isascii():
            return command
        parts = [p for p in raw.split(os.pathsep) if p]
        if not parts:
            return command
        src = parts[0]
        if not os.path.isdir(src):
            return command
        target = os.path.join(paths.local_appdata(), "CBL", "natives", version_id)
        try:
            os.makedirs(target, exist_ok=True)
            for name in os.listdir(src):
                s = os.path.join(src, name)
                d = os.path.join(target, name)
                if os.path.isfile(s) and (not os.path.isfile(d)
                                          or os.path.getsize(d) != os.path.getsize(s)):
                    shutil.copy2(s, d)
        except OSError as e:
            print(f"[launch] 复制 native 库到英文路径失败（游戏可能起不来）: {e}", file=sys.stderr)
            return command
        rest = parts[1:]
        command[i] = "-Djava.library.path=" + os.pathsep.join([target] + rest)
        print(f"[launch] native 库改用英文路径: {target}", file=sys.stderr)
        return command
    return command


def split_jvm_args(raw: str) -> list[str]:
    """按空格切分 JVM 参数，但尊重引号。

    用户会直接粘贴形如 -Dfoo="C:/Program Files/x" 的参数，
    str.split() 会把它拆坏，这里做一次最小可用的引号感知解析。
    """
    if not raw:
        return []
    args: list[str] = []
    buf: list[str] = []
    quote = ""
    for ch in raw:
        if quote:
            if ch == quote:
                quote = ""
            else:
                buf.append(ch)
        elif ch in ("'", '"'):
            quote = ch
        elif ch.isspace():
            if buf:
                args.append("".join(buf))
                buf = []
        else:
            buf.append(ch)
    if buf:
        args.append("".join(buf))
    return args


def auth_fields(auth: Optional[dict], config=None) -> dict:
    """把 provider 收到的 auth dict 规范成启动所需字段。

    令牌只从 auth dict 取（不读 config 里存的 token）；用户名在 auth 缺失时
    才回落到 config，方便只有离线名的老界面继续工作。
    """
    auth = auth or {}
    username = str(auth.get("username") or auth.get("name") or "").strip()
    if not username and config is not None:
        username = str(config.get("username") or "").strip()
    if not username:
        username = "Player"

    token = str(auth.get("access_token") or auth.get("token") or "").strip()
    if not token:
        token = "0"      # 离线模式的占位令牌

    player_uuid = str(auth.get("uuid") or auth.get("id") or "").strip()
    if not player_uuid:
        # 离线身份必须稳定：由用户名派生，和 auth.offline_login 的算法一致
        player_uuid = str(_uuid.uuid3(_uuid.NAMESPACE_DNS, username))

    auth_type = str(auth.get("auth_type") or auth.get("type") or "").strip().lower()
    if not auth_type and config is not None:
        auth_type = str(config.get("auth_type") or "").strip().lower()

    api_root = str(auth.get("api_root") or auth.get("yggdrasil_api") or "").strip()
    if not api_root and auth_type == "yggdrasil" and config is not None:
        api_root = str(config.get("yggdrasil_api") or "").strip()

    return {
        "username": username,
        "uuid": player_uuid,
        "token": token,
        "auth_type": auth_type,
        "api_root": api_root,
    }


def _has_mod_loader(version_id: str) -> bool:
    low = (version_id or "").lower()
    return any(k in low for k in _MODLOADER_KEYS)


def _mod_profile(version_id: str, java_major: int, *mod_dirs):
    """把「版本 / 加载器 / mod 数 / Java」凑成调优输入。

    mod 数以前只看版本号里有没有 forge —— 那是"有没有加载器"，不是"有几个 mod"。
    原版 + 40 个 mod（靠 Sinytra 之类）和原版空目录会被算成同一档，堆差一倍。
    """
    from core.providers.java import combos
    detected = combos.detect_from_version_id(version_id)
    loader = ""
    for lid in ("neoforge", "forge", "quilt", "fabric", "liteloader"):
        if lid in detected or lid in (version_id or "").lower():
            loader = lid
            break
    mc_version = combos.mc_version_of(version_id)
    mod_count = performance.count_mod_jars(*[d for d in mod_dirs if d])
    return performance.build_profile(
        mc_version=mc_version, loader=loader,
        mod_count=mod_count, java_major=java_major)


def build_jvm_args(mc_dir: str, config, java_path: str, version_id: str,
                   instance: Optional[Instance] = None,
                   auth: Optional[dict] = None) -> list[str]:
    """内存 + GC + authlib-injector + 用户自定义参数。

    实例级 ram_min/ram_max/jvm_args 优先于全局 config。
    """
    inst_min = int(getattr(instance, "ram_min", 0) or 0)
    inst_max = int(getattr(instance, "ram_max", 0) or 0)

    auto = config is not None and config.get("auto_performance", True)
    if auto:
        # 自动模式优先：内存与 JVM 由「机器 + 版本 + 加载器 + mod 数」算出来，
        # 实例上的旧数值不再参与（那些字段是上一版 UI 留下的，用户已经看不到输入框）。
        # 问不出 Java 版本时按版本要求兜底：1.7.10 不该拿到 Java 11+ 才有的 GC 参数
        java_major = _java_major(java_path) or required_java(mc_dir, version_id) or 17
        game_dir = _game_dir(instance, mc_dir) if instance is not None else mc_dir
        profile = _mod_profile(version_id, java_major,
                               os.path.join(game_dir, "mods"),
                               os.path.join(mc_dir, "mods"))
        args, _notes = performance.build_args(profile)
    elif inst_max:
        ram_min = inst_min or max(512, inst_max // 4)
        args = [f"-Xms{ram_min}M", f"-Xmx{inst_max}M"]
    elif config is not None:
        args = [f"-Xms{config.get_ram_min()}M", f"-Xmx{config.get_ram_max()}M"]
    else:
        args = ["-Xms512M", "-Xmx2048M"]

    # Yggdrasil（LittleSkin 等）需要 -javaagent 注入 authlib-injector
    fields = auth_fields(auth, config)
    if fields["auth_type"] == "yggdrasil" and fields["api_root"]:
        try:
            if yggdrasil.is_injector_installed(mc_dir):
                args.append(yggdrasil.get_injector_jvm_arg(mc_dir, fields["api_root"]))
            else:
                print("[java.launch] 未安装 authlib-injector，LittleSkin 皮肤/皮肤签名将不可用",
                      file=sys.stderr)
        except Exception as e:
            print(f"[java.launch] authlib-injector 注入失败（不影响启动）: {e}", file=sys.stderr)

    custom = (getattr(instance, "jvm_args", "") or "").strip()
    if not custom and config is not None:
        custom = str(config.get("jvm_args") or "")
    args.extend(split_jvm_args(custom))
    return args


def build_options(mc_dir: str, config, instance: Instance,
                  auth: Optional[dict] = None, java_path: str = "") -> dict:
    """构建 minecraft-launcher-lib 的启动选项。"""
    fields = auth_fields(auth, config)
    game_dir = _game_dir(instance, mc_dir)
    options = {
        "username": fields["username"],
        "uuid": fields["uuid"],
        "token": fields["token"],
        "executablePath": java_path or "java",
        "gameDirectory": game_dir,
        "jvmArguments": build_jvm_args(mc_dir, config, java_path, instance.version_id,
                                       instance, auth),
    }
    return options


def build_command(mc_dir: str, config, instance: Instance,
                  auth: Optional[dict] = None,
                  java_path: str = "") -> tuple[list[str], str]:
    """只构建启动命令，不创建进程（自检 / 诊断用）。返回 (command, java_path)。"""
    if instance is None:
        raise LaunchError("没有可启动的实例。")
    version_id = (instance.version_id or "").strip()
    if not version_id:
        raise LaunchError("实例没有绑定游戏版本，请先在实例设置里选择版本。")

    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if not os.path.isdir(ver_dir):
        raise LaunchError(f"版本 {version_id} 未安装。\n目录不存在: {ver_dir}")

    if not java_path:
        java_path = resolve_java(config, mc_dir, version_id)

    # 中文安装目录：让 JVM 通过 ASCII 目录联接看到纯英文路径（Java 8 的硬限制）
    mc_effective = mc_dir
    if paths.IS_WINDOWS and not os.path.abspath(mc_dir).isascii():
        try:
            mc_effective = paths.ascii_mirror(mc_dir)
        except Exception as e:
            print(f"[launch] 建立 ASCII 联接失败: {e}", file=sys.stderr)
            mc_effective = mc_dir
        if os.path.normcase(mc_effective) == os.path.normcase(os.path.abspath(mc_dir)):
            # 联接没建起来：Java 8 会直接崩在 classpath / native 库上，提前说清楚
            major_guess = java_utils.get_major_java_version(java_path) or 0
            if not major_guess or major_guess <= 8:
                raise LaunchError(
                    "安装目录含中文，Java 8 无法从中文路径加载 jar 与 native 库。\n\n"
                    f"当前目录：{mc_dir}\n\n"
                    "启动器已尝试建立英文路径联接但失败（常见原因是目标目录跨磁盘）。\n"
                    "请把启动器放到纯英文路径，或在「设置 → 游戏目录」换一个英文目录。"
                )

    options = build_options(mc_effective, config, instance, auth, java_path)
    try:
        command = minecraft_launcher_lib.command.get_minecraft_command(
            version_id, mc_effective, options
        )
    except Exception as e:
        raise LaunchError(f"生成启动命令失败:\n{e}") from e
    if not command:
        raise LaunchError("启动命令为空，版本文件可能损坏。")
    command = list(command)
    # 路径统一换成 ASCII 联接前缀（classpath / library.path / gameDir 一次解决）
    command = rewrite_root(command, mc_dir, mc_effective)
    # 兜底：万一联接没建立成功，至少把 native 库复制到英文目录并改写 -Djava.library.path
    try:
        command = prepare_ascii_natives(command, version_id)
    except Exception as e:
        print(f"[launch] native 路径处理失败: {e}", file=sys.stderr)
    return command, java_path


# ═══════════════════ 启动 ═══════════════════

def _game_dir(instance: Instance, mc_dir: str) -> str:
    """实例的游戏目录（工作目录 + --gameDir）；无效时抛 LaunchError。"""
    game_dir = (getattr(instance, "game_dir", "") or "").strip() or mc_dir
    if not os.path.isabs(game_dir):
        raise LaunchError(f"实例游戏目录不是绝对路径: {game_dir!r}\n请在实例设置里重新选择。")
    if os.path.exists(game_dir) and not os.path.isdir(game_dir):
        raise LaunchError(f"实例游戏目录被同名文件占用: {game_dir}")
    return os.path.normpath(game_dir)


def _deploy_skin(config, game_dir: str):
    """部署本地皮肤（配置了才做，失败不影响启动）。"""
    if config is None:
        return
    skin_path = config.get("local_skin_path", "")
    cape_path = config.get("local_cape_path", "")
    if not skin_path and not cape_path:
        return
    username = str(config.get("username", "Player") or "Player")
    model = config.get("skin_model", "default")
    try:
        skin_local.deploy_local_skin(game_dir, username, skin_path, cape_path, model)
    except Exception as e:
        print(f"[java.launch] 本地皮肤部署失败（不影响启动）: {e}", file=sys.stderr)


def _pick_java(config, mc_dir: str, version_id: str, instance: Instance,
               required: int) -> str:
    """实例 java_path 优先，其次自动挑选；不兼容时给出可读错误。"""
    configured = (getattr(instance, "java_path", "") or "").strip()
    if not configured:
        return find_best_java(config, mc_dir, required)

    if not (os.path.isfile(configured) or configured == "java"):
        raise LaunchError(
            f"实例配置的 Java 不可用:\n{configured}\n"
            f"该文件不存在，请在实例设置里重新选择。"
        )
    major = _java_major(configured)
    if major is None:
        # 版本问不出来（javaw 无输出、运行时被裁剪等）：尊重实例里的显式选择
        print(f"[java.launch] 无法判断 {configured} 的 Java 版本，按实例设置直接使用",
              file=sys.stderr)
        return configured
    if not _java_compatible(required, major):
        raise LaunchError(
            f"实例配置的 Java {major or '?'} 与版本要求不兼容:\n{configured}\n"
            f"此版本需要 Java {required}+"
            + ("（1.16 及更老只支持 Java 8~17）" if required <= 8 else "")
            + "，请在实例设置里更换 Java。"
        )
    return configured


def launch_instance(mc_dir: str, config, instance: Instance,
                    auth: Optional[dict] = None,
                    cb: Optional[dict] = None) -> LaunchHandle:
    """启动游戏。失败抛 LaunchError（消息可直接给用户看）。"""
    if instance is None:
        raise LaunchError("没有可启动的实例。")

    version_id = (instance.version_id or "").strip()
    if not version_id:
        raise LaunchError("实例没有绑定游戏版本，请先在实例设置里选择版本。")

    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if not os.path.isdir(ver_dir):
        raise LaunchError(f"版本 {version_id} 未安装。\n目录不存在: {ver_dir}")

    game_dir = _game_dir(instance, mc_dir)
    try:
        os.makedirs(game_dir, exist_ok=True)
    except OSError as e:
        raise LaunchError(f"无法创建游戏目录:\n{game_dir}\n{e}") from e

    _deploy_skin(config, game_dir)

    required = required_java(mc_dir, version_id)
    java_path = _pick_java(config, mc_dir, version_id, instance, required)
    command, java_path = build_command(mc_dir, config, instance, auth, java_path)

    java_major = _java_major(java_path)
    java_info = f"Java {java_major}" if java_major else "Java"
    if java_major is None:
        print(f"[java.launch] 无法确认 {java_path} 的 Java 版本（运行时可能损坏），"
              f"若启动失败请重新下载 Java 环境", file=sys.stderr)

    if cb and "setStatus" in cb:
        cb["setStatus"](f"正在启动 {version_id}（{java_info}）…")

    log_path = log_manager.get_game_log_path(mc_dir)
    log_manager.cleanup_old_logs(mc_dir)

    log_file = None
    try:
        log_file = open(log_path, "w", encoding="utf-8", errors="replace")
        log_file.write("# CBL Cube Launcher — 游戏会话日志\n")
        log_file.write(f"# 版本: {version_id}\n")
        log_file.write(f"# 实例: {getattr(instance, 'name', '') or instance.id}\n")
        log_file.write(f"# Java: {java_path} ({java_info}, 版本要求 {required})\n")
        log_file.write(f"# 时间: {datetime.now().isoformat()}\n")
        log_file.write(f"# 工作目录: {game_dir}\n")
        log_file.write(f"# {'=' * 60}\n\n")
        log_file.flush()
        process = subprocess.Popen(
            command,
            cwd=game_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
        )
        # LaunchHandle.close_log() 会关掉这个句柄；保留属性名与旧实现一致
        process._log_file = log_file
        process._log_path = log_path
    except FileNotFoundError:
        _safe_close(log_file)
        raise LaunchError(f"{java_info} 可执行文件未找到:\n{java_path}")
    except OSError as e:
        _safe_close(log_file)
        raise LaunchError(f"进程创建失败 ({java_info}):\n{e}") from e

    return LaunchHandle(
        process=process,
        pid=int(getattr(process, "pid", 0) or 0),
        log_path=log_path,
        note=f"{version_id} · {java_info}",
    )


def _safe_close(f):
    if f is None:
        return
    try:
        f.close()
    except Exception:
        pass


def close_game_log(process):
    """关闭游戏进程的日志句柄（Windows 上不放手旧日志就删不掉）。"""
    _safe_close(getattr(process, "_log_file", None))
    try:
        process._log_file = None
    except Exception:
        pass
