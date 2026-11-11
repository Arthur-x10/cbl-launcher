"""下载源智能管理 — 多镜像源自动测速 + URL 重写（作用于 requests.Session）。

内置: 官方源 / BMCLAPI / FastMinecraftMirror。
启动时自动测速选最快的，下载失败自动重试并回退。

关键点：minecraft-launcher-lib 8.0 的下载全部走 requests.Session
（install.py 里 session = requests.session()，_helper.download_file 再调
session.get），因此只补 requests.get 是无效的 —— 必须补
requests.sessions.Session.request，模块级 requests.get/head 会自动经过它。
"""

import sys
import threading
import time

import requests as _requests_mod

# ═══════════════════ 镜像源定义 ═══════════════════

SOURCES = {
    "official": {
        "name": "官方源 (Mojang)",
        "desc": "直接从 Mojang 官方下载，需要可访问境外网络",
        "test_url": "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
        "map": {},
    },
    "bmclapi": {
        "name": "BMCLAPI (国内推荐)",
        "desc": "bangbang93 维护的公益镜像，国内最大 MC 下载加速节点",
        "test_url": "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json",
        "map": {
            "piston-meta.mojang.com": "bmclapi2.bangbang93.com",
            "piston-data.mojang.com": "bmclapi2.bangbang93.com",
            "launchermeta.mojang.com": "bmclapi2.bangbang93.com",
            "launcher.mojang.com": "bmclapi2.bangbang93.com",
            "libraries.minecraft.net": "bmclapi2.bangbang93.com/maven",
            "resources.download.minecraft.net": "bmclapi2.bangbang93.com/assets",
            "files.minecraftforge.net": "bmclapi2.bangbang93.com/maven",
            "maven.minecraftforge.net": "bmclapi2.bangbang93.com/maven",
            "meta.fabricmc.net": "bmclapi2.bangbang93.com/fabric-meta",
            "maven.fabricmc.net": "bmclapi2.bangbang93.com/maven",
            "maven.neoforged.net/releases": "bmclapi2.bangbang93.com/maven",
            "meta.quiltmc.org": "bmclapi2.bangbang93.com/quilt-meta",
            "maven.quiltmc.org/repository/release": "bmclapi2.bangbang93.com/maven",
        },
    },
    "fastmirror": {
        "name": "FastMinecraftMirror",
        "desc": "独立 MC 下载加速源",
        "test_url": "https://launchermeta.fastmcmirror.org/mc/game/version_manifest_v2.json",
        "map": {
            "piston-meta.mojang.com": "launchermeta.fastmcmirror.org",
            "launchermeta.mojang.com": "launchermeta.fastmcmirror.org",
            "launcher.mojang.com": "launcher.fastmcmirror.org",
            "libraries.minecraft.net": "libraries.fastmcmirror.org",
            "resources.download.minecraft.net": "resources.fastmcmirror.org",
            "files.minecraftforge.net/maven": "forge.fastmcmirror.org",
            "maven.minecraftforge.net": "forge.fastmcmirror.org",
            "meta.fabricmc.net": "fabricmeta.fastmcmirror.org",
            "maven.fabricmc.net": "fabric.fastmcmirror.org",
        },
    },
}

SOURCE_KEYS = list(SOURCES.keys())

# ═══════════════════ 测速 ═══════════════════


def test_source_speed(key: str, timeout: float = 5.0) -> float:
    """测试镜像源延迟 (秒)。返回 -1 表示不可用。"""
    src = SOURCES.get(key)
    if not src or not src.get("test_url"):
        return -1
    try:
        start = time.time()
        resp = _requests_mod.head(src["test_url"], timeout=timeout, allow_redirects=True)
        if resp.status_code < 400:
            return time.time() - start
    except Exception:
        pass
    return -1


def test_all_sources(timeout: float = 5.0) -> list[tuple[str, float]]:
    """并发测试所有源，返回 [(key, latency_ms), ...] 按速度排序。不可用的排末尾。"""
    results: dict[str, float] = {}
    threads = []

    def _test(k):
        results[k] = test_source_speed(k, timeout)

    for k in SOURCE_KEYS:
        t = threading.Thread(target=_test, args=(k,), daemon=True)
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout + 1)

    ranked = []
    for k in SOURCE_KEYS:
        lat = results.get(k, -1)
        ranked.append((k, round(lat * 1000) if lat > 0 else -1))
    ranked.sort(key=lambda x: x[1] if x[1] > 0 else 99999)
    return ranked


def find_best_source(timeout: float = 5.0) -> str:
    """自动选择最快的可用源。"""
    for key, ms in test_all_sources(timeout):
        if ms > 0:
            return key
    return "official"


# ═══════════════════ URL 重写 + 重试（Session 级补丁） ═══════════════════

_original_request = None
_active_map: dict = {}
_active_key: str = "official"
_retry_times: int = 2
_lock = threading.Lock()

RETRY_STATUS = (500, 502, 503, 504, 520, 521, 522, 523, 524)

# 镜像明确"没有这个文件"的状态码：命中就回退原始地址
FALLBACK_STATUS = (403, 404, 410)

# 已在镜像上确认缺失的原始 URL，进进程级黑名单，后续直接走官方
_DIRECT_FALLBACK: set[str] = set()
_fallback_lock = threading.Lock()

# 最近发生的回退事件（文件名, HTTP 状态），给 UI / 日志用
_FALLBACK_EVENTS: list[tuple[str, int]] = []


def _rewrite_url(url: str) -> str:
    m = _active_map
    if not m or not isinstance(url, str):
        return url
    for original, mirror in m.items():
        if original in url:
            return url.replace(original, mirror)
    return url


def _request_with_retry(session, method, url, **kwargs):
    """对单个 URL 做失败重试（5xx / 连接错误），返回最后一个响应。"""
    attempts = max(1, _retry_times + 1)
    last_exc = None
    for i in range(attempts):
        try:
            resp = _original_request(session, method, url, **kwargs)
        except _requests_mod.RequestException as e:
            last_exc = e
            if i + 1 < attempts:
                time.sleep(min(0.5 * (2 ** i), 4.0))
                continue
            raise
        if resp.status_code in RETRY_STATUS and i + 1 < attempts:
            try:
                resp.close()
            except Exception:
                pass
            time.sleep(min(0.5 * (2 ** i), 4.0))
            continue
        return resp
    if last_exc is not None:
        raise last_exc
    raise _requests_mod.RequestException("下载失败：重试已用尽")


def _patched_request(self, method, url, **kwargs):
    """替换 requests.sessions.Session.request：镜像重写 + 失败重试 + 缺文件回退。

    BMCLAPI 并没有镜像所有 object：例如 1.7 时代的 log4j 配置
    `launcher.mojang.com/v1/objects/<sha1>/client-1.7.xml` 在镜像上是 404。
    以前这种 404 会原样抛给用户，表现成"换国内源反而装不上 1.7.10"。
    现在命中 FALLBACK_STATUS 就用原始 URL 再请求一次，并把该 URL 记进
    进程级黑名单，后续直接走官方（只多付一次 404 的代价）。
    """
    if not _active_map or url in _DIRECT_FALLBACK:
        return _request_with_retry(self, method, url, **kwargs)

    target = _rewrite_url(url)
    if target == url:
        return _request_with_retry(self, method, url, **kwargs)

    resp = _request_with_retry(self, method, target, **kwargs)
    if resp.status_code not in FALLBACK_STATUS:
        return resp

    try:
        resp.close()
    except Exception:
        pass
    name = str(url).rsplit("/", 1)[-1]
    with _fallback_lock:
        _DIRECT_FALLBACK.add(url)
        _FALLBACK_EVENTS.append((name, resp.status_code))
        del _FALLBACK_EVENTS[:-50]
    print(f"[mirror] 镜像缺文件（HTTP {resp.status_code}）{name}，已回退官方源", file=sys.stderr)
    return _request_with_retry(self, method, url, **kwargs)


# ═══════════════════ 公开 API ═══════════════════


def activate(source_key: str):
    """启用指定下载源（同时安装 Session 级补丁与重试）。"""
    global _original_request, _active_map, _active_key

    if source_key not in SOURCES:
        source_key = "official"

    with _lock:
        _active_key = source_key
        _active_map = SOURCES[source_key]["map"]

        if _original_request is None:
            _original_request = _requests_mod.sessions.Session.request

        # 覆盖 requests.get / requests.head / session.get / session.request 全部路径：
        # requests.api 内部总是创建 Session 再调 Session.request。
        _requests_mod.sessions.Session.request = _patched_request


def set_retry(times: int):
    """设置失败重试次数（不含首次）。安装整合包时调大。"""
    global _retry_times
    _retry_times = max(0, int(times))


def activate_auto():
    """自动测速并激活最快源。返回 (key, latency_ms)。"""
    best = find_best_source()
    activate(best)
    return best


def get_active_key() -> str:
    return _active_key


def get_name(key: str) -> str:
    return SOURCES.get(key, SOURCES["official"])["name"]


def fallback_events() -> list[tuple[str, int]]:
    """本次进程里"镜像缺失 → 已回退官方源"的文件列表。"""
    with _fallback_lock:
        return list(_FALLBACK_EVENTS)


def clear_fallback_events():
    with _fallback_lock:
        _FALLBACK_EVENTS.clear()


def describe(key: str) -> str:
    """给人看的源名称 + 是否已启用镜像。"""
    src = SOURCES.get(key, SOURCES["official"])
    return src["name"]
