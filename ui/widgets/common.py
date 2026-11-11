"""可复用 UI 组件 — 玻璃面板、页面标题、带标签字段、分隔线、版本类型。"""

import re
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget


def friendly_error(msg) -> str:
    """把下载/网络异常翻成人话，并给出可执行的下一步。

    裸的 "404 Client Error: Not Found for url: ..." 对用户没有意义，
    而且这种情况往往不是网络问题，是当前镜像确实缺那个文件。
    """
    text = str(msg or "").strip()
    low = text.lower()
    hint = ""
    if "404" in text or "not found" in low:
        hint = ("当前下载源缺少这个文件（不是你的网络问题）。启动器已自动尝试官方源；"
                "若仍失败，到「设置 → 下载」换一个源再试。")
    elif any(k in low for k in ("timeout", "timed out", "connection reset", "connection aborted",
                                "ssl", "proxy", "unknownhost", "max retries", "getaddrinfo")):
        hint = "网络请求失败。可以到「设置 → 下载」换个源，或检查代理 / 防火墙。"
    elif "sha1" in low or "校验" in text:
        hint = "文件校验不通过（下载被截断或被替换）。重试一次通常就能好。"
    elif "permission" in low or "access is denied" in low:
        hint = "写入被拒绝：检查游戏目录权限，或把启动器换到可写的位置。"
    if not hint:
        return text or "未知错误"
    return (text + "\n\n" + hint) if text else hint


def make_sheet(obj_name: str = "panel") -> QFrame:
    """创建半透明玻璃面板。"""
    f = QFrame()
    f.setObjectName(obj_name)
    return f


def page_title(title: str, subtitle: str = "") -> QWidget:
    """页面标题 + 可选副标题。"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 8)
    lay.setSpacing(4)

    t = QLabel(title)
    t.setObjectName("title")
    lay.addWidget(t)

    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("subtitle")
        s.setWordWrap(True)
        lay.addWidget(s)
    return w


def labeled_field(label: str, widget, helper: str = "") -> QWidget:
    """标签 + 控件 + 可选帮助文字的垂直包装。"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)

    lbl = QLabel(label)
    lbl.setObjectName("fieldLabel")
    lay.addWidget(lbl)

    if isinstance(widget, QWidget):
        lay.addWidget(widget)

    if helper:
        h = QLabel(helper)
        h.setObjectName("mutedLabel")
        h.setWordWrap(True)
        lay.addWidget(h)
    return w


def vline() -> QFrame:
    """竖向分隔线 2px（MC 风格深色）。"""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.VLine)
    line.setFixedWidth(2)
    line.setStyleSheet("background: #1A172A; border: none;")
    return line


def version_kind(vid: str) -> str:
    """从版本 ID 推断类型标签。"""
    v = vid.lower()
    if "neoforge" in v:
        return "NeoForge"
    if "forge" in v:
        return "Forge"
    if "fabric" in v:
        return "Fabric"
    if "quilt" in v:
        return "Quilt"
    if "optifine" in v:
        return "OptiFine"
    if re.search(r"\d+w\d+[a-z]", v) or "-pre" in v or "-rc" in v:
        return "快照"
    return "正式版"


# ───────────── 多产品重构新增的小工具 ─────────────

_KIND_TEXT = {
    "release": "正式版",
    "snapshot": "快照",
    "old": "远古",
    "old_alpha": "远古α",
    "old_beta": "远古β",
    "loader": "加载器",
    "store": "商店",
    "server": "服务端",
}


def kind_text(kind: str) -> str:
    """GameVersion.kind → 中文标签（安装列表与实例详情共用）。"""
    k = (kind or "").strip()
    return _KIND_TEXT.get(k, k or "未知")


def auth_dict(config) -> dict:
    """从 config 组装 provider.launch(instance, auth) 需要的 auth 字典。"""
    def _g(key, default=""):
        try:
            v = config.get(key, default)
        except Exception:
            return default
        return default if v is None else v

    auth_type = str(_g("auth_type", "offline") or "offline")
    return {
        "auth_type": auth_type,
        "username": str(_g("username", "") or ""),
        "uuid": str(_g("uuid", "") or ""),
        "access_token": str(_g("access_token", "") or ""),
        "refresh_token": str(_g("refresh_token", "") or ""),
        "yggdrasil_api": str(_g("yggdrasil_api", "") or ""),
    }


def tree_sheet() -> str:
    """QTreeWidget 的 MC 凹槽风格（styles.py 未覆盖该控件，避免露出 Fusion 浅色底）。"""
    return """
    QTreeWidget {
        background-color: #1A172A;
        color: #CCCCDD;
        border-top: 2px solid #0E0C1E;
        border-left: 2px solid #0E0C1E;
        border-bottom: 2px solid #3A3748;
        border-right: 2px solid #3A3748;
        border-radius: 0;
        outline: none;
        padding: 2px;
        selection-background-color: #1E3A12;
        selection-color: #55FF55;
    }
    QTreeWidget::item {
        padding: 5px 2px;
        border: none;
    }
    QTreeWidget::item:selected {
        background-color: #1E3A12;
        color: #55FF55;
    }
    QTreeWidget::item:hover:!selected {
        background-color: #2A2838;
        color: #FFFFFF;
    }
    QTreeWidget::branch {
        background: transparent;
    }
    """


def console_sheet() -> str:
    """只读控制台的凹槽风格（styles.py 未覆盖 QPlainTextEdit）。"""
    return """
    QPlainTextEdit {
        background-color: #100F1A;
        color: #AAAAAA;
        border-top: 2px solid #0E0C1E;
        border-left: 2px solid #0E0C1E;
        border-bottom: 2px solid #3A3748;
        border-right: 2px solid #3A3748;
        border-radius: 0;
        padding: 4px;
        selection-background-color: #1E3A12;
        selection-color: #55FF55;
    }
    """


def notify_diagnose(parent, config, log_path: str = "", exit_code: int = 0) -> None:
    """游戏非 0 退出后的诊断弹窗。

    core.diagnose 还在并行开发：用 getattr 探测 analyze_file；
    没有就退回旧的「打开日志文件夹 + 日志尾巴」提示，绝不因为缺模块而崩。
    """
    from PyQt6.QtWidgets import QMessageBox

    detail = ""
    analyze = None
    try:
        from core import diagnose as _diagnose  # type: ignore
        analyze = getattr(_diagnose, "analyze_file", None)
    except Exception:
        analyze = None

    if callable(analyze) and log_path:
        try:
            result = analyze(log_path)
            if isinstance(result, str):
                detail = result
            elif isinstance(result, (list, tuple)):
                detail = "\n".join(str(x) for x in result)
            elif isinstance(result, dict):
                detail = "\n".join(f"{k}: {v}" for k, v in result.items())
            elif result is not None:
                detail = str(result)
        except Exception as e:
            detail = f"诊断失败：{e}"

    # 再补一份日志尾巴，让详情里总有可读内容
    try:
        from core import log_manager
        tail = log_manager.read_log_tail(log_path, 30) if log_path else ""
        if tail:
            detail = (detail + "\n\n" if detail else "") + f"游戏日志（最后 30 行）：\n{tail}"
    except Exception:
        pass

    try:
        dlg = QMessageBox(parent)
        dlg.setWindowTitle("游戏异常退出")
        dlg.setIcon(QMessageBox.Icon.Warning)
        dlg.setText(f"游戏异常退出（代码 {exit_code}）")
        if detail:
            dlg.setInformativeText("下面是自动诊断与日志摘要。")
            dlg.setDetailedText(detail)
        else:
            dlg.setInformativeText(
                "没有可用的诊断信息。可能是 Mod 不兼容、Java 版本不匹配或内存不足。"
            )
        btn_log = dlg.addButton("打开日志文件夹", QMessageBox.ButtonRole.ActionRole)
        dlg.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
        dlg.exec()
        if dlg.clickedButton() is btn_log:
            try:
                mc_dir = config.get_minecraft_dir()
                log_manager.open_logs_folder(mc_dir)
            except Exception:
                pass
    except Exception:
        # 弹窗本身失败（例如 offscreen）也不能把调用方拖崩
        pass
