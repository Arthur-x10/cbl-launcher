"""游戏产品抽象层。

设计目标：UI 只依赖 GameProvider 的 capabilities，不写 if provider == "java"。
新增一个产品 = 新增一个 provider 包，不动界面代码。
"""

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable

# ── 能力标记（UI 按它决定显示哪些面板） ──
CAP_MODLOADER = "modloader"        # 可安装 Forge/Fabric/Quilt/NeoForge
CAP_JVM = "jvm"                    # 有 JVM 参数 / 内存分配
CAP_JAVA = "java_runtime"          # 需要 Java 运行时
CAP_PACK_IMPORT = "pack_import"    # 可导入整合包 / mcpack / mcworld
CAP_CONSOLE = "console"            # 有控制台（服务端）
CAP_STORE = "store_managed"        # 由商店安装与更新，启动器只唤醒
CAP_VERSION_LIST = "version_list"  # 可以列出远端可下载版本
CAP_UNINSTALL = "uninstall"
CAP_INSTANCE_DIR = "instance_dir"  # 实例拥有独立游戏目录


@dataclass(frozen=True)
class GameVersion:
    """一个可安装/可启动的版本条目。"""

    provider: str
    id: str
    display: str = ""
    kind: str = "release"          # release / snapshot / old / loader / store / server
    parent: str = ""               # 加载器版本指向的原版
    java_major: int = 0            # 仅 java provider 有意义
    installed: bool = False
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.display:
            object.__setattr__(self, "display", self.id)


@dataclass
class Instance:
    """一个可启动的实例：版本 + 独立游戏目录 + 启动配置。"""

    id: str
    name: str
    provider: str
    version_id: str
    game_dir: str
    icon: str = ""
    note: str = ""
    java_path: str = ""      # 空 = 自动
    jvm_args: str = ""
    ram_min: int = 0         # 0 = 跟随全局设置
    ram_max: int = 0
    created: str = ""
    last_played: str = ""
    play_seconds: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "provider": self.provider,
            "version_id": self.version_id, "game_dir": self.game_dir,
            "icon": self.icon, "note": self.note, "java_path": self.java_path,
            "jvm_args": self.jvm_args, "ram_min": self.ram_min, "ram_max": self.ram_max,
            "created": self.created, "last_played": self.last_played,
            "play_seconds": self.play_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Instance":
        return cls(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            provider=str(d.get("provider", "java")),
            version_id=str(d.get("version_id", "")),
            game_dir=str(d.get("game_dir", "")),
            icon=str(d.get("icon", "")),
            note=str(d.get("note", "")),
            java_path=str(d.get("java_path", "")),
            jvm_args=str(d.get("jvm_args", "")),
            ram_min=int(d.get("ram_min", 0) or 0),
            ram_max=int(d.get("ram_max", 0) or 0),
            created=str(d.get("created", "")),
            last_played=str(d.get("last_played", "")),
            play_seconds=int(d.get("play_seconds", 0) or 0),
        )


@dataclass
class LaunchHandle:
    """一次启动的句柄。基岩版是靠 shell 唤醒的，process 为 None。"""

    process: object = None
    pid: int = 0
    log_path: str = ""
    note: str = ""

    def running(self) -> bool:
        if self.process is None:
            return False
        try:
            return self.process.poll() is None
        except Exception:
            return False

    def close_log(self):
        f = getattr(self.process, "_log_file", None) if self.process is not None else None
        if f is not None:
            try:
                f.close()
            except Exception:
                pass


class LaunchError(Exception):
    """启动失败；message 直接展示给用户。"""


@runtime_checkable
class GameProvider(Protocol):
    id: str
    name: str

    def capabilities(self) -> set[str]: ...

    def list_remote(self) -> Optional[list[GameVersion]]:
        """远端可下载版本；返回 None 表示该产品不支持/不适用（如商店托管）。"""
        ...

    def list_installed(self) -> list[GameVersion]: ...

    def install(self, version: GameVersion, cb: dict) -> None:
        """cb: {"setStatus","setProgress","setMax"}"""
        ...

    def launch(self, instance: Instance, auth: dict, cb: Optional[dict] = None) -> LaunchHandle: ...

    def uninstall(self, version_id: str) -> tuple[bool, str]: ...

    def version_size_mb(self, version_id: str) -> float: ...
