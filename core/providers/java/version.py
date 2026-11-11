"""Java 版版本管理 —— 远端版本列表、已安装版本、分组、父版本、体积统计与删除。"""

import json
import os
import shutil
import sys
from typing import Optional

import minecraft_launcher_lib

from core.providers.base import GameVersion

PROVIDER_ID = "java"

# Mojang 版本清单里的类型 → GameVersion.kind（base.py 只列了 release/snapshot/old）
_KIND_MAP = {
    "release": "release",
    "snapshot": "snapshot",
    "old_alpha": "old",
    "old_beta": "old",
}


# ═══════════════════ 远端列表 ═══════════════════

def get_all_versions() -> Optional[list[dict]]:
    """Mojang 全部可用版本（原始 dict）。

    返回 None 表示「请求失败」（网络/镜像不可用），与「确实没有版本」区分开，
    这样 UI 才能提示用户重试而不是显示「共 0 个版本」。
    """
    try:
        return minecraft_launcher_lib.utils.get_version_list()
    except Exception:
        return None


def get_latest_release() -> Optional[str]:
    """最新正式版版本号。"""
    for v in (get_all_versions() or []):
        if v.get("type") == "release":
            return v["id"]
    return None


def list_remote(mc_dir: str = "") -> Optional[list[GameVersion]]:
    """远端版本列表；请求失败返回 None。传入 mc_dir 时会顺带标注已安装。"""
    raw = get_all_versions()
    if raw is None:
        return None
    installed = _installed_ids(mc_dir) if mc_dir else set()
    out: list[GameVersion] = []
    for v in raw:
        vid = str(v.get("id") or "")
        if not vid:
            continue
        vtype = str(v.get("type") or "release")
        out.append(GameVersion(
            provider=PROVIDER_ID,
            id=vid,
            display=vid,
            kind=_KIND_MAP.get(vtype, vtype),
            installed=vid in installed,
            meta={"type": vtype},
        ))
    return out


def filter_versions(versions: list[dict],
                    show_releases=True,
                    show_snapshots=False,
                    show_old=False) -> list[dict]:
    """按类型过滤原始版本 dict 列表（旧接口，UI 的版本页仍在用）。"""
    result = []
    for v in versions or []:
        vtype = v.get("type", "")
        if vtype == "release" and show_releases:
            result.append(v)
        elif vtype == "snapshot" and show_snapshots:
            result.append(v)
        elif vtype in ("old_alpha", "old_beta") and show_old:
            result.append(v)
    return result


# ═══════════════════ 本地已安装 ═══════════════════

def get_installed_versions(mc_dir: str) -> list[dict]:
    """列出已安装版本：逐个解析 versions/<id>/<id>.json，坏文件只跳过它自己。

    不走库的 minecraft_launcher_lib.utils.get_installed_versions —— 它对任何
    一个缺 releaseTime 或损坏的版本 json 都会整批抛异常（KeyError/JSONDecodeError），
    结果是"有一个坏文件，所有版本都从界面上消失"。这里逐个 try/except，
    并按 releaseTime 倒序（缺字段的排后面）。
    """
    base = os.path.join(mc_dir, "versions")
    out: list[dict] = []
    if not os.path.isdir(base):
        return out
    try:
        names = os.listdir(base)
    except OSError:
        return out
    for name in names:
        folder = os.path.join(base, name)
        if not os.path.isdir(folder):
            continue
        json_path = os.path.join(folder, name + ".json")
        if not os.path.isfile(json_path):
            continue
        try:
            with open(json_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except Exception:
            continue
        out.append({
            "id": str(data.get("id") or name),
            "type": str(data.get("type") or "release"),
            "releaseTime": str(data.get("releaseTime") or ""),
        })
    out.sort(key=lambda v: v.get("releaseTime") or "", reverse=True)
    return out


def _installed_ids(mc_dir: str) -> set[str]:
    return {str(v.get("id") or "") for v in get_installed_versions(mc_dir)}


def is_version_installed(mc_dir: str, version_id: str) -> bool:
    return version_id in _installed_ids(mc_dir)


def list_installed(mc_dir: str) -> list[GameVersion]:
    """已安装版本 → GameVersion。加载器版本的 parent 指向原版，display 带可读标签。"""
    from core.providers.java.launch import required_java

    out: list[GameVersion] = []
    for v in get_installed_versions(mc_dir):
        vid = str(v.get("id") or "")
        if not vid:
            continue
        vtype = str(v.get("type") or "release")
        parent = get_parent_version(mc_dir, vid) or ""
        label = loader_label(vid) if parent else vid
        display = f"{parent} · {label}" if parent else vid
        try:
            java_major = required_java(mc_dir, vid)
        except Exception:
            java_major = 0
        out.append(GameVersion(
            provider=PROVIDER_ID,
            id=vid,
            display=display,
            kind="loader" if parent else _KIND_MAP.get(vtype, vtype),
            parent=parent,
            java_major=java_major,
            installed=True,
            meta={"label": label, "type": vtype},
        ))
    return out


def get_parent_version(mc_dir: str, version_id: str) -> Optional[str]:
    """读取版本 JSON 的 inheritsFrom，判断父版本。"""
    path = os.path.join(mc_dir, "versions", version_id, f"{version_id}.json")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("inheritsFrom") or None
    except Exception:
        return None


# ═══════════════════ 安装 / 删除 ═══════════════════

def install_version(mc_dir: str, version_id: str, cb: Optional[dict] = None):
    """安装原版（下载所有必要文件）。cb: setStatus/setProgress/setMax。"""
    minecraft_launcher_lib.install.install_minecraft_version(
        version_id, mc_dir, callback=cb
    )


def delete_version(mc_dir: str, version_id: str) -> tuple[bool, str]:
    """删除已安装版本（versions/{id}/ 目录）。

    返回 (成功, 错误信息)。游戏正在运行、文件被占用或权限不足时
    必须把失败交给 UI 显示，不能静默返回「删了」。
    """
    if not version_id:
        return False, "版本 id 为空"
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if not os.path.isdir(ver_dir):
        return True, ""
    try:
        shutil.rmtree(ver_dir)
    except FileNotFoundError:
        return True, ""
    except OSError as e:
        return False, str(e)
    if os.path.isdir(ver_dir) and os.listdir(ver_dir):
        return False, "目录仍然存在（文件可能被游戏占用）"
    return True, ""


def version_size_mb(mc_dir: str, version_id: str) -> float:
    """版本目录的总体积 (MB)，含子目录。"""
    ver_dir = os.path.join(mc_dir, "versions", version_id)
    if not os.path.isdir(ver_dir):
        return 0.0
    total = 0
    for root, _dirs, files in os.walk(ver_dir):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return round(total / (1024 * 1024), 1)


# ═══════════════════ 分组 / 标签 ═══════════════════

def loader_label(version_id: str) -> str:
    """从版本 ID 提取加载器可读名称。

    覆盖真实的几种命名：
      1.20.1-forge-47.4.23 / 1.7.10-Forge10.13.4.1614-1.7.10
      1.20.1-neoforge-47.1.100 / neoforge-21.1.77
      fabric-loader-0.15.11-1.21.1 / quilt-loader-0.24.0-1.21.1
    判断顺序很重要：neoforge 里含有 forge，必须先判。
    """
    vid = version_id or ""
    v = vid.lower()

    def _tail(sep: str) -> str:
        idx = v.find(sep)
        if idx < 0:
            return ""
        return vid[idx + len(sep):].lstrip("-_. ")

    if "neoforge" in v:
        return f"NeoForge {_tail('neoforge').split('-')[0]}".strip()
    if "quilt" in v:
        rest = _tail("quilt-loader-") or _tail("quilt")
        return f"Quilt {rest.split('-')[0]}".strip()
    if "fabric" in v:
        rest = _tail("fabric-loader-") or _tail("fabric")
        return f"Fabric {rest.split('-')[0]}".strip()
    if "optifine" in v:
        return f"OptiFine {_tail('optifine').lstrip('_')}".strip()
    if "forge" in v:
        return f"Forge {_tail('forge').split('-')[0]}".strip()
    return vid


def get_grouped_versions(mc_dir: str) -> list[dict]:
    """按基础版本分组（旧接口，UI 版本页仍在用）。

    返回:
    [
      {"id": "1.7.10", "type": "release", "children": [
          {"id": "1.7.10-Forge10.13.4.1614-1.7.10", "type": "release", "label": "Forge 10.13.4.1614"},
      ]},
      {"id": "1.21.1", "type": "release", "children": []},
    ]
    """
    all_vers = get_installed_versions(mc_dir)
    bases: dict[str, dict] = {}
    children: list[tuple[str, dict]] = []

    for v in all_vers:
        vid = str(v.get("id") or "")
        if not vid:
            continue
        parent = get_parent_version(mc_dir, vid)
        if parent:
            child = dict(v)
            child["label"] = loader_label(vid)
            children.append((parent, child))
        else:
            bases[vid] = {**v, "children": []}

    for parent_id, child in children:
        if parent_id in bases:
            bases[parent_id]["children"].append(child)
        else:
            bases[child["id"]] = {**child, "children": []}

    return list(bases.values())


# ═══════════════════ mods 目录 ═══════════════════

def get_mods_list(game_dir: str) -> list[str]:
    """列出 mods/ 文件夹里的 .jar 文件名。"""
    mods_dir = os.path.join(game_dir, "mods")
    if not os.path.isdir(mods_dir):
        return []
    try:
        return sorted(f for f in os.listdir(mods_dir) if f.lower().endswith(".jar"))
    except OSError as e:
        print(f"[java.version] 读取 mods 目录失败: {e}", file=sys.stderr)
        return []


def open_mods_folder(game_dir: str) -> str:
    """在文件管理器中打开 mods 文件夹（不存在则创建）。返回实际路径。"""
    if not game_dir or not os.path.isabs(game_dir):
        raise ValueError(f"游戏目录无效: {game_dir!r}，请先在设置里填写绝对路径。")
    mods_dir = os.path.join(game_dir, "mods")
    os.makedirs(mods_dir, exist_ok=True)
    from core.paths import open_folder
    return open_folder(mods_dir)
