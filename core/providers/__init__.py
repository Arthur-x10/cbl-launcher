"""Provider 注册表 + 运行上下文。

一个 provider 加载失败不能拖垮其它产品（例如基岩版在非 Windows 上没有意义），
所以 ensure() 对每个模块单独 try/except，并打印失败原因。
"""

import importlib
import sys
from dataclasses import dataclass
from typing import Optional

from core.providers.base import GameProvider

_PROVIDER_MODULES = [
    "core.providers.java",
    "core.providers.bedrock",
    "core.providers.server",
]


@dataclass
class ProviderContext:
    """provider 需要的一切外部依赖，由 MainWindow 构造一次。"""

    mc_dir: str
    config: object          # core.config.Config
    store: object           # core.instances.InstanceStore
    downloader: object      # core.download.Downloader


_REGISTRY: dict[str, GameProvider] = {}
_CTX: Optional[ProviderContext] = None


def ensure(ctx: ProviderContext) -> dict[str, GameProvider]:
    """加载全部 provider（幂等）。"""
    global _CTX
    _CTX = ctx
    for name in _PROVIDER_MODULES:
        try:
            mod = importlib.import_module(name)
        except Exception as e:
            print(f"[providers] import {name} 失败: {e}", file=sys.stderr)
            continue
        try:
            factory = getattr(mod, "create_provider", None)
            provider = factory(ctx) if callable(factory) else getattr(mod, "PROVIDER", None)
            pid = getattr(provider, "id", "")
            if provider is not None and pid:
                _REGISTRY[pid] = provider
            else:
                print(f"[providers] {name} 没有返回有效 provider", file=sys.stderr)
        except Exception as e:
            print(f"[providers] {name} 初始化失败: {e}", file=sys.stderr)
    return _REGISTRY


def get(provider_id: str) -> Optional[GameProvider]:
    return _REGISTRY.get(provider_id)


def all_providers() -> list[GameProvider]:
    return list(_REGISTRY.values())


def context() -> Optional[ProviderContext]:
    return _CTX


def capability_of(provider_id: str) -> set[str]:
    p = _REGISTRY.get(provider_id)
    try:
        return set(p.capabilities()) if p is not None else set()
    except Exception:
        return set()
