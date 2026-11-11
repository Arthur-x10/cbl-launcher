"""日志管理 — 游戏会话日志 + 崩溃报告收集 + 启动器日志。"""

import os
import glob
import logging
from datetime import datetime
from pathlib import Path

MAX_GAME_LOGS = 15


def setup_launcher_log(mc_dir: str) -> logging.Logger:
    """初始化启动器日志，写入 .minecraft/launcher.log。"""
    log_path = os.path.join(mc_dir, "launcher.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    logger = logging.getLogger("CBL")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8", mode="a")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(fh)

    logger.info("=" * 50)
    logger.info("CBL Cube Launcher 启动")
    return logger


def get_game_log_path(mc_dir: str) -> str:
    """生成带时间戳的游戏日志文件路径。"""
    logs_dir = os.path.join(mc_dir, "logs", "game_sessions")
    os.makedirs(logs_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(logs_dir, f"game_{ts}.log")


def cleanup_old_logs(mc_dir: str):
    """清理多余的游戏会话日志，保留最近 N 个。"""
    logs_dir = os.path.join(mc_dir, "logs", "game_sessions")
    if not os.path.isdir(logs_dir):
        return
    logs = sorted(glob.glob(os.path.join(logs_dir, "game_*.log")))
    while len(logs) > MAX_GAME_LOGS:
        victim = logs.pop(0)
        try:
            os.remove(victim)
        except OSError:
            # 被游戏进程或杀软占用：跳过这一个，继续清理更老的，
            # 以前这里是 break，一个删不掉就永远不再清理。
            continue


def get_latest_crash_report(mc_dir: str) -> str:
    """获取最新的 Minecraft 崩溃报告路径。"""
    crash_dir = os.path.join(mc_dir, "crash-reports")
    if not os.path.isdir(crash_dir):
        return ""
    reports = sorted(
        glob.glob(os.path.join(crash_dir, "crash-*.txt")),
        key=os.path.getmtime, reverse=True
    )
    return reports[0] if reports else ""


def get_latest_game_log(mc_dir: str) -> str:
    """获取最新的游戏会话日志路径。"""
    logs_dir = os.path.join(mc_dir, "logs", "game_sessions")
    if not os.path.isdir(logs_dir):
        return ""
    logs = sorted(
        glob.glob(os.path.join(logs_dir, "game_*.log")),
        key=os.path.getmtime, reverse=True
    )
    return logs[0] if logs else ""


def read_log_tail(path: str, lines: int = 80) -> str:
    """读取日志文件末尾 N 行。"""
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return "".join(all_lines[-lines:])
    except Exception:
        return ""


def open_logs_folder(mc_dir: str):
    """在文件管理器中打开日志文件夹。"""
    import subprocess, sys
    logs_dir = os.path.join(mc_dir, "logs", "game_sessions")
    os.makedirs(logs_dir, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(logs_dir)
    else:
        subprocess.Popen(["xdg-open", logs_dir])
