"""极简 i18n：中文为源语言，英文覆盖界面骨架，缺键回退中文再回退 key。

用法：
    from core.i18n import t
    label = t("nav.library")
    msg = t("launch.version_missing", v="1.20.1")
"""

import json
import os

_LANG = "zh"
_SUPPORTED = ("zh", "en")

_TABLE: dict[str, dict[str, str]] = {
    "zh": {
        "app.name": "CBL Cube Launcher",
        "nav.home": "首页",
        "nav.library": "库",
        "nav.settings": "设置",
        "login.title": "开始游戏",
        "login.offline": "离线",
        "login.microsoft": "微软正版",
        "login.littleskin": "LittleSkin",
        "login.enter": "进入启动器",
        "home.launch": "开始游戏",
        "home.running": "游戏运行中",
        "home.starting": "正在启动…",
        "home.no_game": "还没有游戏",
        "home.go_library": "前往库",
        "library.title": "库",
        "library.installed": "已安装",
        "library.install_new": "+ 安装",
        "library.create_instance": "新建实例",
        "library.instance": "实例",
        "library.version": "版本",
        "library.type": "类型",
        "library.size": "大小",
        "library.dir": "游戏目录",
        "library.mods": "Mods",
        "library.open_mods": "打开 mods 文件夹",
        "library.delete": "删除",
        "library.play": "启动",
        "library.none": "还没有安装任何版本",
        "settings.title": "设置",
        "settings.save": "保存设置",
        "settings.theme": "背景主题",
        "settings.source": "下载源",
        "common.ok": "确定",
        "common.cancel": "取消",
        "common.close": "关闭",
        "common.refresh": "刷新",
        "common.query": "查询",
        "common.install": "安装",
        "common.failed": "失败",
        "common.done": "完成",
        "common.cancelled": "已取消",
    },
    "en": {
        "app.name": "CBL Cube Launcher",
        "nav.home": "Home",
        "nav.library": "Library",
        "nav.settings": "Settings",
        "login.title": "Play Minecraft",
        "login.offline": "Offline",
        "login.microsoft": "Microsoft",
        "login.littleskin": "LittleSkin",
        "login.enter": "Enter launcher",
        "home.launch": "Play",
        "home.running": "Game running",
        "home.starting": "Starting…",
        "home.no_game": "No game yet",
        "home.go_library": "Open library",
        "library.title": "Library",
        "library.installed": "Installed",
        "library.install_new": "+ Install",
        "library.create_instance": "New instance",
        "library.instance": "Instance",
        "library.version": "Version",
        "library.type": "Type",
        "library.size": "Size",
        "library.dir": "Game folder",
        "library.mods": "Mods",
        "library.open_mods": "Open mods folder",
        "library.delete": "Delete",
        "library.play": "Play",
        "library.none": "Nothing installed yet",
        "settings.title": "Settings",
        "settings.save": "Save",
        "settings.theme": "Background theme",
        "settings.source": "Download source",
        "common.ok": "OK",
        "common.cancel": "Cancel",
        "common.close": "Close",
        "common.refresh": "Refresh",
        "common.query": "Check",
        "common.install": "Install",
        "common.failed": "Failed",
        "common.done": "Done",
        "common.cancelled": "Cancelled",
    },
}


def supported() -> tuple[str, ...]:
    return _SUPPORTED


def get_lang() -> str:
    return _LANG


def set_lang(code: str) -> str:
    global _LANG
    _LANG = code if code in _SUPPORTED else "zh"
    return _LANG


def t(key: str, **kw) -> str:
    table = _TABLE.get(_LANG, {})
    text = table.get(key) or _TABLE["zh"].get(key) or key
    if kw:
        try:
            return text.format(**kw)
        except Exception:
            return text
    return text
