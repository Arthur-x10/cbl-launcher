"""服务端 provider —— 目前只做基岩版官方服务端（BDS）。

Java 版服务端（forge/fabric 的 server jar + 启动脚本）不在这里：那套要拼 classpath、
要跟 Java provider 共用 libraries/versions，归 Java provider 的后续工作。

边界
----
* 不下载：BDS 只有官网一个入口（minecraft.net/download/server/bedrock），没有可枚举的
  版本 API，所以 list_remote() 返回 None，install() 直接拒绝并告诉用户去官网；
* 不代勾 EULA：导入只解压，绝不写 eula.txt。启动前检查，没同意就报错并指出改哪一行 ——
  那是用户与 Mojang 的法律协议，启动器不能替用户点同意；
* 不做进程守护/自动重启：只提供 stdin 写命令（send_command）和日志尾部（tail）。

目录布局
--------
  <mc_dir>/instances/<instance_id>/server/                 BDS 解压目录 = 工作目录（cwd）
  <mc_dir>/instances/<instance_id>/server/logs/server-<时间>.log

进程句柄
--------
launch() 返回的 LaunchHandle.process 是 subprocess.Popen，额外挂了：
  _log_file  可读日志句柄（pump 线程写、退出后关闭）
  _log_path  日志文件路径（tail 用它）
  _stdin     子进程 stdin（send_command 用它）
stdout/stderr 合并后由后台线程原样落盘，BDS 不会因为管道写满而卡死。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile

from core.providers.base import (
    CAP_CONSOLE,
    CAP_INSTANCE_DIR,
    CAP_VERSION_LIST,
    GameVersion,
    Instance,
    LaunchError,
    LaunchHandle,
)

IS_WINDOWS = sys.platform == "win32"

# Windows 版是 bedrock_server.exe，Linux 版是同名的无扩展名二进制。
EXE_NAMES = ("bedrock_server.exe", "bedrock_server")

# eula.txt 里的有效行；注释行（#eula=false）不算。
_EULA_RE = re.compile(r"^[ \t]*eula[ \t]*=[ \t]*(\w+)", re.IGNORECASE | re.MULTILINE)

_TAIL_BYTES = 512 * 1024

# 实例元数据旁注文件：没有任何实例注册表时（例如用户把 server 目录拷来拷去），
# 靠它把「显示名 / zip 版本」带回来；BDS 只认自己的文件，忽略点开头的文件。
_INSTANCE_META_FILE = ".cbl-instance.json"


# ────────────────────────── 小工具 ──────────────────────────


def _now_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


def _report(cb, text: str) -> None:
    if not isinstance(cb, dict):
        return
    fn = cb.get("setStatus")
    if callable(fn):
        try:
            fn(text)
        except Exception:
            pass


def _safe_extract(zip_file: zipfile.ZipFile, dest: str) -> None:
    """解压并防 zip slip：成员 realpath 必须落在 dest 内。

    BDS zip 是官方包，但下载可能被中间人替换，所以按不可信输入处理。
    """
    dest_real = os.path.realpath(dest)
    os.makedirs(dest_real, exist_ok=True)
    prefix = dest_real + os.sep
    for info in zip_file.infolist():
        name = (info.filename or "").replace("\\", "/")
        if not name or name.endswith("/"):
            continue
        if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
            raise ValueError("zip 里有绝对路径条目：" + name)
        parts = [p for p in name.split("/") if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            raise ValueError("zip 里有越界路径条目：" + name)
        target = os.path.realpath(os.path.join(dest_real, *parts))
        if not (target == dest_real or target.startswith(prefix)):
            raise ValueError("zip 里有越界路径条目：" + name)
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            continue
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with zip_file.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out, 256 * 1024)


def _write_instance_meta(server_dir: str, inst: Instance) -> None:
    payload = {
        "provider": inst.provider,
        "id": inst.id,
        "name": inst.name,
        "version_id": inst.version_id,
        "created": inst.created,
    }
    try:
        with open(os.path.join(server_dir, _INSTANCE_META_FILE), "w",
                  encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _read_instance_meta(server_dir: str) -> dict:
    path = os.path.join(server_dir, _INSTANCE_META_FILE)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _move_children(src: str, dst: str) -> None:
    """把 src 下的内容搬进 dst；目标已存在的条目跳过，绝不覆盖。"""
    os.makedirs(dst, exist_ok=True)
    for entry in os.listdir(src):
        source = os.path.join(src, entry)
        target = os.path.join(dst, entry)
        if os.path.exists(target):
            continue
        shutil.move(source, target)


def _dir_size_mb(path: str) -> float:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    continue
    except OSError:
        return 0.0
    return round(total / (1024.0 * 1024.0), 1)


# ────────────────────────── provider ──────────────────────────


class ServerProvider:
    id = "server"
    name = "服务端"

    def __init__(self, ctx=None):
        self.ctx = ctx
        self.mc_dir = (getattr(ctx, "mc_dir", "") or "") if ctx is not None else ""
        self.store = getattr(ctx, "store", None) if ctx is not None else None
        self.instances_root = os.path.join(self.mc_dir, "instances") if self.mc_dir else ""

    # ── 能力 ──

    def capabilities(self) -> set:
        return {CAP_CONSOLE, CAP_INSTANCE_DIR, CAP_VERSION_LIST}

    # ── 官方 BDS 下载 ──

    def list_bds(self) -> list:
        """Mojang 公开链接接口里的 BDS 列表（只留 Windows 能跑的）。"""
        try:
            from core.providers.server import links as _links
            return [dict(x) for x in _links.fetch_links() if x.get("platform") == "win"]
        except Exception as e:  # noqa: BLE001 — 拿不到列表不该让整页崩
            print("[server] 取 BDS 链接失败: %s" % e, file=sys.stderr)
            return []

    def list_remote(self):
        """远端可下载的 BDS 版本（正式版 + 预览版）。"""
        out = []
        for item in self.list_bds():
            version = str(item.get("version") or "")
            kind = str(item.get("kind") or "bds")
            if not version:
                continue
            preview = kind.endswith("preview")
            out.append(GameVersion(
                provider=self.id,
                id=(version if not preview else "preview:" + version),
                display=(version if not preview else version + "（预览版）"),
                kind=("server-preview" if preview else "server"),
                installed=False,
                meta={
                    "version": version,
                    "url": item.get("url", ""),
                    "file_name": item.get("file_name", ""),
                    "kind": kind,
                    "preview": preview,
                },
            ))
        return out

    def _bds_item(self, version) -> dict:
        from core.providers.server import links as _links
        vid = str(getattr(version, "id", version) or "").strip()
        preview = vid.startswith("preview:")
        plain = vid.split(":", 1)[-1]
        want_kind = "bds-preview" if preview else "bds"
        for item in self.list_bds():
            if item.get("kind") != want_kind:
                continue
            if item.get("version") == plain:
                return dict(item)
        found = _links.find(plain)
        return dict(found) if found.get("platform") == "win" else {}

    def install(self, version, cb=None):
        """下载官方 BDS zip 并自动注册成实例。返回 Instance。"""
        item = self._bds_item(version)
        if not item:
            raise LaunchError("找不到这个 BDS 版本的官方下载链接（可能已经被下线）")
        url = item["url"]
        name = item.get("file_name") or ("bedrock-server-%s.zip" % item.get("version"))
        tmpdir = tempfile.mkdtemp(prefix="bds-dl-")
        zip_path = os.path.join(tmpdir, name)
        try:
            _report(cb, "正在下载 " + name)
            downloader = getattr(self.ctx, "downloader", None) if self.ctx is not None else None
            if downloader is None:
                from core.download import Downloader
                downloader = Downloader()
            cancel = None
            if isinstance(cb, dict):
                cancel = cb.get("isCancelled") or cb.get("is_cancelled")
            else:
                cancel = getattr(cb, "is_cancelled", None)

            def progress(done, total):
                pct = int(done * 100 / total) if total else 0
                _report(cb, "正在下载 %s（%d%%）" % (name, pct))

            downloader.download(
                url, zip_path, progress=progress,
                cancel=(lambda: bool(cancel())) if callable(cancel) else None,
                overwrite=True)
            if not os.path.isfile(zip_path) or os.path.getsize(zip_path) < 1024:
                raise LaunchError("下载下来的文件不完整：" + zip_path)
            _report(cb, "正在解压并注册实例")
            return self.import_zip(zip_path, "")
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def uninstall(self, version_id: str):
        return False, "服务端没有商店式卸载：在实例列表里「删除实例」即可（会删掉 server 目录）"

    # ── 磁盘约定 ──

    def find_exe(self, server_dir: str) -> str:
        """在目录里找 BDS 主程序（大小写不敏感，兼容 Windows/Linux 包）。"""
        if not server_dir or not os.path.isdir(server_dir):
            return ""
        try:
            entries = os.listdir(server_dir)
        except OSError:
            return ""
        lowered = {}
        for entry in entries:
            lowered.setdefault(entry.lower(), entry)
        for want in EXE_NAMES:
            actual = lowered.get(want)
            if not actual:
                continue
            candidate = os.path.join(server_dir, actual)
            if os.path.isfile(candidate):
                return candidate
        return ""

    def eula_state(self, server_dir: str) -> tuple:
        """返回 (状态, eula.txt 路径)；状态 = accepted / rejected / missing。"""
        path = os.path.join(server_dir or "", "eula.txt")
        if not server_dir or not os.path.isfile(path):
            return "missing", path
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
                text = fh.read(64 * 1024)
        except OSError:
            return "missing", path
        match = _EULA_RE.search(text)
        if match and match.group(1).strip().lower() in ("true", "1", "yes"):
            return "accepted", path
        return "rejected", path

    def _guess_version(self, server_dir: str, fallback: str) -> str:
        """BDS 不在目录里写版本号；优先用目录名兜底。"""
        for name in ("version.txt", "version.json"):
            path = os.path.join(server_dir, name)
            if os.path.isfile(path):
                try:
                    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
                        first = fh.readline().strip()
                except OSError:
                    continue
                if first:
                    return first[:64]
        return fallback

    def _ensure_instances_root(self) -> str:
        if not self.instances_root:
            raise LaunchError("没有可用的 .minecraft 目录，无法放服务端实例")
        try:
            os.makedirs(self.instances_root, exist_ok=True)
        except OSError as exc:
            raise LaunchError("无法创建实例目录 " + self.instances_root + "：" + str(exc))
        return self.instances_root

    # ── 实例发现 ──

    def server_list(self) -> list:
        """已安装的 BDS 实例：先看实例注册表，再扫 instances/*/server 兜底。"""
        items = []
        seen = set()

        def add(inst):
            directory = getattr(inst, "game_dir", "") or ""
            if not directory:
                return
            key = os.path.normcase(os.path.realpath(directory))
            if key in seen:
                return
            if not self.find_exe(directory):
                return
            seen.add(key)
            items.append(inst)

        store = self.store
        if store is not None:
            try:
                for inst in store.all():
                    if str(getattr(inst, "provider", "")) == self.id:
                        add(inst)
            except Exception:
                pass

        names = []
        if self.instances_root:
            try:
                names = sorted(os.listdir(self.instances_root))
            except OSError:
                names = []
        for name in names:
            server_dir = os.path.join(self.instances_root, name, "server")
            if not self.find_exe(server_dir):
                continue
            meta = _read_instance_meta(server_dir)
            add(Instance(
                id=str(meta.get("id") or name),
                name=str(meta.get("name") or name),
                provider=self.id,
                version_id=str(meta.get("version_id")
                               or self._guess_version(server_dir, name)),
                game_dir=server_dir,
                created=str(meta.get("created") or _now_iso()),
            ))
        items.sort(key=lambda inst: (str(inst.name).lower(), str(inst.id)))
        return items

    def list_installed(self) -> list:
        out = []
        for inst in self.server_list():
            state, eula_path = self.eula_state(inst.game_dir)
            out.append(GameVersion(
                provider=self.id,
                id=inst.id,
                display=inst.name or inst.id,
                kind="server",
                installed=True,
                meta={
                    "instance_id": inst.id,
                    "version_id": inst.version_id,
                    "game_dir": inst.game_dir,
                    "eula": state,
                    "eula_path": eula_path,
                },
            ))
        return out

    def version_size_mb(self, version_id: str) -> float:
        target = str(version_id or "")
        if not target:
            return 0.0
        for inst in self.server_list():
            if target in (inst.id, inst.version_id):
                return _dir_size_mb(inst.game_dir)
        return 0.0

    # ── 导入官方 BDS zip ──

    def import_zip(self, zip_path: str, name: str = "") -> Instance:
        raw = str(zip_path or "").strip()
        if not raw:
            raise LaunchError("没有选择 zip 文件")
        src = os.path.abspath(raw)
        if os.path.isdir(src):
            raise LaunchError("这是一个文件夹，请选官方 BDS 的 zip 文件：" + src)
        if not os.path.isfile(src):
            raise LaunchError("找不到 zip 文件：" + src)
        if not zipfile.is_zipfile(src):
            raise LaunchError("这不是有效的 zip：" + os.path.basename(src)
                              + "。官方 BDS 下载得到的就是一个 zip，选它即可")
        root = self._ensure_instances_root()
        version_id = (os.path.splitext(os.path.basename(src))[0] or "bds").strip()
        title = (str(name or "").strip() or version_id)
        tmp = tempfile.mkdtemp(prefix=".bds-", dir=root)
        try:
            try:
                with zipfile.ZipFile(src) as zf:
                    _safe_extract(zf, tmp)
            except zipfile.BadZipFile:
                raise LaunchError("zip 已损坏，无法解压：" + os.path.basename(src))
            except ValueError as exc:
                raise LaunchError("拒绝导入：" + str(exc))
            content = self._content_root(tmp)
            if not content:
                raise LaunchError(
                    "zip 里没有 bedrock_server.exe —— 请确认下载的是官方 Bedrock Dedicated Server"
                    "（Windows 版文件名形如 bedrock-server-<版本>.zip）；Linux 版解出来没有 .exe，"
                    "在 Windows 上用不了。")
            inst, server_dir = self._allocate_instance(version_id, title)
            try:
                _move_children(content, server_dir)
            except OSError as exc:
                raise LaunchError("解压出来的服务端写不进 " + server_dir + "：" + str(exc))
            state, eula_path = self.eula_state(server_dir)
            note = ""
            if state != "accepted":
                note = "首次启动前需要同意 EULA：把 " + eula_path + " 里的 eula=false 改成 eula=true"
            return self._finalize_instance(inst, server_dir, note)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _content_root(self, base: str) -> str:
        """zip 可能把文件裹在一层目录里，往下找最多 3 层含主程序的目录。"""
        if self.find_exe(base):
            return base
        queue = []
        try:
            for entry in os.scandir(base):
                if entry.is_dir():
                    queue.append((entry.path, 1))
        except OSError:
            return ""
        while queue:
            path, depth = queue.pop(0)
            if self.find_exe(path):
                return path
            if depth >= 3:
                continue
            try:
                for entry in os.scandir(path):
                    if entry.is_dir():
                        queue.append((entry.path, depth + 1))
            except OSError:
                continue
        return ""

    def _allocate_instance(self, version_id: str, title: str):
        store = self.store
        if store is not None:
            try:
                inst = store.create(self.id, version_id, name=title)
                server_dir = os.path.join(store.root, inst.id, "server")
                os.makedirs(server_dir, exist_ok=True)
                # store.create 顺手建的空 game/ 对服务端没用，能删就删
                try:
                    os.rmdir(os.path.join(store.root, inst.id, "game"))
                except OSError:
                    pass
                inst.game_dir = server_dir
                store.update(inst)
                return inst, server_dir
            except Exception:
                pass             # 注册失败不该挡住导入，退回不注册的实例
        inst_id = _new_id()
        server_dir = os.path.join(self.instances_root, inst_id, "server")
        os.makedirs(server_dir, exist_ok=True)
        inst = Instance(
            id=inst_id,
            name=title,
            provider=self.id,
            version_id=version_id,
            game_dir=server_dir,
            created=_now_iso(),
        )
        return inst, server_dir

    def _finalize_instance(self, inst: Instance, server_dir: str, note: str = "") -> Instance:
        inst.game_dir = server_dir
        if note:
            inst.note = note
        _write_instance_meta(server_dir, inst)
        if self.store is not None:
            try:
                self.store.update(inst)
            except Exception:
                pass
        return inst

    # ── 启动 / 控制台 ──

    def launch(self, instance: Instance, auth=None, cb=None) -> LaunchHandle:
        server_dir = str(getattr(instance, "game_dir", "") or "")
        if not server_dir or not os.path.isdir(server_dir):
            raise LaunchError("服务端目录不存在：" + (server_dir or "（实例没有 game_dir）")
                              + "。请用「导入服务端」重新导入，或在实例列表里选一个服务端实例。")
        exe = self.find_exe(server_dir)
        if not exe:
            raise LaunchError("在 " + server_dir + " 里找不到 bedrock_server.exe。"
                              "请重新用「导入服务端」导入官方 BDS zip"
                              "（Linux 版没有 .exe，Windows 上用不了）。")
        state, eula_path = self.eula_state(server_dir)
        if state != "accepted":
            raise LaunchError(
                "需要先接受 EULA：编辑 " + eula_path + "，把 eula=false 改成 eula=true 再启动。"
                "（这是 Mojang 的法律协议，启动器不能替你同意；文件不存在就新建一个，"
                "只写一行 eula=true。）")
        logs_dir = os.path.join(server_dir, "logs")
        try:
            os.makedirs(logs_dir, exist_ok=True)
        except OSError as exc:
            raise LaunchError("无法创建日志目录 " + logs_dir + "：" + str(exc))
        log_path = os.path.join(logs_dir, "server-" + _now_stamp() + ".log")
        try:
            log_file = open(log_path, "a", encoding="utf-8", errors="replace", buffering=1)
        except OSError as exc:
            raise LaunchError("无法写日志 " + log_path + "：" + str(exc))
        flags = 0
        if IS_WINDOWS:
            # BDS 是控制台程序；藏掉控制台窗口但保留管道 stdin。
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        _report(cb, "正在启动基岩版官方服务端…")
        try:
            proc = subprocess.Popen(
                [exe],
                cwd=server_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=flags,
            )
        except OSError as exc:
            try:
                log_file.close()
            except Exception:
                pass
            raise LaunchError("启动 bedrock_server 失败：" + str(exc))
        try:
            log_file.write("[launcher] " + time.strftime("%Y-%m-%d %H:%M:%S")
                           + " 启动 " + exe + "\n")
            log_file.write("[launcher] 工作目录 " + server_dir + "\n")
            log_file.flush()
        except (OSError, ValueError):
            pass
        proc._log_file = log_file
        proc._log_path = log_path
        proc._stdin = proc.stdin
        thread = threading.Thread(target=self._pump, args=(proc, log_file),
                                  name="bds-log", daemon=True)
        proc._log_thread = thread
        thread.start()
        _report(cb, "服务端已启动（pid " + str(proc.pid) + "）")
        return LaunchHandle(process=proc, pid=proc.pid, log_path=log_path,
                            note="基岩版官方服务端（BDS）已启动")

    @staticmethod
    def _pump(proc, log_file) -> None:
        """把合并后的 stdout/stderr 原样写进日志文件。"""
        stream = getattr(proc, "stdout", None)
        try:
            if stream is not None:
                for line in stream:
                    try:
                        log_file.write(line)
                        log_file.flush()
                    except (OSError, ValueError):
                        break
        except (OSError, ValueError):
            pass
        finally:
            try:
                code = proc.wait(timeout=5)
                log_file.write("\n[launcher] 服务端已退出，返回码 " + str(code) + "\n")
                log_file.flush()
            except Exception:
                pass
            try:
                log_file.close()
            except Exception:
                pass

    def send_command(self, handle, line: str) -> bool:
        """往 BDS 控制台写一行命令（stop / gamerule / say ...）。"""
        proc = getattr(handle, "process", None)
        if proc is None:
            return False
        try:
            if proc.poll() is not None:
                return False
        except Exception:
            return False
        command = str(line or "").replace("\r", "").replace("\n", "").strip()
        if not command:
            return False
        sink = getattr(proc, "_stdin", None) or getattr(proc, "stdin", None)
        if sink is None or getattr(sink, "closed", True):
            return False
        try:
            sink.write(command + "\n")
            sink.flush()
        except (OSError, ValueError):
            return False
        path = getattr(proc, "_log_path", "") or getattr(handle, "log_path", "")
        if path:
            try:
                with open(path, "a", encoding="utf-8", errors="replace") as fh:
                    fh.write("[launcher] > " + command + "\n")
            except OSError:
                pass
        return True

    def tail(self, handle, lines: int = 200) -> str:
        """读日志尾部 N 行（只读末尾 512KB，不整文件装内存）。"""
        path = getattr(handle, "log_path", "") or ""
        if not path:
            proc = getattr(handle, "process", None)
            path = getattr(proc, "_log_path", "") if proc is not None else ""
        if not path or not os.path.isfile(path):
            return ""
        try:
            size = os.path.getsize(path)
            offset = max(0, size - _TAIL_BYTES)
            with open(path, "rb") as fh:
                if offset:
                    fh.seek(offset)
                data = fh.read()
        except OSError:
            return ""
        text = data.decode("utf-8", "replace")
        rows = text.splitlines()
        if offset and rows:
            rows = rows[1:]          # 首行可能被截半
        count = max(1, int(lines or 200))
        return "\n".join(rows[-count:])


def create_provider(ctx) -> ServerProvider:
    """providers/__init__.ensure() 的工厂入口。"""
    return ServerProvider(ctx)
