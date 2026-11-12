"""库 —— 以实例为中心、按产品分组、按能力渲染。

信息架构:
    左：产品（provider）→ 实例（Instance）两级树 + 安装 / 新建实例 / 删除
    右：QStackedWidget = 空态 / 实例详情 / 安装面板

铁律：
    * 不写 if provider == "java"，一律用 CAP_* 能力判断；
    * 每个后台任务用**独立属性**持有 QThread（共用引用会被 GC → abort）；
    * 线程统一 (payload, error) 信号，异常也一定会发射，按钮不会永久禁用。
"""

import os
import sys
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QStackedWidget, QScrollArea, QFrame, QComboBox,
    QListWidget, QListWidgetItem, QCheckBox, QMessageBox, QInputDialog,
    QLineEdit, QSpinBox, QPlainTextEdit, QFileDialog, QDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QBrush, QColor, QIcon

from core import providers
from core.providers.base import (
    CAP_CONSOLE,
    CAP_JVM,
    CAP_MODLOADER,
    CAP_PACK_IMPORT,
    CAP_STORE,
    CAP_UNINSTALL,
    CAP_VERSION_LIST,
)
from core.i18n import t
from core import paths as core_paths
from ui.widgets.common import (
    make_sheet,
    labeled_field,
    version_kind,
    kind_text,
    auth_dict,
    notify_diagnose,
    tree_sheet,
    console_sheet,
    friendly_error,
)
from ui.widgets.crafting import CraftingBench
from ui.widgets.icons import nav_icon
from ui.widgets.progress_dialog import ProgressDialog
from ui.tokens import SPACE_XL, SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XS, HIT_MIN

# 树节点数据角色
ROLE_PROVIDER = Qt.ItemDataRole.UserRole + 1
ROLE_INSTANCE = Qt.ItemDataRole.UserRole + 2

_LOADERS = (
    ("forge", "Forge"),
    ("fabric", "Fabric"),
    ("quilt", "Quilt"),
    ("neoforge", "NeoForge"),
)

_MUTED = "#7777AA"
_DANGER = "#FF5555"
_OK = "#55FF55"
# 禁用态的危险按钮（颜色压暗，保留 MC 浮雕边框）
_DEL_OFF = (
    "color: #7777AA; background-color: #2A2738;"
    "border-top: 2px solid #1A172A; border-left: 2px solid #1A172A;"
    "border-bottom: 2px solid #3A3748; border-right: 2px solid #3A3748;"
)


# ═══════════════════ 后台任务 ═══════════════════

class _TaskThread(QThread):
    """统一的后台任务线程：done(payload, error) 一定会发射一次。

    provider 调用全部包在 run() 的 try/except 里 —— 异常变成界面文案，
    而不是「信号永不发射、按钮永久禁用」或裸崩。
    """

    done = pyqtSignal(object, str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self._task = task

    def run(self):
        try:
            payload = self._task()
        except Exception as e:  # noqa: BLE001 — 任何异常都要回到界面
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


# ═══════════════════ 新建实例对话框 ═══════════════════

class _NewInstanceDialog(QDialog):
    """从「已安装版本」里挑一个建实例（版本列表由调用方在后台线程取好）。"""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建实例")
        self.setMinimumWidth(480)
        self._choice = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        lay.setSpacing(SPACE_MD)

        tip = QLabel("从已安装的版本里挑一个，创建带独立游戏目录的实例。")
        tip.setObjectName("mutedLabel")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.list = QListWidget()
        self.list.setAccessibleName("已安装版本")
        self.list.setMinimumHeight(240)
        for pid, vid, label in items:
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, (pid, vid))
            self.list.addItem(it)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _it: self._accept())
        lay.addWidget(self.list, 1)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("留空则用版本号")
        lay.addWidget(labeled_field("实例名称", self.name_input))

        self.status = QLabel("")
        self.status.setObjectName("statusLabel")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton(t("common.cancel"))
        cancel.setFixedHeight(HIT_MIN)
        cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        ok = QPushButton("创建")
        ok.setObjectName("btnPrimary")
        ok.setFixedHeight(HIT_MIN)
        ok.setCursor(Qt.CursorShape.PointingHandCursor)
        ok.clicked.connect(self._accept)
        row.addWidget(ok)
        lay.addLayout(row)

    def _accept(self):
        cur = self.list.currentItem()
        if cur is None:
            self.status.setText("请先选一个版本。")
            return
        self._choice = cur.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def choice(self):
        return self._choice

    def name(self):
        return self.name_input.text().strip()


# ═══════════════════ 库页 ═══════════════════

class LibraryPage(QWidget):
    def __init__(self, config, ctx, parent=None):
        super().__init__(parent)
        self.config = config
        self.ctx = ctx
        self.store = getattr(ctx, "store", None)

        self._sel_inst = None
        self._jvm_active = False
        self._handle = None
        self._launched_inst = None
        self._play_start = 0.0
        self._console_handle = None
        self._remote_cache = {}
        self._install_pid = ""
        self._all_remote = []
        self._installed_ids = set()

        # 每个任务一个独立属性：共用引用会被 GC → "Destroyed while running" → abort
        self._th_launch = None
        self._th_remote = None
        self._th_loader = None
        self._th_loader_install = None
        self._th_resolve = None
        self._th_installed = None
        self._th_mods = None
        self._th_modcheck = None
        self._th_delete = None

        self._launch_timer = None
        self._tail_timer = None

        self._build()
        self.refresh()

    # ═══════════════ 布局 ═══════════════

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        root.setSpacing(SPACE_MD)
        root.addWidget(self._build_left(), 2)
        root.addWidget(self._build_right(), 3)

    # ── 左：产品 → 实例 ──

    def _build_left(self):
        panel = make_sheet()
        panel.setMinimumWidth(250)
        panel.setMaximumWidth(340)
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        lay.setSpacing(SPACE_SM)

        hd = QLabel(t("library.title"))
        hd.setObjectName("sectionLabel")
        lay.addWidget(hd)

        sub = QLabel("按产品分组。选一个实例查看它的面板。")
        sub.setObjectName("mutedLabel")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        self.tree = QTreeWidget()
        self.tree.setObjectName("libraryTree")
        self.tree.setAccessibleName("产品与实例")
        self.tree.setHeaderHidden(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setStyleSheet(tree_sheet())
        self.tree.currentItemChanged.connect(self._on_tree_current)
        lay.addWidget(self.tree, 1)

        self.tree_hint = QLabel("")
        self.tree_hint.setObjectName("mutedLabel")
        self.tree_hint.setWordWrap(True)
        self.tree_hint.hide()
        lay.addWidget(self.tree_hint)

        row1 = QHBoxLayout()
        row1.setSpacing(SPACE_SM)
        self.install_btn = QPushButton(t("library.install_new"))
        self.install_btn.setObjectName("btnPrimary")
        self.install_btn.setFixedHeight(HIT_MIN + 2)
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.clicked.connect(self._show_install)
        row1.addWidget(self.install_btn)

        self.new_inst_btn = QPushButton(t("library.create_instance"))
        self.new_inst_btn.setObjectName("btnBlue")
        self.new_inst_btn.setFixedHeight(HIT_MIN + 2)
        self.new_inst_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_inst_btn.clicked.connect(self._new_instance)
        row1.addWidget(self.new_inst_btn)
        lay.addLayout(row1)

        self.del_btn = QPushButton(t("library.delete"))
        self.del_btn.setObjectName("logoutBtn")
        self.del_btn.setFixedHeight(HIT_MIN)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.clicked.connect(self._delete_instance)
        self._set_del_enabled(False)
        lay.addWidget(self.del_btn)
        return panel

    # ── 右：空态 / 详情 / 安装 ──

    def _build_right(self):
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_empty())    # 0
        self.right_stack.addWidget(self._build_detail())   # 1
        self.right_stack.addWidget(self._build_install())  # 2
        return self.right_stack

    def _build_empty(self):
        panel = make_sheet()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.empty_title = QLabel("")
        self.empty_title.setObjectName("title")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.empty_title)

        self.empty_sub = QLabel("")
        self.empty_sub.setObjectName("mutedLabel")
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_sub.setWordWrap(True)
        lay.addWidget(self.empty_sub)
        return panel

    # ── 实例详情 ──

    def _build_detail(self):
        panel = make_sheet()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("scrollArea")
        scroll.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)

        inner = QWidget()
        inner.setObjectName("scrollBody")
        inner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        inner.setAutoFillBackground(False)
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        lay.setSpacing(SPACE_MD)

        self.d_title = QLabel("")
        self.d_title.setObjectName("title")
        lay.addWidget(self.d_title)

        self.d_meta = QLabel("")
        self.d_meta.setObjectName("mutedLabel")
        self.d_meta.setWordWrap(True)
        lay.addWidget(self.d_meta)

        act = QHBoxLayout()
        act.setSpacing(SPACE_SM)
        self.launch_btn = QPushButton(t("library.play"))
        self.launch_btn.setObjectName("btnPrimary")
        self.launch_btn.setFixedHeight(HIT_MIN + 12)
        self.launch_btn.setMinimumWidth(160)
        self.launch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.launch_btn.setAccessibleName("启动游戏")
        self.launch_btn.clicked.connect(self._launch_clicked)
        act.addWidget(self.launch_btn)

        self.open_dir_btn = QPushButton("打开游戏目录")
        self.open_dir_btn.setObjectName("btnGhost")
        self.open_dir_btn.setFixedHeight(HIT_MIN + 12)
        self.open_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_dir_btn.clicked.connect(self._open_game_dir)
        act.addWidget(self.open_dir_btn)
        act.addStretch()
        lay.addLayout(act)

        self.launch_status = QLabel("")
        self.launch_status.setObjectName("statusLabel")
        self.launch_status.setWordWrap(True)
        lay.addWidget(self.launch_status)

        lay.addWidget(self._build_jvm())
        lay.addWidget(self._build_loader())
        lay.addWidget(self._build_mods())
        lay.addWidget(self._build_pack_import())
        lay.addWidget(self._build_console())
        lay.addStretch()
        lay.addWidget(self._build_detail_footer())

        scroll.setWidget(inner)
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(scroll)
        return panel

    # ── CAP_JVM ──

    def _build_jvm(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_SM)
        lay.addWidget(self._sec("内存与 JVM"))

        ram = QHBoxLayout()
        ram.setSpacing(SPACE_LG)
        self.ram_min = QSpinBox()
        self.ram_min.setRange(0, 32768)
        self.ram_min.setSingleStep(256)
        self.ram_min.setSuffix(" MB")
        self.ram_min.setFixedHeight(HIT_MIN)
        self.ram_min.setAccessibleName("最小内存")
        self.ram_max = QSpinBox()
        self.ram_max.setRange(0, 32768)
        self.ram_max.setSingleStep(256)
        self.ram_max.setSuffix(" MB")
        self.ram_max.setFixedHeight(HIT_MIN)
        self.ram_max.setAccessibleName("最大内存")
        ram.addWidget(labeled_field("最小", self.ram_min))
        ram.addWidget(labeled_field("最大", self.ram_max))
        ram.addStretch()
        lay.addLayout(ram)

        self.ram_hint = QLabel("填 0 表示跟随设置页的全局内存。")
        self.ram_hint.setObjectName("mutedLabel")
        self.ram_hint.setWordWrap(True)
        lay.addWidget(self.ram_hint)

        self.jvm_input = QLineEdit()
        self.jvm_input.setPlaceholderText("-XX:+UseG1GC")
        self.jvm_input.setAccessibleName("实例 JVM 参数")
        lay.addWidget(labeled_field("JVM 参数", self.jvm_input, "追加在内存参数之后。"))

        jrow = QHBoxLayout()
        jrow.setSpacing(SPACE_SM)
        self.java_input = QLineEdit()
        self.java_input.setPlaceholderText("留空 = 自动选择")
        self.java_input.setAccessibleName("实例 Java 路径")
        jrow.addWidget(self.java_input, 1)
        browse = QPushButton("浏览")
        browse.setFixedHeight(HIT_MIN)
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(self._browse_java)
        jrow.addWidget(browse)
        clear = QPushButton("还原自动")
        clear.setFixedHeight(HIT_MIN)
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.clicked.connect(lambda: self.java_input.setText(""))
        jrow.addWidget(clear)
        wrap = QWidget()
        wrap.setLayout(jrow)
        lay.addWidget(labeled_field("Java 路径", wrap))

        self.java_resolved = QLabel("")
        self.java_resolved.setObjectName("mutedLabel")
        self.java_resolved.setWordWrap(True)
        lay.addWidget(self.java_resolved)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self.save_btn = QPushButton("保存实例设置")
        self.save_btn.setObjectName("btnBlue")
        self.save_btn.setFixedHeight(HIT_MIN)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_instance_fields)
        save_row.addWidget(self.save_btn)
        lay.addLayout(save_row)

        self.jvm_frame = w
        return w

    # ── CAP_MODLOADER ──

    def _build_loader(self):
        """这个实例是用什么材料合成的 —— 只读合成台。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_SM)

        head = QHBoxLayout()
        head.addWidget(self._sec("这个实例的材料"))
        head.addStretch()
        lay.addLayout(head)

        self.detail_bench = CraftingBench(read_only=True)
        lay.addWidget(self.detail_bench)

        self.loader_status = QLabel("")
        self.loader_status.setObjectName("statusLabel")
        self.loader_status.setWordWrap(True)
        lay.addWidget(self.loader_status)

        self.loader_frame = w
        return w

    # ── CAP_PACK_IMPORT + p.list_mods ──

    def _build_mods(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_SM)
        lay.addWidget(self._sec("Mods"))

        self.mods_label = QLabel("")
        self.mods_label.setObjectName("mutedLabel")
        self.mods_label.setWordWrap(True)
        lay.addWidget(self.mods_label)

        row = QHBoxLayout()
        row.setSpacing(SPACE_SM)
        self.open_mods_btn = QPushButton(t("library.open_mods"))
        self.open_mods_btn.setFixedHeight(HIT_MIN)
        self.open_mods_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_mods_btn.clicked.connect(self._open_mods)
        row.addWidget(self.open_mods_btn)

        self.mod_check_btn = QPushButton("运行 mod 检查")
        self.mod_check_btn.setObjectName("btnBlue")
        self.mod_check_btn.setFixedHeight(HIT_MIN)
        self.mod_check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mod_check_btn.hide()
        self.mod_check_btn.clicked.connect(self._run_mod_check)
        row.addWidget(self.mod_check_btn)
        row.addStretch()
        lay.addLayout(row)

        self.mods_frame = w
        return w

    # ── CAP_PACK_IMPORT + p.import_pack（商店托管的产品） ──

    def _build_pack_import(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_SM)
        lay.addWidget(self._sec("内容包"))

        self.pack_btn = QPushButton("导入 .mcpack / .mcaddon / .mcworld")
        self.pack_btn.setObjectName("btnBlue")
        self.pack_btn.setFixedHeight(HIT_MIN)
        self.pack_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pack_btn.clicked.connect(self._import_pack)
        lay.addWidget(self.pack_btn)

        self.pack_status = QLabel("")
        self.pack_status.setObjectName("statusLabel")
        self.pack_status.setWordWrap(True)
        lay.addWidget(self.pack_status)

        self.pack_frame = w
        return w

    # ── CAP_CONSOLE ──

    def _build_console(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, SPACE_SM, 0, 0)
        lay.setSpacing(SPACE_SM)

        head = QHBoxLayout()
        head.addWidget(self._sec("服务端控制台"))
        head.addStretch()
        self.console_start_btn = QPushButton("启动服务端")
        self.console_start_btn.setObjectName("btnPrimary")
        self.console_start_btn.setFixedHeight(HIT_MIN)
        self.console_start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.console_start_btn.clicked.connect(self._launch_clicked)
        head.addWidget(self.console_start_btn)
        lay.addLayout(head)

        self.console_out = QPlainTextEdit()
        self.console_out.setReadOnly(True)
        self.console_out.setAccessibleName("服务端输出")
        self.console_out.setMinimumHeight(120)
        self.console_out.setStyleSheet(console_sheet())
        self.console_out.setPlaceholderText("服务端输出会显示在这里。")
        lay.addWidget(self.console_out)

        self.console_input = QLineEdit()
        self.console_input.setPlaceholderText("输入命令后回车，例如 list / stop")
        self.console_input.setAccessibleName("服务端命令")
        self.console_input.setEnabled(False)
        self.console_input.returnPressed.connect(self._send_command)
        lay.addWidget(self.console_input)

        self.console_frame = w
        return w

    def _build_detail_footer(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, SPACE_MD, 0, 0)
        lay.setSpacing(SPACE_SM)

        self.rename_btn = QPushButton("重命名")
        self.rename_btn.setFixedHeight(HIT_MIN)
        self.rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rename_btn.clicked.connect(self._rename_instance)
        lay.addWidget(self.rename_btn)

        self.version_dir_btn = QPushButton("打开版本目录")
        self.version_dir_btn.setObjectName("btnGhost")
        self.version_dir_btn.setFixedHeight(HIT_MIN)
        self.version_dir_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_dir_btn.clicked.connect(self._open_version_dir)
        lay.addWidget(self.version_dir_btn)

        lay.addStretch()
        self.delete_inst_btn = QPushButton("删除实例")
        self.delete_inst_btn.setObjectName("logoutBtn")
        self.delete_inst_btn.setFixedHeight(HIT_MIN)
        self.delete_inst_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.delete_inst_btn.clicked.connect(self._delete_instance)
        lay.addWidget(self.delete_inst_btn)
        return w

    # ── 安装面板 ──

    def _build_install(self):
        panel = make_sheet()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        lay.setSpacing(SPACE_MD)

        head = QHBoxLayout()
        title = QLabel(t("library.install_new"))
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch()
        back = QPushButton("返回")
        back.setFixedHeight(HIT_MIN)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self._back_from_install)
        head.addWidget(back)
        lay.addLayout(head)

        # 安装页内容只会越来越长（版本列表 + 合成台 + 材料行）。
        # 不放进滚动区的话，超出高度的部分不会滚动 —— Qt 让子控件画到框外，
        # 表现就是「合成台把版本列表压住」「材料行看不见」。
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("scrollArea")
        scroll.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)

        body = QWidget()
        body.setObjectName("scrollBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body.setAutoFillBackground(False)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(SPACE_MD)

        self.inst_provider = QComboBox()
        self.inst_provider.setFixedHeight(HIT_MIN)
        self.inst_provider.setAccessibleName("安装目标产品")
        self.inst_provider.currentIndexChanged.connect(self._on_install_provider)
        bl.addWidget(labeled_field("产品", self.inst_provider))

        self.inst_stack = QStackedWidget()
        self.inst_stack.addWidget(self._build_install_remote())   # 0
        self.inst_stack.addWidget(self._build_install_server())   # 1
        self.inst_stack.addWidget(self._build_install_store())    # 2
        bl.addWidget(self.inst_stack, 1)

        scroll.setWidget(body)
        lay.addWidget(scroll, 1)

        self.inst_status = QLabel("")
        self.inst_status.setObjectName("statusLabel")
        self.inst_status.setWordWrap(True)
        lay.addWidget(self.inst_status)
        return panel

    def _build_install_remote(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACE_SM)

        flt = QHBoxLayout()
        flt.setSpacing(SPACE_LG)
        self.chk_snap = QCheckBox("快照")
        self.chk_snap.setChecked(bool(self.config.get("show_snapshots", False)))
        self.chk_snap.stateChanged.connect(lambda _s: self._filter_remote())
        flt.addWidget(self.chk_snap)
        self.chk_old = QCheckBox("远古")
        self.chk_old.setChecked(bool(self.config.get("show_old_versions", False)))
        self.chk_old.stateChanged.connect(lambda _s: self._filter_remote())
        flt.addWidget(self.chk_old)
        flt.addStretch()
        self.remote_refresh_btn = QPushButton(t("common.refresh"))
        self.remote_refresh_btn.setFixedHeight(HIT_MIN)
        self.remote_refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.remote_refresh_btn.clicked.connect(lambda: self._load_remote(force=True))
        flt.addWidget(self.remote_refresh_btn)
        lay.addLayout(flt)

        self.remote_list = QListWidget()
        self.remote_list.setMinimumHeight(170)
        # 列表不再无上限地吃掉版面：剩下的高度留给下面的合成台（材料版本行必须看得见）
        self.remote_list.setMaximumHeight(240)
        self.remote_list.setAccessibleName("可下载版本")
        self.remote_list.currentItemChanged.connect(self._on_remote_sel)
        lay.addWidget(self.remote_list, 0)

        # 合成台：所有加载器都摆在明面上，放进同一个实例的组合会被实时校验
        self.inst_bench_frame = QWidget()
        bf = QVBoxLayout(self.inst_bench_frame)
        bf.setContentsMargins(0, 0, 0, 0)
        bf.setSpacing(SPACE_XS)
        hint = QLabel("可选：往下加水。同一实例只能有一个主加载器，附加层会按官方说明校验。")
        hint.setObjectName("mutedLabel")
        hint.setWordWrap(True)
        bf.addWidget(hint)
        self.bench = CraftingBench()
        self.bench.needOptions.connect(self._on_bench_need_options)
        bf.addWidget(self.bench)
        lay.addWidget(self.inst_bench_frame)

        bot = QHBoxLayout()
        bot.addStretch()
        self.uninstall_btn = QPushButton("卸载版本")
        self.uninstall_btn.setObjectName("logoutBtn")
        self.uninstall_btn.setFixedHeight(HIT_MIN + 2)
        self.uninstall_btn.setMinimumWidth(110)
        self.uninstall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.uninstall_btn.setToolTip(
            "删除 versions/<版本>/ 里的版本文件。\n共享的 libraries / assets / runtime 不会动。")
        self.uninstall_btn.clicked.connect(self._do_uninstall)
        self.uninstall_btn.setEnabled(False)
        bot.addWidget(self.uninstall_btn)

        self.install_go_btn = QPushButton(t("common.install"))
        self.install_go_btn.setObjectName("btnPrimary")
        self.install_go_btn.setFixedHeight(HIT_MIN + 2)
        self.install_go_btn.setMinimumWidth(140)
        self.install_go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_go_btn.clicked.connect(self._do_install)
        bot.addWidget(self.install_go_btn)
        lay.addLayout(bot)
        return w

    def _build_install_server(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACE_MD)
        lay.addStretch()

        tip = QLabel(
            "官方 BDS 版本在上面的版本列表里 —— 选中直接点「安装」，"
            "启动器会下载 Mojang 官方 zip、解压、找到 bedrock_server.exe 并注册成实例。"
            "这里留给已经在别处下好 zip 的情况。")
        tip.setObjectName("mutedLabel")
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setWordWrap(True)
        lay.addWidget(tip)

        row = QHBoxLayout()
        row.addStretch()
        self.server_import_btn = QPushButton("选择 zip 并导入")
        self.server_import_btn.setObjectName("btnPrimary")
        self.server_import_btn.setFixedHeight(HIT_MIN + 2)
        self.server_import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.server_import_btn.clicked.connect(self._import_server_zip)
        row.addWidget(self.server_import_btn)
        row.addStretch()
        lay.addLayout(row)
        lay.addStretch()
        return w

    def _build_install_store(self):
        """商店托管的游戏：查得到商店状态、送得进商店页，但下载不了包。"""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(SPACE_MD)

        head = QLabel("基岩版客户端由 Microsoft Store 交付")
        head.setObjectName("fieldLabel")
        lay.addWidget(head)

        self.store_tip = QLabel(
            "商店发的是加密的 MSIXVC 容器，真实下载走 Windows Update，"
            "而且要你自己账号持有这个游戏的许可 —— 第三方启动器拿不到可安装的包。"
            "所以这里不提供「下载版本」，能做的是把商店状态查给你、把你一键送进商店页。")
        self.store_tip.setObjectName("mutedLabel")
        self.store_tip.setWordWrap(True)
        lay.addWidget(self.store_tip)

        card = make_sheet()
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        card_lay.setSpacing(SPACE_XS)

        self.store_title = QLabel("正在读取商店信息…")
        self.store_title.setObjectName("title")
        card_lay.addWidget(self.store_title)

        self.store_meta = QLabel("")
        self.store_meta.setObjectName("mutedLabel")
        self.store_meta.setWordWrap(True)
        card_lay.addWidget(self.store_meta)

        self.store_local = QLabel("")
        self.store_local.setObjectName("statusLabel")
        self.store_local.setWordWrap(True)
        card_lay.addWidget(self.store_local)
        lay.addWidget(card)

        row = QHBoxLayout()
        row.setSpacing(SPACE_SM)
        self.store_open_btn = QPushButton("在商店中打开")
        self.store_open_btn.setObjectName("btnPrimary")
        self.store_open_btn.setFixedHeight(HIT_MIN + 2)
        self.store_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.store_open_btn.setToolTip("打开 Minecraft for Windows 的商店详情页")
        self.store_open_btn.clicked.connect(lambda: self._open_store_page("pdp"))
        row.addWidget(self.store_open_btn)

        self.store_updates_btn = QPushButton("打开商店更新")
        self.store_updates_btn.setFixedHeight(HIT_MIN + 2)
        self.store_updates_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.store_updates_btn.setToolTip("打开商店的「下载与更新」页，检查更新")
        self.store_updates_btn.clicked.connect(lambda: self._open_store_page("updates"))
        row.addWidget(self.store_updates_btn)

        self.store_detect_btn = QPushButton("检测本机安装")
        self.store_detect_btn.setObjectName("btnBlue")
        self.store_detect_btn.setFixedHeight(HIT_MIN + 2)
        self.store_detect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.store_detect_btn.clicked.connect(self._detect_store_install)
        row.addWidget(self.store_detect_btn)
        row.addStretch()
        lay.addLayout(row)

        chan_head = QLabel("其他获取渠道")
        chan_head.setObjectName("fieldLabel")
        lay.addWidget(chan_head)

        self.chan_box = make_sheet()
        self.chan_lay = QVBoxLayout(self.chan_box)
        self.chan_lay.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        self.chan_lay.setSpacing(SPACE_SM)
        self.chan_hint = QLabel("正在解析官方直链…")
        self.chan_hint.setObjectName("mutedLabel")
        self.chan_hint.setWordWrap(True)
        self.chan_lay.addWidget(self.chan_hint)
        self._chan_rows = []
        lay.addWidget(self.chan_box)
        lay.addStretch()
        return w

    def _load_channels(self):
        p = self._provider(self._install_pid)
        fn = getattr(p, "download_channels", None) if p is not None else None
        if not callable(fn):
            self.chan_hint.setText("该产品没有其他下载渠道。")
            return
        self.chan_hint.setText("正在解析官方直链…")
        self._spawn("channels", fn, self._channels_loaded)

    def _channels_loaded(self, payload, err):
        for row in getattr(self, "_chan_rows", []):
            row.setParent(None)
            row.deleteLater()
        self._chan_rows = []
        if err:
            self.chan_hint.setText("解析官方直链失败：" + friendly_error(err))
            return
        items = list(payload or [])
        if not items:
            self.chan_hint.setText("没有可用的下载渠道。")
            return
        self.chan_hint.setText(
            "下面每条都实测过：能直接下的给直链和体积，只能给链接的写清要什么。"
            "注意：谁都不能免费给你国际版基岩客户端的游戏本体。")
        for item in items:
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)

            top = QHBoxLayout()
            top.setSpacing(SPACE_SM)
            title = str(item.get("name") or item.get("id") or "")
            size = str(item.get("size_text") or "")
            label = QLabel(title + ("　·　" + size if size else ""))
            label.setStyleSheet("font-weight: 700;")
            top.addWidget(label)
            top.addStretch()
            btn = QPushButton("下载" if item.get("resolved") else "打开")
            btn.setFixedHeight(HIT_MIN)
            btn.setMinimumWidth(96)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cid = str(item.get("id") or "")
            if item.get("resolved"):
                btn.clicked.connect(
                    lambda _c=False, it=dict(item): self._download_channel(it))
            else:
                btn.setObjectName("btnBlue")
                url = str(item.get("url") or "")
                btn.clicked.connect(
                    lambda _c=False, u=url: self._open_external(u))
            top.addWidget(btn)
            rl.addLayout(top)

            note = QLabel(str(item.get("note") or ""))
            note.setObjectName("mutedLabel")
            note.setWordWrap(True)
            rl.addWidget(note)

            self.chan_lay.addWidget(row)
            self._chan_rows.append(row)

    def _open_external(self, url):
        if not url:
            return
        try:
            os.startfile(url)  # noqa: S606 — 打开浏览器
            self.inst_status.setText("已在浏览器里打开：" + url)
        except OSError as e:
            self.inst_status.setText("打不开链接：%s" % e)

    def _download_channel(self, item):
        cid = str(item.get("id") or "")
        name = str(item.get("name") or cid)
        file_name = str(item.get("file_name") or (cid + ".exe"))
        size = str(item.get("size_text") or "")
        if size and "GB" in size:
            ok = QMessageBox.question(
                self, "确认下载",
                "这个安装包有 %s，确认现在下载？" % size,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ok != QMessageBox.StandardButton.Yes:
                return
        default = os.path.join(os.path.expanduser("~"), "Downloads", file_name)
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 " + name, default, "安装包 (*.exe *.msi);;所有文件 (*)")
        if not path:
            return
        p = self._provider(self._install_pid)
        fn = getattr(p, "download_channel", None) if p is not None else None
        if not callable(fn):
            self.inst_status.setText("该产品不支持下载。")
            return
        holder = {}

        def task(cb):
            holder["path"] = fn(cid, path, cb)

        d = ProgressDialog("下载 " + name, task, self)
        d.start()
        if d.was_cancelled:
            self.inst_status.setText("已取消下载。")
            return
        if not d.success:
            self.inst_status.setText("下载失败：" + friendly_error(d.error_msg))
            QMessageBox.warning(self, "下载失败", friendly_error(d.error_msg))
            return
        done = str(holder.get("path") or path)
        self.inst_status.setText("已下载：" + done)
        if QMessageBox.question(
                self, "下载完成",
                "已经保存到：\n%s\n\n现在打开它吗？" % done,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes:
            self._open_external(done)

    def _load_store_state(self):
        p = self._provider(self._install_pid)
        fn = getattr(p, "store_state", None) if p is not None else None
        if not callable(fn):
            self.store_title.setText("该产品没有商店信息。")
            self.store_meta.setText("")
            self.store_local.setText("")
            return
        self.store_title.setText("正在读取商店信息…")
        self.store_meta.setText("")
        self.store_local.setText("")
        self._spawn("store_state", fn, self._store_state_loaded)
        self._load_channels()

    def _store_state_loaded(self, payload, err):
        if err:
            self.store_title.setText("商店信息读取失败")
            self.store_meta.setText(friendly_error(err))
            return
        d = payload if isinstance(payload, dict) else {}
        self.store_title.setText(str(d.get("title") or "Minecraft for Windows"))
        bits = []
        if d.get("size_text"):
            bits.append("安装体积 " + str(d["size_text"]))
        if d.get("updated_date"):
            bits.append("商店包最近更新 " + str(d["updated_date"]))
        fmts = d.get("package_formats") or []
        if fmts:
            bits.append("交付格式 " + "/".join(str(f) for f in fmts)
                        + "（加密容器，需要账号许可）")
        self.store_meta.setText(" · ".join(bits))
        if d.get("installed"):
            ver = str(d.get("local_version") or "").strip()
            self.store_local.setText("本机：已安装" + (" " + ver if ver else "（版本号读不出来）"))
        else:
            self.store_local.setText("本机：未安装")

    def _open_store_page(self, target: str = "pdp"):
        p = self._provider(self._install_pid)
        fn = getattr(p, "open_store", None) if p is not None else None
        if not callable(fn):
            self.inst_status.setText("该产品没有商店页。")
            return
        ok, msg = fn(target)
        if ok:
            self.inst_status.setText(
                "已打开商店页面。装好之后点「检测本机安装」把它接进来。")
        else:
            self.inst_status.setText(str(msg))

    # ═══════════════ 工具 ═══════════════

    def _sec(self, text):
        lbl = QLabel(text)
        lbl.setObjectName("sectionLabel")
        return lbl

    def _caps(self, pid):
        try:
            return set(providers.capability_of(pid) or set())
        except Exception:
            return set()

    def _provider(self, pid):
        try:
            return providers.get(pid)
        except Exception:
            return None

    def _spawn(self, key, task, slot):
        """起一个后台任务；同名任务还在跑就不重入（避免覆盖引用 → abort）。"""
        attr = "_th_" + key
        old = getattr(self, attr, None)
        if isinstance(old, QThread) and old.isRunning():
            return False
        th = _TaskThread(task)
        setattr(self, attr, th)
        th.done.connect(slot)
        th.start()
        return True

    def _set_del_enabled(self, enabled):
        """删除按钮的可用态：styles.py 的 #logoutBtn 没有 :disabled 规则，
        不禁用样式的话「不可点」看起来和「可点」一模一样。"""
        for name in ("del_btn", "delete_inst_btn"):
            btn = getattr(self, name, None)
            if btn is None:
                continue
            btn.setEnabled(enabled)
            btn.setStyleSheet("" if enabled else _DEL_OFF)

    def _set_stats(self, widget, text, color=""):
        try:
            widget.setText(text)
            widget.setStyleSheet(("color: " + color + ";") if color else "")
        except Exception:
            pass

    # ═══════════════ 刷新 ═══════════════

    def refresh(self):
        """重建产品/实例树，尽量保持当前选中。"""
        keep_id = self._sel_inst.id if self._sel_inst is not None else ""
        self._rebuild_tree()
        inst = self.store.get(keep_id) if (self.store is not None and keep_id) else None
        if inst is not None:
            self._show_detail(inst)
            self._sync_tree_selection(inst.id)
        else:
            self._sel_inst = None
            self._set_del_enabled(False)
            if self.right_stack.currentIndex() != 2:
                # 有实例但没选中：直接打开第一个，否则用户只看到一片空态
                all_inst = self.store.all() if self.store is not None else []
                if all_inst:
                    self._show_detail(all_inst[0])
                    self._sync_tree_selection(all_inst[0].id)
                    return
                self._show_empty()

    def _rebuild_tree(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        try:
            provs = list(providers.all_providers())
        except Exception:
            provs = []

        total_inst = 0
        installed_all: set[str] = set()
        for p in provs:
            pid = str(getattr(p, "id", "") or "")
            if not pid:
                continue
            try:
                for v in (p.list_installed() or []):
                    vid = str(getattr(v, "id", "") or "")
                    if vid:
                        installed_all.add(vid)
            except Exception:
                pass
            name = str(getattr(p, "name", "") or pid)
            node = QTreeWidgetItem([name])
            node.setData(0, ROLE_PROVIDER, pid)
            node.setIcon(0, self._provider_icon(self._caps(pid)))
            # 产品节点只做分组标题，不可选中
            node.setFlags(node.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            try:
                items = self.store.by_provider(pid) if self.store is not None else []
            except Exception:
                items = []
            for inst in items:
                total_inst += 1
                child = QTreeWidgetItem([inst.name or inst.version_id])
                child.setData(0, ROLE_INSTANCE, inst.id)
                child.setToolTip(0, "版本 " + inst.version_id + "\n" + inst.game_dir)
                node.addChild(child)
            if not items:
                # 没有实例的产品也要显示，带一个灰色的不可选占位
                ph = QTreeWidgetItem(["（还没有实例）"])
                ph.setData(0, ROLE_PROVIDER, pid)
                ph.setForeground(0, QBrush(QColor(_MUTED)))
                ph.setFlags(Qt.ItemFlag.NoItemFlags)
                node.addChild(ph)
            self.tree.addTopLevelItem(node)

        self.tree.expandAll()
        self.tree.blockSignals(False)

        if not provs:
            self.tree_hint.setText(
                "没有可用的产品（Java / 基岩 / 服务端的 provider 还没加载成功）。")
            self.tree_hint.show()
        elif total_inst == 0:
            if installed_all:
                self.tree_hint.setText(
                    "检测到磁盘上已有游戏版本，但还没有实例。"
                    "点「新建实例」把版本接进来就能启动。")
            else:
                self.tree_hint.setText("产品已就绪，但还没有实例。点「+ 安装」下载一个版本。")
            self.tree_hint.show()
        else:
            self.tree_hint.setText("")
            self.tree_hint.hide()

    def _provider_icon(self, caps):
        """复用现成的像素图标，不新增资源。"""
        try:
            if CAP_CONSOLE in caps:
                return nav_icon("mods", False)
            if CAP_STORE in caps:
                return nav_icon("home", False)
            if CAP_VERSION_LIST in caps or CAP_JVM in caps:
                return nav_icon("versions", False)
            return nav_icon("settings", False)
        except Exception:
            return QIcon()

    def _show_empty(self):
        try:
            provs = list(providers.all_providers())
        except Exception:
            provs = []
        if not provs:
            self.empty_title.setText("还没有可用的产品")
            self.empty_sub.setText(
                "provider 还没加载成功（Java / 基岩 / 服务端由各自模块提供）。"
                "加载成功后这里会出现按产品分组的实例列表。")
        elif self.store is not None and self.store.all():
            self.empty_title.setText("选一个实例")
            self.empty_sub.setText("左侧树里点一个实例，右侧会按它的能力显示面板。")
        else:
            self.empty_title.setText(t("library.none"))
            self.empty_sub.setText(
                "点左下角「+ 安装」下载一个版本，或「新建实例」挑选已装版本。")
        self.right_stack.setCurrentIndex(0)

    def _sync_tree_selection(self, inst_id):
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(i)
            for j in range(node.childCount()):
                child = node.child(j)
                if child.data(0, ROLE_INSTANCE) == inst_id:
                    self.tree.setCurrentItem(child)
                    self.tree.blockSignals(False)
                    return
        self.tree.blockSignals(False)

    def _on_tree_current(self, current, _previous=None):
        if current is None or self.store is None:
            return
        iid = current.data(0, ROLE_INSTANCE)
        if not iid:
            return
        inst = self.store.get(iid)
        if inst is None:
            return
        self._show_detail(inst)

    # ═══════════════ 详情渲染（按能力） ═══════════════

    def _show_detail(self, inst):
        self._sel_inst = inst
        self._set_del_enabled(True)
        caps = self._caps(inst.provider)
        p = self._provider(inst.provider)

        self.d_title.setText(inst.name or inst.version_id)
        kind = version_kind(inst.version_id)
        size = self._size_text(p, inst.version_id)
        self.d_meta.setText("版本 " + inst.version_id + " · " + kind + " · " + size)

        # ── CAP_JVM ──
        self._jvm_active = CAP_JVM in caps
        self.jvm_frame.setVisible(self._jvm_active)
        if self._jvm_active:
            self.ram_min.setValue(int(inst.ram_min or 0))
            self.ram_max.setValue(int(inst.ram_max or 0))
            self.jvm_input.setText(inst.jvm_args or "")
            self.java_input.setText(inst.java_path or "")
            self._resolve_java(inst, p)

        # ── CAP_MODLOADER ──
        self.loader_frame.setVisible(CAP_MODLOADER in caps)
        if CAP_MODLOADER in caps:
            from core.providers.java import combos as _combos
            mc_ver = _combos.mc_version_of(inst.version_id)
            chosen = _combos.detect_from_version_id(inst.version_id)
            self.detail_bench.set_read_only_state(mc_ver, chosen)
            clashes = [i for i in _combos.check_combo(mc_ver, chosen)
                       if i.level in ("blocked", "warn")]
            if clashes:
                self._set_stats(self.loader_status,
                                "；".join(i.reason for i in clashes), _DANGER)
            else:
                self.loader_status.setText("")

        # ── Mods：CAP_PACK_IMPORT + provider 提供 list_mods ──
        has_mods = CAP_PACK_IMPORT in caps and callable(getattr(p, "list_mods", None))
        self.mods_frame.setVisible(has_mods)
        if has_mods:
            self.mods_label.setText("读取中…")
            self._refresh_mods(inst, p)
            # 只有检查能力真的存在时才显示按钮
            self.mod_check_btn.setVisible(self._mod_check_fn(p) is not None)

        # ── 内容包：CAP_PACK_IMPORT + provider 提供 import_pack ──
        has_pack = CAP_PACK_IMPORT in caps and callable(getattr(p, "import_pack", None))
        self.pack_frame.setVisible(has_pack)
        if has_pack:
            self.pack_status.setText("")

        # ── CAP_CONSOLE ──
        has_console = CAP_CONSOLE in caps
        self.console_frame.setVisible(has_console)
        if has_console:
            self.console_input.setEnabled(self._console_handle is not None)
            if self._launched_inst is not inst:
                self.console_out.setPlainText("")

        # 挂着的进程属于别的实例 → 复位启动按钮
        if self._launched_inst is not None and self._launched_inst.id != inst.id:
            self.launch_status.setText("")
            self._reset_launch_btn()
        elif self._handle is not None and self._launched_inst is inst:
            self.launch_btn.setText(t("home.running"))
            self.launch_btn.setEnabled(False)

        self.right_stack.setCurrentIndex(1)

    def _size_text(self, p, vid):
        try:
            mb = float(p.version_size_mb(vid) or 0)
        except Exception:
            return "大小未知"
        if mb <= 0:
            return "大小未知"
        return "{:.0f} MB".format(mb)

    def _resolve_java(self, inst, p):
        """p.resolve_java 可能扫盘，放后台；失败用红字提示。"""
        self._set_stats(self.java_resolved, "正在解析可用的 Java…", _MUTED)
        resolve = getattr(p, "resolve_java", None) if p is not None else None
        if not callable(resolve):
            self._set_stats(self.java_resolved, "该产品不提供 Java 解析。", _MUTED)
            return
        vid = inst.version_id

        def task():
            return resolve(vid)

        if not self._spawn("resolve", task, self._java_resolved):
            return

    def _java_resolved(self, payload, err):
        if self._sel_inst is None:
            return
        if err:
            self._set_stats(
                self.java_resolved,
                "解析失败：" + err + "（可手动浏览指定 javaw.exe）",
                _DANGER)
            return
        path = str(payload or "")
        if path:
            self._set_stats(self.java_resolved, "将使用：" + path, _OK)
        else:
            self._set_stats(
                self.java_resolved,
                "没有找到匹配的 Java，启动可能失败；请在下方指定。",
                _DANGER)

    def _refresh_mods(self, inst, p):
        game_dir = inst.game_dir
        list_mods = getattr(p, "list_mods", None)

        def task():
            return list(list_mods(game_dir) or [])

        if not self._spawn("mods", task, self._mods_loaded):
            return

    def _mods_loaded(self, payload, err):
        if err:
            self._set_stats(self.mods_label, "读取 mods 失败：" + err, _DANGER)
            return
        mods = list(payload or [])
        if mods:
            self.mods_label.setStyleSheet("")
            self.mods_label.setText("\n".join("  · " + str(m) for m in mods[:40]))
        else:
            self._set_stats(self.mods_label, "mods 文件夹为空，把 .jar 拖进去即可。", _MUTED)

    # ═══════════════ 启动 / 退出 ═══════════════

    def _launch_clicked(self):
        inst = self._sel_inst
        if inst is None or self._handle is not None:
            return
        p = self._provider(inst.provider)
        if p is None:
            QMessageBox.warning(
                self, "无法启动", "产品 " + inst.provider + " 没有加载，无法启动该实例。")
            return
        self._persist_instance(inst)
        auth = auth_dict(self.config)

        self.launch_btn.setEnabled(False)
        self.launch_btn.setText(t("home.starting"))
        self._set_stats(self.launch_status, "正在启动 " + inst.version_id + "…", _MUTED)

        def task():
            return p.launch(inst, auth)

        if not self._spawn(
                "launch", task,
                lambda payload, err: self._launch_done(inst, payload, err)):
            self._reset_launch_btn()

    def _launch_done(self, inst, payload, err):
        if err:
            self._reset_launch_btn()
            self._set_stats(self.launch_status, "启动失败：" + err, _DANGER)
            QMessageBox.critical(self, "无法启动", err)
            return

        handle = payload
        self._launched_inst = inst
        self._play_start = time.time()
        has_console = CAP_CONSOLE in self._caps(inst.provider)
        process = getattr(handle, "process", None) if handle is not None else None

        if has_console:
            self._console_handle = handle
            self.console_input.setEnabled(handle is not None)
            timer = QTimer(self)
            timer.timeout.connect(self._tail_console)
            timer.start(1000)
            self._tail_timer = timer
            self._set_stats(self.launch_status, "服务端已启动，输出见下方控制台。", _OK)
        else:
            self._set_stats(self.launch_status, inst.version_id + " 已启动", _OK)

        if process is None:
            # 商店托管的唤醒式启动：没有进程可轮询
            self._set_stats(
                self.launch_status, inst.version_id + " 已唤醒（由商店托管）", _OK)
            self.launch_btn.setText(t("library.play"))
            self.launch_btn.setEnabled(True)
            self._touch_played(inst)
            self._handle = handle if has_console else None
            if not has_console:
                self._launched_inst = None
            return

        self._handle = handle
        self.launch_btn.setText(t("home.running"))
        self.launch_btn.setEnabled(False)
        timer = QTimer(self)
        timer.timeout.connect(self._poll_launch)
        timer.start(3000)
        self._launch_timer = timer

        if self.config.get("close_on_launch", False):
            QTimer.singleShot(800, self._close_after_launch)

    def _close_after_launch(self):
        win = self.window()
        if win is not None:
            try:
                win.close()
            except Exception:
                pass

    def _poll_launch(self):
        handle = self._handle
        timer = self._launch_timer
        if handle is None:
            if timer is not None:
                timer.stop()
            return
        try:
            running = bool(handle.running())
        except Exception:
            running = False
        if running:
            return

        if timer is not None:
            timer.stop()
        code = 0
        try:
            if handle.process is not None:
                code = handle.process.returncode
        except Exception:
            code = 0
        log_path = str(getattr(handle, "log_path", "") or "")
        inst = self._launched_inst
        elapsed = int(max(0, time.time() - self._play_start))
        try:
            handle.close_log()
        except Exception:
            pass
        if inst is not None:
            self._touch_played(inst, elapsed)
        self._handle = None
        self._console_handle = None
        if self._tail_timer is not None:
            self._tail_timer.stop()
        self.console_input.setEnabled(False)
        self._reset_launch_btn()

        if code in (None, 0):
            self._set_stats(self.launch_status, "游戏已退出", _MUTED)
        else:
            self._set_stats(self.launch_status, "游戏崩溃（代码 {}）".format(code), _DANGER)
            notify_diagnose(self, self.config, log_path, int(code))
        self.refresh()

    def _touch_played(self, inst, seconds=0):
        if self.store is None:
            return
        try:
            self.store.touch_played(inst.id, seconds)
        except Exception:
            pass

    def _reset_launch_btn(self, enabled=True):
        self.launch_btn.setEnabled(enabled)
        self.launch_btn.setText(t("library.play"))

    # ═══════════════ 实例字段保存 ═══════════════

    def _persist_instance(self, inst):
        if not self._jvm_active or self._sel_inst is None:
            return False
        if self._sel_inst.id != inst.id:
            return False
        mn, mx = int(self.ram_min.value()), int(self.ram_max.value())
        if mn > 0 and mx > 0 and mn > mx:
            self._set_stats(self.launch_status, "最小内存不能大于最大内存。", _DANGER)
            return False
        inst.ram_min = mn
        inst.ram_max = mx
        inst.jvm_args = self.jvm_input.text().strip()
        inst.java_path = self.java_input.text().strip()
        try:
            return bool(self.store.update(inst)) if self.store is not None else False
        except Exception:
            return False

    def _save_instance_fields(self):
        inst = self._sel_inst
        if inst is None:
            return
        if not self._jvm_active:
            QMessageBox.information(self, "提示", "该产品没有可编辑的 JVM 设置。")
            return
        ok = self._persist_instance(inst)
        self._set_stats(
            self.launch_status,
            "实例设置已保存。" if ok else "实例设置保存失败（注册表不可写）。",
            _OK if ok else _DANGER)

    def _browse_java(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Java", "", "Java (javaw.exe java.exe);;All (*)")
        if path:
            self.java_input.setText(path)

    # ═══════════════ 打开目录 / 重命名 / 删除 ═══════════════

    def _open_game_dir(self):
        inst = self._sel_inst
        if inst is None:
            return
        try:
            core_paths.open_folder(inst.game_dir)
        except Exception as e:
            QMessageBox.warning(self, "无法打开", inst.game_dir + "\n" + str(e))

    def _open_version_dir(self):
        inst = self._sel_inst
        if inst is None:
            return
        target = inst.game_dir
        p = self._provider(inst.provider)
        for attr in ("version_dir", "game_version_dir"):
            fn = getattr(p, attr, None) if p is not None else None
            try:
                if callable(fn):
                    got = fn(inst.version_id)
                    if got:
                        target = str(got)
                        break
                elif isinstance(fn, str) and fn:
                    target = fn
                    break
            except Exception:
                continue
        try:
            core_paths.open_folder(target)
        except Exception as e:
            QMessageBox.warning(self, "无法打开", target + "\n" + str(e))

    def _rename_instance(self):
        inst = self._sel_inst
        if inst is None or self.store is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名实例", "新名称：", text=inst.name or inst.version_id)
        if not ok:
            return
        name = (name or "").strip()
        if not name:
            return
        inst.name = name
        try:
            if not self.store.update(inst):
                QMessageBox.warning(self, "保存失败", "实例注册表不可写。")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))
        self.refresh()

    def _delete_instance(self):
        inst = self._sel_inst
        if inst is None or self.store is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("删除实例")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText("删除实例「" + (inst.name or inst.version_id) + "」？")
        box.setInformativeText(
            "「只删记录」保留该实例目录里的存档和 mods；"
            "「连实例文件一起删」会移除这个实例的独立游戏目录（存档 / mods / 配置）。\n\n"
            f"版本本体（versions/{inst.version_id}、共享的 libraries / assets）不会被删除 —— "
            "要删它在「+ 安装」里选中该版本点「卸载版本」。")
        only_rec = box.addButton("只删记录", QMessageBox.ButtonRole.AcceptRole)
        with_files = box.addButton("连实例文件一起删", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(t("common.cancel"), QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None:
            return
        if clicked is not only_rec and clicked is not with_files:
            return
        remove_files = clicked is with_files

        # 记下"用户主动删了这个版本的实例"，启动时的自动补建会跳过它
        try:
            key = f"{inst.provider}::{inst.version_id}"
            tomb = list(self.config.get("instance_tombstones", []) or [])
            if key not in tomb:
                tomb.append(key)
                self.config.set("instance_tombstones", tomb)
        except Exception:
            pass

        iid = inst.id
        self._set_del_enabled(False)

        def task():
            return self.store.delete(iid, remove_files)

        if not self._spawn("delete", task, self._deleted):
            self._set_del_enabled(True)

    def _deleted(self, payload, err):
        self._set_del_enabled(False)
        if err:
            QMessageBox.warning(self, "删除失败", err)
            self.refresh()
            return
        ok, msg = payload if isinstance(payload, tuple) else (True, "")
        if not ok:
            QMessageBox.warning(
                self, "删除失败",
                "实例记录已移除，但文件没有删干净：\n" + str(msg) +
                "\n游戏正在运行时请先关闭游戏。")
        self._sel_inst = None
        self.refresh()

    # ═══════════════ 新建实例 ═══════════════

    def _new_instance(self):
        try:
            provs = [p for p in providers.all_providers()
                     if callable(getattr(p, "list_installed", None))]
        except Exception:
            provs = []
        if not provs:
            QMessageBox.information(self, "提示", "没有可用的产品，无法新建实例。")
            return
        self.new_inst_btn.setEnabled(False)
        self.new_inst_btn.setText("读取中…")

        def task():
            out, errors = [], []
            for p in provs:
                pid = str(getattr(p, "id", ""))
                try:
                    versions = list(p.list_installed() or [])
                except Exception as e:
                    errors.append(pid + ": " + str(e))
                    continue
                for v in versions:
                    vid = str(getattr(v, "id", "") or "")
                    if not vid:
                        continue
                    label = str(getattr(v, "display", "") or vid)
                    out.append((pid, vid,
                                label + "    (" + pid + " · " +
                                kind_text(getattr(v, "kind", "")) + ")"))
            return out, errors

        if not self._spawn("installed", task, self._installed_loaded):
            self.new_inst_btn.setEnabled(True)
            self.new_inst_btn.setText(t("library.create_instance"))

    def _installed_loaded(self, payload, err):
        self.new_inst_btn.setEnabled(True)
        self.new_inst_btn.setText(t("library.create_instance"))
        if err:
            QMessageBox.warning(self, "读取失败", "无法读取已安装版本：" + err)
            return
        items, errors = payload if isinstance(payload, tuple) else ([], [])
        if not items:
            msg = "没有已安装的版本。先用「+ 安装」下载一个。"
            if errors:
                msg += "\n\n" + "\n".join(errors)
            QMessageBox.information(self, "提示", msg)
            return
        dlg = _NewInstanceDialog(items, self)
        try:
            accepted = dlg.exec()
        except Exception:
            accepted = False
        if not accepted:
            return
        choice = dlg.choice()
        if not choice or self.store is None:
            return
        pid, vid = choice
        try:
            inst = self.store.create(pid, vid, name=dlg.name() or vid)
        except Exception as e:
            QMessageBox.warning(self, "创建失败", str(e))
            return
        self._clear_tombstone(pid, vid)
        self.refresh()
        self._show_detail(inst)
        self._sync_tree_selection(inst.id)

    # ═══════════════ 加载器（CAP_MODLOADER） ═══════════════

    def _open_mods(self):
        inst = self._sel_inst
        if inst is None:
            return
        p = self._provider(inst.provider)
        opener = getattr(p, "open_mods_folder", None) if p is not None else None
        try:
            if callable(opener):
                opener(inst.game_dir)
            else:
                core_paths.open_folder(os.path.join(inst.game_dir, "mods"))
        except Exception as e:
            QMessageBox.warning(self, "无法打开", str(e))

    def _mod_check_fn(self, provider=None):
        """mod 检查：优先 provider.check_mods，其次 core.providers.java.deps.check_mods。

        两者都没有就返回 None（按钮不显示），绝不让按钮点下去只会崩。
        """
        p = provider
        if p is None and self._sel_inst is not None:
            p = self._provider(self._sel_inst.provider)
        fn = getattr(p, "check_mods", None) if p is not None else None
        if callable(fn):
            return fn
        try:
            import importlib
            mod = importlib.import_module("core.providers.java.deps")
            deps_fn = getattr(mod, "check_mods", None)
            return deps_fn if callable(deps_fn) else None
        except Exception:
            return None

    def _run_mod_check(self):
        inst = self._sel_inst
        if inst is None:
            return
        p = self._provider(inst.provider)
        provider_fn = getattr(p, "check_mods", None) if p is not None else None
        if not callable(provider_fn):
            provider_fn = None
        deps_fn = None
        if provider_fn is None:
            deps_fn = self._mod_check_fn(p)
        if provider_fn is None and deps_fn is None:
            QMessageBox.information(self, "暂不可用", "mod 检查模块还没就绪。")
            return
        game_dir = inst.game_dir
        vid = inst.version_id
        self.mod_check_btn.setEnabled(False)
        self.mod_check_btn.setText("检查中…")

        def task():
            if provider_fn is not None:
                return provider_fn(game_dir, vid)
            mods_dir = os.path.join(game_dir, "mods")
            try:
                return deps_fn(mods_dir, vid)
            except TypeError:
                return deps_fn(mods_dir)

        if not self._spawn("modcheck", task, self._mod_check_done):
            self.mod_check_btn.setEnabled(True)
            self.mod_check_btn.setText("运行 mod 检查")

    def _mod_check_done(self, payload, err):
        self.mod_check_btn.setEnabled(True)
        self.mod_check_btn.setText("运行 mod 检查")
        if err:
            QMessageBox.warning(self, "mod 检查失败", err)
            return
        if isinstance(payload, str):
            text = payload
        elif isinstance(payload, (list, tuple)):
            text = "\n".join(str(x) for x in payload)
        elif isinstance(payload, dict):
            text = "\n".join(str(k) + ": " + str(v) for k, v in payload.items())
        else:
            text = str(payload)
        dlg = QMessageBox(self)
        dlg.setWindowTitle("mod 检查")
        dlg.setText("mod 检查结果")
        dlg.setInformativeText(text[:800] or "没有发现问题。")
        if len(text) > 800:
            dlg.setDetailedText(text)
        dlg.exec()

    def _import_pack(self):
        inst = self._sel_inst
        if inst is None:
            return
        p = self._provider(inst.provider)
        importer = getattr(p, "import_pack", None) if p is not None else None
        if not callable(importer):
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择内容包", "",
            "Minecraft 内容包 (*.mcpack *.mcaddon *.mcworld);;All (*)")
        if not path:
            return
        holder = {}

        def task(cb):
            holder["res"] = importer(path)

        self.pack_btn.setEnabled(False)
        dlg = ProgressDialog("导入内容包", task, self)
        dlg.start()
        self.pack_btn.setEnabled(True)
        if dlg.was_cancelled:
            self._set_stats(self.pack_status, "已取消导入。", _MUTED)
            return
        if not dlg.success:
            self._set_stats(self.pack_status,
                            "导入失败：" + friendly_error(dlg.error_msg), _DANGER)
            QMessageBox.warning(self, "导入失败", friendly_error(dlg.error_msg))
            return
        res = holder.get("res", (True, ""))
        if isinstance(res, tuple) and len(res) == 2:
            ok, msg = bool(res[0]), str(res[1] or "")
        else:
            ok, msg = True, str(res or "导入成功")
        self._set_stats(self.pack_status, msg or ("导入成功" if ok else "导入失败"),
                        _OK if ok else _DANGER)
        self.refresh()

    def _send_command(self):
        handle = self._console_handle
        inst = self._launched_inst or self._sel_inst
        if handle is None or inst is None:
            self.console_out.appendPlainText("[未启动] 服务端还没启动。")
            return
        p = self._provider(inst.provider)
        sender = getattr(p, "send_command", None) if p is not None else None
        if not callable(sender):
            return
        line = self.console_input.text().strip()
        if not line:
            return
        try:
            sender(handle, line)
        except Exception as e:
            self.console_out.appendPlainText("[发送失败] " + str(e))
            return
        self.console_out.appendPlainText("> " + line)
        self.console_input.clear()

    def _tail_console(self):
        handle = self._console_handle
        inst = self._launched_inst
        if handle is None or inst is None:
            if self._tail_timer is not None:
                self._tail_timer.stop()
            return
        p = self._provider(inst.provider)
        tail = getattr(p, "tail", None) if p is not None else None
        if not callable(tail):
            return
        try:
            lines = tail(handle, 60) or []
        except Exception as e:
            self.console_out.appendPlainText("[读取失败] " + str(e))
            return
        text = "\n".join(str(x) for x in lines)
        if text and text != self.console_out.toPlainText():
            self.console_out.setPlainText(text)
            bar = self.console_out.verticalScrollBar()
            bar.setValue(bar.maximum())

    # ═══════════════ 安装面板 ═══════════════

    def _back_from_install(self):
        # refresh() 在安装面板打开时不会切页（会保持当前页），所以这里显式切走
        inst = None
        if self.store is not None and self._sel_inst is not None:
            inst = self.store.get(self._sel_inst.id)
        if inst is not None:
            self._show_detail(inst)
            self._sync_tree_selection(inst.id)
            return
        self._sel_inst = None
        self._set_del_enabled(False)
        self._show_empty()

    def _install_targets(self):
        """(显示名, provider id, 面板模式)；只列能装的产品。"""
        out = []
        try:
            provs = list(providers.all_providers())
        except Exception:
            provs = []
        for p in provs:
            pid = str(getattr(p, "id", "") or "")
            if not pid:
                continue
            name = str(getattr(p, "name", "") or pid)
            caps = self._caps(pid)
            if CAP_VERSION_LIST in caps:
                out.append((name, pid, "remote"))
            elif CAP_STORE in caps:
                out.append((name + "（商店托管）", pid, "store"))
            elif callable(getattr(p, "import_zip", None)):
                out.append((name + " · 导入 zip", pid, "server"))
        return out

    def _show_install(self):
        targets = self._install_targets()
        self.inst_provider.blockSignals(True)
        self.inst_provider.clear()
        for label, pid, mode in targets:
            self.inst_provider.addItem(label, (pid, mode))
        self.inst_provider.blockSignals(False)

        if not targets:
            self.right_stack.setCurrentIndex(2)
            self.inst_provider.setEnabled(False)
            self.inst_stack.setCurrentIndex(2)
            self.store_tip.setText(
                "没有可用的产品。等 provider 加载成功后这里会有内容。")
            self.store_detect_btn.setEnabled(False)
            self.inst_status.setText("没有可安装的产品（provider 还没加载成功）。")
            return

        self.inst_provider.setEnabled(True)
        self.store_detect_btn.setEnabled(True)
        self.right_stack.setCurrentIndex(2)
        self.inst_provider.setCurrentIndex(0)
        self._on_install_provider(0)

    def _on_install_provider(self, _index=None):
        data = self.inst_provider.currentData()
        if not data:
            return
        pid, mode = data
        self._install_pid = pid
        caps = self._caps(pid)

        if mode == "server":
            self.inst_stack.setCurrentIndex(1)
            self.inst_status.setText("选择一个服务端压缩包导入。")
            return

        if mode == "store":
            self.inst_stack.setCurrentIndex(2)
            self._load_store_state()
            self.inst_status.setText("")
            return

        self.inst_stack.setCurrentIndex(0)
        self.inst_bench_frame.setVisible(CAP_MODLOADER in caps)
        bench = getattr(self, "bench", None)
        if bench is not None:
            cur = self.remote_list.currentItem()
            version = cur.data(Qt.ItemDataRole.UserRole) if cur is not None else None
            bench.set_version(str(getattr(version, "id", "") or ""), force=True)
        self._load_remote()

    def _load_remote(self, force=False):
        pid = self._install_pid
        p = self._provider(pid)
        if p is None:
            self.inst_status.setText("产品没有加载，无法获取版本列表。")
            return
        cached = self._remote_cache.get(pid)
        if cached and not force:
            self._all_remote, self._installed_ids = cached
            self._filter_remote()
            return

        self.remote_refresh_btn.setEnabled(False)
        self.remote_refresh_btn.setText("加载中…")
        self.install_go_btn.setEnabled(False)
        self.inst_status.setText("正在获取版本列表…")

        def task():
            versions = p.list_remote()
            if versions is None:
                raise RuntimeError("该产品不提供远端版本列表。")
            try:
                installed = set(str(v.id) for v in (p.list_installed() or []))
            except Exception:
                installed = set()
            return list(versions), installed

        if not self._spawn("remote", task, self._remote_loaded):
            self.remote_refresh_btn.setEnabled(True)
            self.remote_refresh_btn.setText(t("common.refresh"))

    def _remote_loaded(self, payload, err):
        self.remote_refresh_btn.setEnabled(True)
        self.remote_refresh_btn.setText(t("common.refresh"))
        if err:
            self.install_go_btn.setEnabled(True)
            self.inst_status.setText("获取版本列表失败：" + err + "（可点「刷新」重试）")
            return
        versions, installed = payload if isinstance(payload, tuple) else ([], set())
        self._all_remote = list(versions or [])
        self._installed_ids = set(installed or set())
        self._remote_cache[self._install_pid] = (self._all_remote, self._installed_ids)
        self._filter_remote()

    def _filter_remote(self):
        self.remote_list.clear()
        versions = list(getattr(self, "_all_remote", []) or [])
        show_snap = self.chk_snap.isChecked()
        show_old = self.chk_old.isChecked()
        try:
            self.config.set("show_snapshots", show_snap)
            self.config.set("show_old_versions", show_old)
        except Exception:
            pass
        installed = getattr(self, "_installed_ids", set()) or set()
        shown = 0
        for v in versions:
            kind = str(getattr(v, "kind", "") or "")
            vid = str(getattr(v, "id", "") or "")
            if not vid:
                continue
            if kind == "snapshot" and not show_snap:
                continue
            if kind.startswith("old") and not show_old:
                continue
            if vid in installed:
                has_inst = (self.store is not None
                            and self.store.find_by_version(self._install_pid, vid) is not None)
                # 版本文件在 ≠ 有实例可启动，两个状态必须能一眼分辨
                tag = "  ✓已安装" if has_inst else "  ✓已安装 · 无实例"
            else:
                tag = ""
            disp = str(getattr(v, "display", "") or vid)
            item = QListWidgetItem(disp + "    " + kind_text(kind) + tag)
            item.setData(Qt.ItemDataRole.UserRole, v)
            self.remote_list.addItem(item)
            shown += 1
        if shown:
            # 默认选中第一项，否则「开始安装」会先弹「请先选择一个版本」
            self.remote_list.setCurrentRow(0)
        self.install_go_btn.setEnabled(True)
        self.inst_status.setText(
            "共 {} 个可安装版本（全部 {}）。".format(shown, len(versions)))

    def _clear_tombstone(self, pid: str, vid: str):
        """用户手动为这个版本建了实例，就把"别再自动补建"的记号去掉。"""
        try:
            key = f"{pid}::{vid}"
            tomb = list(self.config.get("instance_tombstones", []) or [])
            if key in tomb:
                tomb = [t for t in tomb if t != key]
                self.config.set("instance_tombstones", tomb)
        except Exception:
            pass

    def _client_jar_ok(self, pid: str, vid: str, min_mb: int = 1) -> bool:
        """粗略判断这个版本是否装完整：客户端 jar 存在且不太小。

        versions/<id>/ 目录和 json 可能在上次失败时已经落地，但 jar 还没下完。
        只看"目录存在"会让人建出启动不了的实例。
        """
        try:
            mc_dir = str(getattr(self.ctx, "mc_dir", "") or "")
            if not mc_dir:
                return True
            jar = os.path.join(mc_dir, "versions", vid, vid + ".jar")
            return os.path.isfile(jar) and os.path.getsize(jar) > min_mb * 1024 * 1024
        except Exception:
            return True

    def _on_remote_sel(self, cur, _prev=None):
        """选中已安装的版本时，主按钮变成「创建实例」——装了却没实例才是常见卡点。"""
        if cur is None:
            self.install_go_btn.setText(t("common.install"))
            return
        version = cur.data(Qt.ItemDataRole.UserRole)
        vid = str(getattr(version, "id", "") or "")
        bench = getattr(self, "bench", None)
        if bench is not None:
            bench.set_version(vid)
        installed = vid in (getattr(self, "_installed_ids", set()) or set())
        if installed:
            self.install_go_btn.setText("创建实例")
        else:
            self.install_go_btn.setText(t("common.install"))
        # 还有实例在用时不允许卸载（先删实例才安全）
        has_inst = False
        try:
            has_inst = (self.store is not None and bool(vid)
                        and self.store.find_by_version(self._install_pid, vid) is not None)
        except Exception:
            has_inst = False
        try:
            can_uninstall = bool(installed and not has_inst
                                 and CAP_UNINSTALL in self._caps(self._install_pid))
        except Exception as e:
            # 这里以前把 NameError 也吞了，表现为"按钮永远点不动"
            print(f"[library] 计算卸载可用性失败: {e}", file=sys.stderr)
            can_uninstall = False
        btn = getattr(self, "uninstall_btn", None)
        if btn is not None:
            btn.setEnabled(can_uninstall)

    def _on_bench_need_options(self, mc_ver):
        """合成台要某个 MC 版本的加载器版本表 —— 自己去取，不再设「查询」按钮。"""
        pid = self._install_pid
        p = self._provider(pid)
        options = getattr(p, "loader_options", None) if p is not None else None
        if not callable(options) or not mc_ver:
            return
        if CAP_MODLOADER not in self._caps(pid):
            return

        def task():
            return options(mc_ver)

        def done(payload, err):
            if err:
                self.inst_status.setText("取加载器版本失败：" + friendly_error(err))
                return
            self.bench.apply_options(mc_ver, payload)

        self._spawn("loader_install", task, done)


    def _do_uninstall(self):
        """卸载版本本体（versions/<id>/）。和"删除实例"是两件事。"""
        pid = self._install_pid
        p = self._provider(pid)
        cur = self.remote_list.currentItem()
        if p is None or cur is None:
            return
        version = cur.data(Qt.ItemDataRole.UserRole)
        vid = str(getattr(version, "id", "") or "")
        if not vid:
            return
        if self.store is not None and self.store.find_by_version(pid, vid) is not None:
            QMessageBox.warning(
                self, "先删实例",
                "还有实例在用它。先在左侧删除对应实例，再卸载版本。")
            return
        uninstall = getattr(p, "uninstall", None)
        if not callable(uninstall):
            QMessageBox.warning(self, "不支持", "该产品不支持卸载版本。")
            return
        if QMessageBox.question(
            self, "卸载版本",
            f"删除 {vid} 的版本文件？\n\n"
            f"会移除 versions/{vid}/ 目录。\n"
            "共享的 libraries / assets / runtime 不会动（其它版本还在用）。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        btn = getattr(self, "uninstall_btn", None)
        if btn is not None:
            btn.setEnabled(False)
        self.install_go_btn.setEnabled(False)
        try:
            ok, err = uninstall(vid)
        except Exception as e:
            ok, err = False, str(e)
        finally:
            self.install_go_btn.setEnabled(True)
        if not ok:
            QMessageBox.warning(self, "卸载失败", err or "未知错误")
            return
        try:
            self._installed_ids.discard(vid)
        except Exception:
            pass
        # 版本都没了，墓碑也就没意义了；将来重装这个版本应当能自动补建实例
        self._clear_tombstone(pid, vid)
        self.inst_status.setText("已卸载：" + vid + "（版本文件已删除）")
        self._filter_remote()

    def _do_install(self):
        pid = self._install_pid
        p = self._provider(pid)
        if p is None:
            return
        cur = self.remote_list.currentItem()
        if cur is None:
            QMessageBox.warning(self, "提示", "请先选择一个版本。")
            return
        version = cur.data(Qt.ItemDataRole.UserRole)
        vid = str(getattr(version, "id", "") or "")
        if not vid:
            return

        # 服务端这类产品：install() 下载 zip 后自己就注册好实例了，
        # 不能再来一遍 store.create（会多出一个重复实例），也没有客户端 jar 可校验。
        if CAP_MODLOADER not in self._caps(pid) and callable(getattr(p, "import_zip", None)):
            self._install_direct(p, version, vid)
            return

        installed_ids = getattr(self, "_installed_ids", set()) or set()
        if vid in installed_ids and self.store is not None:
            existing = self.store.find_by_version(pid, vid)
            if existing is not None and self._client_jar_ok(pid, vid):
                self.inst_status.setText("这个版本已经有实例了，已在右侧打开。")
                self.refresh()
                self._show_detail(existing)
                return
            if self._client_jar_ok(pid, vid):
                # 文件齐了（例如上次装完但没建实例），直接建，不再校验几百 MB
                try:
                    inst = self.store.create(pid, vid, name=vid)
                except Exception as e:
                    QMessageBox.warning(self, "创建实例失败", str(e))
                    return
                self._clear_tombstone(pid, vid)
                self.inst_status.setText("已创建实例：" + vid)
                self._remote_cache.pop(pid, None)
                self.refresh()
                self._show_detail(inst)
                return
            # 目录在但客户端 jar 缺失/过小：上次安装没走完，继续补全而不是建个空实例
            self.inst_status.setText("上次安装不完整，正在补全文件…")

        caps = self._caps(pid)
        bench = getattr(self, "bench", None)
        plan = {"loader": "", "loader_version": "", "extra_jars": [], "name": vid}
        if CAP_MODLOADER in caps and bench is not None:
            if not bench.can_compose():
                blocked = [i.reason for i in bench.issues() if i.level == "blocked"]
                QMessageBox.warning(
                    self, "这套配方合不出来",
                    "\n".join(blocked) or "材料还没选全：选中的加载器还没取到版本号。")
                return
            plan = bench.install_plan()

        loader_type = plan.get("loader") or "none"
        loader_ver = plan.get("loader_version") or None
        extra_jars = [j for j in (plan.get("extra_jars") or []) if j]
        manual = [m for m in (plan.get("manual") or []) if m]
        name = dict(_LOADERS).get(loader_type, loader_type)

        if loader_type != "none" and not loader_ver:
            QMessageBox.warning(
                self, "还没选加载器版本",
                "加载器版本还没取到。等一下版本列表加载完，或把那个槽位取消。")
            return

        self.install_go_btn.setEnabled(False)
        try:
            d = ProgressDialog("安装 " + vid, lambda cb: p.install(version, cb), self)
            d.start()
            if d.was_cancelled:
                self.inst_status.setText("已取消安装。")
                return
            if not d.success:
                self.inst_status.setText("安装失败。")
                QMessageBox.critical(self, "安装失败", friendly_error(d.error_msg))
                return

            final_vid = vid
            if loader_type != "none":
                self.inst_status.setText(
                    "正在安装 " + name + " " + str(loader_ver) + "…")
                install_loader = getattr(p, "install_loader", None)
                if not callable(install_loader):
                    QMessageBox.warning(self, "无法安装加载器", "该产品不支持加载器。")
                else:
                    holder = {}

                    def loader_task(cb):
                        holder["vid"] = install_loader(
                            vid, loader_type, str(loader_ver), cb)

                    d2 = ProgressDialog(
                        "安装 " + name + " " + str(loader_ver), loader_task, self)
                    d2.start()
                    if d2.was_cancelled:
                        self.inst_status.setText(
                            "已取消安装 " + name + "（原版已装好）。")
                        self.refresh()
                        return
                    if not d2.success:
                        self.inst_status.setText(
                            name + " 安装失败（原版已装好）。")
                        QMessageBox.warning(self, name, friendly_error(d2.error_msg))
                        self.refresh()
                        return
                    final_vid = str(holder.get("vid") or vid)

            inst = None
            inst_name = str(plan.get("name") or "").strip() or final_vid
            if self.store is not None:
                try:
                    inst = self.store.create(pid, final_vid, name=inst_name)
                except Exception as e:
                    self.inst_status.setText("版本装好了，但建实例失败：" + str(e))
            placed = self._place_extra_jars(inst, extra_jars) if inst is not None else []
            # 镜像缺文件是常态（1.7.10 的 log4j 配置、老 natives 等），
            # 回退已经发生在请求层，这里只把事实告诉用户，避免"换源反而更慢"的困惑。
            note = ""
            try:
                from core import mirror as _mirror
                events = _mirror.fallback_events()
                if events:
                    note = f"（{len(events)} 个文件在当前源缺失，已自动改走官方源）"
                    _mirror.clear_fallback_events()
            except Exception:
                note = ""
            extra_note = ("（已放入 mods/：" + "、".join(placed) + "）") if placed else ""
            manual_note = ""
            if manual:
                manual_note = ("；" + "、".join(
                    dict(_LOADERS).get(m, m) if m != "liteloader" else "LiteLoader"
                    for m in manual) + " 本启动器不代装，需要你手动加进这个版本")
            self.inst_status.setText(
                "安装完成：" + final_vid + note + extra_note + manual_note)
            self._remote_cache.pop(pid, None)
            self.refresh()
            if inst is not None:
                self._show_detail(inst)
                self._sync_tree_selection(inst.id)
        finally:
            self.install_go_btn.setEnabled(True)

    def _place_extra_jars(self, inst, jars) -> list:
        """把用户挑的补丁 jar（OptiFine 之类）放进实例的 mods/，返回文件名列表。"""
        if inst is None or not jars:
            return []
        game_dir = str(getattr(inst, "game_dir", "") or "")
        if not game_dir:
            return []
        import os as _os
        import shutil as _shutil
        mods = _os.path.join(game_dir, "mods")
        placed = []
        try:
            _os.makedirs(mods, exist_ok=True)
        except OSError as e:
            print(f"[library] 建 mods 目录失败: {e}", file=sys.stderr)
            return []
        for src in jars:
            try:
                dst = _os.path.join(mods, _os.path.basename(src))
                _shutil.copy2(src, dst)
                placed.append(_os.path.basename(src))
            except OSError as e:
                print(f"[library] 复制 {src} 失败: {e}", file=sys.stderr)
        return placed

    def _install_direct(self, p, version, vid):
        """provider 自己会建实例的产品（BDS）：下载 + 注册，一步到位。"""
        holder = {}

        def task(cb):
            holder["inst"] = p.install(version, cb)

        self.install_go_btn.setEnabled(False)
        try:
            d = ProgressDialog("下载 " + vid, task, self)
            d.start()
            if d.was_cancelled:
                self.inst_status.setText("已取消下载。")
                return
            if not d.success:
                self.inst_status.setText("下载失败。")
                QMessageBox.critical(self, "下载失败", friendly_error(d.error_msg))
                return
            inst = holder.get("inst")
            if inst is None:
                self.inst_status.setText("装好了，但没拿到实例信息。")
                self.refresh()
                return
            self.inst_status.setText("装好了：" + vid)
            self.refresh()
            self._show_detail(inst)
            self._sync_tree_selection(inst.id)
        finally:
            self.install_go_btn.setEnabled(True)

    def _import_server_zip(self):
        pid = self._install_pid
        p = self._provider(pid)
        importer = getattr(p, "import_zip", None) if p is not None else None
        if not callable(importer):
            QMessageBox.information(self, "暂不可用", "该产品不支持 zip 导入。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "选择服务端压缩包", "", "ZIP (*.zip);;All (*)")
        if not path:
            return
        holder = {}

        def task(cb):
            holder["inst"] = importer(path, "")

        self.server_import_btn.setEnabled(False)
        d = ProgressDialog("导入服务端", task, self)
        d.start()
        self.server_import_btn.setEnabled(True)
        if d.was_cancelled:
            self.inst_status.setText("已取消导入。")
            return
        if not d.success:
            self.inst_status.setText("导入失败：" + friendly_error(d.error_msg))
            QMessageBox.warning(self, "导入失败", friendly_error(d.error_msg))
            return
        inst = holder.get("inst")
        # provider 可能只返回 Instance 没落库，这里补一次注册
        if inst is not None and self.store is not None:
            try:
                if not self.store.get(str(getattr(inst, "id", ""))):
                    self.store.update(inst)
            except Exception:
                pass
        self.inst_status.setText("导入完成，实例已注册。")
        self.refresh()

    def _detect_store_install(self):
        pid = self._install_pid
        p = self._provider(pid)
        lister = getattr(p, "list_installed", None) if p is not None else None
        if not callable(lister):
            self.inst_status.setText("该产品不提供本机检测。")
            return
        self.store_detect_btn.setEnabled(False)
        self.store_detect_btn.setText("检测中…")
        self.inst_status.setText("正在检测本机安装…")

        def task():
            return list(lister() or [])

        if not self._spawn("installed", task, self._store_detected):
            self.store_detect_btn.setEnabled(True)
            self.store_detect_btn.setText("检测本机安装")

    def _store_detected(self, payload, err):
        self.store_detect_btn.setEnabled(True)
        self.store_detect_btn.setText("检测本机安装")
        if err:
            self.inst_status.setText("检测失败：" + err)
            return
        versions = list(payload or [])
        if not versions:
            self.inst_status.setText("没有在 Microsoft Store 里找到安装记录。先去商店装一次。")
            return
        names = "、".join(
            str(getattr(v, "display", "") or getattr(v, "id", "")) for v in versions[:5])
        self.inst_status.setText("检测到 {} 个安装：{}".format(len(versions), names))
        self._load_store_state()
        pid = self._install_pid
        for v in versions:
            vid = str(getattr(v, "id", "") or "")
            if not vid or self.store is None:
                continue
            try:
                if self.store.find_by_version(pid, vid) is None:
                    self.store.create(
                        pid, vid, name=str(getattr(v, "display", "") or vid))
            except Exception:
                pass
        self.refresh()

    # ═══════════════ 生命周期 ═══════════════

    def shutdown(self, wait_ms=1500):
        """主窗口关闭前等后台线程收尾，避免解释器退出时 abort。"""
        for _name, value in list(vars(self).items()):
            if isinstance(value, QThread):
                try:
                    if value.isRunning():
                        value.wait(wait_ms)
                except Exception:
                    pass
        for timer_name in ("_launch_timer", "_tail_timer"):
            timer = getattr(self, timer_name, None)
            if isinstance(timer, QTimer):
                try:
                    timer.stop()
                except Exception:
                    pass
