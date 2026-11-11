"""整合包导入 — 支持 Modrinth (.mrpack) + CurseForge/通用 (.zip)。"""

import json
import os
import shutil
import zipfile
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import minecraft_launcher_lib


_retry_installed = False

def _enable_retry():
    """给下载加重试 + 确保镜像源 URL 重写生效。"""
    global _retry_installed
    if _retry_installed:
        return
    _retry_installed = True

    from core.mirror import activate, get_active_key, SOURCES

    retry = Retry(total=5, backoff_factor=1.5,
                  status_forcelist=[500, 502, 503, 504, 520, 521, 522, 523, 524])
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    active_map = SOURCES.get(get_active_key(), {}).get("map", {})

    def _rewrite(url):
        for orig, mirror in active_map.items():
            if orig in url:
                return url.replace(orig, mirror)
        return url

    _real_get = requests.__dict__.get("_orig_get", requests.get)

    def _smart_get(url, **kwargs):
        kwargs.setdefault("timeout", 30)
        url = _rewrite(url)
        try:
            return session.get(url, **kwargs)
        except Exception:
            return _real_get(url, **kwargs)

    if "_orig_get" not in requests.__dict__:
        requests._orig_get = requests.get
    requests.get = _smart_get


def detect_format(path: str) -> str:
    """检测整合包格式。返回 'mrpack' / 'curseforge' / 'mmc' / 'generic' / 'unknown'。"""
    if path.lower().endswith(".mrpack"):
        return "mrpack"
    if not zipfile.is_zipfile(path):
        return "unknown"
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            if "modrinth.index.json" in names:
                return "mrpack"
            if "manifest.json" in names:
                return "curseforge"
            if "mmc-pack.json" in names or "instance.cfg" in names:
                return "mmc"
            if any(n.startswith("mods/") or n.startswith("config/") for n in names):
                return "generic"
    except Exception:
        pass
    return "unknown"


def get_info(path: str) -> dict:
    """读取整合包信息。返回 {name, version, mc_version, format, mod_count, summary}。"""
    fmt = detect_format(path)
    info = {
        "name": os.path.basename(path),
        "version": "",
        "mc_version": "",
        "format": fmt,
        "mod_count": 0,
        "summary": "",
        "loader": "",
    }

    if fmt == "mrpack":
        try:
            mi = minecraft_launcher_lib.mrpack.get_mrpack_information(path)
            info["name"] = mi["name"]
            info["version"] = mi.get("versionId", "")
            info["mc_version"] = mi.get("minecraftVersion", "")
            info["summary"] = mi.get("summary", "")
            with zipfile.ZipFile(path) as zf:
                idx = json.loads(zf.read("modrinth.index.json"))
                info["mod_count"] = len(idx.get("files", []))
                deps = idx.get("dependencies", {})
                if "forge" in deps:
                    info["loader"] = f"Forge {deps['forge']}"
                elif "fabric-loader" in deps:
                    info["loader"] = f"Fabric {deps['fabric-loader']}"
                elif "quilt-loader" in deps:
                    info["loader"] = f"Quilt {deps['quilt-loader']}"
                elif "neoforge" in deps:
                    info["loader"] = f"NeoForge {deps['neoforge']}"
        except Exception:
            pass

    elif fmt == "curseforge":
        try:
            with zipfile.ZipFile(path) as zf:
                manifest = json.loads(zf.read("manifest.json"))
                info["name"] = manifest.get("name", info["name"])
                info["version"] = manifest.get("version", "")
                info["mc_version"] = manifest.get("minecraft", {}).get("version", "")
                info["mod_count"] = len(manifest.get("files", []))
                loaders = manifest.get("minecraft", {}).get("modLoaders", [])
                if loaders:
                    info["loader"] = loaders[0].get("id", "")
        except Exception:
            pass

    elif fmt == "mmc":
        try:
            with zipfile.ZipFile(path) as zf:
                if "mmc-pack.json" in zf.namelist():
                    pack = json.loads(zf.read("mmc-pack.json"))
                    for comp in pack.get("components", []):
                        if comp.get("uid") == "net.minecraft":
                            info["mc_version"] = comp.get("version", "")
                        elif "forge" in comp.get("uid", "").lower():
                            info["loader"] = f"Forge {comp.get('version', '')}"
                        elif "fabric" in comp.get("uid", "").lower():
                            info["loader"] = f"Fabric {comp.get('version', '')}"
                mods = [n for n in zf.namelist()
                        if n.startswith((".minecraft/mods/", "mods/")) and n.endswith(".jar")]
                info["mod_count"] = len(mods)
        except Exception:
            pass

    elif fmt == "generic":
        try:
            with zipfile.ZipFile(path) as zf:
                mods = [n for n in zf.namelist() if n.startswith("mods/") and n.endswith(".jar")]
                info["mod_count"] = len(mods)
        except Exception:
            pass

    return info


def install_mrpack(path: str, mc_dir: str, callback=None):
    """安装 Modrinth 整合包（一键：MC版本 + 加载器 + Mod + 配置）。"""
    _enable_retry()
    minecraft_launcher_lib.mrpack.install_mrpack(
        path, mc_dir, callback=callback
    )


def install_curseforge_zip(path: str, mc_dir: str, callback=None):
    """安装 CurseForge 整合包（部分支持：MC版本 + overrides，Mod 需手动下载）。

    CurseForge 的 Mod 通过 projectID/fileID 引用，下载需要 CurseForge API Key。
    本函数只提取 overrides 目录内容（config, mods 等 jar 文件，resourcepacks 等）。
    """
    _enable_retry()
    if callback and "setStatus" in callback:
        callback["setStatus"]("正在解析 CurseForge 整合包…")

    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("manifest.json"))
        mc_ver = manifest.get("minecraft", {}).get("version", "")
        overrides_dir = manifest.get("overrides", "overrides")

        if mc_ver:
            if callback and "setStatus" in callback:
                callback["setStatus"](f"正在安装 Minecraft {mc_ver}…")
            minecraft_launcher_lib.install.install_minecraft_version(
                mc_ver, mc_dir, callback=callback
            )

        if callback and "setStatus" in callback:
            callback["setStatus"]("正在提取整合包文件…")

        for entry in zf.namelist():
            if entry.startswith(overrides_dir + "/"):
                rel = entry[len(overrides_dir) + 1:]
                if not rel:
                    continue
                dst = os.path.join(mc_dir, rel)
                if entry.endswith("/"):
                    os.makedirs(dst, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with zf.open(entry) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)

    if callback and "setStatus" in callback:
        cf_mods = len(manifest.get("files", []))
        if cf_mods > 0:
            callback["setStatus"](
                f"overrides 已提取。注意：{cf_mods} 个 CurseForge Mod 需在 CurseForge 客户端下载。"
            )


def install_generic_zip(path: str, mc_dir: str, callback=None):
    """安装通用 .zip 整合包（直接解压 mods/config 等到 .minecraft）。"""
    if callback and "setStatus" in callback:
        callback["setStatus"]("正在提取整合包文件…")

    known_dirs = {"mods", "config", "resourcepacks", "shaderpacks", "scripts", "saves"}

    with zipfile.ZipFile(path, "r") as zf:
        for entry in zf.namelist():
            top = entry.split("/")[0] if "/" in entry else ""
            if top.lower() in known_dirs or top == ".minecraft":
                rel = entry[len(".minecraft/"):] if entry.startswith(".minecraft/") else entry
                if not rel:
                    continue
                dst = os.path.join(mc_dir, rel)
                if entry.endswith("/"):
                    os.makedirs(dst, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with zf.open(entry) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)

    if callback and "setStatus" in callback:
        callback["setStatus"]("整合包文件提取完成")


def install_mmc_zip(path: str, mc_dir: str, callback=None):
    """安装 MultiMC/Prism 格式整合包。"""
    if callback and "setStatus" in callback:
        callback["setStatus"]("正在提取 MultiMC 整合包…")

    with zipfile.ZipFile(path, "r") as zf:
        for entry in zf.namelist():
            if entry.startswith(".minecraft/"):
                rel = entry[len(".minecraft/"):]
            elif entry.startswith("minecraft/"):
                rel = entry[len("minecraft/"):]
            else:
                continue
            if not rel:
                continue
            dst = os.path.join(mc_dir, rel)
            if entry.endswith("/"):
                os.makedirs(dst, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with zf.open(entry) as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)

    if callback and "setStatus" in callback:
        callback["setStatus"]("MultiMC 整合包提取完成")
