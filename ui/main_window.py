"""主窗口 — 无边框 + 全屏英雄布局 + 自定义标题栏 + 边缘缩放。"""

import sys
import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QStackedWidget, QMessageBox,
)
from PyQt6.QtCore import Qt, QSize, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QKeySequence, QShortcut

from core.config import Config
from core import skin_manager, java_manager, log_manager
from core import download as download_mod
from core.instances import InstanceStore
from core.providers import ProviderContext, ensure as ensure_providers
from core.i18n import t
from ui.background import BackgroundWidget
from ui.pages.home_page import HomePage, LoginWidget
from ui.pages.library_page import LibraryPage
from ui.pages.settings_page import SettingsPage
from ui.widgets.icons import CubeMark, AvatarBadge, nav_icon, window_icon
from ui.tokens import SPACE_LG, SPACE_SM, ICON


# ── 可拖拽标题栏 ───────────────────────────────────

class _DragBar(QWidget):
    """鼠标拖拽 = 移动窗口，双击 = 切换最大化。"""

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            wh = self.window().windowHandle()
            if wh:
                wh.startSystemMove()

    def mouseDoubleClickEvent(self, event):
        win = self.window()
        if hasattr(win, "_toggle_max"):
            win._toggle_max()


# ── 主窗口 ─────────────────────────────────────────

class MainWindow(QMainWindow):
    _EDGE = 5

    def __init__(self):
        super().__init__()
        self.config = Config()
        self.java_ready = False
        self.setWindowTitle("CBL - Cube Launcher")
        self.setWindowIcon(window_icon())
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(960, 600)
        self.resize(1100, 720)

        self._bg = BackgroundWidget()
        self.setCentralWidget(self._bg)

        saved_theme = self.config.get("theme", "")
        if saved_theme and saved_theme != "random":
            self._bg.set_theme(saved_theme)
        else:
            self._bg.set_random_theme()

        root = QVBoxLayout(self._bg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topstrip())

        self.stack = QStackedWidget()
        self.stack.setObjectName("contentStack")

        self._init_providers()

        self.login_widget = LoginWidget(self.config)
        self.login_widget.login_success.connect(self.on_login_success)

        self.home_page = HomePage(self.config, self.ctx)
        self.home_page.go_library.connect(lambda: self.switch_page(1))
        self.library_page = LibraryPage(self.config, self.ctx)
        self.settings_page = SettingsPage(self.config, self.ctx)

        self.stack.addWidget(self.login_widget)    # 0
        self.stack.addWidget(self.home_page)       # 1
        self.stack.addWidget(self.library_page)    # 2
        self.stack.addWidget(self.settings_page)   # 3
        root.addWidget(self.stack, 1)

        root.addWidget(self._build_navbar())
        self._shortcuts()

        if self.config.get("username") and self.config.get("uuid"):
            self.on_login_success()
        else:
            self.stack.setCurrentIndex(0)
            self._set_nav_enabled(False)

        self._logger = log_manager.setup_launcher_log(self.config.get_minecraft_dir())
        self._logger.info(f"版本 0.6.0 | 下载源: {self.config.get('download_source', 'auto')}")
        self._check_java_env()
        self._show_source_info()

    # ── 多产品上下文 ────────────────────────────────

    def _init_providers(self):
        """构造 ProviderContext 并加载 provider；任何失败都不能拖垮窗口。

        providers 一个都没加载成功时（例如 java provider 还在并行开发），
        ctx 仍然可用，库页显示空态而不是崩。
        """
        mc_dir = self.config.get_minecraft_dir()
        self.store = None
        self.providers = {}

        try:
            self.store = InstanceStore(mc_dir)
        except Exception as e:
            print(f"[main] 实例库初始化失败: {e}", file=sys.stderr)

        self.ctx = None
        try:
            self.ctx = ProviderContext(
                mc_dir=mc_dir,
                config=self.config,
                store=self.store,
                downloader=download_mod.default_downloader(),
            )
        except Exception as e:
            print(f"[main] ProviderContext 构造失败: {e}", file=sys.stderr)

        if self.ctx is None:
            # 兜底上下文：界面仍然能构建，只是没有任何产品
            from types import SimpleNamespace
            self.ctx = SimpleNamespace(mc_dir=mc_dir, config=self.config,
                                       store=self.store, downloader=None)
            return

        try:
            self.providers = ensure_providers(self.ctx) or {}
        except Exception as e:
            print(f"[main] provider 加载失败: {e}", file=sys.stderr)
            self.providers = {}

        # 一次性把老的 selected_version / game_directories 迁移成实例
        if self.store is not None:
            try:
                migrated = self.store.migrate_legacy(self.config)
                if migrated:
                    print(f"[main] 已迁移 {migrated} 个旧版本为实例", file=sys.stderr)
            except Exception as e:
                print(f"[main] 旧版本迁移失败: {e}", file=sys.stderr)

            # 已经装在磁盘上但没有实例的版本，直接补建实例。
            # 否则用户装完版本回到库页，看到的还是「还没有实例」，无从启动。
            try:
                tombstones = self.config.get("instance_tombstones", []) or []
                added = self.store.sync_installed(
                    self.providers.values(), tombstones)
                if added:
                    print(f"[main] 为 {added} 个已安装版本补建了实例", file=sys.stderr)
            except Exception as e:
                print(f"[main] 补建实例失败: {e}", file=sys.stderr)

    # ── 自定义标题栏 (可拖拽 + 窗口控件) ─────────────

    def _build_topstrip(self) -> QWidget:
        strip = _DragBar()
        strip.setObjectName("topStrip")
        strip.setFixedHeight(40)
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(SPACE_LG, 0, 4, 0)
        lay.setSpacing(SPACE_SM)

        lay.addWidget(CubeMark(18))
        brand = QLabel("CBL")
        brand.setObjectName("brandTitle")
        lay.addWidget(brand)
        sub = QLabel("CUBE LAUNCHER")
        sub.setObjectName("brandSub")
        lay.addWidget(sub)
        lay.addStretch()

        self.avatar = AvatarBadge(24)
        lay.addWidget(self.avatar)
        names = QVBoxLayout()
        names.setContentsMargins(4, 5, 0, 5)
        names.setSpacing(0)
        self.user_label = QLabel("未登录")
        self.user_label.setObjectName("topUser")
        names.addWidget(self.user_label)
        self.auth_label = QLabel("请先登录")
        self.auth_label.setObjectName("topAuth")
        names.addWidget(self.auth_label)
        lay.addLayout(names)

        self.logout_btn = QPushButton("退出")
        self.logout_btn.setObjectName("logoutBtn")
        self.logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.logout_btn.clicked.connect(self.logout)
        self.logout_btn.hide()
        lay.addWidget(self.logout_btn)

        self.env_label = QLabel("")
        self.env_label.setObjectName("topAuth")
        lay.addWidget(self.env_label)

        lay.addSpacing(8)

        self._max_btn = QPushButton("□")
        for btn, name, slot in [
            (QPushButton("─"), "winMin", self.showMinimized),
            (self._max_btn, "winMax", self._toggle_max),
            (QPushButton("✕"), "winClose", self.close),
        ]:
            btn.setObjectName(name)
            btn.setFixedSize(36, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        return strip

    def closeEvent(self, event):
        """关窗口时给后台线程一点收尾时间，避免解释器退出时警告 Killed while running。"""
        for attr in ("_java_thread", "_speed_thread"):
            th = getattr(self, attr, None)
            try:
                if th is not None and th.isRunning():
                    th.wait(1500)
            except Exception:
                pass
        # 页面自己的后台任务同样要收尾（库页 / 首页各自持有线程）
        for page in (getattr(self, "home_page", None),
                     getattr(self, "library_page", None)):
            try:
                if page is not None and hasattr(page, "shutdown"):
                    page.shutdown(1500)
            except Exception:
                pass
        super().closeEvent(event)

    def _toggle_max(self):
        if self.isMaximized():
            self.showNormal()
            self._max_btn.setText("□")
            self._bg._draw_border = True
        else:
            self.showMaximized()
            self._max_btn.setText("❐")
            self._bg._draw_border = False

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            is_max = self.isMaximized()
            self._max_btn.setText("❐" if is_max else "□")
            self._bg._draw_border = not is_max
            # 最小化时停掉背景粒子动画（50fps 全窗重绘）
            self._bg.set_animating(not self.isMinimized())
        super().changeEvent(event)

    # ── 边缘缩放 (鼠标事件方式，跨平台) ──────────────

    def _edge_at(self, pos) -> str | None:
        """检测鼠标是否在窗口边缘（用于缩放）。"""
        if self.isMaximized():
            return None
        e = self._EDGE
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        l, r = x < e, x > w - e
        t, b = y < e, y > h - e
        if t and l: return "tl"
        if t and r: return "tr"
        if b and l: return "bl"
        if b and r: return "br"
        if t: return "t"
        if b: return "b"
        if l: return "l"
        if r: return "r"
        return None

    _CURSOR_MAP = {
        "t": Qt.CursorShape.SizeVerCursor,
        "b": Qt.CursorShape.SizeVerCursor,
        "l": Qt.CursorShape.SizeHorCursor,
        "r": Qt.CursorShape.SizeHorCursor,
        "tl": Qt.CursorShape.SizeFDiagCursor,
        "br": Qt.CursorShape.SizeFDiagCursor,
        "tr": Qt.CursorShape.SizeBDiagCursor,
        "bl": Qt.CursorShape.SizeBDiagCursor,
    }

    _QT_EDGE_MAP = {
        "t": Qt.Edge.TopEdge,
        "b": Qt.Edge.BottomEdge,
        "l": Qt.Edge.LeftEdge,
        "r": Qt.Edge.RightEdge,
        "tl": Qt.Edge.TopEdge | Qt.Edge.LeftEdge,
        "tr": Qt.Edge.TopEdge | Qt.Edge.RightEdge,
        "bl": Qt.Edge.BottomEdge | Qt.Edge.LeftEdge,
        "br": Qt.Edge.BottomEdge | Qt.Edge.RightEdge,
    }

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                wh = self.windowHandle()
                if wh:
                    wh.startSystemResize(self._QT_EDGE_MAP[edge])
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        edge = self._edge_at(event.position().toPoint())
        if edge:
            self.setCursor(self._CURSOR_MAP[edge])
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    # ── 底部导航栏 ──────────────────────────────────

    def _build_navbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("navBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 6, 0, 10)
        lay.addStretch()

        inner = QHBoxLayout()
        inner.setSpacing(4)

        self.nav_buttons: list[tuple[str, QPushButton]] = []
        # key 只用于选像素图标；文案走 i18n
        for key, label in [
            ("home", t("nav.home")),
            ("versions", t("nav.library")),
            ("settings", t("nav.settings")),
        ]:
            btn = QPushButton(f" {label}")
            btn.setObjectName("navTab")
            btn.setIcon(nav_icon(key, False))
            btn.setIconSize(QSize(ICON, ICON))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", "false")
            btn.setAccessibleName(label)
            btn.clicked.connect(
                lambda _, k=key: self.switch_page(
                    next(i for i, (kk, __) in enumerate(self.nav_buttons) if kk == k)
                )
            )
            inner.addWidget(btn)
            self.nav_buttons.append((key, btn))

        lay.addLayout(inner)
        lay.addStretch()
        return bar

    # ── 快捷键 / 页面切换 ───────────────────────────

    def _shortcuts(self):
        for i in range(len(self.nav_buttons)):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda idx=i: self._nav_shortcut(idx))

    def _nav_shortcut(self, idx):
        if idx < len(self.nav_buttons) and self.nav_buttons[idx][1].isEnabled():
            self.switch_page(idx)

    def switch_page(self, index):
        if not self.nav_buttons[0][1].isEnabled():
            return
        self.stack.setCurrentIndex(index + 1)
        for i, (key, btn) in enumerate(self.nav_buttons):
            active = (i == index)
            btn.setProperty("active", "true" if active else "false")
            btn.setIcon(nav_icon(key, active))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        pages = [self.home_page, self.library_page, self.settings_page]
        if hasattr(pages[index], "refresh"):
            pages[index].refresh()

    def _set_nav_enabled(self, enabled):
        for key, btn in self.nav_buttons:
            btn.setEnabled(enabled)
            btn.setProperty("active", "false")
            btn.setIcon(nav_icon(key, False))
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ── 登录 / 登出 ─────────────────────────────────

    def on_login_success(self):
        username = self.config.get("username", "Player")
        auth_type = self.config.get("auth_type", "offline")
        self.user_label.setText(username)
        self.auth_label.setText("微软正版" if auth_type == "microsoft" else "离线模式")
        self.avatar.set_name(username)
        self.logout_btn.show()
        self._set_nav_enabled(True)
        self._load_avatar()
        self.switch_page(0)

    def _load_avatar(self):
        uid = self.config.get("uuid", "")
        if self.config.get("auth_type") == "microsoft" and uid:
            hp = skin_manager.download_skin_head(uid)
            if hp and os.path.exists(hp):
                px = QPixmap(hp).scaled(
                    24, 24,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.avatar.set_pixmap(px)
                return
        self.avatar.set_pixmap(None)

    def logout(self):
        reply = QMessageBox.question(
            self, "确认退出",
            "退出当前账号？本地游戏文件不会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for key in ("auth_type", "uuid", "access_token", "refresh_token"):
            self.config.set(key, "" if key != "auth_type" else "offline")
        self.user_label.setText("未登录")
        self.auth_label.setText("请先登录")
        self.avatar.set_name("?")
        self.avatar.set_pixmap(None)
        self.logout_btn.hide()
        self._set_nav_enabled(False)
        self.stack.setCurrentIndex(0)

    def _show_source_info(self):
        """在顶部条显示当前下载源，并在后台重新测速（不阻塞窗口）。"""
        from core import mirror
        key = mirror.get_active_key()
        self.env_label.setText(f"下载源 {mirror.get_name(key)}")
        # 只有“自动”才需要在后台重新测速
        if self.config.get("download_source", "auto") != "auto":
            return
        self._speed_thread = _SourceSpeedThread()
        self._speed_thread.done.connect(self._speed_done)
        self._speed_thread.start()

    def _speed_done(self, key: str, ms: int):
        from core import mirror
        if not key:
            self.env_label.setText(f"下载源 {mirror.get_name(mirror.get_active_key())}（测速失败）")
            return
        mirror.activate(key)
        self.config.set("last_good_source", key)
        self.env_label.setText(
            f"下载源 {mirror.get_name(key)}" + (f" · {ms}ms" if ms > 0 else "")
        )

    # ── Java 环境自动检查与下载 ──────────────────────

    def _check_java_env(self):
        """后台检查 Java 环境：必要时把运行时迁到英文路径，缺的再补下。

        为什么每次都要跑：含中文的安装目录下，Java 8 的 zip.dll 会加载失败
        （"no zip in java.library.path"），所以运行时必须先落到 ASCII 根。
        线程内部只在真的做了事时才更新顶部状态，不打扰"下载源"那行信息。
        """
        mc = self.config.get_minecraft_dir()
        java_p = (self.providers or {}).get("java")
        self.java_ready = False
        self._java_thread = _JavaInstallThread(mc, java_p)
        self._java_thread.status.connect(lambda s: self.env_label.setText(s))
        self._java_thread.done.connect(self._java_done)
        self._java_thread.start()

    def _java_done(self, ok):
        self.java_ready = bool(ok)
        th = getattr(self, "_java_thread", None)
        if not getattr(th, "did_work", False):
            # 什么都不用做：别把"下载源 BMCLAPI · 289ms"这行覆盖掉
            return
        if ok:
            self.env_label.setText("Java 环境就绪")
        else:
            self.env_label.setText("Java 准备失败，可在设置里手动指定 Java")


class _SourceSpeedThread(QThread):
    """后台测速，避免在窗口出现前同步阻塞最多 6 秒。"""

    done = pyqtSignal(str, int)

    def run(self):
        try:
            from core.mirror import test_all_sources
            for key, ms in test_all_sources():
                if ms > 0:
                    self.done.emit(key, ms)
                    return
            self.done.emit("", -1)
        except Exception:
            self.done.emit("", -1)


class _JavaInstallThread(QThread):
    """后台下载缺失的 Java 运行时。"""
    status = pyqtSignal(str)
    done = pyqtSignal(bool)

    def __init__(self, mc_dir, provider=None):
        super().__init__()
        self._mc = mc_dir
        self._provider = provider
        self.did_work = False

    def run(self):
        cb = {"setStatus": lambda s: self.status.emit(s)}
        try:
            if self._provider is not None:
                # 1) 先把含中文路径的运行时迁到 ASCII 根（Java 8 必需）
                migrate = getattr(self._provider, "migrate_runtimes", None)
                if callable(migrate):
                    moved = migrate(cb=cb["setStatus"])
                    if moved:
                        self.did_work = True
                        self.status.emit(f"已把 {moved} 个 Java 运行时迁到英文路径")
                # 2) 再看还缺什么
                check = getattr(self._provider, "missing_java", None)
                missing = check() if callable(check) else []
                if missing:
                    self.did_work = True
                    names = "、".join(label for _, label, _ in missing)
                    self.status.emit(f"正在准备 {names}…")
                    install = getattr(self._provider, "install_missing_java", None)
                    if callable(install):
                        install(cb)
            else:
                java_manager.install_all_missing(self._mc, callback=cb)
            self.done.emit(True)
        except Exception as e:
            self.status.emit(f"Java 环境准备失败: {e}")
            self.done.emit(False)
