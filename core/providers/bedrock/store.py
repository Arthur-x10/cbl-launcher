"""Microsoft Store 侧的基岩版元数据。

为什么这里没有 download()：
    实测（2026-11-12）微软两条公开接口都拿不到可安装的包：
      * displaycatalog  给出 3 个 SKU，PackageFormat 全部是 MSIXVC（加密容器），
        Version 是 "0"、PackageFullName 是空、PackageUri 是占位域名；
      * storeedgefd     只给 WuBundleId / WuCategoryId，也就是「走 Windows Update 交付」。
    真实下载由 Store 用 Delivery Optimization 完成，并且需要**当前账号持有该游戏的许可**。
    所以第三方启动器能做的上限是：查商店元数据、比对本机版本、把用户送进商店页。

这个模块只做这三件事，全部失败都返回空值，绝不抛异常给界面。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

PRODUCT_ID = "9NBLGGH2JHXJ"           # Minecraft for Windows（基岩版客户端）
APPS_URL = "https://apps.microsoft.com/detail/" + PRODUCT_ID
STORE_PDP = "ms-windows-store://pdp/?ProductId=" + PRODUCT_ID
STORE_UPDATES = "ms-windows-store://downloadsandupdates"

_CATALOG = ("https://displaycatalog.mp.microsoft.com/v7.0/products/"
            + PRODUCT_ID + "?languages={lang}&market={market}")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_TTL = 600.0
_cache: dict = {}
_cache_at: float = 0.0


def _get_json(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def human_size(num) -> str:
    try:
        n = float(num)
    except (TypeError, ValueError):
        return ""
    if n <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            # 字节不带小数，其余一律两位 —— 尺寸展示不需要更细
            return ("%.0f %s" % (n, unit)) if unit == "B" else ("%.2f %s" % (n, unit))
        n /= 1024.0
    return ""


def fetch_info(market: str = "CN", lang: str = "zh-cn", force: bool = False) -> dict:
    """商店包里能公开拿到的全部信息。失败返回 {}。"""
    global _cache, _cache_at
    now = time.monotonic()
    if not force and _cache and (now - _cache_at) < _TTL:
        return dict(_cache)

    info: dict = {}
    for mk, lg in ((market, lang), ("US", "en-us")):
        try:
            data = _get_json(_CATALOG.format(lang=lg, market=mk))
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError):
            continue
        prod = (data or {}).get("Product") or {}
        if not prod:
            continue
        localized = prod.get("LocalizedProperties") or [{}]
        first = localized[0] if isinstance(localized[0], dict) else {}
        skus = []
        size = 0
        updated = ""
        package_formats = set()
        for avail in prod.get("DisplaySkuAvailabilities") or []:
            sku = (avail or {}).get("Sku") or {}
            if not sku:
                continue
            skus.append(str(sku.get("SkuId") or ""))
            if not updated:
                updated = str(sku.get("LastModifiedDate") or "")
            packages = ((sku.get("Properties") or {}).get("Packages")) or []
            for pkg in packages:
                package_formats.add(str(pkg.get("PackageFormat") or ""))
                try:
                    size = max(size, int(pkg.get("MaxDownloadSizeInBytes") or 0))
                except (TypeError, ValueError):
                    pass
        info = {
            "product_id": PRODUCT_ID,
            "title": str(first.get("ProductTitle") or "Minecraft for Windows"),
            "description": str(first.get("ShortDescription") or "").strip(),
            "size_bytes": size,
            "size_text": human_size(size),
            "updated": updated,
            "updated_date": updated[:10],
            "sku_ids": [s for s in skus if s],
            "package_formats": sorted(f for f in package_formats if f),
            "market": mk,
            "apps_url": APPS_URL,
            "delivery": "store",
        }
        break

    _cache = dict(info)
    _cache_at = now
    return info


def open_store(uri: str = STORE_PDP) -> tuple:
    """把用户送进商店页。返回 (ok, 说明)。"""
    if sys.platform != "win32":
        return False, "只有 Windows 有 Microsoft Store。"
    for launcher in (["cmd", "/c", "start", "", uri], ["explorer.exe", uri]):
        try:
            subprocess.Popen(launcher, close_fds=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, uri
        except OSError:
            continue
    try:
        import os
        os.startfile(uri)  # noqa: S606 — 打开已注册的 ms-windows-store 协议
        return True, uri
    except OSError as e:
        return False, "打不开商店页：%s" % e
