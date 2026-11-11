"""Mod 加载器管理模块 - Forge / Fabric（含老版本 Forge 安装修复）。"""

import json
import os
import shutil
from typing import Optional

import minecraft_launcher_lib


def get_forge_versions(mc_version: str) -> list[str]:
    """获取指定 MC 版本可用的 Forge 版本列表"""
    try:
        versions = minecraft_launcher_lib.forge.list_forge_versions()
        return [v for v in versions if v.startswith(mc_version + "-")]
    except Exception:
        return []


def find_forge_version(mc_version: str) -> Optional[str]:
    """获取指定 MC 版本推荐的 Forge 版本"""
    try:
        return minecraft_launcher_lib.forge.find_forge_version(mc_version)
    except Exception:
        return None


def install_forge(mc_dir: str, forge_version: str,
                  callback: Optional[dict] = None):
    """安装 Forge（安装后自动修复老版本文件错位问题）。

    forge_version: 如 "1.20.4-49.0.30" 或 "1.7.10-10.13.4.1614"
    """
    minecraft_launcher_lib.forge.install_forge_version(
        forge_version, mc_dir, callback=callback
    )
    _fix_forge_files(mc_dir, forge_version)


def _fix_forge_files(mc_dir: str, forge_version: str):
    """修复老版本 Forge 安装后 JSON/JAR 文件错位。

    minecraft-launcher-lib 对 1.7~1.12 的 Forge 可能创建:
      versions/Forge X.X.X-Y.Y.Y/Forge X.X.X-Y.Y.Y.json  (带空格，错)
    而正确的应该是:
      versions/{mc}-Forge{X.X.X}-{mc}/{mc}-Forge{X.X.X}-{mc}.json
    """
    ver_dir = os.path.join(mc_dir, "versions")
    if not os.path.isdir(ver_dir):
        return

    for name in os.listdir(ver_dir):
        full = os.path.join(ver_dir, name)
        if not os.path.isdir(full):
            continue

        # 检测带空格的错误 Forge 目录 (如 "Forge 10.13.4.1614-1.7.10")
        if name.startswith("Forge "):
            json_path = os.path.join(full, f"{name}.json")
            if not os.path.isfile(json_path):
                continue

            # 找到对应的正确目录名
            target_name = _find_matching_forge_dir(ver_dir, name)
            if not target_name:
                continue

            target_dir = os.path.join(ver_dir, target_name)
            target_json = os.path.join(target_dir, f"{target_name}.json")

            # 如果目标 JSON 不存在，复制并修正 id
            if not os.path.isfile(target_json):
                os.makedirs(target_dir, exist_ok=True)
                try:
                    raw = open(json_path, "rb").read()
                    if raw[:3] == b"\xef\xbb\xbf":
                        raw = raw[3:]
                    data = json.loads(raw)
                    data["id"] = target_name
                    with open(target_json, "w", encoding="utf-8", newline="\n") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                except Exception:
                    shutil.copy2(json_path, target_json)

            # 复制 JAR（如果目标缺失）
            src_jar = os.path.join(full, f"{name}.jar")
            dst_jar = os.path.join(target_dir, f"{target_name}.jar")
            if os.path.isfile(src_jar) and not os.path.isfile(dst_jar):
                shutil.copy2(src_jar, dst_jar)

            # 清理错误目录
            try:
                shutil.rmtree(full)
            except Exception:
                pass


def _find_matching_forge_dir(ver_dir: str, wrong_name: str) -> Optional[str]:
    """从 'Forge X.X.X-Y.Y.Y' 找到对应的正确目录名。"""
    # "Forge 10.13.4.1614-1.7.10" → 找 "1.7.10-Forge10.13.4.1614-1.7.10"
    for name in os.listdir(ver_dir):
        if "Forge" in name and name != wrong_name and os.path.isdir(os.path.join(ver_dir, name)):
            # 版本号部分应该有交集
            wrong_nums = wrong_name.replace("Forge ", "")
            if wrong_nums in name or name.split("-Forge")[-1] in wrong_name:
                return name

    # 尝试从名字重构: "Forge 10.13.4.1614-1.7.10" → 提取 mc_ver 和 forge_ver
    parts = wrong_name.replace("Forge ", "").split("-")
    if len(parts) >= 2:
        forge_num = parts[0]
        mc_ver = "-".join(parts[1:])
        candidate = f"{mc_ver}-Forge{forge_num}-{mc_ver}"
        if os.path.isdir(os.path.join(ver_dir, candidate)):
            return candidate
        candidate2 = f"{mc_ver}-Forge{forge_num}"
        if os.path.isdir(os.path.join(ver_dir, candidate2)):
            return candidate2

    return None


def get_fabric_versions() -> list[dict]:
    """获取所有可用的 Fabric Loader 版本"""
    try:
        return minecraft_launcher_lib.fabric.get_all_loader_versions()
    except Exception:
        return []


def install_fabric(mc_dir: str, mc_version: str,
                   loader_version: Optional[str] = None,
                   callback: Optional[dict] = None):
    """安装 Fabric"""
    kw = {"callback": callback}
    if loader_version:
        kw["loader_version"] = loader_version
    minecraft_launcher_lib.fabric.install_fabric(mc_version, mc_dir, **kw)


# ═══════════════════ Quilt ═══════════════════

def get_quilt_versions() -> list[dict]:
    """获取所有可用的 Quilt Loader 版本"""
    try:
        return minecraft_launcher_lib.quilt.get_all_loader_versions()
    except Exception:
        return []


def install_quilt(mc_dir: str, mc_version: str,
                  loader_version: Optional[str] = None,
                  callback: Optional[dict] = None):
    """安装 Quilt"""
    kw = {"callback": callback}
    if loader_version:
        kw["loader_version"] = loader_version
    minecraft_launcher_lib.quilt.install_quilt(mc_version, mc_dir, **kw)


# ═══════════════════ NeoForge ═══════════════════

def get_neoforge_versions(mc_version: str) -> list[str]:
    """获取指定 MC 版本可用的 NeoForge 版本"""
    try:
        return minecraft_launcher_lib.mod_loader.list_mod_loader("neoforge", mc_version)
    except Exception:
        return []


def install_neoforge(mc_dir: str, neoforge_version: str,
                     callback: Optional[dict] = None):
    """安装 NeoForge"""
    try:
        ml = minecraft_launcher_lib.mod_loader.get_mod_loader("neoforge", neoforge_version)
        ml.install(mc_dir, callback=callback)
    except AttributeError:
        minecraft_launcher_lib.forge.install_forge_version(
            neoforge_version, mc_dir, callback=callback
        )
