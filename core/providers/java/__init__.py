"""Java 版 provider —— 把 Java 版的版本/启动/加载器/整合包能力接进多产品抽象层。"""

import os
from typing import Optional

from core.providers.base import (
    CAP_INSTANCE_DIR,
    CAP_JAVA,
    CAP_JVM,
    CAP_MODLOADER,
    CAP_PACK_IMPORT,
    CAP_UNINSTALL,
    CAP_VERSION_LIST,
    GameVersion,
    Instance,
    LaunchHandle,
)
from core.providers.java import deps, launch, loaders, packs, runtime, version

PROVIDER_ID = "java"

__all__ = ["JavaProvider", "create_provider", "PROVIDER_ID"]


class JavaProvider:
    """Minecraft Java 版（含 Forge/Fabric/Quilt/NeoForge 与整合包导入）。

    构造后只做极轻量的属性保存，所有磁盘/网络动作都在方法里发生；
    线程由调用方（UI）负责，core 层不依赖 Qt。
    """

    id = PROVIDER_ID
    name = "Minecraft Java 版"

    def __init__(self, ctx=None):
        self.ctx = ctx
        self.mc_dir = str(getattr(ctx, "mc_dir", "") or "")
        self.config = getattr(ctx, "config", None)
        self.store = getattr(ctx, "store", None)
        self.downloader = getattr(ctx, "downloader", None)

    def __repr__(self) -> str:
        return f"<JavaProvider mc_dir={self.mc_dir!r}>"

    # ═══════════════════ GameProvider ═══════════════════

    def capabilities(self) -> set[str]:
        return {
            CAP_MODLOADER,       # 可装 Forge/Fabric/Quilt/NeoForge
            CAP_JVM,             # JVM 参数 / 内存分配
            CAP_JAVA,            # 需要 Java 运行时
            CAP_PACK_IMPORT,     # 可导入 mrpack / CurseForge / MultiMC / 通用 zip
            CAP_VERSION_LIST,    # 可以列出远端可下载版本
            CAP_UNINSTALL,
            CAP_INSTANCE_DIR,    # 实例拥有独立游戏目录
        }

    def list_remote(self) -> Optional[list[GameVersion]]:
        """远端版本；网络/镜像失败返回 None（UI 据此提示重试而不是「共 0 个」）。"""
        return version.list_remote(self.mc_dir)

    def list_installed(self) -> list[GameVersion]:
        return version.list_installed(self.mc_dir)

    def install(self, gv: GameVersion, cb: Optional[dict] = None) -> None:
        """安装版本。带 loader 元数据时走加载器安装，否则装原版。"""
        meta = getattr(gv, "meta", None) or {}
        if meta.get("loader"):
            mc_version = str(meta.get("mc_version") or meta.get("parent") or gv.parent or "")
            if mc_version:
                self.install_loader(mc_version, str(meta["loader"]),
                                    str(meta.get("loader_version") or ""), cb)
                return
        version.install_version(self.mc_dir, gv.id, cb)

    def launch(self, instance: Instance, auth: dict,
               cb: Optional[dict] = None) -> LaunchHandle:
        """启动实例。失败抛 LaunchError（消息可直接给用户看）。"""
        return launch.launch_instance(self.mc_dir, self.config, instance, auth, cb)

    def uninstall(self, version_id: str) -> tuple[bool, str]:
        return version.delete_version(self.mc_dir, version_id)

    def version_size_mb(self, version_id: str) -> float:
        return version.version_size_mb(self.mc_dir, version_id)

    # ═══════════════════ 扩展：加载器 ═══════════════════

    def loader_options(self, mc_version: str) -> dict[str, list[str]]:
        """{"forge": [...], "fabric": [...], "quilt": [...], "neoforge": [...]}"""
        return loaders.loader_options(mc_version)

    def install_loader(self, mc_version: str, loader: str,
                       loader_version: str, cb: dict) -> str:
        """安装加载器，返回安装出的版本 id（可直接拿去建实例）。"""
        return loaders.install_loader(self.mc_dir, mc_version, loader,
                                      loader_version, cb)

    # ═══════════════════ 扩展：整合包 ═══════════════════

    def detect_modpack(self, path: str) -> tuple[str, dict]:
        """("mrpack"|"curseforge"|"mmc"|"generic"|"unknown", info_dict)"""
        return packs.detect_modpack(path)

    def install_modpack(self, path: str, cb: dict, game_dir: str = "") -> str:
        """导入整合包，返回安装出的版本 id（能确定时；否则空串）。

        game_dir 为空装进全局 .minecraft；传实例目录则装进该实例（推荐，避免污染）。
        """
        return packs.install_modpack(self._game_dir(game_dir), path, cb)

    # ═══════════════════ 扩展：mods ═══════════════════

    def list_mods(self, game_dir: str) -> list[str]:
        return version.get_mods_list(self._game_dir(game_dir))

    def open_mods_folder(self, game_dir: str) -> str:
        return version.open_mods_folder(self._game_dir(game_dir))

    def scan_mods(self, game_dir: str) -> list:
        """mods 目录里每个 jar 的 ModInfo（不联网、不解压）。"""
        return deps.scan_mods(self._mods_dir(game_dir))

    def check_mods(self, game_dir: str, mc_version: str, loader: str = "") -> list[str]:
        """人话问题列表：重复 modId / 缺前置 / MC 版本范围不符 / jar 损坏。"""
        return deps.check_mods(self._mods_dir(game_dir), mc_version, loader)

    # ═══════════════════ 扩展：Java ═══════════════════

    def required_java(self, version_id: str) -> int:
        """该版本要求的 Java 主版本号（加载器版本沿 inheritsFrom 回溯）。"""
        return launch.required_java(self.mc_dir, version_id)

    def resolve_java(self, version_id: str) -> str:
        """挑一个可用的 Java；没有兼容的 Java 时抛 LaunchError。"""
        return launch.resolve_java(self.config, self.mc_dir, version_id)

    # ═══════════════════ 额外便捷方法 ═══════════════════

    def grouped_versions(self) -> list[dict]:
        """已安装版本按原版分组（下拉框/树形列表用）。"""
        return version.get_grouped_versions(self.mc_dir)

    def is_installed(self, version_id: str) -> bool:
        return version.is_version_installed(self.mc_dir, version_id)

    def latest_release(self) -> Optional[str]:
        return version.get_latest_release()

    def java_runtimes(self) -> list[dict]:
        """Mojang 三个运行时的安装状态（首页 Java 环境提示用）。"""
        return runtime.get_runtime_status(self.mc_dir)

    def migrate_runtimes(self, cb=None) -> int:
        """把旧位置（含中文的 .minecraft/runtime）里的运行时迁到 ASCII 根。

        Java 8 只能从纯 ASCII 路径启动，首次启动时自动跑一次即可。
        """
        return runtime.migrate_to_ascii(self.mc_dir, cb)

    def missing_java(self) -> list[tuple[str, str, str]]:
        """缺失的 Mojang 运行时：[(name, label, covers)]，空列表表示都齐。"""
        return runtime.get_missing_runtimes(self.mc_dir)

    def install_missing_java(self, cb: Optional[dict] = None):
        """补齐缺失的 Mojang 运行时（首次启动用，阻塞调用，请放后台线程）。"""
        runtime.install_all_missing(self.mc_dir, cb)

    # ═══════════════════ 内部 ═══════════════════

    def _game_dir(self, game_dir: str) -> str:
        game_dir = str(game_dir or "").strip()
        return game_dir or self.mc_dir

    def _mods_dir(self, game_dir: str) -> str:
        base = self._game_dir(game_dir)
        return os.path.join(base, "mods") if base else ""


def create_provider(ctx) -> JavaProvider:
    """core.providers.ensure() 调用的工厂。"""
    return JavaProvider(ctx)
