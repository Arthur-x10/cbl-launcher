"""实例存储 —— 每个实例 = 版本 + 独立游戏目录 + 启动配置。

目录布局：
  <.minecraft>/instances/instances.json     # 注册表
  <.minecraft>/instances/<id>/game/         # 该实例的 .minecraft 等效目录
  <.minecraft>/instances/<id>/icon.png      # 可选图标

老的 config.json（selected_version + game_directories）会被一次性迁移成实例，
迁移后旧键仍然保留但不再使用。
"""

import json
import os
import shutil
import time
import uuid
from typing import Optional

from core.providers.base import Instance

REGISTRY_NAME = "instances.json"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class InstanceStore:
    def __init__(self, mc_dir: str):
        self.mc_dir = mc_dir
        self.root = os.path.join(mc_dir, "instances")
        self.registry_path = os.path.join(self.root, REGISTRY_NAME)
        self._items: dict[str, Instance] = {}
        self.last_error = ""
        self.load()

    # ── 读写 ──

    def load(self):
        self._items = {}
        try:
            os.makedirs(self.root, exist_ok=True)
        except OSError as e:
            self.last_error = f"无法创建实例目录: {e}"
            return
        if not os.path.isfile(self.registry_path):
            return
        try:
            with open(self.registry_path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            entries = data.get("instances", data) if isinstance(data, dict) else data
            if isinstance(entries, dict):
                entries = list(entries.values())
            for d in entries or []:
                inst = Instance.from_dict(d)
                if inst.id and inst.version_id:
                    self._items[inst.id] = inst
        except Exception as e:
            self.last_error = f"实例注册表损坏: {e}"
            self._items = {}

    def save(self) -> bool:
        try:
            os.makedirs(self.root, exist_ok=True)
            tmp = self.registry_path + ".tmp"
            payload = {
                "version": 2,
                "instances": [i.to_dict() for i in self._items.values()],
            }
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.registry_path)
            self.last_error = ""
            return True
        except OSError as e:
            self.last_error = f"无法写入实例注册表: {e}"
            return False

    # ── 查询 ──

    def all(self) -> list[Instance]:
        return sorted(self._items.values(),
                      key=lambda i: (i.last_played or i.created or ""), reverse=True)

    def by_provider(self, provider: str) -> list[Instance]:
        return [i for i in self.all() if i.provider == provider]

    def get(self, inst_id: str) -> Optional[Instance]:
        return self._items.get(inst_id)

    def find_by_version(self, provider: str, version_id: str) -> Optional[Instance]:
        for i in self._items.values():
            if i.provider == provider and i.version_id == version_id:
                return i
        return None

    def default_game_dir(self, provider: str, version_id: str) -> str:
        """没有实例时，provider 使用的默认目录（java = .minecraft 本身）。"""
        return self.mc_dir

    # ── 写 ──

    def create(self, provider: str, version_id: str, name: str = "",
               game_dir: str = "") -> Instance:
        iid = uuid.uuid4().hex[:10]
        if not game_dir:
            game_dir = os.path.join(self.root, iid, "game")
        try:
            os.makedirs(game_dir, exist_ok=True)
        except OSError:
            pass
        inst = Instance(
            id=iid,
            name=name or version_id,
            provider=provider,
            version_id=version_id,
            game_dir=game_dir,
            created=_now(),
        )
        self._items[iid] = inst
        self.save()
        return inst

    def update(self, inst: Instance) -> bool:
        self._items[inst.id] = inst
        return self.save()

    def delete(self, inst_id: str, remove_files: bool = False) -> tuple[bool, str]:
        inst = self._items.get(inst_id)
        if inst is None:
            return True, ""
        self._items.pop(inst_id, None)
        self.save()
        if remove_files:
            base = os.path.join(self.root, inst_id)
            if os.path.isdir(base) and os.path.realpath(base).startswith(os.path.realpath(self.root)):
                try:
                    shutil.rmtree(base)
                except OSError as e:
                    return False, str(e)
        return True, ""

    def touch_played(self, inst_id: str, seconds: int = 0):
        inst = self._items.get(inst_id)
        if inst is None:
            return
        inst.last_played = _now()
        if seconds:
            inst.play_seconds += int(seconds)
        self.save()

    # ── 补建 ──

    def sync_installed(self, providers, tombstones=None,
                       max_per_provider: int = 50) -> int:
        """为「已经装在磁盘上但没有实例」的版本自动补建实例。

        用户的直觉是"装完就能玩"，而不是"装完还要再手动建一个实例"。
        删除实例时会把 provider::version 记进 tombstone，补建时跳过，
        这样主动删掉的不至于每次启动又被加回来。
        """
        tomb = set(tombstones or [])
        created = 0
        for p in providers or []:
            pid = str(getattr(p, "id", "") or "")
            if not pid:
                continue
            try:
                installed = list(p.list_installed() or [])
            except Exception:
                continue
            for v in installed[:max_per_provider]:
                vid = str(getattr(v, "id", "") or "")
                if not vid:
                    continue
                if f"{pid}::{vid}" in tomb:
                    continue
                if self.find_by_version(pid, vid) is not None:
                    continue
                name = str(getattr(v, "display", "") or vid)
                self.create(pid, vid, name=name)
                created += 1
        return created

    # ── 迁移 ──

    def migrate_legacy(self, config) -> int:
        """把老的 selected_version / game_directories 迁移成实例。返回迁移数量。"""
        if config.get("instances_migrated"):
            return 0
        created = 0
        sel = (config.get("selected_version") or "").strip()
        if sel:
            inst = self.find_by_version("java", sel)
            if inst is None:
                dirs = config.get("game_directories", {}) or {}
                inst = self.create("java", sel, name=sel, game_dir=dirs.get(sel, ""))
                created += 1
        else:
            # 没有选择记录：为每个已安装的 java 版本建一个实例，避免列表空着
            try:
                from core.providers.java.version import get_installed_versions
                for v in get_installed_versions(self.mc_dir):
                    if self.find_by_version("java", v["id"]) is None:
                        self.create("java", v["id"], name=v["id"])
                        created += 1
            except Exception:
                pass
        config.set("instances_migrated", True)
        return created
