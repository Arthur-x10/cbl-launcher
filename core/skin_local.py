"""本地皮肤管理 — 部署皮肤/披风到 CustomSkinLoader 目录。

离线玩家安装 CustomSkinLoader Mod 后，启动器自动把选择的皮肤
复制到正确位置，游戏加载时自动生效。
"""

import os
import shutil


def deploy_local_skin(mc_dir: str, username: str,
                      skin_path: str = "", cape_path: str = "",
                      model: str = "default"):
    """将皮肤/披风文件部署到 CustomSkinLoader/LocalSkin 目录。

    model: 'default' (Steve 标准) 或 'slim' (Alex 纤细)
    """
    base = os.path.join(mc_dir, "CustomSkinLoader", "LocalSkin")
    skins_dir = os.path.join(base, "skins")
    capes_dir = os.path.join(base, "capes")
    os.makedirs(skins_dir, exist_ok=True)
    os.makedirs(capes_dir, exist_ok=True)

    if skin_path and os.path.isfile(skin_path):
        dst = os.path.join(skins_dir, f"{username}.png")
        shutil.copy2(skin_path, dst)

    if cape_path and os.path.isfile(cape_path):
        dst = os.path.join(capes_dir, f"{username}.png")
        shutil.copy2(cape_path, dst)

    _ensure_csl_config(mc_dir, model)


def _ensure_csl_config(mc_dir: str, model: str = "default"):
    """确保 CustomSkinLoader.json 存在且 LocalSkin 在加载列表前面。"""
    import json
    cfg_path = os.path.join(mc_dir, "CustomSkinLoader", "CustomSkinLoader.json")

    default_config = {
        "enable": True,
        "loadlist": [
            {"name": "LocalSkin", "type": "Legacy",
             "root": "LocalSkin/skins/", "model": model},
            {"name": "LocalCape", "type": "Legacy",
             "root": "LocalSkin/capes/", "checkPNG": False},
            {"name": "LittleSkin", "type": "CustomSkinAPI",
             "root": "https://littleskin.cn/csl/"},
            {"name": "Mojang", "type": "MojangAPI"},
        ]
    }

    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            has_local = any(
                e.get("name") == "LocalSkin" for e in data.get("loadlist", [])
            )
            if not has_local:
                data.setdefault("loadlist", []).insert(0, {
                    "name": "LocalSkin", "type": "Legacy",
                    "root": "LocalSkin/skins/", "model": model,
                })
                with open(cfg_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            return
        except Exception:
            pass

    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=2, ensure_ascii=False)


def has_csl_mod(mc_dir: str) -> bool:
    """检查 mods 文件夹是否已有 CustomSkinLoader。"""
    mods_dir = os.path.join(mc_dir, "mods")
    if not os.path.isdir(mods_dir):
        return False
    return any(
        "customskinloader" in f.lower() or "csl" in f.lower()
        for f in os.listdir(mods_dir) if f.endswith(".jar")
    )
