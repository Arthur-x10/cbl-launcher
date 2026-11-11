"""下载器 —— Range 续传 + 分块并发 + SHA1 校验，并接管 minecraft-launcher-lib。

库里的下载是串行、无续传、无并发的：每个文件一次 GET 写盘，断流就整文件重来。
这里补上：

  - HEAD 探测 Content-Length / Accept-Ranges；
  - 支持 Range 时按并发数分块拉取，各写一个 .part.<i>，完成后按序拼接；
  - 单流模式遇断线从 .part 断点续传（最多 3 次指数退避）；
  - 下载完校验 SHA1，不符就丢弃；
  - 保留库的回调语义（setStatus / setProgress / setMax）。

接管方式：把 fast_download_file 绑到库内 11 个模块的 download_file 名字上
（它们是 `from ._helper import download_file`，只 patch _helper 不会生效）。
"""

import hashlib
import lzma
import os
import threading
import time
from typing import Callable, Optional

import requests

PART_SUFFIX = ".part"

_MLL_MODULES = [
    "minecraft_launcher_lib._helper",
    "minecraft_launcher_lib.install",
    "minecraft_launcher_lib.fabric",
    "minecraft_launcher_lib.forge",
    "minecraft_launcher_lib.quilt",
    "minecraft_launcher_lib.runtime",
    "minecraft_launcher_lib.mrpack",
    "minecraft_launcher_lib.mod_loader._fabric",
    "minecraft_launcher_lib.mod_loader._forge",
    "minecraft_launcher_lib.mod_loader._neoforge",
    "minecraft_launcher_lib.mod_loader._quilt",
]


class Cancelled(Exception):
    """用户取消下载。"""


def sha1_of(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class Downloader:
    def __init__(self, concurrency: int = 4, timeout: int = 30, retries: int = 3,
                 rate_limit_kbps: int = 0, chunk_threshold: int = 4 * 1024 * 1024):
        self.concurrency = max(1, int(concurrency))
        self.timeout = int(timeout)
        self.retries = max(1, int(retries))
        self.rate_limit_kbps = max(0, int(rate_limit_kbps))
        self.chunk_threshold = int(chunk_threshold)
        self.bytes_done = 0
        self.bytes_total = 0

    # ── 公开 API ──

    def download(self, url: str, dst: str, sha1: Optional[str] = None,
                 progress: Optional[Callable[[int, int], None]] = None,
                 cancel: Optional[Callable[[], bool]] = None,
                 overwrite: bool = False) -> bool:
        """下载到 dst。True=真的传了数据，False=本地已满足（存在且校验通过）。"""
        if os.path.isfile(dst) and not overwrite:
            if sha1 and sha1_of(dst) == sha1:
                return False
            if not sha1:
                return False
        if cancel and cancel():
            raise Cancelled()

        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        part = dst + PART_SUFFIX

        size, ranges = self._probe(url)
        self.bytes_total = size or 0
        self.bytes_done = 0
        if ranges and size and size > self.chunk_threshold and self.concurrency > 1:
            self._chunked(url, part, size, progress, cancel)
        else:
            self._stream(url, part, progress, cancel)

        if sha1:
            got = sha1_of(part)
            if got != sha1:
                try:
                    os.remove(part)
                except OSError:
                    pass
                raise IOError(f"SHA1 校验失败: 期望 {sha1[:12]}…, 实际 {got[:12]}…")
        os.replace(part, dst)
        return True

    # ── 探测 ──

    def _probe(self, url: str):
        try:
            r = requests.head(url, timeout=self.timeout, allow_redirects=True)
            size = int(r.headers.get("Content-Length") or 0)
            ranges = (r.headers.get("Accept-Ranges", "") or "").lower() == "bytes"
            if size <= 0:
                r2 = requests.get(url, timeout=self.timeout, headers={"Range": "bytes=0-0"})
                if r2.status_code == 206:
                    cr = r2.headers.get("Content-Range", "")
                    if "/" in cr:
                        size = int(cr.rsplit("/", 1)[1])
                    ranges = True
            return size, ranges
        except Exception:
            return 0, False

    # ── 单流（带断点续传） ──

    def _stream(self, url, part, progress, cancel):
        start = os.path.getsize(part) if os.path.isfile(part) else 0
        for attempt in range(self.retries):
            headers = {"Range": f"bytes={start}-"} if start else {}
            try:
                with requests.get(url, headers=headers, timeout=self.timeout, stream=True) as r:
                    if start and r.status_code != 206:
                        start = 0
                        headers = {}
                        continue
                    r.raise_for_status()
                    with open(part, "ab" if start else "wb") as f:
                        for chunk in r.iter_content(65536):
                            if cancel and cancel():
                                raise Cancelled()
                            if not chunk:
                                continue
                            f.write(chunk)
                            start += len(chunk)
                            self.bytes_done = start
                            if progress:
                                progress(start, self.bytes_total or start)
                            self._throttle(len(chunk))
                return
            except Cancelled:
                raise
            except Exception:
                if attempt == self.retries - 1:
                    raise
                time.sleep(min(1.5 * (2 ** attempt), 5))
                start = os.path.getsize(part) if os.path.isfile(part) else 0

    # ── 分块并发 ──

    def _chunked(self, url, part, size, progress, cancel):
        n = min(self.concurrency, max(1, size // (2 * 1024 * 1024)))
        step = size // n
        pieces = []
        for i in range(n):
            a = i * step
            b = (size - 1) if i == n - 1 else (a + step - 1)
            pieces.append((a, b, f"{part}.{i}"))
        done = [0] * n
        errs: list[BaseException] = []
        lock = threading.Lock()

        def work(idx, a, b, p):
            want = b - a + 1
            if os.path.isfile(p) and os.path.getsize(p) == want:
                with lock:
                    done[idx] = want
                return
            for attempt in range(self.retries):
                try:
                    with requests.get(url, timeout=self.timeout, stream=True,
                                      headers={"Range": f"bytes={a}-{b}"}) as r:
                        r.raise_for_status()
                        with open(p, "wb") as f:
                            for chunk in r.iter_content(65536):
                                if cancel and cancel():
                                    raise Cancelled()
                                if not chunk:
                                    continue
                                f.write(chunk)
                                with lock:
                                    done[idx] += len(chunk)
                                    total = sum(done)
                                if progress:
                                    progress(total, size)
                                self._throttle(len(chunk))
                    return
                except Cancelled:
                    errs.append(Cancelled())
                    return
                except Exception as e:
                    if attempt == self.retries - 1:
                        errs.append(e)
                        return
                    with lock:
                        done[idx] = 0
                    time.sleep(min(1.2 * (2 ** attempt), 4))

        threads = [threading.Thread(target=work, args=(i, a, b, p), daemon=True)
                   for i, (a, b, p) in enumerate(pieces)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if any(isinstance(e, Cancelled) for e in errs) or (cancel and cancel()):
            raise Cancelled()
        if errs:
            raise errs[0]
        with open(part, "wb") as out:
            for _a, _b, p in pieces:
                with open(p, "rb") as f:
                    while True:
                        buf = f.read(1 << 20)
                        if not buf:
                            break
                        out.write(buf)
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _throttle(self, nbytes: int):
        if not self.rate_limit_kbps:
            return
        delay = nbytes / (self.rate_limit_kbps * 1024.0)
        if delay > 0:
            time.sleep(min(delay, 0.4))


# ═══════════════════ 接管 minecraft-launcher-lib ═══════════════════

_DEFAULT = Downloader()


def make_download_file(d: Downloader):
    """生成一个与库 _helper.download_file 签名兼容的实现。"""

    def fast_download_file(url, path, callback=None, sha1=None, lzma_compressed=False,
                           session=None, minecraft_directory=None, overwrite=False):
        callback = callback or {}
        if minecraft_directory is not None:
            try:
                from minecraft_launcher_lib._helper import check_path_inside_minecraft_directory
                check_path_inside_minecraft_directory(minecraft_directory, path)
            except Exception:
                raise
        status = callback.get("setStatus")
        set_max = callback.get("setMax")
        set_progress = callback.get("setProgress")
        if status:
            try:
                status(f"下载 {os.path.basename(path)}")
            except Exception:
                pass
        if set_max:
            try:
                set_max(1)
            except Exception:
                pass

        if lzma_compressed:
            # 库的语义：URL 指向 .lzma 压缩体，落盘前必须先解压，
            # 而且给定的 sha1 是「解压后」内容的哈希。
            # 早期实现忽略了这一点，JRE 安装会在 SHA1 校验处直接失败。
            wrote = _download_lzma(d, url, path, sha1)
        else:
            try:
                wrote = d.download(url, path, sha1=sha1, overwrite=overwrite)
            except TypeError:
                # 兼容旧签名（不带 overwrite）
                wrote = d.download(url, path, sha1=sha1)
        if set_progress:
            try:
                set_progress(1 if wrote else 0)
            except Exception:
                pass
        return wrote

    return fast_download_file


def _download_lzma(d: Downloader, url: str, path: str,
                   sha1: Optional[str]) -> bool:
    """下载 .lzma 压缩体 → 解压 → 校验解压后的 sha1 → 落盘。"""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".lzma"
    try:
        d.download(url, tmp, sha1=None, overwrite=True)
        with open(tmp, "rb") as f:
            raw = f.read()
        try:
            data = lzma.decompress(raw)
        except Exception:
            # 少数源直接给未压缩内容，兜底按原样处理
            data = raw
        if sha1:
            got = hashlib.sha1(data).hexdigest()
            if got != sha1:
                raise IOError(f"SHA1 校验失败（解压后）: 期望 {sha1[:12]}…, 实际 {got[:12]}…")
        with open(path, "wb") as f:
            f.write(data)
        return True
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def install_into_mll(d: Optional[Downloader] = None) -> int:
    """把下载器接管到库里所有 import 过 download_file 的模块。返回替换的模块数。"""
    import importlib

    d = d or _DEFAULT
    fn = make_download_file(d)
    patched = 0
    for name in _MLL_MODULES:
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        if hasattr(mod, "download_file"):
            mod.download_file = fn  # type: ignore[attr-defined]
            patched += 1
    return patched


def default_downloader() -> Downloader:
    return _DEFAULT
