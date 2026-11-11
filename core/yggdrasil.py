"""Yggdrasil 第三方认证 (LittleSkin 等) + authlib-injector 管理。"""

import hashlib
import json
import os
import zipfile
from typing import Optional

import requests


# ═══════════════════ Yggdrasil 认证 ═══════════════════

DEFAULT_API = "https://littleskin.cn/api/yggdrasil"

# 官方源优先，镜像仅作回退：authlib-injector 要被 -javaagent 当代码执行，
# 下载来源越单一越可控。
AUTHLIB_INJECTOR_META = "https://authlib-injector.yushi.moe/artifact/latest.json"
AUTHLIB_INJECTOR_MIRROR_META = "https://bmclapi2.bangbang93.com/mirrors/authlib-injector/artifact/latest.json"
AUTHLIB_INJECTOR_FALLBACK = "https://authlib-injector.yushi.moe/artifact/latest/authlib-injector-latest.jar"

MIN_JAR_SIZE = 10000


class YggdrasilResult:
    def __init__(self, username: str, uuid: str, access_token: str,
                 api_root: str, skin_url: str = ""):
        self.auth_type = "yggdrasil"
        self.username = username
        self.uuid = uuid
        self.access_token = access_token
        self.refresh_token = ""
        self.api_root = api_root
        self.skin_url = skin_url


def authenticate(email: str, password: str,
                 api_root: str = DEFAULT_API) -> Optional[YggdrasilResult]:
    """Yggdrasil 认证（邮箱+密码）。"""
    url = f"{api_root}/authserver/authenticate"
    payload = {
        "agent": {"name": "Minecraft", "version": 1},
        "username": email,
        "password": password,
        "requestUser": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        profile = data.get("selectedProfile") or {}
        skin = ""
        for prop in profile.get("properties", []):
            if prop.get("name") == "textures":
                skin = "(has textures)"

        return YggdrasilResult(
            username=profile.get("name", email),
            uuid=profile.get("id", ""),
            access_token=data.get("accessToken", ""),
            api_root=api_root,
            skin_url=skin,
        )
    except requests.HTTPError as e:
        try:
            err = e.response.json()
            msg = err.get("errorMessage", str(e))
        except Exception:
            msg = str(e)
        raise RuntimeError(f"认证失败: {msg}")
    except Exception as e:
        raise RuntimeError(f"连接失败: {e}")


# ═══════════════════ authlib-injector 管理 ═══════════════════

def get_injector_path(mc_dir: str) -> str:
    """authlib-injector.jar 的存放路径。"""
    return os.path.join(mc_dir, "authlib-injector.jar")


def validate_jar(path: str) -> tuple[bool, str]:
    """校验一个 jar 是否像可用的 authlib-injector。

    无法验签（上游不提供签名），至少保证：大小合理、是合法 zip、
    带 META-INF/MANIFEST.MF。以前只判「> 10000 字节」，
    一个被截断或被替换的文件也会被当成可用并注入游戏进程。
    """
    if not os.path.isfile(path):
        return False, "文件不存在"
    size = os.path.getsize(path)
    if size < MIN_JAR_SIZE:
        return False, f"文件过小 ({size} 字节)"
    if not zipfile.is_zipfile(path):
        return False, "不是有效的 jar/zip"
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except Exception as e:
        return False, f"无法读取: {e}"
    if "META-INF/MANIFEST.MF" not in names:
        return False, "缺少 META-INF/MANIFEST.MF"
    return True, ""


def is_injector_installed(mc_dir: str) -> bool:
    ok, _reason = validate_jar(get_injector_path(mc_dir))
    return ok


def _resolve_download_url() -> str:
    """依次询问官方源与镜像的 latest.json，拿不到就用固定回退地址。"""
    for meta_url in (AUTHLIB_INJECTOR_META, AUTHLIB_INJECTOR_MIRROR_META):
        try:
            meta = requests.get(meta_url, timeout=10).json()
            url = meta.get("download_url") or ""
            if url.startswith("https://"):
                return url
        except Exception:
            continue
    return AUTHLIB_INJECTOR_FALLBACK


def download_injector(mc_dir: str, callback=None):
    """下载最新版 authlib-injector（先写临时文件，校验通过才替换）。"""
    dst = get_injector_path(mc_dir)
    if callback:
        callback("正在获取 authlib-injector 下载地址…")

    jar_url = _resolve_download_url()

    if callback:
        callback("正在下载 authlib-injector…")

    resp = requests.get(jar_url, timeout=60)
    resp.raise_for_status()
    content = resp.content
    if len(content) < MIN_JAR_SIZE:
        raise RuntimeError(f"下载内容异常（{len(content)} 字节）: {jar_url}")

    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp = dst + ".part"
    with open(tmp, "wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())

    ok, reason = validate_jar(tmp)
    if not ok:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise RuntimeError(f"authlib-injector 校验失败（{reason}）: {jar_url}")

    os.replace(tmp, dst)

    if callback:
        digest = hashlib.sha256(content).hexdigest()[:16]
        callback(f"authlib-injector 下载完成 (sha256 {digest}…)")

    return dst


def get_injector_jvm_arg(mc_dir: str, api_root: str) -> str:
    """返回 -javaagent 参数。"""
    if not api_root.startswith(("https://", "http://")):
        raise ValueError(f"无效的 api_root: {api_root!r}")
    jar = get_injector_path(mc_dir)
    return f"-javaagent:{jar}={api_root}"
