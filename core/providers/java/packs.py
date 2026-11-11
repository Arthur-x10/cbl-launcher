"""Java 版整合包导入 —— mrpack / CurseForge / MultiMC / 通用 zip 的识别与安装。"""

import json
import os
import re
import shutil
import zipfile
from typing import Optional

import minecraft_launcher_lib

FORMATS = ("mrpack", "curseforge", "mmc", "generic", "unknown")

# 通用 zip 里认得的顶层目录
_GENERIC_DIRS = {"mods", "config", "resourcepacks", "shaderpacks", "scripts", "saves"}


def _enable_retry():
    """整合包安装时把下载重试次数调高。

    镜像 URL 重写与重试统一由 core.mirror 在 requests.Session.request 上处理，
    core.download 已接管库内的 download_file；这里不再自己 patch requests。
    """
    from core import mirror
    try:
        mirror.activate(mirror.get_active_key())
        mirror.set_retry(5)
    except Exception:
        pass


def _safe_join(base_dir: str, rel: str) -> Optional[str]:
    """把压缩包内的相对路径安全拼到 base_dir 下，越界返回 None。

    防 zip slip：整合包是用户从站外下载的不受信文件，条目名里的
    "../../x"、"/etc/x"、'C:/Windows/x' 以前会被 os.path.join 原样接受，
    等于给整合包作者一个任意路径写原语。
    """
    if not rel:
        return None
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or re.match(r"^[a-zA-Z]:", rel):
        return None
    base_abs = os.path.realpath(base_dir)
    dst = os.path.realpath(os.path.join(base_abs, rel))
    if dst != base_abs and not dst.startswith(base_abs + os.sep):
        return None
    return dst


def _status(cb: Optional[dict], text: str):
    if cb and "setStatus" in cb:
        cb["setStatus"](text)


# ═══════════════════ 识别 ═══════════════════

def detect_format(path: str) -> str:
    """检测整合包格式。返回 'mrpack' / 'curseforge' / 'mmc' / 'generic' / 'unknown'。"""
    if not path or not os.path.isfile(path):
        return "unknown"
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
    """读取整合包信息。返回 {name, version, mc_version, format, mod_count, summary, loader}。"""
    fmt = detect_format(path)
    info = {
        "name": os.path.basename(path or ""),
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
                names = zf.namelist()
                if "mmc-pack.json" in names:
                    pack = json.loads(zf.read("mmc-pack.json"))
                    for comp in pack.get("components", []):
                        uid = str(comp.get("uid", "")).lower()
                        if uid == "net.minecraft":
                            info["mc_version"] = comp.get("version", "")
                        elif "neoforge" in uid:
                            info["loader"] = f"NeoForge {comp.get('version', '')}"
                        elif "forge" in uid:
                            info["loader"] = f"Forge {comp.get('version', '')}"
                        elif "fabric" in uid:
                            info["loader"] = f"Fabric {comp.get('version', '')}"
                        elif "quilt" in uid:
                            info["loader"] = f"Quilt {comp.get('version', '')}"
                info["mod_count"] = len([n for n in names
                                         if n.startswith((".minecraft/mods/", "mods/"))
                                         and n.endswith(".jar")])
        except Exception:
            pass

    elif fmt == "generic":
        try:
            with zipfile.ZipFile(path) as zf:
                info["mod_count"] = len([n for n in zf.namelist()
                                         if n.startswith("mods/") and n.endswith(".jar")])
        except Exception:
            pass

    return info


def detect_modpack(path: str) -> tuple[str, dict]:
    """provider.detect_modpack：返回 (格式, 信息 dict)。"""
    fmt = detect_format(path)
    return fmt, get_info(path) if fmt != "unknown" else {
        "name": os.path.basename(path or ""),
        "version": "", "mc_version": "", "format": "unknown",
        "mod_count": 0, "summary": "", "loader": "",
    }


def _extract(zf: zipfile.ZipFile, entries: list[tuple[str, str]], mc_dir: str) -> int:
    """按 (压缩包内路径, 目标相对路径) 解压；越界条目直接跳过。返回写入的文件数。"""
    written = 0
    for entry, rel in entries:
        dst = _safe_join(mc_dir, rel)
        if dst is None:
            continue
        try:
            if entry.endswith("/"):
                os.makedirs(dst, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dst) or mc_dir, exist_ok=True)
            with zf.open(entry) as src, open(dst, "wb") as out:
                shutil.copyfileobj(src, out)
            written += 1
        except OSError:
            continue
    return written


# ═══════════════════ 安装 ═══════════════════

def install_mrpack(mc_dir: str, path: str, cb: Optional[dict] = None) -> str:
    """安装 Modrinth 整合包（MC 版本 + 加载器 + Mod + 配置），返回启动版本 id。"""
    _enable_retry()
    _status(cb, "正在安装 Modrinth 整合包…")
    minecraft_launcher_lib.mrpack.install_mrpack(path, mc_dir, callback=cb)
    try:
        version = minecraft_launcher_lib.mrpack.get_mrpack_launch_version(path)
    except Exception:
        return ""
    if version and os.path.isdir(os.path.join(mc_dir, "versions", version)):
        return version
    return version or ""


def install_curseforge_zip(mc_dir: str, path: str, cb: Optional[dict] = None) -> str:
    """安装 CurseForge 整合包（部分支持：MC 版本 + overrides；Mod 需手动下载）。

    CurseForge 的 Mod 通过 projectID/fileID 引用，下载需要 CurseForge API Key。
    本函数只提取 overrides 目录内容（config, mods 等 jar 文件，resourcepacks 等）。
    返回装好的原版版本 id（拿不到就返回空串）。
    """
    _enable_retry()
    _status(cb, "正在解析 CurseForge 整合包…")

    manifest = {}
    with zipfile.ZipFile(path, "r") as zf:
        try:
            manifest = json.loads(zf.read("manifest.json"))
        except Exception as e:
            raise RuntimeError(f"CurseForge 整合包的 manifest.json 无法读取: {e}") from e

        mc_ver = str(manifest.get("minecraft", {}).get("version", "") or "")
        overrides_dir = str(manifest.get("overrides", "overrides") or "overrides")

        if mc_ver:
            _status(cb, f"正在安装 Minecraft {mc_ver}…")
            minecraft_launcher_lib.install.install_minecraft_version(
                mc_ver, mc_dir, callback=cb
            )

        _status(cb, "正在提取整合包文件…")
        entries = []
        for entry in zf.namelist():
            if entry.startswith(overrides_dir + "/"):
                entries.append((entry, entry[len(overrides_dir) + 1:]))
        _extract(zf, entries, mc_dir)

    cf_mods = len(manifest.get("files", []))
    if cf_mods > 0:
        _status(cb, f"overrides 已提取。注意：{cf_mods} 个 CurseForge Mod 需在 CurseForge 客户端下载。")
    else:
        _status(cb, "整合包文件提取完成")
    return str(manifest.get("minecraft", {}).get("version", "") or "")


def install_generic_zip(mc_dir: str, path: str, cb: Optional[dict] = None) -> str:
    """安装通用 .zip 整合包（直接解压 mods/config 等到 mc_dir）。返回空串。"""
    _status(cb, "正在提取整合包文件…")
    entries = []
    with zipfile.ZipFile(path, "r") as zf:
        for entry in zf.namelist():
            top = entry.split("/")[0] if "/" in entry else ""
            if top.lower() in _GENERIC_DIRS or top == ".minecraft":
                rel = entry[len(".minecraft/"):] if entry.startswith(".minecraft/") else entry
                entries.append((entry, rel))
        _extract(zf, entries, mc_dir)
    _status(cb, "整合包文件提取完成")
    return ""


def install_mmc_zip(mc_dir: str, path: str, cb: Optional[dict] = None) -> str:
    """安装 MultiMC/Prism 格式整合包（取 .minecraft/ 或 minecraft/ 下的内容）。"""
    _status(cb, "正在提取 MultiMC 整合包…")
    entries = []
    with zipfile.ZipFile(path, "r") as zf:
        for entry in zf.namelist():
            if entry.startswith(".minecraft/"):
                rel = entry[len(".minecraft/"):]
            elif entry.startswith("minecraft/"):
                rel = entry[len("minecraft/"):]
            else:
                continue
            entries.append((entry, rel))
        _extract(zf, entries, mc_dir)
    _status(cb, "MultiMC 整合包提取完成")
    return ""


def install_modpack(mc_dir: str, path: str, cb: Optional[dict] = None) -> str:
    """provider.install_modpack：按格式分发，返回安装出的版本 id（能确定时）。"""
    if not path or not os.path.isfile(path):
        raise RuntimeError(f"整合包文件不存在: {path}")
    fmt = detect_format(path)
    if fmt == "mrpack":
        return install_mrpack(mc_dir, path, cb)
    if fmt == "curseforge":
        return install_curseforge_zip(mc_dir, path, cb)
    if fmt == "mmc":
        return install_mmc_zip(mc_dir, path, cb)
    if fmt == "generic":
        return install_generic_zip(mc_dir, path, cb)
    raise RuntimeError(
        "无法识别这个整合包格式。\n"
        "支持：Modrinth (.mrpack)、CurseForge (.zip)、MultiMC/Prism (.zip)、"
        "以及带 mods/ 或 config/ 目录的通用 .zip。"
    )
