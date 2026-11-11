"""MC 版本管理模块 — 安装/删除/查询/分组。"""

import json
import os
import shutil
import subprocess
import sys
from typing import Optional

import minecraft_launcher_lib


def get_all_versions() -> list[dict]:
    """获取 Mojang 所有可用版本列表
    
    返回: [{"id": "1.20.4", "type": "release", "releaseTime": "..."}]
    """
    try:
        return minecraft_launcher_lib.utils.get_version_list()
    except Exception:
        return []


def get_installed_versions(mc_dir: str) -> list[dict]:
    """获取本地已安装的版本列表"""
    try:
        return minecraft_launcher_lib.utils.get_installed_versions(mc_dir)
    except Exception:
        return []


def get_latest_release() -> Optional[str]:
    """获取最新正式版版本号"""
    versions = get_all_versions()
    for v in versions:
        if v.get("type") == "release":
            return v["id"]
    return None


def filter_versions(versions: list[dict],
                    show_releases=True,
                    show_snapshots=False,
                    show_old=False) -> list[dict]:
    """根据类型过滤版本列表"""
    result = []
    for v in versions:
        vtype = v.get("type", "")
        if vtype == "release" and show_releases:
            result.append(v)
        elif vtype == "snapshot" and show_snapshots:
            result.append(v)
        elif vtype in ("old_alpha", "old_beta") and show_old:
            result.append(v)
    return result


def is_version_installed(mc_dir: str, version_id: str) -> bool:
    """检查某版本是否已安装"""
    installed = get_installed_versions(mc_dir)
    return any(v["id"] == version_id for v in installed)


def install_version(mc_dir: str, version_id: str,
                    callback: Optional[dict] = None):
    """安装指定版本（下载所有必要文件）
    
    callback 字典示例:
    {
        "setStatus": lambda text: ...,
        "setProgress": lambda value: ...,
        "setMax": lambda value: ...
    }
    """
    minecraft_launcher_lib.install.install_minecraft_version(
        version_id, mc_dir, callback=callback
    )


def get_parent_version(mc_dir: str, version_id: str) -> Optional[str]:
    """读取版本 JSON 的 inheritsFrom，判断父版本。"""
    path = os.path.join(mc_dir, "versions", version_id, f"{version_id}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("inheritsFrom")
    except Exception:
        return None


def get_grouped_versions(mc_dir: str) -> list[dict]:
    """按基础版本分组。

    返回:
    [
      {"id": "1.7.10", "type": "release", "children": [
          {"id": "1.7.10-Forge...", "type": "release", "label": "Forge 10.13.4.1614"},
      ]},
      {"id": "1.21.1", "type": "release", "children": []},
    ]
    """
    all_vers = get_installed_versions(mc_dir)
    bases: dict[str, dict] = {}
    children: list[tuple[str, dict]] = []

    for v in all_vers:
        vid = v["id"]
        parent = get_parent_version(mc_dir, vid)
        if parent:
            v["label"] = _loader_label(vid)
            children.append((parent, v))
        else:
            bases[vid] = {**v, "children": []}

    for parent_id, child in children:
        if parent_id in bases:
            bases[parent_id]["children"].append(child)
        else:
            bases[child["id"]] = {**child, "children": []}

    return list(bases.values())


def _loader_label(vid: str) -> str:
    """从版本 ID 提取加载器可读名称。"""
    v = vid.lower()
    if "neoforge" in v:
        for sep in ("-neoforge-", "-NeoForge-"):
            if sep.lower() in v:
                parts = vid.split(sep if sep in vid else sep.lower())
                if len(parts) >= 2:
                    return f"NeoForge {parts[1]}"
    if "forge" in v:
        if "-Forge" in vid:
            parts = vid.split("-Forge")
            if len(parts) >= 2:
                num = parts[1].split("-")[0]
                return f"Forge {num}"
        if "-forge-" in vid:
            parts = vid.split("-forge-")
            if len(parts) >= 2:
                return f"Forge {parts[1]}"
    if "fabric-loader-" in v:
        parts = vid.split("fabric-loader-")
        if len(parts) >= 2:
            loader_ver = parts[1].split("-")[0]
            return f"Fabric {loader_ver}"
    if "quilt-loader-" in v:
        parts = vid.split("quilt-loader-")
        if len(parts) >= 2:
            loader_ver = parts[1].split("-")[0]
            return f"Quilt {loader_ver}"
    return vid


def delete_version(mc_dir: str, version_id: str):
    """删除已安装版本（versions/{id}/ 目录）。"""
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if os.path.isdir(ver_dir):
        shutil.rmtree(ver_dir, ignore_errors=True)


def get_version_size_mb(mc_dir: str, version_id: str) -> float:
    """获取版本目录大小 (MB)。"""
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if not os.path.isdir(ver_dir):
        return 0
    total = sum(
        f.stat().st_size for f in os.scandir(ver_dir) if f.is_file()
    )
    return round(total / (1024 * 1024), 1)


def get_mods_list(mc_dir: str) -> list[str]:
    """列出 mods/ 文件夹里的 .jar 文件名。"""
    mods_dir = os.path.join(mc_dir, "mods")
    if not os.path.isdir(mods_dir):
        return []
    return sorted(
        f for f in os.listdir(mods_dir)
        if f.lower().endswith(".jar")
    )


def open_mods_folder(mc_dir: str):
    """在文件管理器中打开 mods 文件夹（不存在则创建）。"""
    mods_dir = os.path.join(mc_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(mods_dir)
    else:
        subprocess.Popen(["xdg-open", mods_dir])
