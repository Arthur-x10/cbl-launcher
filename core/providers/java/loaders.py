"""Java 版 Mod 加载器 —— Forge / Fabric / Quilt / NeoForge 的版本枚举与安装。"""

import json
import os
import shutil
import warnings
from typing import Optional

import minecraft_launcher_lib

LOADERS = ("forge", "fabric", "quilt", "neoforge")

_LOADER_NAMES = {
    "forge": "Forge",
    "fabric": "Fabric",
    "quilt": "Quilt",
    "neoforge": "NeoForge",
}

# minecraft-launcher-lib 8.0 的 neoforge 通道只覆盖 1.20.2 及以上
_NEOFORGE_MIN_MC = "1.20.2"
_NEOFORGE_HINT = "NeoForge 需要 Minecraft 1.20.2 及以上；1.20.1 请改用 Forge。"


def loader_name(loader: str) -> str:
    return _LOADER_NAMES.get((loader or "").strip().lower(), loader or "")


def _mod_loader(loader: str):
    """minecraft-launcher-lib 8.0 的统一 ModLoader 句柄。"""
    return minecraft_launcher_lib.mod_loader.get_mod_loader(loader)


def _status(cb: Optional[dict], text: str):
    if cb and "setStatus" in cb:
        cb["setStatus"](text)


# ═══════════════════ 版本枚举 ═══════════════════

def get_forge_versions(mc_version: str) -> list[str]:
    """指定 MC 版本可用的 Forge 版本列表（形如 1.20.1-47.4.23）。"""
    try:
        versions = minecraft_launcher_lib.forge.list_forge_versions()
    except Exception:
        return []
    return [v for v in versions if v.startswith(mc_version + "-")]


def find_forge_version(mc_version: str) -> Optional[str]:
    """指定 MC 版本推荐的 Forge 版本。"""
    try:
        return minecraft_launcher_lib.forge.find_forge_version(mc_version)
    except Exception:
        return None


def get_fabric_versions() -> list[dict]:
    """所有可用的 Fabric Loader 版本（原始 dict：version / stable）。"""
    try:
        return minecraft_launcher_lib.fabric.get_all_loader_versions()
    except Exception:
        return []


def get_quilt_versions() -> list[dict]:
    """所有可用的 Quilt Loader 版本（原始 dict：version / stable）。"""
    try:
        return minecraft_launcher_lib.quilt.get_all_loader_versions()
    except Exception:
        return []


def _is_stable(raw_item: dict) -> bool:
    """Loader 版本是否稳定版。quilt 的接口不返回 stable 字段，按版本号里的 "-" 粗略判断。"""
    if "stable" in raw_item:
        return bool(raw_item["stable"])
    return "-" not in str(raw_item.get("version") or "")


def _version_strings(raw: list[dict]) -> list[str]:
    """稳定版优先，其次不稳定版；UI 直接拿去填下拉框。"""
    stable = [str(v.get("version")) for v in raw if _is_stable(v)]
    unstable = [str(v.get("version")) for v in raw if not _is_stable(v)]
    return stable + unstable


def neoforge_supported(mc_version: str) -> bool:
    """当前依赖库是否支持给这个 MC 版本装 NeoForge。"""
    try:
        return bool(_mod_loader("neoforge").is_minecraft_version_supported(mc_version))
    except Exception:
        return False


def get_neoforge_versions(mc_version: str) -> list[str]:
    """指定 MC 版本可用的 NeoForge 版本（新 → 旧）。

    实测 8.0 的 neoforge 通道只覆盖 1.20.2 及以上（1.20.1 的 47.x 构建既不在
    neoforge 通道，也不在 forge 通道），所以 1.20.1 返回空列表 —— UI 据此提示
    「需要 1.20.2+，请改用 Forge」。
    """
    try:
        ml = _mod_loader("neoforge")
        if not ml.is_minecraft_version_supported(mc_version):
            return []
        return list(ml.get_loader_versions(mc_version, False))
    except Exception:
        return []


def loader_options(mc_version: str) -> dict[str, list[str]]:
    """某个 MC 版本能装哪些加载器、各有哪些版本（UI 的加载器下拉框数据源）。"""
    return {
        "forge": get_forge_versions(mc_version),
        "fabric": _version_strings(get_fabric_versions()),
        "quilt": _version_strings(get_quilt_versions()),
        "neoforge": get_neoforge_versions(mc_version),
    }


# ═══════════════════ 安装后的版本目录 ═══════════════════

def _versions_dir(mc_dir: str) -> str:
    return os.path.join(mc_dir, "versions")


def _snapshot(mc_dir: str) -> set[str]:
    root = _versions_dir(mc_dir)
    try:
        return set(os.listdir(root))
    except OSError:
        return set()


def _pick_installed(mc_dir: str, before: set[str], expected: list[str]) -> str:
    """确定安装出的版本目录名：优先 expected，其次本次新增的目录。"""
    root = _versions_dir(mc_dir)
    for name in expected:
        if name and os.path.isdir(os.path.join(root, name)):
            return name
    new_dirs = sorted(_snapshot(mc_dir) - before)
    for name in new_dirs:
        if os.path.isdir(os.path.join(root, name)):
            return name
    return expected[0] if expected else ""


# ═══════════════════ Forge ═══════════════════

def install_forge(mc_dir: str, forge_version: str, cb: Optional[dict] = None) -> str:
    """安装 Forge（安装后自动修复老版本文件错位），返回版本目录名。

    forge_version: 形如 "1.20.4-49.0.30" 或 "1.7.10-10.13.4.1614"。
    """
    if not forge_version:
        raise RuntimeError("没有指定 Forge 版本。")
    before = _snapshot(mc_dir)
    _status(cb, f"正在安装 Forge {forge_version}…")
    # 老接口仍支持 1.7~1.12 的安装器；8.0 标了 DeprecationWarning，这里只是噪音
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        minecraft_launcher_lib.forge.install_forge_version(
            forge_version, mc_dir, callback=cb
        )
    _fix_forge_files(mc_dir, forge_version)

    mc_ver, _sep, forge_num = forge_version.partition("-")
    expected = [
        f"{mc_ver}-forge-{forge_num}",
        f"{mc_ver}-Forge{forge_num}-{mc_ver}",
        f"{mc_ver}-Forge{forge_num}",
        f"{mc_ver}-forge-{forge_num}",
    ]
    return _pick_installed(mc_dir, before, expected)


def _fix_forge_files(mc_dir: str, forge_version: str = ""):
    """修复老版本 Forge 安装后 JSON/JAR 文件错位。

    minecraft-launcher-lib 对 1.7~1.12 的 Forge 可能创建:
      versions/Forge X.X.X-Y.Y.Y/Forge X.X.X-Y.Y.Y.json  (带空格，错)
    而正确的应该是:
      versions/{mc}-Forge{X.X.X}-{mc}/{mc}-Forge{X.X.X}-{mc}.json
    """
    ver_dir = _versions_dir(mc_dir)
    if not os.path.isdir(ver_dir):
        return

    for name in os.listdir(ver_dir):
        full = os.path.join(ver_dir, name)
        if not os.path.isdir(full):
            continue
        if not name.startswith("Forge "):
            continue
        json_path = os.path.join(full, f"{name}.json")
        if not os.path.isfile(json_path):
            continue

        target_name = _find_matching_forge_dir(ver_dir, name)
        if not target_name:
            continue

        target_dir = os.path.join(ver_dir, target_name)
        target_json = os.path.join(target_dir, f"{target_name}.json")

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

        src_jar = os.path.join(full, f"{name}.jar")
        dst_jar = os.path.join(target_dir, f"{target_name}.jar")
        if os.path.isfile(src_jar) and not os.path.isfile(dst_jar):
            shutil.copy2(src_jar, dst_jar)

        # 只有目标文件确实齐了才删源目录，避免半途失败把唯一副本删掉
        if not os.path.isfile(target_json):
            continue
        if os.path.isfile(src_jar) and not os.path.isfile(dst_jar):
            continue
        try:
            shutil.rmtree(full)
        except Exception:
            pass


def _find_matching_forge_dir(ver_dir: str, wrong_name: str) -> Optional[str]:
    """从 'Forge X.X.X-Y.Y.Y' 精确推导对应的正确目录名。

    只做版本号精确比对，不用子串交集 —— 旧实现会把 1.7.10 和 1.12.2
    的 Forge 认成同一个目录，进而覆盖并删除别人的版本目录。
    """
    body = wrong_name[len("Forge "):].strip()      # 例：10.13.4.1614-1.7.10
    parts = body.split("-")
    if len(parts) < 2:
        return None
    forge_num = parts[0]
    mc_ver = "-".join(parts[1:])
    for cand in (
        f"{mc_ver}-Forge{forge_num}-{mc_ver}",
        f"{mc_ver}-Forge{forge_num}",
        f"{mc_ver}-forge-{forge_num}",
    ):
        if os.path.isdir(os.path.join(ver_dir, cand)):
            return cand
    return None


# ═══════════════════ Fabric / Quilt ═══════════════════

def install_fabric(mc_dir: str, mc_version: str,
                   loader_version: Optional[str] = None,
                   cb: Optional[dict] = None) -> str:
    """安装 Fabric，返回版本目录名。"""
    before = _snapshot(mc_dir)
    _status(cb, f"正在安装 Fabric（MC {mc_version}）…")
    kw = {"callback": cb}
    if loader_version:
        kw["loader_version"] = loader_version
    minecraft_launcher_lib.fabric.install_fabric(mc_version, mc_dir, **kw)
    expected = []
    try:
        ml = _mod_loader("fabric")
        lv = loader_version or ml.get_latest_loader_version(mc_version)
        expected.append(ml.get_installed_version(mc_version, lv))
    except Exception:
        pass
    expected.append(f"fabric-loader-{loader_version or ''}-{mc_version}")
    return _pick_installed(mc_dir, before, expected)


def install_quilt(mc_dir: str, mc_version: str,
                  loader_version: Optional[str] = None,
                  cb: Optional[dict] = None) -> str:
    """安装 Quilt，返回版本目录名。"""
    before = _snapshot(mc_dir)
    _status(cb, f"正在安装 Quilt（MC {mc_version}）…")
    kw = {"callback": cb}
    if loader_version:
        kw["loader_version"] = loader_version
    minecraft_launcher_lib.quilt.install_quilt(mc_version, mc_dir, **kw)
    expected = []
    try:
        ml = _mod_loader("quilt")
        lv = loader_version or ml.get_latest_loader_version(mc_version)
        expected.append(ml.get_installed_version(mc_version, lv))
    except Exception:
        pass
    expected.append(f"quilt-loader-{loader_version or ''}-{mc_version}")
    return _pick_installed(mc_dir, before, expected)


# ═══════════════════ NeoForge ═══════════════════

def _guess_neoforge_mc_version(ml, neoforge_version: str) -> Optional[str]:
    """从 NeoForge 版本号反查对应 MC 版本。

    现代命名 21.1.77 → 1.21.1、20.4.237 → 1.20.4；
    早期 1.20.1 用的是 47.x 命名，前缀规则推不出来，退回接口枚举。
    """
    parts = neoforge_version.split(".")
    if len(parts) >= 2 and parts[0].isdigit():
        cand = f"1.{parts[0]}.{parts[1]}"
        try:
            if ml.is_minecraft_version_supported(cand):
                if neoforge_version in ml.get_loader_versions(cand, False):
                    return cand
        except Exception:
            pass
    try:
        for mv in list(ml.get_minecraft_versions(True)):
            try:
                if neoforge_version in ml.get_loader_versions(mv, False):
                    return mv
            except Exception:
                continue
    except Exception:
        pass
    return None


def install_neoforge(mc_dir: str, neoforge_version: str = "",
                     cb: Optional[dict] = None,
                     mc_version: Optional[str] = None) -> str:
    """安装 NeoForge（走 8.0 的 mod_loader），返回版本目录名。

    mc_version 已知时直接传进来（避免网络反查）；否则按版本号推断。
    不支持的情况抛出可读的 RuntimeError，由 UI 原样展示。
    """
    ml = _mod_loader("neoforge")

    target_mc = (mc_version or "").strip()
    if target_mc and not ml.is_minecraft_version_supported(target_mc):
        raise RuntimeError(
            f"当前依赖库不支持为 Minecraft {target_mc} 安装 NeoForge。\n{_NEOFORGE_HINT}"
        )

    version = (neoforge_version or "").strip()
    if not version:
        if not target_mc:
            raise RuntimeError(f"没有指定 NeoForge 版本。\n{_NEOFORGE_HINT}")
        try:
            version = ml.get_latest_loader_version(target_mc)
        except Exception as e:
            raise RuntimeError(
                f"无法获取 Minecraft {target_mc} 的 NeoForge 版本列表。\n{_NEOFORGE_HINT}\n{e}"
            ) from e

    if not target_mc:
        target_mc = _guess_neoforge_mc_version(ml, version) or ""
        if not target_mc:
            raise RuntimeError(
                f"无法确定 NeoForge {version} 对应的 Minecraft 版本。\n{_NEOFORGE_HINT}"
            )
        if not ml.is_minecraft_version_supported(target_mc):
            raise RuntimeError(
                f"当前依赖库不支持为 Minecraft {target_mc} 安装 NeoForge。\n{_NEOFORGE_HINT}"
            )

    _status(cb, f"正在安装 NeoForge {version}（MC {target_mc}）…")
    before = _snapshot(mc_dir)
    installed = ml.install(target_mc, mc_dir, loader_version=version, callback=cb)
    try:
        expected = [installed, ml.get_installed_version(target_mc, version)]
    except Exception:
        expected = [installed or ""]
    return _pick_installed(mc_dir, before, expected)


# ═══════════════════ 统一入口 ═══════════════════

def install_loader(mc_dir: str, mc_version: str, loader: str,
                   loader_version: str = "", cb: Optional[dict] = None) -> str:
    """安装加载器并返回安装出的版本 id。

    loader: forge / fabric / quilt / neoforge
    loader_version:
      forge   —— 全 id（1.20.1-47.4.23）或纯版本号（47.4.23）都接受，空 = 推荐版
      fabric / quilt —— Loader 版本号，空 = 最新
      neoforge —— 版本号（21.1.77），空 = 最新
    """
    loader = (loader or "").strip().lower()
    if loader not in LOADERS:
        raise ValueError(f"未知的加载器: {loader!r}（可选 {', '.join(LOADERS)}）")
    if not (mc_version or "").strip():
        raise ValueError("没有指定 Minecraft 版本。")
    mc_version = mc_version.strip()
    lv = (loader_version or "").strip()

    if loader == "forge":
        fv = lv
        if fv and not fv.startswith(mc_version + "-"):
            fv = f"{mc_version}-{fv}"
        if not fv:
            fv = find_forge_version(mc_version) or ""
            if not fv:
                versions = get_forge_versions(mc_version)
                fv = versions[0] if versions else ""
            if not fv:
                raise RuntimeError(f"找不到 Minecraft {mc_version} 可用的 Forge 版本。")
        return install_forge(mc_dir, fv, cb)

    if loader == "fabric":
        return install_fabric(mc_dir, mc_version, lv or None, cb)

    if loader == "quilt":
        return install_quilt(mc_dir, mc_version, lv or None, cb)

    return install_neoforge(mc_dir, lv, cb, mc_version=mc_version)
