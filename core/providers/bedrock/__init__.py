r"""基岩版（Bedrock / UWP）provider。

边界（诚实实现，不伪造能力）
---------------------------
Windows 上的基岩版是 AppX/UWP 包，由 Microsoft Store 交付与更新。第三方启动器：
  * 不能安装、不能降级、不能替换游戏文件；
  * 不能注入账号（登录走 Xbox 账户，令牌从不经过启动器）；
  * 只能把已安装的包唤醒。

所以这里只做三件事：
  1. 探测本机已安装的包（HKCU AppModel 仓库 -> %LOCALAPPDATA%\Packages  ->
     C:\Program Files\WindowsApps 依次回退，任一步失败都不抛异常）；
  2. explorer.exe shell:appsFolder\<AUMID> 唤醒游戏；
  3. 把 .mcpack / .mcaddon / .mcworld 解到 com.mojang 对应目录。

capabilities() 里因此没有 VERSION_LIST / MODLOADER / JVM：UI 不该给这个产品画
「选版本」「装 Forge」「调内存」这些面板。

数据目录（存档/包都在包数据目录里，不在 .minecraft）
--------------------------------------------------
%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe\LocalState\games\com.mojang
    behavior_packs/    行为包
    resource_packs/    资源包
    skin_packs/        皮肤包
    world_templates/   世界模板
    minecraftWorlds/   世界（一个文件夹 = 一个世界）
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
import tempfile
import time
import zipfile

from core.providers.base import (
    CAP_PACK_IMPORT,
    CAP_STORE,
    GameVersion,
    Instance,
    LaunchError,
    LaunchHandle,
)

IS_WINDOWS = sys.platform == "win32"

PACKAGE_NAME = "Microsoft.MinecraftUWP"
PUBLISHER_ID = "8wekyb3d8bbwe"
PACKAGE_FAMILY_NAME = PACKAGE_NAME + "_" + PUBLISHER_ID
APP_ID = "App"
# AppUserModelID 用「包族名!AppId」，不带版本号 —— 所以游戏升级后照样能唤醒。
AUMID = PACKAGE_FAMILY_NAME + "!" + APP_ID

_REGISTRY_PACKAGES = (
    r"Software\Classes\Local Settings\Software\Microsoft\Windows"
    r"\CurrentVersion\AppModel\Repository\Packages"
)

# Microsoft.MinecraftUWP_1.21.44.1_x64__8wekyb3d8bbwe
_PKG_NAME_RE = re.compile(
    r"^" + re.escape(PACKAGE_NAME) + r"_(?P<version>\d+(?:\.\d+){1,3})_(?P<arch>[^_]+)__"
    + re.escape(PUBLISHER_ID) + r"$",
    re.IGNORECASE,
)

# manifest 里的模块类型 -> (com.mojang 下的目录, 中文名)；判定顺序即优先级。
_CATEGORY_BY_TYPE = {
    "data": ("behavior_packs", "行为包"),
    "behavior": ("behavior_packs", "行为包"),
    "behavior_pack": ("behavior_packs", "行为包"),
    "resources": ("resource_packs", "资源包"),
    "resource": ("resource_packs", "资源包"),
    "resource_pack": ("resource_packs", "资源包"),
    "script": ("resource_packs", "资源包"),
    "skin": ("skin_packs", "皮肤包"),
    "skin_pack": ("skin_packs", "皮肤包"),
    "world_template": ("world_templates", "世界模板"),
}
_TYPE_PRIORITY = (
    "data", "behavior", "behavior_pack",
    "resources", "resource", "resource_pack",
    "skin", "skin_pack",
    "world_template",
    "script",
)

_WINDOWS_RESERVED = frozenset(
    "CON PRN AUX NUL COM1 COM2 COM3 COM4 COM5 COM6 COM7 COM8 COM9 "
    "LPT1 LPT2 LPT3 LPT4 LPT5 LPT6 LPT7 LPT8 LPT9".split()
)

_MAX_MANIFEST_BYTES = 1024 * 1024


# ────────────────────────── 小工具 ──────────────────────────


def _local_appdata() -> str:
    return os.environ.get("LOCALAPPDATA", "") or os.path.join(
        os.path.expanduser("~"), "AppData", "Local")


def _packages_root() -> str:
    return os.path.join(_local_appdata(), "Packages")


def _version_key(version: str) -> tuple:
    parts = []
    for chunk in str(version or "").split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _program_files_roots() -> list:
    roots = []
    for env in ("ProgramW6432", "ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env, "")
        if base:
            roots.append(os.path.join(base, "WindowsApps"))
    roots.append(os.path.join(r"C:\Program Files", "WindowsApps"))
    out = []
    seen = set()
    for root in roots:
        key = os.path.normcase(root)
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def _report(cb, text: str) -> None:
    """把状态推给 UI 的回调字典（{"setStatus": fn, ...}），失败静默。"""
    if not isinstance(cb, dict):
        return
    fn = cb.get("setStatus")
    if callable(fn):
        try:
            fn(text)
        except Exception:
            pass


def _cancel_of(cb):
    """从 UI 的回调字典里取取消查询函数；没有就返回 None。"""
    if isinstance(cb, dict):
        fn = cb.get("isCancelled") or cb.get("is_cancelled")
    else:
        fn = getattr(cb, "is_cancelled", None)
    return fn if callable(fn) else None


def _safe_extract(zip_file: zipfile.ZipFile, dest: str) -> None:
    """解压并防 zip slip：每个成员的 realpath 必须落在 dest 里。

    规则：拒绝绝对路径、盘符、含 .. 的条目；符号链接一律跳过。
    与 core/providers/java 里 pack 导入同一个思路（这里独立实现，避免跨产品依赖）。
    """
    dest_real = os.path.realpath(dest)
    os.makedirs(dest_real, exist_ok=True)
    prefix = dest_real + os.sep
    for info in zip_file.infolist():
        name = (info.filename or "").replace("\\", "/")
        if not name or name.endswith("/"):
            continue
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            raise ValueError("包里有绝对路径条目：" + name)
        parts = [p for p in name.split("/") if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            raise ValueError("包里有越界路径条目：" + name)
        target = os.path.realpath(os.path.join(dest_real, *parts))
        if not (target == dest_real or target.startswith(prefix)):
            raise ValueError("包里有越界路径条目：" + name)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:          # 符号链接
            continue
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with zip_file.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out, 256 * 1024)


def _read_manifest(zip_file: zipfile.ZipFile) -> dict:
    try:
        raw = zip_file.read("manifest.json")
    except (KeyError, OSError, RuntimeError):
        return {}
    if not raw or len(raw) > _MAX_MANIFEST_BYTES:
        return {}
    try:
        data = json.loads(raw.decode("utf-8-sig", "replace"))
    except (ValueError, UnicodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _manifest_types(manifest: dict) -> list:
    seen = []
    header = manifest.get("header") if isinstance(manifest.get("header"), dict) else {}
    for key in ("module_type", "type"):
        value = header.get(key)
        if isinstance(value, str) and value.strip():
            seen.append(value.strip().lower())
    modules = manifest.get("modules")
    if isinstance(modules, list):
        for module in modules:
            if isinstance(module, dict):
                value = module.get("type")
                if isinstance(value, str) and value.strip():
                    seen.append(value.strip().lower())
    out = []
    for item in seen:
        if item not in out:
            out.append(item)
    return out


def _category_of(manifest: dict) -> tuple:
    types = _manifest_types(manifest)
    for want in _TYPE_PRIORITY:
        if want in types:
            return _CATEGORY_BY_TYPE[want]
    return ("", "")


def _manifest_uuid(manifest: dict) -> str:
    header = manifest.get("header") if isinstance(manifest.get("header"), dict) else {}
    value = header.get("uuid")
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    modules = manifest.get("modules")
    if isinstance(modules, list):
        for module in modules:
            if isinstance(module, dict):
                value = module.get("uuid")
                if isinstance(value, str) and value.strip():
                    return value.strip().lower()
    return ""


def _pack_title(manifest: dict, fallback: str) -> str:
    header = manifest.get("header") if isinstance(manifest.get("header"), dict) else {}
    for key in ("name", "description"):
        value = header.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _safe_folder(name: str, uid: str) -> str:
    """把包名变成合法目录名：保留中英文数字，非法字符换下划线，附 uuid 前 8 位防撞。"""
    chars = []
    for ch in str(name or ""):
        if ch.isalnum() or ch in " _-.":
            chars.append(ch)
        elif ch in '\\/:*?"<>|':
            chars.append("_")
        else:
            chars.append(" ")
    base = "".join(chars).strip(" ._-")[:48].strip(" ._-") or "pack"
    if base.split(".")[0].upper() in _WINDOWS_RESERVED:
        base = "pack_" + base
    suffix = (str(uid or "")).replace("-", "")[:8] or "import"
    return base + "_" + suffix


def _random_id(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def _new_world_id(worlds_dir: str) -> str:
    for _ in range(24):
        candidate = _random_id(16)
        if not os.path.exists(os.path.join(worlds_dir, candidate)):
            return candidate
    return _random_id(20)


def _find_pack_by_uuid(base_dir: str, uid: str) -> str:
    """在已安装的包目录里找同一个 uuid（同包换名重装也能认出来）。"""
    if not uid:
        return ""
    try:
        entries = list(os.scandir(base_dir))
    except OSError:
        return ""
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        manifest_path = os.path.join(entry.path, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "rb") as fh:
                raw = fh.read(_MAX_MANIFEST_BYTES)
            data = json.loads(raw.decode("utf-8-sig", "replace"))
        except (OSError, ValueError, UnicodeError):
            continue
        if isinstance(data, dict) and _manifest_uuid(data) == uid:
            return entry.path
    return ""


# ────────────────────────── provider ──────────────────────────


class BedrockProvider:
    id = "bedrock"
    name = "基岩版"

    def __init__(self, ctx=None):
        self.ctx = ctx
        self.mc_dir = (getattr(ctx, "mc_dir", "") or "") if ctx is not None else ""
        self._cache = None
        self._cache_at = 0.0
        self._errors = []
        self._cache_ttl = 30.0

    # ── 能力 ──

    def capabilities(self) -> set:
        return {CAP_STORE, CAP_PACK_IMPORT}

    def list_remote(self):
        """商店托管，没有可枚举的远端版本列表。"""
        return None

    # ── 探测 ──

    def data_dir(self) -> str:
        """com.mojang 目录（存档/包都在这里）。非 Windows 返回空串。"""
        if not IS_WINDOWS:
            return ""
        return os.path.join(
            _packages_root(), PACKAGE_FAMILY_NAME,
            "LocalState", "games", "com.mojang")

    def is_installed(self) -> bool:
        if not IS_WINDOWS:
            return False
        return self._detect() is not None

    def _detect(self, force: bool = False):
        now = time.monotonic()
        if not force and self._cache is not None and (now - self._cache_at) < self._cache_ttl:
            return self._cache
        info = None
        errors = []
        for probe in (self._probe_registry, self._probe_local_packages, self._probe_windows_apps):
            try:
                found = probe()
            except Exception as exc:          # 探测失败绝不能把启动器带崩
                errors.append(probe.__name__ + ": " + str(exc))
                continue
            if found:
                info = found
                break
        self._errors = errors
        self._cache = info
        self._cache_at = now
        return info

    def _probe_registry(self):
        if not IS_WINDOWS:
            return None
        try:
            import winreg
        except Exception:
            return None
        entries = []
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REGISTRY_PACKAGES, 0, winreg.KEY_READ)
        except OSError:
            return None
        try:
            index = 0
            while True:
                try:
                    sub = winreg.EnumKey(key, index)
                except OSError:
                    break
                index += 1
                match = _PKG_NAME_RE.match(sub)
                if not match:
                    continue
                entries.append({
                    "package_full_name": sub,
                    "version": match.group("version"),
                    "arch": match.group("arch"),
                    "source": "registry",
                })
        finally:
            try:
                winreg.CloseKey(key)
            except Exception:
                pass
        if not entries:
            return None
        entries.sort(key=lambda item: _version_key(item.get("version", "")), reverse=True)
        return entries[0]

    def _probe_local_packages(self):
        if not IS_WINDOWS:
            return None
        package_dir = os.path.join(_packages_root(), PACKAGE_FAMILY_NAME)
        try:
            if not os.path.isdir(package_dir):
                return None
        except OSError:
            return None
        return {
            "package_full_name": PACKAGE_FAMILY_NAME,
            "version": "",
            "arch": "",
            "source": "localappdata",
            "package_dir": package_dir,
        }

    def _probe_windows_apps(self):
        if not IS_WINDOWS:
            return None
        entries = []
        for root in _program_files_roots():
            try:
                names = os.listdir(root)
            except OSError:
                continue            # WindowsApps 通常读不了，静默跳过
            for name in names:
                match = _PKG_NAME_RE.match(name)
                if match:
                    entries.append({
                        "package_full_name": name,
                        "version": match.group("version"),
                        "arch": match.group("arch"),
                        "source": "windowsapps",
                    })
        if not entries:
            return None
        entries.sort(key=lambda item: _version_key(item.get("version", "")), reverse=True)
        return entries[0]

    def probe_detail(self) -> dict:
        """给 UI / 自检用的探测明细（含耗时与失败原因）。"""
        started = time.perf_counter()
        info = self._detect(force=True)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        data_dir = self.data_dir()
        return {
            "installed": bool(info),
            "version": (info or {}).get("version", ""),
            "package_family_name": PACKAGE_FAMILY_NAME,
            "package_full_name": (info or {}).get("package_full_name", ""),
            "source": (info or {}).get("source", ""),
            "aumid": AUMID,
            "data_dir": data_dir,
            "data_dir_exists": bool(data_dir) and os.path.isdir(data_dir),
            "platform_supported": IS_WINDOWS,
            "elapsed_ms": elapsed,
            "probe_errors": list(self._errors),
        }

    # ── 版本列表 / 安装 ──

    def list_installed(self) -> list:
        if not IS_WINDOWS:
            return []
        info = self._detect()
        if not info:
            return []
        version = info.get("version") or ""
        display = ("基岩版 " + version) if version else "基岩版（已安装）"
        return [GameVersion(
            provider=self.id,
            id=version or "installed",
            display=display,
            kind="store",
            installed=True,
            meta={
                "package_family_name": PACKAGE_FAMILY_NAME,
                "package_full_name": info.get("package_full_name", ""),
                "version": version,
                "aumid": AUMID,
                "data_dir": self.data_dir(),
                "source": info.get("source", ""),
                "can_install": False,
                "can_uninstall": False,
            },
        )]

    # ── 商店元数据（只读，不承诺能下载） ──

    def store_info(self) -> dict:
        """商店里这个产品的公开元数据。拿不到就返回 {}，不抛。"""
        try:
            from core.providers.bedrock import store as _store
            return _store.fetch_info()
        except Exception as e:  # noqa: BLE001 — 商店接口挂了不该影响启动器
            print("[bedrock] 取商店信息失败: %s" % e, file=sys.stderr)
            return {}

    def store_state(self) -> dict:
        """商店元数据 + 本机安装状态，给「商店页」那一栏用。"""
        info = self.store_info()
        probe = self.probe_detail()
        return {
            "title": info.get("title") or "Minecraft for Windows",
            "size_text": info.get("size_text") or "",
            "updated_date": info.get("updated_date") or "",
            "package_formats": info.get("package_formats") or [],
            "market": info.get("market") or "",
            "apps_url": info.get("apps_url") or "",
            "installed": bool(probe.get("installed")),
            "local_version": probe.get("version") or "",
            "package_full_name": probe.get("package_full_name") or "",
            "data_dir": probe.get("data_dir") or "",
            "data_dir_exists": bool(probe.get("data_dir_exists")),
            "can_download": False,
        }

    # ── 其他获取渠道 ──

    def download_channels(self) -> list:
        """能真下载的官方安装包（启动器 MSI / GameCore / 教育版）+ 只能给链接的渠道。"""
        try:
            from core.providers.bedrock import channels as _ch
            items = _ch.list_channels()
            return items + [dict(x, resolved=False, size_text="", url=x.get("url", ""))
                            for x in _ch.LINKS_ONLY]
        except Exception as e:  # noqa: BLE001
            print("[bedrock] 解析下载渠道失败: %s" % e, file=sys.stderr)
            return []

    def download_channel(self, channel_id: str, dst: str, cb=None) -> str:
        """下载某个渠道的安装包。返回本地路径。"""
        from core.providers.bedrock import channels as _ch
        item = _ch.find_channel(channel_id)
        if not item:
            raise LaunchError("没有这个下载渠道：" + str(channel_id))
        _report(cb, "正在下载 " + (item.get("file_name") or item.get("name") or channel_id))
        cancel = _cancel_of(cb)

        def progress(done, total):
            pct = int(done * 100 / total) if total else 0
            _report(cb, "下载 %s（%d%%，%s / %s）" % (
                item.get("name") or channel_id, pct,
                _ch.human_size(done), _ch.human_size(total)))

        return _ch.download(item, dst, progress=progress, cancel=cancel)

    def open_store(self, target: str = "pdp") -> tuple:
        """打开商店页（pdp=详情页 / updates=下载与更新）。"""
        try:
            from core.providers.bedrock import store as _store
            uri = _store.STORE_UPDATES if str(target).lower() == "updates" else _store.STORE_PDP
            return _store.open_store(uri)
        except Exception as e:  # noqa: BLE001
            return False, "打不开商店页：%s" % e

    def install(self, version, cb=None):
        raise LaunchError(
            "基岩版客户端只能由 Microsoft Store 交付：商店里是加密的 MSIXVC 容器，"
            "下载需要你自己的账号持有这个游戏的许可，第三方启动器拿不到可安装的包。"
            "请用「在商店中打开」按钮安装或更新。")

    def uninstall(self, version_id: str):
        return False, "基岩版请在 Windows 设置里卸载"

    def version_size_mb(self, version_id: str) -> float:
        return 0.0

    # ── 启动 ──

    def launch(self, instance: Instance, auth=None, cb=None, force: bool = False) -> LaunchHandle:
        if not IS_WINDOWS:
            raise LaunchError("基岩版仅 Windows 支持")
        info = self._detect(force=True)
        if info is None and not force:
            raise LaunchError(
                "没有检测到已安装的基岩版。请先在 Microsoft Store 安装 Minecraft（基岩版），"
                "或用开始菜单的 Minecraft 启动一次确认能跑。"
                "（账号由 Xbox 管理，启动器既不能安装也不能注入登录。）")
        _report(cb, "正在唤醒基岩版…")
        try:
            subprocess.Popen(["explorer.exe", "shell:appsFolder\\" + AUMID], close_fds=True)
        except FileNotFoundError:
            raise LaunchError("找不到 explorer.exe，无法通过 shell:appsFolder 唤醒基岩版")
        except OSError as exc:
            raise LaunchError("唤醒基岩版失败：" + str(exc))
        _report(cb, "已交给系统唤醒")
        return LaunchHandle(process=None, pid=0, note="已交给系统唤醒")

    # ── 包 / 世界导入（扩展方法，UI 用 getattr 探测） ──

    def import_pack(self, path: str) -> tuple:
        if not IS_WINDOWS:
            return False, "基岩版仅 Windows 支持，导入功能不可用"
        raw = str(path or "").strip()
        if not raw:
            return False, "没有选择文件"
        src = os.path.abspath(raw)
        if os.path.isdir(src):
            return False, "这是一个文件夹，不是包文件：" + src
        if not os.path.isfile(src):
            return False, "文件不存在：" + src
        ext = os.path.splitext(src)[1].lower()
        if ext == ".mcworld":
            return self._import_world(src)
        if ext == ".mcpack":
            return self._import_mcpack(src)
        if ext == ".mcaddon":
            return self._import_mcaddon(src)
        return False, "只支持 .mcpack / .mcaddon / .mcworld，当前是 " + (ext or "无扩展名")

    def _import_mcaddon(self, path: str) -> tuple:
        if not zipfile.is_zipfile(path):
            return False, ".mcaddon 不是有效的 zip：" + os.path.basename(path)
        tmp = tempfile.mkdtemp(prefix="cbl-mcaddon-")
        try:
            with zipfile.ZipFile(path) as zf:
                try:
                    _safe_extract(zf, tmp)
                except ValueError as exc:
                    return False, "拒绝导入：" + str(exc)
            packs = []
            for root, _dirs, files in os.walk(tmp):
                for name in files:
                    if name.lower().endswith(".mcpack"):
                        packs.append(os.path.join(root, name))
            if not packs:
                return False, ".mcaddon 里没有 .mcpack（这个文件可能是 .mcworld，或已损坏）"
            done = []
            failed = []
            for pack in sorted(packs):
                ok, message = self._import_mcpack(pack)
                if ok:
                    done.append(message)
                else:
                    failed.append(os.path.basename(pack) + "：" + message)
            if done and not failed:
                return True, "已导入 " + str(len(done)) + " 个包：" + "；".join(done)
            if done and failed:
                return True, ("已导入 " + str(len(done)) + " 个包，另有 " + str(len(failed))
                              + " 个跳过：" + "；".join(failed))
            return False, "一个包都没导入：" + "；".join(failed)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _import_mcpack(self, path: str) -> tuple:
        root = self.data_dir()
        if not root:
            return False, "拿不到基岩版数据目录（%LOCALAPPDATA% 不可用）"
        if not zipfile.is_zipfile(path):
            return False, "不是有效的 zip：" + os.path.basename(path)
        with zipfile.ZipFile(path) as zf:
            manifest = _read_manifest(zf)
            if not manifest:
                return False, "包里没有 manifest.json，不是有效的基岩版包：" + os.path.basename(path)
            folder, label = _category_of(manifest)
            if not folder:
                return False, ("manifest.json 里没有可识别的包类型（modules[].type / header.module_type），"
                               "无法判断该放进哪个目录：" + os.path.basename(path))
            uid = _manifest_uuid(manifest)
            base = os.path.join(root, folder)
            try:
                os.makedirs(base, exist_ok=True)
            except OSError as exc:
                return False, "无法创建目录 " + base + "：" + str(exc)
            same = _find_pack_by_uuid(base, uid) if uid else ""
            if same:
                return False, ("这个" + label + "已经装过了（" + os.path.basename(same)
                               + "），没有覆盖；要更新请先在游戏里删掉旧包")
            title = _pack_title(manifest, os.path.splitext(os.path.basename(path))[0])
            name = _safe_folder(title, uid or path)
            dest = os.path.join(base, name)
            if os.path.exists(dest):
                return False, ("同名" + label + "已存在（" + name
                               + "），没有覆盖；要更新请先在游戏里删掉旧包")
            tmp = tempfile.mkdtemp(prefix=".cbl-pack-", dir=base)
            try:
                try:
                    _safe_extract(zf, tmp)
                except ValueError as exc:
                    return False, "拒绝导入：" + str(exc)
                os.replace(tmp, dest)
            except OSError as exc:
                return False, "写入失败：" + str(exc)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        return True, "已导入" + label + "「" + title + "」→ " + folder + "/" + name

    def _import_world(self, path: str) -> tuple:
        root = self.data_dir()
        if not root:
            return False, "拿不到基岩版数据目录（%LOCALAPPDATA% 不可用）"
        if not zipfile.is_zipfile(path):
            return False, ".mcworld 不是有效的 zip：" + os.path.basename(path)
        worlds = os.path.join(root, "minecraftWorlds")
        try:
            os.makedirs(worlds, exist_ok=True)
        except OSError as exc:
            return False, "无法创建目录 " + worlds + "：" + str(exc)
        tmp = ""
        try:
            tmp = tempfile.mkdtemp(prefix=".cbl-world-", dir=worlds)
            with zipfile.ZipFile(path) as zf:
                names = [(item.filename or "").replace("\\", "/")
                         for item in zf.infolist() if not item.is_dir()]
                if not any(n == "level.dat" or n.endswith("/level.dat") for n in names):
                    return False, "这个 .mcworld 里没有 level.dat，不是有效的基岩版世界存档"
                try:
                    _safe_extract(zf, tmp)
                except ValueError as exc:
                    return False, "拒绝导入：" + str(exc)
            content = tmp
            if not os.path.isfile(os.path.join(content, "level.dat")):
                dirs = [d for d in os.listdir(content)
                        if os.path.isdir(os.path.join(content, d))]
                if len(dirs) == 1 and os.path.isfile(os.path.join(content, dirs[0], "level.dat")):
                    content = os.path.join(content, dirs[0])
                else:
                    return False, ("解压后找不到 level.dat，存档结构不标准："
                                   + os.path.basename(path))
            world_id = _new_world_id(worlds)
            dest = os.path.join(worlds, world_id)
            shutil.move(content, dest)
            title = os.path.splitext(os.path.basename(path))[0].strip() or "导入的世界"
            name_file = os.path.join(dest, "levelname.txt")
            if not os.path.isfile(name_file):
                try:
                    with open(name_file, "w", encoding="utf-8", newline="") as fh:
                        fh.write(title)
                except OSError:
                    pass
            return True, ("已导入世界「" + title + "」→ minecraftWorlds/" + world_id
                          + "（重启游戏后出现在「世界」列表里）")
        except zipfile.BadZipFile:
            return False, "这个 .mcworld 已损坏，无法解压"
        except OSError as exc:
            return False, "写入失败：" + str(exc)
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)


def create_provider(ctx) -> BedrockProvider:
    """providers/__init__.ensure() 的工厂入口。"""
    return BedrockProvider(ctx)
