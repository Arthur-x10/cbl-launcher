"""基岩版的其他获取渠道（全部实测过）。

一句话结论：**国际版 Windows 客户端的游戏本体没有任何公开直链**，
但有三种东西是能真下载、真安装的，都从这里出：

    launcher_msi   Minecraft 启动器（MSI，2.1 MB）    launcher.mojang.com
    launcher_exe   Minecraft 启动器（GameCore，34 MB） launcher.mojang.com
    education      Minecraft Education（1.16 GB）      minecrafteduservices.com

前两个是启动器本身，装完它拉游戏还是走 Store / Xbox（LIVE 许可）；
第三个是基岩引擎的教育版，安装包公开、能装，但进游戏要教育账号（有试用）。
它们都不是「免费的国际版基岩客户端」，别把这话说错。

链接都是 aka.ms 短链，最后落在哪个文件、多大，靠 HEAD 解析出来，
解析不到就不显示体积 —— 不猜。
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

CHANNELS = (
    {
        "id": "launcher_msi",
        "name": "Minecraft 启动器（MSI）",
        "aka": "https://aka.ms/minecraftClientWindows",
        "note": "微软官方的 Windows 安装程序。装完能在里面启动 Java 版；"
                "基岩版仍要由 Store / Xbox 交付。",
        "kind": "installer",
    },
    {
        "id": "launcher_exe",
        "name": "Minecraft 启动器（GameCore）",
        "aka": "https://aka.ms/minecraftClientGameCoreWindows",
        "note": "同一款启动器的 GameCore 打包版（更大，适合新系统）。",
        "kind": "installer",
    },
    {
        "id": "education",
        "name": "Minecraft Education",
        "aka": "https://aka.ms/downloadmee-desktopApp",
        "note": "基岩引擎的教育版，安装包是公开直链。能装、能启动；"
                "进游戏需要教育账号（官方有试用）。不是国际版基岩客户端。",
        "kind": "game",
    },
)

LINKS_ONLY = (
    {"id": "netease", "name": "网易《我的世界》中国版",
     "url": "https://mc.163.com/",
     "note": "免费的独立客户端（基于基岩版），需要网易账号；"
             "和国际版账号、存档互不相通。"},
    {"id": "google_play", "name": "Android（Google Play）",
     "url": "https://play.google.com/store/apps/details?id=com.mojang.minecraftpe",
     "note": "移动端本体，需购买。"},
)

_cache: dict = {}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _resolve(aka: str, hops: int = 6, timeout: float = 20.0) -> dict:
    """跟完 aka.ms 的跳转，返回最终 URL、文件名、大小。失败返回 {}。"""
    opener = urllib.request.build_opener(_NoRedirect)
    url = aka
    for _ in range(hops):
        req = urllib.request.Request(url, headers={"User-Agent": _UA}, method="HEAD")
        try:
            with opener.open(req, timeout=timeout) as resp:
                size = 0
                try:
                    size = int(resp.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    size = 0
                name = os.path.basename(str(resp.geturl()).split("?")[0])
                return {"url": str(resp.geturl()), "file_name": name, "size_bytes": size}
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location")
            if loc and e.code in (301, 302, 303, 307, 308):
                url = urllib.parse.urljoin(url, loc)
                continue
            return {}
        except Exception:
            return {}
    return {}


def human_size(num) -> str:
    try:
        n = float(num)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.2f %s" % (n, unit))
        n /= 1024.0
    return ""


def list_channels(force: bool = False) -> list:
    """解析出每个可下载渠道的真实地址与体积。拿不到的条目也保留（标 resolved=False）。"""
    out = []
    for ch in CHANNELS:
        cid = ch["id"]
        cached = _cache.get(cid)
        if cached and not force:
            out.append(dict(cached))
            continue
        info = _resolve(ch["aka"])
        item = dict(ch)
        item.update({
            "url": info.get("url", ""),
            "file_name": info.get("file_name", ""),
            "size_bytes": info.get("size_bytes", 0),
            "size_text": human_size(info.get("size_bytes", 0)),
            "resolved": bool(info.get("url")),
        })
        _cache[cid] = dict(item)
        out.append(item)
    return out


def find_channel(channel_id: str, force: bool = False) -> dict:
    for item in list_channels(force=force):
        if item["id"] == channel_id:
            return item
    return {}


def download(item: dict, dst: str, progress=None, cancel=None) -> str:
    """下载某个渠道的安装包到 dst。返回本地路径。"""
    url = str((item or {}).get("url") or "")
    if not url:
        raise ValueError("这个渠道没有解析出可下载地址")
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    done = 0
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = 0
        try:
            total = int(resp.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            total = 0
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            while True:
                if cancel and cancel():
                    f.close()
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise RuntimeError("已取消")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total or done)
    os.replace(tmp, dst)
    return dst
