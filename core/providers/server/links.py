"""官方 BDS（Bedrock Dedicated Server）下载链接。

Mojang 有一个公开的、不需要登录的链接接口，minecraft.net 的下载页就是用它：

    https://net-secondary.web.minecraft-services.net/api/v1.0/download/links
    -> {"result": {"links": [
         {"downloadType": "serverBedrockWindows",
          "downloadUrl": ".../bedrock-server-1.26.63.1.zip"}, ...]}}

基岩版**客户端**没有这条待遇（商店发加密 MSIXVC，见 bedrock/store.py），
但服务端是自由下载的 —— 所以这个启动器能「下载基岩版」，只是下载的是服务端。

版本号直接从文件名里取，取不到就不列（不猜）。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

LINKS_URLS = (
    "https://net-secondary.web.minecraft-services.net/api/v1.0/download/links",
    "https://net.web.minecraft-services.net/api/v1.0/download/links",
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
_BDS_RE = re.compile(r"bedrock-server-(?P<version>\d+(?:\.\d+){2,3})\.zip$", re.IGNORECASE)
_TTL = 600.0
_cache: list = []
_cache_at: float = 0.0

# downloadType -> (内部 kind, 中文名, 平台)
_KINDS = {
    "serverBedrockWindows": ("bds", "基岩版服务端（Windows）", "win"),
    "serverBedrockPreviewWindows": ("bds-preview", "基岩版服务端预览版（Windows）", "win"),
    "serverBedrockLinux": ("bds-linux", "基岩版服务端（Linux）", "linux"),
    "serverBedrockPreviewLinux": ("bds-preview-linux", "基岩版服务端预览版（Linux）", "linux"),
}


def _get_json(url: str, timeout: float = 20.0):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _version_of(url: str) -> str:
    m = _BDS_RE.search(str(url or ""))
    return m.group("version") if m else ""


def fetch_links(force: bool = False) -> list:
    """[{kind, name, platform, version, url}]，失败返回 []。"""
    global _cache, _cache_at
    now = time.monotonic()
    if not force and _cache and (now - _cache_at) < _TTL:
        return [dict(x) for x in _cache]

    data = None
    for url in LINKS_URLS:
        try:
            data = _get_json(url)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            continue
        if data:
            break
    if not data:
        return []

    out: list = []
    for link in ((data.get("result") or {}).get("links") or []):
        dtype = str(link.get("downloadType") or "")
        meta = _KINDS.get(dtype)
        if not meta:
            continue
        kind, name, platform = meta
        url = str(link.get("downloadUrl") or "")
        version = _version_of(url)
        if not url or not version:
            continue
        out.append({
            "kind": kind,
            "name": name,
            "platform": platform,
            "version": version,
            "url": url,
            "file_name": url.rsplit("/", 1)[-1],
        })
    _cache = [dict(x) for x in out]
    _cache_at = now
    return out


def find(version: str) -> dict:
    """按版本号找一条（kind 也可当键，例如 "bds-preview"）。"""
    key = str(version or "").strip()
    for item in fetch_links():
        if key in (item["version"], item["kind"]):
            return dict(item)
    return {}
