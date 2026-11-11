"""配置管理模块 - 负责读写启动器配置（原子写入 + 损坏备份 + 写失败不崩）"""

import json
import os
import shutil
import sys
import time
from pathlib import Path

from core import secret


def _get_launcher_dir() -> Path:
    """检测启动器根目录（兼容 PyInstaller / Nuitka / 开发模式）。"""
    # PyInstaller
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # Nuitka 或其他编译 exe
    if sys.argv:
        exe = Path(os.path.abspath(sys.argv[0]))
        if exe.suffix.lower() == ".exe":
            return exe.parent
    # 开发模式
    return Path(os.path.dirname(os.path.abspath(__file__))).parent


LAUNCHER_DIR = _get_launcher_dir()

# .minecraft 放在启动器文件夹内（便携式，不污染系统目录）
DEFAULT_MC_DIR = str(LAUNCHER_DIR / ".minecraft")

# 配置文件也放在启动器文件夹内
CONFIG_DIR = LAUNCHER_DIR
CONFIG_FILE = CONFIG_DIR / "config.json"
BACKUP_FILE = CONFIG_DIR / "config.json.bak"

# 所有配置键的默认值。新增键必须加在这里，
# 否则老的 config.json 缺键时行为会随 get() 的临时默认值漂移。
DEFAULT_CONFIG = {
    "minecraft_directory": DEFAULT_MC_DIR,
    "java_path": "",  # 空字符串表示自动检测
    "jvm_args": "",
    "ram_min": 512,
    "ram_max": 2048,
    "selected_version": "",
    "auth_type": "offline",  # "offline" / "microsoft" / "yggdrasil"
    "username": "Player",
    "uuid": "",
    "access_token": "",
    "refresh_token": "",
    "show_snapshots": False,
    "show_old_versions": False,
    "close_on_launch": False,
    "game_directories": {},  # 版本 -> 独立游戏目录的映射
    "auto_performance": True,  # True 时按本机内存自动生成 JVM 参数
    "local_skin_path": "",
    "local_cape_path": "",
    "skin_model": "default",
    "download_source": "auto",  # auto / official / bmclapi / fastmirror
    "last_good_source": "official",  # 上一次测速选中的源，供下次启动秒开
    "download_concurrency": 4,  # 分块并发下载数
    "download_rate_limit": 0,   # KB/s，0 = 不限速
    "lang": "zh",               # zh / en
    "instances_migrated": False,  # 老 selected_version 是否已迁移成实例
    "instance_tombstones": [],    # 用户主动删除的实例（provider::version），不再自动补建
    "theme": "random",
    "modpack_names": {},  # 版本 id -> 整合包可读名
    "yggdrasil_api": "https://littleskin.cn/api/yggdrasil",
    "agreement_accepted": False,
    "agreement_time": "",
}


# 需要加密落盘的键（微软 OAuth 凭证）
SENSITIVE_KEYS = ("access_token", "refresh_token")


class Config:
    """启动器配置管理器。

    - 写入走「临时文件 + os.replace」原子替换，断电不会留下半个 JSON。
    - 每次成功写入前保留一份 config.json.bak。
    - 原文件损坏时备份为 config.json.corrupt-<时间>，再用默认值继续，
      绝不静默覆盖用户数据（其中含登录凭证）。
    - 目录只读等写失败不会抛异常，只记录 last_error 并继续运行。
    """

    def __init__(self, config_file=None):
        self._path = Path(config_file) if config_file else CONFIG_FILE
        self._dir = self._path.parent
        self._data: dict = {}
        self.last_error = ""
        self.load()

    # ── 读 ──

    def load(self):
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.last_error = f"无法创建配置目录: {e}"
            print(f"[config] {self.last_error}", file=sys.stderr)

        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("配置根节点不是 JSON 对象")
                self._data = data
            except Exception as e:
                bad = self._backup_corrupt()
                print(f"[config] 读取失败({e})，已备份为 {bad}，使用默认配置", file=sys.stderr)
                self._data = {}
        else:
            self._data = {}

        changed = False
        for key, value in DEFAULT_CONFIG.items():
            if key not in self._data:
                self._data[key] = value
                changed = True

        # 老版本把令牌明文写在 config.json 里，这里静默迁移成 DPAPI 密文
        for key in SENSITIVE_KEYS:
            value = self._data.get(key)
            if value and not secret.is_encrypted(value):
                self._data[key] = secret.encrypt(value, slot=key)
                changed = True

        if changed or not self._path.exists():
            self.save()

    def _backup_corrupt(self) -> str:
        ts = time.strftime("%Y%m%d-%H%M%S")
        bad = self._path.with_name(f"{self._path.name}.corrupt-{ts}")
        try:
            shutil.copy2(self._path, bad)
            return str(bad)
        except OSError:
            return "(备份失败)"

    # ── 写 ──

    def save(self) -> bool:
        """原子保存。成功返回 True；目录不可写等失败返回 False 且不抛异常。"""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.last_error = f"无法创建配置目录: {e}"
            return False

        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            if self._path.exists():
                try:
                    shutil.copy2(self._path, BACKUP_FILE)
                except OSError:
                    pass
            os.replace(tmp, self._path)
            self.last_error = ""
            return True
        except OSError as e:
            self.last_error = f"无法写入配置文件 ({self._path}): {e}"
            print(f"[config] {self.last_error}", file=sys.stderr)
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

    # ── 访问 ──

    def get(self, key: str, default=None):
        value = self._data.get(key, default)
        if key in SENSITIVE_KEYS and isinstance(value, str):
            # 存的是密文，取出来是明文；解不开（换了机器/用户）时返回空串
            return secret.decrypt(value, slot=key)
        return value

    def set(self, key: str, value) -> bool:
        if key in SENSITIVE_KEYS and isinstance(value, str):
            value = secret.encrypt(value, slot=key)
        self._data[key] = value
        return self.save()

    def update(self, **kwargs) -> bool:
        """批量写入，只落盘一次。"""
        for key, value in kwargs.items():
            if key in SENSITIVE_KEYS and isinstance(value, str):
                value = secret.encrypt(value, slot=key)
            self._data[key] = value
        return self.save()

    def get_minecraft_dir(self) -> str:
        return self._data.get("minecraft_directory", DEFAULT_MC_DIR) or DEFAULT_MC_DIR

    def get_java_path(self) -> str:
        return self._data.get("java_path", "")

    def get_ram_max(self) -> int:
        return self._data.get("ram_max", 2048)

    def get_ram_min(self) -> int:
        return self._data.get("ram_min", 512)

    @property
    def data(self) -> dict:
        return self._data
