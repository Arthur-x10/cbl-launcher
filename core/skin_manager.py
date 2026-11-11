"""皮肤管理模块 - 获取玩家皮肤头像"""

import os
from pathlib import Path
from typing import Optional

import requests

from core.config import CONFIG_DIR

SKIN_CACHE_DIR = CONFIG_DIR / "skin_cache"


def get_skin_url(uuid_str: str) -> Optional[str]:
    """通过 UUID 获取玩家皮肤 URL"""
    if not uuid_str:
        return None
    try:
        clean_uuid = uuid_str.replace("-", "")
        url = f"https://sessionserver.mojang.com/session/minecraft/profile/{clean_uuid}"
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        import base64, json
        for prop in data.get("properties", []):
            if prop["name"] == "textures":
                decoded = json.loads(base64.b64decode(prop["value"]))
                textures = decoded.get("textures", {})
                skin = textures.get("SKIN", {})
                return skin.get("url")
    except Exception:
        pass
    return None


def download_skin_head(uuid_str: str, size: int = 64) -> Optional[str]:
    """下载玩家头像（使用 Crafatar API），返回本地缓存路径"""
    if not uuid_str:
        return None
    SKIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    clean_uuid = uuid_str.replace("-", "")
    cache_file = SKIN_CACHE_DIR / f"{clean_uuid}_head.png"

    # 有缓存直接返回
    if cache_file.exists():
        return str(cache_file)

    try:
        url = f"https://crafatar.com/avatars/{clean_uuid}?size={size}&overlay"
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            with open(cache_file, "wb") as f:
                f.write(resp.content)
            return str(cache_file)
    except Exception:
        pass

    return None


def get_default_head() -> Optional[str]:
    """获取默认 Steve 头像"""
    default_file = SKIN_CACHE_DIR / "default_head.png"
    if default_file.exists():
        return str(default_file)

    try:
        SKIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        url = "https://crafatar.com/avatars/MHF_Steve?size=64&overlay"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            with open(default_file, "wb") as f:
                f.write(resp.content)
            return str(default_file)
    except Exception:
        pass
    return None


def clear_skin_cache():
    """清除皮肤缓存"""
    if SKIN_CACHE_DIR.exists():
        for f in SKIN_CACHE_DIR.iterdir():
            try:
                f.unlink()
            except OSError:
                pass
