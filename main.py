"""CBL Cube Launcher — 入口"""

import os
import sys
import traceback


def _setup_paths():
    """设置工作目录和 Python 路径（兼容 PyInstaller / Nuitka / 开发模式）。"""
    if getattr(sys, "frozen", False):
        d = os.path.dirname(sys.executable)
    elif sys.argv and os.path.abspath(sys.argv[0]).lower().endswith(".exe"):
        d = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        d = os.path.dirname(os.path.abspath(__file__))
    try:
        os.chdir(d)
    except OSError as e:
        # 只读介质 / 受控目录 / Program Files：继续用当前目录，别在启动阶段就崩
        print(f"[main] 无法切换工作目录到 {d}: {e}", file=sys.stderr)
    if d not in sys.path:
        sys.path.insert(0, d)


_setup_paths()

from PyQt6.QtWidgets import QApplication, QMessageBox

from ui.styles import MAIN_STYLE
from core.config import Config


def _fatal(message: str):
    print(message, file=sys.stderr)
    app = QApplication.instance()
    if app is not None:
        try:
            QMessageBox.critical(None, "CBL 启动失败", message)
        except Exception:
            pass
    sys.exit(1)


def main():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401 — 必须在 QApp 之前导入
    app = QApplication(sys.argv)
    app.setApplicationName("CBL - Cube Launcher")
    app.setStyle("Fusion")
    app.setStyleSheet(MAIN_STYLE)

    try:
        config = Config()
    except Exception:
        _fatal("读取配置失败：\n" + traceback.format_exc(limit=3))
        return

    if getattr(config, "last_error", ""):
        print(f"[main] {config.last_error}（设置将无法保存）", file=sys.stderr)

    if not config.get("agreement_accepted"):
        from ui.agreement_dialog import AgreementDialog
        dlg = AgreementDialog()
        if dlg.exec() and dlg.accepted_result:
            from datetime import datetime
            config.set("agreement_accepted", True)
            config.set("agreement_time", datetime.now().isoformat())
        else:
            sys.exit(0)

    from core import mirror
    src = config.get("download_source", "auto")
    if src == "auto":
        # 秒开：先用上一次测速结果，真正的测速交给主窗口的后台线程，
        # 不再在窗口出现前同步等 6 秒。
        mirror.activate(config.get("last_good_source", "official"))
    else:
        mirror.activate(src)

    # 接管 minecraft-launcher-lib 的下载：Range 续传 + 分块并发 + SHA1 校验
    from core import download
    try:
        downloader = download.Downloader(
            concurrency=int(config.get("download_concurrency", 4) or 4),
            rate_limit_kbps=int(config.get("download_rate_limit", 0) or 0),
        )
        patched = download.install_into_mll(downloader)
        print(f"[main] 下载器已接管 {patched} 个库模块", file=sys.stderr)
    except Exception:
        print("[main] 下载器接管失败，回退库内实现\n" + traceback.format_exc(limit=3),
              file=sys.stderr)

    # 界面语言
    from core.i18n import set_lang
    set_lang(config.get("lang", "zh"))

    try:
        from ui.main_window import MainWindow
        window = MainWindow()
    except Exception:
        _fatal("创建主窗口失败：\n" + traceback.format_exc(limit=6))
        return
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
