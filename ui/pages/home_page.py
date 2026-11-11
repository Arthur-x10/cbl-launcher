"""登录面板 + 英雄启动页。"""

import math
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QMessageBox, QLineEdit, QFrame, QStackedWidget, QSizePolicy,
    QGraphicsDropShadowEffect, QButtonGroup,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence, QColor, QStandardItem

from core import auth, java_utils, yggdrasil
from core import providers
from core.i18n import t
from ui.widgets.common import (
    make_sheet, labeled_field, version_kind, auth_dict, notify_diagnose,
)
from ui.tokens import (
    SPACE_XL, SPACE_LG, SPACE_MD, SPACE_SM, SHEET_MAX_W, LAUNCH_W, LAUNCH_H,
    HIT_MIN, PRIMARY,
)


class LoginWidget(QWidget):
    login_success = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._code_verifier = None
        self._ms_state = ""
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sheet = make_sheet("loginSheet")
        sheet.setFixedWidth(SHEET_MAX_W)
        body = QVBoxLayout(sheet)
        body.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
        body.setSpacing(SPACE_MD)

        title = QLabel("开始游戏")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(title)

        sub = QLabel("离线进档，或使用微软账号登录正版。")
        sub.setObjectName("subtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        body.addWidget(sub)

        seg = QFrame()
        seg.setObjectName("segment")
        seg_l = QHBoxLayout(seg)
        seg_l.setContentsMargins(4, 4, 4, 4)
        seg_l.setSpacing(4)
        self.tab_offline = QPushButton("离线")
        self.tab_ms = QPushButton("微软正版")
        self.tab_ygg = QPushButton("LittleSkin")
        for b in (self.tab_offline, self.tab_ms, self.tab_ygg):
            b.setObjectName("segBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tab_offline.setChecked(True)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.tab_offline, 0)
        group.addButton(self.tab_ms, 1)
        group.addButton(self.tab_ygg, 2)
        group.idClicked.connect(self._seg)
        seg_l.addWidget(self.tab_offline)
        seg_l.addWidget(self.tab_ms)
        seg_l.addWidget(self.tab_ygg)
        body.addWidget(seg)

        self.forms = QStackedWidget()
        self.forms.addWidget(self._offline_form())
        self.forms.addWidget(self._ms_form())
        self.forms.addWidget(self._ygg_form())
        body.addWidget(self.forms)

        root.addWidget(sheet, 0, Qt.AlignmentFlag.AlignCenter)
        self.username_input.setFocus()

    def _offline_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_MD)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("3～16 个字符")
        self.username_input.setText(self.config.get("username", "Player"))
        self.username_input.setClearButtonEnabled(True)
        self.username_input.returnPressed.connect(self._offline_login)
        lay.addWidget(labeled_field("玩家名称", self.username_input, "不会上传账号，只用于存档显示名。"))

        self.offline_btn = QPushButton("进入启动器")
        self.offline_btn.setObjectName("btnPrimary")
        self.offline_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.offline_btn.setFixedHeight(HIT_MIN + 4)
        self.offline_btn.clicked.connect(self._offline_login)
        lay.addWidget(self.offline_btn)
        return w

    def _ms_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_MD)

        hint = QLabel("点击下方按钮，在弹出的窗口中登录微软账号。\n登录完成后自动返回启动器，无需任何手动操作。")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.ms_btn = QPushButton("微软正版登录")
        self.ms_btn.setObjectName("btnPrimary")
        self.ms_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ms_btn.setFixedHeight(HIT_MIN + 4)
        self.ms_btn.clicked.connect(self._ms_start)
        lay.addWidget(self.ms_btn)

        self.ms_status = QLabel("")
        self.ms_status.setObjectName("statusLabel")
        self.ms_status.setWordWrap(True)
        lay.addWidget(self.ms_status)
        return w

    def _seg(self, idx: int):
        self.tab_offline.setChecked(idx == 0)
        self.tab_ms.setChecked(idx == 1)
        self.tab_ygg.setChecked(idx == 2)
        self.forms.setCurrentIndex(idx)
        if idx == 0:
            self.username_input.setFocus()
        elif idx == 2:
            self.ygg_email.setFocus()

    def _offline_login(self):
        name = self.username_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入玩家名称。")
            self.username_input.setFocus()
            return
        if not (3 <= len(name) <= 16):
            QMessageBox.warning(self, "提示", "玩家名称需要 3～16 个字符。")
            self.username_input.setFocus()
            return
        r = auth.offline_login(name)
        self.config.set("auth_type", r.auth_type)
        self.config.set("username", r.username)
        self.config.set("uuid", r.uuid)
        self.config.set("access_token", r.access_token)
        self.login_success.emit()

    # ── LittleSkin (Yggdrasil) ──

    def _ygg_form(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_MD)

        hint = QLabel("使用 LittleSkin 账号登录，支持自定义皮肤、披风，无需正版。")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        self.ygg_email = QLineEdit()
        self.ygg_email.setPlaceholderText("注册邮箱")
        lay.addWidget(labeled_field("邮箱", self.ygg_email))

        self.ygg_pw = QLineEdit()
        self.ygg_pw.setPlaceholderText("密码")
        self.ygg_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.ygg_pw.returnPressed.connect(self._ygg_login)
        lay.addWidget(labeled_field("密码", self.ygg_pw))

        self.ygg_btn = QPushButton("登录 LittleSkin")
        self.ygg_btn.setObjectName("btnPrimary")
        self.ygg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ygg_btn.setFixedHeight(HIT_MIN + 4)
        self.ygg_btn.clicked.connect(self._ygg_login)
        lay.addWidget(self.ygg_btn)

        reg_btn = QPushButton("没有账号？前往 LittleSkin 注册")
        reg_btn.setObjectName("btnGhost")
        reg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reg_btn.setFixedHeight(HIT_MIN)
        reg_btn.clicked.connect(lambda: __import__("webbrowser").open("https://littleskin.cn/auth/register"))
        lay.addWidget(reg_btn)

        self.ygg_status = QLabel("")
        self.ygg_status.setObjectName("statusLabel")
        self.ygg_status.setWordWrap(True)
        lay.addWidget(self.ygg_status)
        return w

    def _ygg_login(self):
        email = self.ygg_email.text().strip()
        pw = self.ygg_pw.text()
        if not email or not pw:
            QMessageBox.warning(self, "提示", "请输入邮箱和密码。")
            return

        self.ygg_btn.setEnabled(False)
        self.ygg_btn.setText("登录中…")
        mc = self.config.get_minecraft_dir()

        self._ygg_t = _YggThread(email, pw, yggdrasil.DEFAULT_API, mc)
        self._ygg_t.status_msg.connect(lambda s: self.ygg_status.setText(s))
        self._ygg_t.done.connect(self._ygg_done)
        self._ygg_t.start()

    def _ygg_done(self, result):
        self.ygg_btn.setEnabled(True)
        self.ygg_btn.setText("登录 LittleSkin")
        if isinstance(result, str):
            self.ygg_status.setText(result)
            return
        self.config.set("auth_type", "yggdrasil")
        self.config.set("username", result.username)
        self.config.set("uuid", result.uuid)
        self.config.set("access_token", result.access_token)
        self.config.set("yggdrasil_api", result.api_root)
        self.ygg_status.setText(f"欢迎，{result.username}！")
        self.login_success.emit()

    def _ms_start(self):
        """内嵌浏览器微软登录 — 弹出窗口，自动拦截授权码。"""
        self.ms_btn.setEnabled(False)
        self.ms_btn.setText("正在打开登录…")
        self.ms_status.setText("")

        try:
            login_url, state, code_verifier = auth.get_microsoft_login_url()
            self._ms_cv = code_verifier
            self._ms_state = state

            from ui.widgets.ms_login_dialog import MsLoginDialog
            dlg = MsLoginDialog(
                login_url, auth.REDIRECT_URL, state, self.window()
            )
            dlg.code_received.connect(self._ms_got_code)

            self.ms_btn.setText("等待登录…")
            result = dlg.exec()

            if not result:
                self.ms_btn.setEnabled(True)
                self.ms_btn.setText("微软正版登录")
                if dlg.get_code():
                    return
                if getattr(dlg, "invalid_callback_seen", False):
                    self.ms_status.setText("登录校验失败，请重试")
                else:
                    self.ms_status.setText("登录已取消")
        except Exception as e:
            self.ms_btn.setEnabled(True)
            self.ms_btn.setText("微软正版登录")
            self.ms_status.setText(f"错误: {e}")

    def _ms_got_code(self, code):
        """内嵌浏览器成功拦截到授权码（state 已在对话框内校验相等）。"""
        code = (code or "").strip()
        if not code:
            self.ms_btn.setEnabled(True)
            self.ms_btn.setText("微软正版登录")
            self.ms_status.setText("登录校验失败，请重试")
            return
        self.ms_status.setText("正在验证微软账号…")
        self._ms_t = _MsCompleteThread(code, self._ms_cv)
        self._ms_t.done.connect(self._ms_done)
        self._ms_t.start()

    def _ms_done(self, r):
        self.ms_btn.setEnabled(True)
        self.ms_btn.setText("微软正版登录")
        if r:
            for k in ("auth_type", "username", "uuid", "access_token", "refresh_token"):
                self.config.set(k, getattr(r, k, ""))
            self.ms_status.setText(f"欢迎，{r.username}！")
            self.login_success.emit()
        else:
            self.ms_status.setText("验证失败，请重试。")


class _YggThread(QThread):
    """LittleSkin Yggdrasil 认证线程。"""
    done = pyqtSignal(object)
    status_msg = pyqtSignal(str)

    def __init__(self, email, password, api_root, mc_dir):
        super().__init__()
        self._email = email
        self._pw = password
        self._api = api_root
        self._mc = mc_dir

    def run(self):
        try:
            self.status_msg.emit("正在下载 authlib-injector…")
            if not yggdrasil.is_injector_installed(self._mc):
                yggdrasil.download_injector(self._mc)

            self.status_msg.emit("正在验证 LittleSkin 账号…")
            result = yggdrasil.authenticate(self._email, self._pw, self._api)
            self.done.emit(result)
        except Exception as e:
            self.done.emit(str(e))


class _MsCompleteThread(QThread):
    """后台完成微软登录（auth code → MC token，耗时操作）。"""
    done = pyqtSignal(object)

    def __init__(self, code, cv):
        super().__init__()
        self._code, self._cv = code, cv

    def run(self):
        self.done.emit(auth.complete_microsoft_login(self._code, self._cv))


class _LaunchThread(QThread):
    """启动放后台：p.launch 会做 Java 解析、拼命令行，可能耗时。"""

    done = pyqtSignal(object, str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            payload = self._fn()
        except Exception as e:  # noqa: BLE001 — 异常必须回到界面
            try:
                self.done.emit(None, str(e) or e.__class__.__name__)
            except Exception:
                pass
            return
        try:
            self.done.emit(payload, "")
        except Exception as e:  # noqa: BLE001
            try:
                self.done.emit(None, str(e) or "回调失败")
            except Exception:
                pass


class HomePage(QWidget):
    go_library = pyqtSignal()

    def __init__(self, config, ctx, parent=None):
        super().__init__(parent)
        self.config = config
        self.ctx = ctx
        self.store = getattr(ctx, "store", None) if ctx is not None else None
        self._instances = []
        self._inst = None
        self._handle = None
        self._play_start = 0.0
        self._glow = None
        self._java_text = ""
        self._timer = None
        self._th_launch = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        root.addStretch(3)

        hero = QVBoxLayout()
        hero.setSpacing(SPACE_MD)
        hero.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.ver_title = QLabel("选择实例")
        self.ver_title.setObjectName("heroTitle")
        self.ver_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(self.ver_title)

        self.ver_meta = QLabel("")
        self.ver_meta.setObjectName("heroMeta")
        self.ver_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(self.ver_meta)

        picker = QHBoxLayout()
        picker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.ver_combo = QComboBox()
        self.ver_combo.setObjectName("ghostCombo")
        self.ver_combo.setAccessibleName("游戏实例")
        self.ver_combo.setMaxVisibleItems(12)
        self.ver_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.ver_combo.currentIndexChanged.connect(self._on_ver)
        picker.addWidget(self.ver_combo)
        hero.addLayout(picker)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.launch_btn = QPushButton(t("home.launch"))
        self.launch_btn.setObjectName("launchBtn")
        self.launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_btn.setFixedSize(LAUNCH_W, LAUNCH_H)
        self.launch_btn.setAccessibleName("开始游戏")
        self.launch_btn.clicked.connect(self._launch)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(22)
        self._glow.setColor(QColor(85, 255, 85, 80))
        self._glow.setOffset(0, 4)
        self.launch_btn.setGraphicsEffect(self._glow)

        self._glow_phase = 0.0
        self._glow_timer = QTimer(self)
        self._glow_timer.timeout.connect(self._pulse_glow)
        self._glow_timer.start(45)
        btn_row.addWidget(self.launch_btn)
        hero.addLayout(btn_row)

        self.empty_btn = QPushButton(t("home.go_library"))
        self.empty_btn.setObjectName("btnGhost")
        self.empty_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.empty_btn.setFixedHeight(HIT_MIN + 4)
        self.empty_btn.clicked.connect(self.go_library.emit)
        self.empty_btn.hide()
        empty_row = QHBoxLayout()
        empty_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_row.addWidget(self.empty_btn)
        hero.addLayout(empty_row)

        self.status = QLabel("就绪")
        self.status.setObjectName("statusLabel")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero.addWidget(self.status)

        root.addLayout(hero)
        root.addStretch(4)

        sc = QShortcut(QKeySequence(Qt.Key.Key_Return), self)
        sc.activated.connect(self._launch)

    # ── 数据 ──

    def _provider_name(self, pid):
        try:
            p = providers.get(pid)
        except Exception:
            p = None
        name = getattr(p, "name", "") if p is not None else ""
        return str(name or pid)

    def _instance_at(self, idx):
        if idx is None or idx < 0:
            return None
        try:
            iid = self.ver_combo.itemData(idx)
        except Exception:
            iid = None
        for inst in self._instances:
            if inst.id == iid:
                return inst
        if self.store is not None and iid:
            try:
                return self.store.get(iid)
            except Exception:
                return None
        return None

    def refresh(self):
        insts = []
        try:
            insts = list(self.store.all()) if self.store is not None else []
        except Exception:
            insts = []
        self._instances = insts

        self.ver_combo.blockSignals(True)
        self.ver_combo.clear()
        for inst in insts:
            label = "{}  ({} · {})".format(
                inst.name or inst.version_id,
                self._provider_name(inst.provider),
                inst.version_id,
            )
            self.ver_combo.addItem(label, inst.id)
        self.ver_combo.blockSignals(False)

        jp = self.config.get_java_path()
        if not jp:
            d = java_utils.auto_detect_java()
            if d:
                self.config.set("java_path", d)
                jp = d
        if jp:
            self._java_text = "Java " + (java_utils.get_java_version(jp) or "?")
        else:
            self._java_text = "未检测到 Java"

        if insts:
            self.ver_combo.show()
            self.launch_btn.show()
            self.empty_btn.hide()
            last = self.config.get("last_instance_id", "")
            idx = 0
            for i in range(self.ver_combo.count()):
                if self.ver_combo.itemData(i) == last:
                    idx = i
                    break
            self.ver_combo.setCurrentIndex(idx)
            self._on_ver(idx)
        else:
            self.ver_combo.hide()
            self.launch_btn.hide()
            self.empty_btn.show()
            self.ver_title.setText(t("home.no_game"))
            self.ver_meta.setText("先到「库」里安装一个版本")
            self.status.setText("")
            self._inst = None

    def _on_ver(self, index_or_text):
        idx = index_or_text if isinstance(index_or_text, int) else self.ver_combo.currentIndex()
        inst = self._instance_at(idx)
        if inst is None:
            return
        self._inst = inst
        self.ver_title.setText(inst.name or inst.version_id)
        self.ver_meta.setText("{}  ·  {}  ·  {}".format(
            version_kind(inst.version_id),
            self._provider_name(inst.provider),
            self._java_text,
        ))

    # ── 启动 ──

    def _launch(self):
        if self._handle is not None:
            return
        if not self.launch_btn.isVisible() or not self.launch_btn.isEnabled():
            if self.empty_btn.isVisible():
                self.go_library.emit()
            return
        inst = self._inst or self._instance_at(self.ver_combo.currentIndex())
        if inst is None:
            QMessageBox.warning(self, "提示", "还没有可启动的实例，先到「库」里装一个。")
            return
        try:
            p = providers.get(inst.provider)
        except Exception:
            p = None
        if p is None:
            QMessageBox.critical(
                self, "无法启动",
                "产品 " + inst.provider + " 没有加载，无法启动这个实例。")
            return

        auth = auth_dict(self.config)
        try:
            self.config.set("last_instance_id", inst.id)
        except Exception:
            pass
        self.launch_btn.setEnabled(False)
        self.launch_btn.setText(t("home.starting"))
        self.launch_btn.setGraphicsEffect(None)
        self.status.setText("正在启动 " + inst.version_id)

        def task():
            return p.launch(inst, auth)

        th = _LaunchThread(task)
        self._th_launch = th
        th.done.connect(lambda payload, err: self._launched(inst, payload, err))
        th.start()

    def _launched(self, inst, payload, err):
        if err:
            self._reset_btn("启动失败")
            QMessageBox.critical(self, "无法启动", err)
            return
        handle = payload
        process = getattr(handle, "process", None) if handle is not None else None
        if process is None:
            # 商店托管的唤醒式启动：没有进程可轮询
            self.status.setText(inst.version_id + " 已唤醒（由商店托管）")
            self._reset_btn("")
            self._touch_played(inst)
            return

        self._handle = handle
        self._play_start = time.time()
        self.status.setText(inst.version_id + " 已启动")
        self.launch_btn.setText(t("home.running"))
        self.launch_btn.setEnabled(False)
        timer = QTimer(self)
        timer.timeout.connect(self._poll)
        timer.start(3000)
        self._timer = timer
        if self.config.get("close_on_launch", False):
            QTimer.singleShot(800, self._close_after_launch)

    def _close_after_launch(self):
        """按「启动游戏后关闭启动器」设置关闭主窗口。"""
        win = self.window()
        if win is not None:
            win.close()

    def _touch_played(self, inst, seconds=0):
        if self.store is None:
            return
        try:
            self.store.touch_played(inst.id, seconds)
        except Exception:
            pass

    def _poll(self):
        handle = self._handle
        if handle is None:
            if self._timer is not None:
                self._timer.stop()
            return
        try:
            running = bool(handle.running())
        except Exception:
            running = False
        if running:
            return

        if self._timer is not None:
            self._timer.stop()
        code = 0
        try:
            if handle.process is not None:
                code = handle.process.returncode
        except Exception:
            code = 0
        log_path = str(getattr(handle, "log_path", "") or "")
        elapsed = int(max(0, time.time() - self._play_start))
        try:
            handle.close_log()
        except Exception:
            pass
        inst = self._inst
        if inst is not None:
            self._touch_played(inst, elapsed)
        self._handle = None

        if code in (None, 0):
            self._reset_btn("游戏已退出")
        else:
            self._reset_btn("游戏崩溃（代码 {}）".format(code))
            notify_diagnose(self, self.config, log_path, int(code))
        self.refresh()

    def _reset_btn(self, status_text="就绪"):
        self.launch_btn.setEnabled(True)
        self.launch_btn.setText(t("home.launch"))
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(22)
        self._glow.setColor(QColor(85, 255, 85, 80))
        self._glow.setOffset(0, 4)
        self.launch_btn.setGraphicsEffect(self._glow)
        if status_text:
            self.status.setText(status_text)

    # ── 生命周期 ──

    def shutdown(self, wait_ms=1500):
        th = self._th_launch
        try:
            if th is not None and th.isRunning():
                th.wait(wait_ms)
        except Exception:
            pass
        if isinstance(self._timer, QTimer):
            try:
                self._timer.stop()
            except Exception:
                pass

    def showEvent(self, event):
        """只有首页可见时才跑呼吸光效。"""
        super().showEvent(event)
        timer = getattr(self, "_glow_timer", None)
        if timer is not None and self._glow is not None:
            timer.start(45)

    def hideEvent(self, event):
        super().hideEvent(event)
        timer = getattr(self, "_glow_timer", None)
        if timer is not None:
            timer.stop()

    def _pulse_glow(self):
        """启动按钮呼吸光效 — 绿色附魔风格脉冲。"""
        if not self._glow or self.launch_btn.graphicsEffect() is not self._glow:
            return
        self._glow_phase += 0.06
        if self._glow_phase > math.pi * 2:
            self._glow_phase -= math.pi * 2
        radius = 22 + 12 * math.sin(self._glow_phase)
        alpha = int(60 + 50 * math.sin(self._glow_phase))
        self._glow.setBlurRadius(radius)
        c = QColor(85, 255, 85, max(0, min(255, alpha)))
        self._glow.setColor(c)
