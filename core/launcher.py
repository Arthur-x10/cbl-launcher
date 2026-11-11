"""游戏启动模块 — 命令构建 + Java 兼容性检查 + 进程创建。"""

import json
import os
import subprocess
from typing import Optional

import minecraft_launcher_lib

from core.config import Config
from core import java_utils, java_manager, skin_local, log_manager, performance


class LaunchError(Exception):
    """启动失败时抛出，附带用户可读信息。"""
    pass


def _read_version_json(mc_dir: str, version_id: str) -> dict:
    """读取版本 JSON，获取 Java 要求和继承关系。"""
    path = os.path.join(mc_dir, "versions", version_id, f"{version_id}.json")
    if not os.path.isfile(path):
        raise LaunchError(f"版本文件不存在: {path}\n请先安装此版本。")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_required_java(mc_dir: str, version_id: str) -> int:
    """获取该版本要求的 Java 主版本号。"""
    try:
        data = _read_version_json(mc_dir, version_id)
        # Forge/Fabric 可能 inheritsFrom 父版本
        if "javaVersion" in data:
            return data["javaVersion"].get("majorVersion", 8)
        parent = data.get("inheritsFrom")
        if parent:
            return get_required_java(mc_dir, parent)
    except Exception:
        pass
    return 8  # 默认 Java 8（兼容老版本）



def find_best_java(config: Config, mc_dir: str, required_major: int) -> str:
    """根据版本要求找到最合适的 Java。

    优先级:
    1. java_manager 管理的 Mojang 运行时（最可靠）
    2. 用户手动配置的 Java（如果兼容）
    3. 系统扫描到的兼容 Java
    4. 抛出错误
    """
    # Mojang 官方运行时（首选）
    rt = java_manager.find_java_for_version(mc_dir, required_major)
    if rt:
        return rt

    # 用户配置的 Java
    is_legacy = required_major <= 8
    user_java = config.get_java_path()
    if user_java and java_utils.validate_java(user_java):
        major = java_utils.get_major_java_version(user_java)
        if major:
            if is_legacy and 8 <= major <= 17:
                return user_java
            elif not is_legacy and major >= required_major:
                return user_java

    # 系统扫描
    all_javas = java_utils.find_java_in_common_locations()
    for j in sorted(all_javas, key=lambda j: java_utils.get_major_java_version(j["path"]) or 99):
        major = java_utils.get_major_java_version(j["path"])
        if not major:
            continue
        if is_legacy and 8 <= major <= 17:
            return j["path"]
        elif not is_legacy and major >= required_major:
            return j["path"]

    # 兜底
    if user_java and java_utils.validate_java(user_java):
        return user_java

    raise LaunchError(
        f"未找到兼容的 Java。\n"
        f"此版本需要 Java {required_major}+。\n"
        f"请先在首页等待 Java 环境自动下载完成。"
    )


def build_launch_options(config: Config, java_path: str,
                         version_id_hint: str = "") -> dict:
    """构建 minecraft-launcher-lib 启动选项。"""
    options = {
        "username": config.get("username", "Player"),
        "uuid": config.get("uuid", ""),
        "token": config.get("access_token", "0"),
        "executablePath": java_path,
    }

    auto_perf = config.get("auto_performance", True)
    if auto_perf:
        sys_info = performance.get_system_info()
        has_mods = any(k in version_id_hint.lower()
                       for k in ("forge", "fabric", "quilt", "neoforge")
                       ) if version_id_hint else False
        java_maj = java_utils.get_major_java_version(java_path) or 17
        jvm_args = performance.generate_jvm_args(
            sys_info["total_ram_mb"], sys_info["cpu_cores"], has_mods, java_maj
        )
    else:
        jvm_args = [f"-Xms{config.get_ram_min()}M", f"-Xmx{config.get_ram_max()}M"]

    # Yggdrasil (LittleSkin 等) 需要注入 authlib-injector
    if config.get("auth_type") == "yggdrasil":
        api_root = config.get("yggdrasil_api", "")
        if api_root:
            from core import yggdrasil
            mc_dir_for_inj = config.get_minecraft_dir()
            if yggdrasil.is_injector_installed(mc_dir_for_inj):
                jvm_args.append(yggdrasil.get_injector_jvm_arg(mc_dir_for_inj, api_root))

    custom = config.get("jvm_args", "")
    if custom:
        jvm_args.extend(custom.split())
    options["jvmArguments"] = jvm_args

    selected = config.get("selected_version", "")
    game_dirs = config.get("game_directories", {})
    if selected and selected in game_dirs:
        options["gameDirectory"] = game_dirs[selected]

    return options


def launch_game(version_id: str, mc_dir: str, config: Config) -> subprocess.Popen:
    """启动游戏。失败抛出 LaunchError，不再返回 None。"""

    # 0. 部署本地皮肤（如果配置了）
    username = config.get("username", "Player")
    skin_path = config.get("local_skin_path", "")
    cape_path = config.get("local_cape_path", "")
    skin_model = config.get("skin_model", "default")
    if skin_path or cape_path:
        try:
            skin_local.deploy_local_skin(mc_dir, username, skin_path, cape_path, skin_model)
        except Exception:
            pass

    # 1. 检查版本是否存在
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if not os.path.isdir(ver_dir):
        raise LaunchError(f"版本 {version_id} 未安装。\n目录不存在: {ver_dir}")

    # 2. 确定 Java 版本
    required = get_required_java(mc_dir, version_id)
    java_path = find_best_java(config, mc_dir, required)

    java_major = java_utils.get_major_java_version(java_path)
    java_info = f"Java {java_major}" if java_major else "Java"

    # 3. 生成启动命令
    options = build_launch_options(config, java_path, version_id)
    try:
        command = minecraft_launcher_lib.command.get_minecraft_command(
            version_id, mc_dir, options
        )
    except Exception as e:
        raise LaunchError(f"生成启动命令失败:\n{e}") from e

    if not command:
        raise LaunchError("启动命令为空，版本文件可能损坏。")

    # 4. 创建进程（输出写入带时间戳的日志文件）
    log_path = log_manager.get_game_log_path(mc_dir)
    log_manager.cleanup_old_logs(mc_dir)
    try:
        log_file = open(log_path, "w", encoding="utf-8", errors="replace")
        log_file.write(f"# CBL Cube Launcher — 游戏会话日志\n")
        log_file.write(f"# 版本: {version_id}\n")
        log_file.write(f"# Java: {java_path} ({java_info})\n")
        log_file.write(f"# 时间: {__import__('datetime').datetime.now().isoformat()}\n")
        log_file.write(f"# {'=' * 60}\n\n")
        log_file.flush()
        process = subprocess.Popen(
            command,
            cwd=mc_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        process._log_file = log_file
        process._log_path = log_path
    except FileNotFoundError:
        raise LaunchError(f"{java_info} 可执行文件未找到:\n{java_path}")
    except OSError as e:
        raise LaunchError(f"进程创建失败 ({java_info}):\n{e}")

    return process
