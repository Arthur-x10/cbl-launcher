"""统一版本管理 — 已安装列表 + 详情/安装/加载器/Mod 全生命周期。"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QCheckBox, QComboBox, QMessageBox, QStackedWidget,
    QScrollArea, QFrame, QFileDialog,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core import version_manager, mod_manager, modpack
from core.launcher import get_required_java
from ui.widgets.progress_dialog import ProgressDialog
from ui.widgets.common import make_sheet, vline, version_kind, labeled_field
from ui.tokens import SPACE_XL, SPACE_LG, SPACE_MD, SPACE_SM, HIT_MIN


class VersionsPage(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._all_remote = []
        self._selected_vid = ""
        self._build()

    # ═══════════════════ 布局 ═══════════════════

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        root.setSpacing(SPACE_MD)

        root.addWidget(self._build_left(), 2)
        root.addWidget(self._build_right(), 3)

    def _build_left(self) -> QWidget:
        """左侧：已安装版本列表 + 安装按钮。"""
        panel = make_sheet()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        lay.setSpacing(SPACE_SM)

        hd = QLabel("已安装版本")
        hd.setObjectName("sectionLabel")
        lay.addWidget(hd)

        self.ver_list = QListWidget()
        self.ver_list.setAccessibleName("已安装版本")
        self.ver_list.currentItemChanged.connect(self._on_select)
        lay.addWidget(self.ver_list, 1)

        self.empty_hint = QLabel("还没有安装版本")
        self.empty_hint.setObjectName("mutedLabel")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.hide()
        lay.addWidget(self.empty_hint)

        bot_row = QHBoxLayout()
        bot_row.setSpacing(SPACE_SM)

        self.install_new_btn = QPushButton("+ 安装版本")
        self.install_new_btn.setObjectName("btnPrimary")
        self.install_new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_new_btn.setFixedHeight(HIT_MIN + 2)
        self.install_new_btn.clicked.connect(self._show_install)
        bot_row.addWidget(self.install_new_btn)

        self.import_pack_btn = QPushButton("导入整合包")
        self.import_pack_btn.setObjectName("btnBlue")
        self.import_pack_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_pack_btn.setFixedHeight(HIT_MIN + 2)
        self.import_pack_btn.clicked.connect(self._import_modpack)
        bot_row.addWidget(self.import_pack_btn)

        lay.addLayout(bot_row)

        return panel

    def _build_right(self) -> QWidget:
        """右侧：详情 / 安装面板（QStackedWidget 切换）。"""
        self.right_stack = QStackedWidget()

        self.right_stack.addWidget(self._build_empty())
        self.right_stack.addWidget(self._build_detail())
        self.right_stack.addWidget(self._build_install_panel())

        return self.right_stack

    # ── 右侧 Page 0: 空状态 ──

    def _build_empty(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("← 选择一个版本查看详情\n或点击「安装新版本」")
        lbl.setObjectName("mutedLabel")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl)
        return w

    # ── 右侧 Page 1: 版本详情 ──

    def _build_detail(self) -> QWidget:
        panel = make_sheet()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
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

        # 加载器安装区
        self.loader_frame = QWidget()
        loader_lay = QVBoxLayout(self.loader_frame)
        loader_lay.setContentsMargins(0, SPACE_SM, 0, 0)
        loader_lay.setSpacing(SPACE_SM)

        ldr_title = QLabel("安装加载器")
        ldr_title.setObjectName("sectionLabel")
        loader_lay.addWidget(ldr_title)

        # Forge 行
        forge_row = QHBoxLayout()
        forge_row.setSpacing(SPACE_SM)
        forge_lbl = QLabel("Forge")
        forge_lbl.setObjectName("fieldLabel")
        forge_lbl.setFixedWidth(48)
        forge_row.addWidget(forge_lbl)

        self.forge_combo = QComboBox()
        self.forge_combo.setFixedHeight(HIT_MIN)
        self.forge_combo.setAccessibleName("Forge 版本")
        self.forge_combo.setPlaceholderText("点击「查询」获取列表")
        forge_row.addWidget(self.forge_combo, 1)

        self.forge_query_btn = QPushButton("查询")
        self.forge_query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forge_query_btn.setFixedHeight(HIT_MIN)
        self.forge_query_btn.clicked.connect(self._query_forge)
        forge_row.addWidget(self.forge_query_btn)

        self.forge_install_btn = QPushButton("安装")
        self.forge_install_btn.setObjectName("btnPrimary")
        self.forge_install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forge_install_btn.setFixedHeight(HIT_MIN)
        self.forge_install_btn.clicked.connect(self._install_forge)
        self.forge_install_btn.hide()
        forge_row.addWidget(self.forge_install_btn)

        loader_lay.addLayout(forge_row)

        # Fabric 行
        fabric_row = QHBoxLayout()
        fabric_row.setSpacing(SPACE_SM)
        fabric_lbl = QLabel("Fabric")
        fabric_lbl.setObjectName("fieldLabel")
        fabric_lbl.setFixedWidth(48)
        fabric_row.addWidget(fabric_lbl)

        self.fabric_combo = QComboBox()
        self.fabric_combo.setFixedHeight(HIT_MIN)
        self.fabric_combo.setAccessibleName("Fabric Loader")
        self.fabric_combo.setPlaceholderText("点击「查询」获取列表")
        fabric_row.addWidget(self.fabric_combo, 1)

        self.fabric_query_btn = QPushButton("查询")
        self.fabric_query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fabric_query_btn.setFixedHeight(HIT_MIN)
        self.fabric_query_btn.clicked.connect(self._query_fabric)
        fabric_row.addWidget(self.fabric_query_btn)

        self.fabric_install_btn = QPushButton("安装")
        self.fabric_install_btn.setObjectName("btnBlue")
        self.fabric_install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fabric_install_btn.setFixedHeight(HIT_MIN)
        self.fabric_install_btn.clicked.connect(self._install_fabric)
        self.fabric_install_btn.hide()
        fabric_row.addWidget(self.fabric_install_btn)

        loader_lay.addLayout(fabric_row)

        # Quilt 行
        quilt_row = QHBoxLayout()
        quilt_row.setSpacing(SPACE_SM)
        quilt_lbl = QLabel("Quilt")
        quilt_lbl.setObjectName("fieldLabel")
        quilt_lbl.setFixedWidth(48)
        quilt_row.addWidget(quilt_lbl)

        self.quilt_combo = QComboBox()
        self.quilt_combo.setFixedHeight(HIT_MIN)
        self.quilt_combo.setPlaceholderText("点击「查询」获取列表")
        quilt_row.addWidget(self.quilt_combo, 1)

        self.quilt_query_btn = QPushButton("查询")
        self.quilt_query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quilt_query_btn.setFixedHeight(HIT_MIN)
        self.quilt_query_btn.clicked.connect(self._query_quilt)
        quilt_row.addWidget(self.quilt_query_btn)

        self.quilt_install_btn = QPushButton("安装")
        self.quilt_install_btn.setObjectName("btnPrimary")
        self.quilt_install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quilt_install_btn.setFixedHeight(HIT_MIN)
        self.quilt_install_btn.clicked.connect(self._install_quilt)
        self.quilt_install_btn.hide()
        quilt_row.addWidget(self.quilt_install_btn)

        loader_lay.addLayout(quilt_row)

        # NeoForge 行
        neo_row = QHBoxLayout()
        neo_row.setSpacing(SPACE_SM)
        neo_lbl = QLabel("NeoForge")
        neo_lbl.setObjectName("fieldLabel")
        neo_lbl.setFixedWidth(48)
        neo_row.addWidget(neo_lbl)

        self.neo_combo = QComboBox()
        self.neo_combo.setFixedHeight(HIT_MIN)
        self.neo_combo.setPlaceholderText("点击「查询」(1.20.1+)")
        neo_row.addWidget(self.neo_combo, 1)

        self.neo_query_btn = QPushButton("查询")
        self.neo_query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.neo_query_btn.setFixedHeight(HIT_MIN)
        self.neo_query_btn.clicked.connect(self._query_neoforge)
        neo_row.addWidget(self.neo_query_btn)

        self.neo_install_btn = QPushButton("安装")
        self.neo_install_btn.setObjectName("btnPrimary")
        self.neo_install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.neo_install_btn.setFixedHeight(HIT_MIN)
        self.neo_install_btn.clicked.connect(self._install_neoforge)
        self.neo_install_btn.hide()
        neo_row.addWidget(self.neo_install_btn)

        loader_lay.addLayout(neo_row)

        self.loader_status = QLabel("")
        self.loader_status.setObjectName("statusLabel")
        loader_lay.addWidget(self.loader_status)

        lay.addWidget(self.loader_frame)

        # Mod 管理区
        mod_title = QLabel("Mods")
        mod_title.setObjectName("sectionLabel")
        lay.addWidget(mod_title)

        self.mod_list_label = QLabel("无 mods")
        self.mod_list_label.setObjectName("mutedLabel")
        self.mod_list_label.setWordWrap(True)
        lay.addWidget(self.mod_list_label)

        self.open_mods_btn = QPushButton("打开 mods 文件夹")
        self.open_mods_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_mods_btn.setFixedHeight(HIT_MIN)
        self.open_mods_btn.clicked.connect(self._open_mods)
        lay.addWidget(self.open_mods_btn)

        lay.addStretch()

        # 删除按钮 (底部)
        self.del_btn = QPushButton("删除此版本")
        self.del_btn.setObjectName("logoutBtn")
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setFixedHeight(HIT_MIN)
        self.del_btn.clicked.connect(self._delete_version)
        lay.addWidget(self.del_btn)

        scroll.setWidget(inner)
        panel_lay = QVBoxLayout(panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.addWidget(scroll)
        return panel

    # ── 右侧 Page 2: 安装新版本 ──

    def _build_install_panel(self) -> QWidget:
        panel = make_sheet()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        lay.setSpacing(SPACE_MD)

        head = QHBoxLayout()
        t = QLabel("安装新版本")
        t.setObjectName("title")
        head.addWidget(t)
        head.addStretch()

        back_btn = QPushButton("返回")
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setFixedHeight(HIT_MIN)
        back_btn.clicked.connect(lambda: self.right_stack.setCurrentIndex(0))
        head.addWidget(back_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setFixedHeight(HIT_MIN)
        self.refresh_btn.clicked.connect(self._load_remote)
        head.addWidget(self.refresh_btn)
        lay.addLayout(head)

        # 过滤
        flt = QHBoxLayout()
        flt.setSpacing(SPACE_LG)
        self.chk_snap = QCheckBox("快照")
        self.chk_snap.setChecked(self.config.get("show_snapshots", False))
        self.chk_snap.stateChanged.connect(self._filter_remote)
        flt.addWidget(self.chk_snap)
        self.chk_old = QCheckBox("远古")
        self.chk_old.setChecked(self.config.get("show_old_versions", False))
        self.chk_old.stateChanged.connect(self._filter_remote)
        flt.addWidget(self.chk_old)
        flt.addStretch()
        lay.addLayout(flt)

        # 版本列表
        self.remote_list = QListWidget()
        self.remote_list.setAccessibleName("可下载版本")
        lay.addWidget(self.remote_list, 1)

        # 可选加载器
        opt_title = QLabel("可选：同时安装加载器")
        opt_title.setObjectName("fieldLabel")
        lay.addWidget(opt_title)

        type_row = QHBoxLayout()
        type_row.setSpacing(SPACE_SM)
        self.opt_loader = QComboBox()
        self.opt_loader.addItem("不安装加载器", "none")
        self.opt_loader.addItem("Forge", "forge")
        self.opt_loader.addItem("Fabric", "fabric")
        self.opt_loader.addItem("Quilt", "quilt")
        self.opt_loader.addItem("NeoForge (1.20.1+)", "neoforge")
        self.opt_loader.setFixedHeight(HIT_MIN)
        self.opt_loader.currentIndexChanged.connect(self._on_loader_type_change)
        type_row.addWidget(self.opt_loader, 1)

        self.opt_query_btn = QPushButton("查询可用版本")
        self.opt_query_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.opt_query_btn.setFixedHeight(HIT_MIN)
        self.opt_query_btn.clicked.connect(self._query_loader_versions)
        self.opt_query_btn.hide()
        type_row.addWidget(self.opt_query_btn)
        lay.addLayout(type_row)

        ver_row = QHBoxLayout()
        ver_row.setSpacing(SPACE_SM)
        self.opt_loader_ver = QComboBox()
        self.opt_loader_ver.setFixedHeight(HIT_MIN)
        self.opt_loader_ver.setPlaceholderText("先查询可用版本")
        self.opt_loader_ver.hide()
        ver_row.addWidget(self.opt_loader_ver, 1)
        lay.addLayout(ver_row)

        # 安装按钮
        bot = QHBoxLayout()
        self.inst_status = QLabel("")
        self.inst_status.setObjectName("statusLabel")
        bot.addWidget(self.inst_status, 1)
        self.dl_btn = QPushButton("开始安装")
        self.dl_btn.setObjectName("btnPrimary")
        self.dl_btn.setFixedHeight(HIT_MIN + 2)
        self.dl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dl_btn.clicked.connect(self._do_install)
        bot.addWidget(self.dl_btn)
        lay.addLayout(bot)

        return panel

    # ═══════════════════ 数据加载 ═══════════════════

    def refresh(self):
        self._refresh_installed()
        if self.right_stack.currentIndex() == 2 and not self._all_remote:
            self._load_remote()

    def _refresh_installed(self):
        self.ver_list.clear()
        mc = self.config.get_minecraft_dir()
        groups = version_manager.get_grouped_versions(mc)
        if not groups:
            self.empty_hint.show()
            self.ver_list.hide()
            self.right_stack.setCurrentIndex(0)
            return
        self.empty_hint.hide()
        self.ver_list.show()
        for g in groups:
            vid = g["id"]
            kind = version_kind(vid)
            item = QListWidgetItem(f"{vid}    {kind}")
            item.setData(Qt.ItemDataRole.UserRole, vid)
            self.ver_list.addItem(item)
            for child in g.get("children", []):
                label = child.get("label", child["id"])
                citem = QListWidgetItem(f"   └ {label}")
                citem.setData(Qt.ItemDataRole.UserRole, child["id"])
                self.ver_list.addItem(citem)

    def _get_children(self, parent_vid: str) -> list[dict]:
        """获取某个原版的所有加载器子版本。"""
        mc = self.config.get_minecraft_dir()
        groups = version_manager.get_grouped_versions(mc)
        for g in groups:
            if g["id"] == parent_vid:
                return g.get("children", [])
        return []

    # ═══════════════════ 版本详情 ═══════════════════

    def _on_select(self, current, previous=None):
        if not current:
            self.right_stack.setCurrentIndex(0)
            return
        vid = current.data(Qt.ItemDataRole.UserRole)
        if not vid:
            return
        self._selected_vid = vid
        mc = self.config.get_minecraft_dir()
        kind = version_kind(vid)
        size = version_manager.get_version_size_mb(mc, vid)

        java_req = get_required_java(mc, vid)
        self.d_title.setText(vid)
        self.d_meta.setText(
            f"类型: {kind}　　Java: {java_req}+　　大小: {size} MB"
        )

        is_vanilla = kind in ("正式版", "快照")
        self.loader_frame.setVisible(is_vanilla)

        # 清空加载器查询状态
        for combo in (self.forge_combo, self.fabric_combo, self.quilt_combo, self.neo_combo):
            combo.clear()
        for btn in (self.forge_install_btn, self.fabric_install_btn,
                    self.quilt_install_btn, self.neo_install_btn):
            btn.hide()

        # 显示已安装的加载器
        children = self._get_children(vid)
        if children:
            installed_labels = ", ".join(c.get("label", c["id"]) for c in children)
            self.loader_status.setText(f"已安装: {installed_labels}")
        else:
            self.loader_status.setText("")

        mods = version_manager.get_mods_list(mc)
        if mods:
            self.mod_list_label.setText("\n".join(f"  · {m}" for m in mods))
        else:
            self.mod_list_label.setText("mods 文件夹为空，将 .jar 文件放入即可。")

        self.right_stack.setCurrentIndex(1)

    # ═══════════════════ 加载器查询与安装 ═══════════════════

    def _query_forge(self):
        vid = self._selected_vid
        self.forge_query_btn.setEnabled(False)
        self.forge_query_btn.setText("查询中…")
        self.loader_status.setText("正在查询 Forge 版本…")

        class T(QThread):
            done = pyqtSignal(list, str)
            def run(self):
                rec = mod_manager.find_forge_version(vid) or ""
                vs = mod_manager.get_forge_versions(vid)
                if rec and rec in vs:
                    vs.remove(rec)
                    vs.insert(0, rec)
                self.done.emit(vs, rec)

        self._fq = T()
        self._fq.done.connect(self._forge_loaded)
        self._fq.start()

    def _forge_loaded(self, versions, recommended):
        self.forge_query_btn.setEnabled(True)
        self.forge_query_btn.setText("查询")
        self.forge_combo.clear()
        for v in versions:
            tag = " (推荐)" if v == recommended else ""
            self.forge_combo.addItem(f"{v}{tag}", v)
        if versions:
            self.forge_install_btn.show()
            self.loader_status.setText(f"找到 {len(versions)} 个 Forge 版本")
        else:
            self.forge_install_btn.hide()
            self.loader_status.setText("此 MC 版本没有可用的 Forge。")

    def _install_forge(self):
        fv = self.forge_combo.currentData()
        if not fv:
            return
        mc = self.config.get_minecraft_dir()

        def task(cb):
            mod_manager.install_forge(mc, fv, cb)

        d = ProgressDialog(f"安装 Forge {fv}", task, self)
        d.start()
        if d.success:
            self.loader_status.setText("Forge 安装成功!")
            self._refresh_installed()
        else:
            self.loader_status.setText(f"失败: {d.error_msg}")

    def _query_fabric(self):
        self.fabric_query_btn.setEnabled(False)
        self.fabric_query_btn.setText("查询中…")
        self.loader_status.setText("正在查询 Fabric Loader…")

        class T(QThread):
            done = pyqtSignal(list)
            def run(self):
                self.done.emit(mod_manager.get_fabric_versions())

        self._fbq = T()
        self._fbq.done.connect(self._fabric_loaded)
        self._fbq.start()

    def _fabric_loaded(self, loaders):
        self.fabric_query_btn.setEnabled(True)
        self.fabric_query_btn.setText("查询")
        self.fabric_combo.clear()
        for l in loaders[:30]:
            v = l.get("version", "")
            stable = l.get("stable", False)
            tag = " (推荐)" if stable else ""
            self.fabric_combo.addItem(f"{v}{tag}", v)
            if stable and self.fabric_combo.count() == 1:
                self.fabric_combo.setCurrentIndex(0)
        if loaders:
            self.fabric_install_btn.show()
            self.loader_status.setText(f"找到 {len(loaders)} 个 Fabric Loader")
        else:
            self.fabric_install_btn.hide()
            self.loader_status.setText("没有可用的 Fabric Loader。")

    def _install_fabric(self):
        lv = self.fabric_combo.currentData()
        if not lv:
            return
        mc = self.config.get_minecraft_dir()
        vid = self._selected_vid

        def task(cb):
            mod_manager.install_fabric(mc, vid, lv, cb)

        d = ProgressDialog(f"安装 Fabric ({vid})", task, self)
        d.start()
        if d.success:
            self.loader_status.setText("Fabric 安装成功!")
            self._refresh_installed()
        else:
            self.loader_status.setText(f"失败: {d.error_msg}")

    # ── Quilt ──

    def _query_quilt(self):
        self.quilt_query_btn.setEnabled(False)
        self.quilt_query_btn.setText("查询中…")
        self.loader_status.setText("正在查询 Quilt Loader…")

        class T(QThread):
            done = pyqtSignal(list)
            def run(self):
                self.done.emit(mod_manager.get_quilt_versions())

        self._qq = T()
        self._qq.done.connect(self._quilt_loaded)
        self._qq.start()

    def _quilt_loaded(self, loaders):
        self.quilt_query_btn.setEnabled(True)
        self.quilt_query_btn.setText("查询")
        self.quilt_combo.clear()
        for l in loaders[:30]:
            v = l.get("version", "")
            stable = l.get("stable", False)
            tag = " (推荐)" if stable else ""
            self.quilt_combo.addItem(f"{v}{tag}", v)
        if loaders:
            self.quilt_install_btn.show()
            self.loader_status.setText(f"找到 {len(loaders)} 个 Quilt Loader")
        else:
            self.quilt_install_btn.hide()
            self.loader_status.setText("没有可用的 Quilt Loader。")

    def _install_quilt(self):
        lv = self.quilt_combo.currentData()
        if not lv:
            return
        mc = self.config.get_minecraft_dir()
        vid = self._selected_vid

        def task(cb):
            mod_manager.install_quilt(mc, vid, lv, cb)

        d = ProgressDialog(f"安装 Quilt ({vid})", task, self)
        d.start()
        if d.success:
            self.loader_status.setText("Quilt 安装成功!")
            self._refresh_installed()
        else:
            self.loader_status.setText(f"失败: {d.error_msg}")

    # ── NeoForge ──

    def _query_neoforge(self):
        vid = self._selected_vid
        self.neo_query_btn.setEnabled(False)
        self.neo_query_btn.setText("查询中…")
        self.loader_status.setText("正在查询 NeoForge…")

        class T(QThread):
            done = pyqtSignal(list)
            def run(self):
                self.done.emit(mod_manager.get_neoforge_versions(vid))

        self._nq = T()
        self._nq.done.connect(self._neoforge_loaded)
        self._nq.start()

    def _neoforge_loaded(self, versions):
        self.neo_query_btn.setEnabled(True)
        self.neo_query_btn.setText("查询")
        self.neo_combo.clear()
        for i, v in enumerate(versions[:30]):
            tag = " (推荐)" if i == 0 else ""
            self.neo_combo.addItem(f"{v}{tag}", v)
        if versions:
            self.neo_install_btn.show()
            self.loader_status.setText(f"找到 {len(versions)} 个 NeoForge 版本")
        else:
            self.neo_install_btn.hide()
            self.loader_status.setText("此 MC 版本没有 NeoForge (需 1.20.1+)。")

    def _install_neoforge(self):
        nv = self.neo_combo.currentData()
        if not nv:
            return
        mc = self.config.get_minecraft_dir()

        def task(cb):
            mod_manager.install_neoforge(mc, nv, cb)

        d = ProgressDialog(f"安装 NeoForge {nv}", task, self)
        d.start()
        if d.success:
            self.loader_status.setText("NeoForge 安装成功!")
            self._refresh_installed()
        else:
            self.loader_status.setText(f"失败: {d.error_msg}")

    # ═══════════════════ Mod 管理 ═══════════════════

    def _open_mods(self):
        mc = self.config.get_minecraft_dir()
        version_manager.open_mods_folder(mc)

    # ═══════════════════ 删除版本 ═══════════════════

    def _delete_version(self):
        vid = self._selected_vid
        if not vid:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"删除版本 {vid}？\n将移除 versions/{vid}/ 目录下的所有文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        mc = self.config.get_minecraft_dir()
        version_manager.delete_version(mc, vid)
        self._selected_vid = ""
        self.right_stack.setCurrentIndex(0)
        self._refresh_installed()

    # ═══════════════════ 安装新版本 ═══════════════════

    def _show_install(self):
        self.right_stack.setCurrentIndex(2)
        if not self._all_remote:
            self._load_remote()

    def _load_remote(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("加载中…")
        self.inst_status.setText("正在获取版本列表…")

        class T(QThread):
            done = pyqtSignal(list)
            def run(self):
                self.done.emit(version_manager.get_all_versions())

        self._rt = T()
        self._rt.done.connect(self._remote_loaded)
        self._rt.start()

    def _remote_loaded(self, vs):
        self._all_remote = vs
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("刷新")
        self._filter_remote()
        self.inst_status.setText(f"共 {len(vs)} 个版本")

    def _filter_remote(self):
        self.remote_list.clear()
        mc = self.config.get_minecraft_dir()
        self.config.set("show_snapshots", self.chk_snap.isChecked())
        self.config.set("show_old_versions", self.chk_old.isChecked())

        for v in version_manager.filter_versions(
            self._all_remote, True,
            self.chk_snap.isChecked(), self.chk_old.isChecked()
        ):
            vid = v["id"]
            vt = v.get("type", "")
            inst = version_manager.is_version_installed(mc, vid)
            tp = {"release": "正式版", "snapshot": "快照",
                  "old_alpha": "远古α", "old_beta": "远古β"}.get(vt, vt)
            tag = "  ✓已安装" if inst else ""
            item = QListWidgetItem(f"{vid}    {tp}{tag}")
            item.setData(Qt.ItemDataRole.UserRole, vid)
            self.remote_list.addItem(item)

    def _on_loader_type_change(self):
        ltype = self.opt_loader.currentData()
        show = ltype != "none"
        self.opt_query_btn.setVisible(show)
        self.opt_loader_ver.setVisible(show)
        self.opt_loader_ver.clear()
        if not show:
            self.opt_query_btn.setText("查询可用版本")

    def _query_loader_versions(self):
        cur = self.remote_list.currentItem()
        if not cur:
            QMessageBox.warning(self, "提示", "请先在上方选择一个 MC 版本。")
            return
        vid = cur.data(Qt.ItemDataRole.UserRole)
        ltype = self.opt_loader.currentData()
        if not ltype or ltype == "none":
            return

        self.opt_query_btn.setEnabled(False)
        self.opt_query_btn.setText("查询中…")
        self.opt_loader_ver.clear()

        class T(QThread):
            done = pyqtSignal(list, str)
            def __init__(self, mc_ver, loader_type):
                super().__init__()
                self._v, self._t = mc_ver, loader_type
            def run(self):
                results = []
                rec = ""
                if self._t == "forge":
                    rec = mod_manager.find_forge_version(self._v) or ""
                    vs = mod_manager.get_forge_versions(self._v)
                    if rec and rec in vs:
                        vs.remove(rec)
                        vs.insert(0, rec)
                    results = [{"v": v, "rec": v == rec} for v in vs]
                elif self._t == "fabric":
                    for l in mod_manager.get_fabric_versions()[:30]:
                        v = l.get("version", "")
                        stable = l.get("stable", False)
                        results.append({"v": v, "rec": stable})
                elif self._t == "quilt":
                    for l in mod_manager.get_quilt_versions()[:30]:
                        v = l.get("version", "")
                        stable = l.get("stable", False)
                        results.append({"v": v, "rec": stable})
                elif self._t == "neoforge":
                    vs = mod_manager.get_neoforge_versions(self._v)
                    for i, v in enumerate(vs[:30]):
                        results.append({"v": v, "rec": i == 0})
                self.done.emit(results, self._t)

        self._lq = T(vid, ltype)
        self._lq.done.connect(self._loader_versions_loaded)
        self._lq.start()

    def _loader_versions_loaded(self, results, ltype):
        self.opt_query_btn.setEnabled(True)
        self.opt_query_btn.setText("查询可用版本")
        self.opt_loader_ver.clear()
        names = {"forge": "Forge", "fabric": "Fabric", "quilt": "Quilt", "neoforge": "NeoForge"}
        name = names.get(ltype, ltype)
        for r in results:
            tag = " (推荐)" if r["rec"] else ""
            self.opt_loader_ver.addItem(f"{r['v']}{tag}", r["v"])
        if results:
            self.opt_loader_ver.show()
            self.inst_status.setText(f"找到 {len(results)} 个 {name} 版本")
        else:
            self.inst_status.setText(f"此 MC 版本没有可用的 {name}。")

    def _do_install(self):
        cur = self.remote_list.currentItem()
        if not cur:
            QMessageBox.warning(self, "提示", "请先选择一个版本。")
            return
        vid = cur.data(Qt.ItemDataRole.UserRole)
        mc = self.config.get_minecraft_dir()

        if version_manager.is_version_installed(mc, vid):
            QMessageBox.information(self, "已安装", f"{vid} 已在本地。")
            return

        loader_type = self.opt_loader.currentData()
        loader_ver = self.opt_loader_ver.currentData() if loader_type != "none" else None

        # Step 1: 下载原版
        def dl_task(cb):
            version_manager.install_version(mc, vid, cb)

        d = ProgressDialog(f"下载 {vid}", dl_task, self)
        d.start()
        if not d.success:
            if d.error_msg:
                QMessageBox.critical(self, "下载失败", d.error_msg)
            return

        # Step 2: 安装用户选择的加载器版本
        if loader_type != "none" and loader_ver:
            names = {"forge": "Forge", "fabric": "Fabric", "quilt": "Quilt", "neoforge": "NeoForge"}
            name = names.get(loader_type, loader_type)
            self.inst_status.setText(f"正在安装 {name} {loader_ver}…")

            def loader_task(cb):
                if loader_type == "forge":
                    mod_manager.install_forge(mc, loader_ver, cb)
                elif loader_type == "fabric":
                    mod_manager.install_fabric(mc, vid, loader_ver, cb)
                elif loader_type == "quilt":
                    mod_manager.install_quilt(mc, vid, loader_ver, cb)
                elif loader_type == "neoforge":
                    mod_manager.install_neoforge(mc, loader_ver, cb)

            d2 = ProgressDialog(f"安装 {name} {loader_ver}", loader_task, self)
            d2.start()
            if not d2.success:
                QMessageBox.warning(
                    self, name,
                    f"{name} 安装失败: {d2.error_msg}\n原版 {vid} 已安装成功。"
                )

        self.inst_status.setText("安装完成!")
        self._refresh_installed()
        QMessageBox.information(self, "完成", f"{vid} 安装成功。")

    # ═══════════════════ 导入整合包 ═══════════════════

    def _import_modpack(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择整合包文件", "",
            "整合包 (*.mrpack *.zip);;Modrinth (*.mrpack);;ZIP (*.zip);;All (*)"
        )
        if not path:
            return

        fmt = modpack.detect_format(path)
        if fmt == "unknown":
            QMessageBox.warning(self, "无法识别", "不支持此文件格式。\n支持：.mrpack (Modrinth) / .zip (CurseForge/MultiMC/通用)")
            return

        info = modpack.get_info(path)
        fmt_names = {
            "mrpack": "Modrinth", "curseforge": "CurseForge",
            "mmc": "MultiMC/Prism", "generic": "通用 ZIP"
        }

        details = f"名称: {info['name']}\n"
        if info["version"]:
            details += f"版本: {info['version']}\n"
        if info["mc_version"]:
            details += f"MC 版本: {info['mc_version']}\n"
        if info["loader"]:
            details += f"加载器: {info['loader']}\n"
        details += f"Mod 数量: {info['mod_count']}\n"
        details += f"格式: {fmt_names.get(fmt, fmt)}\n"
        if info["summary"]:
            details += f"\n{info['summary']}"

        if fmt == "curseforge":
            details += "\n\n⚠ CurseForge 整合包：将安装 MC 版本并提取配置文件。\nMod 文件需通过 CurseForge 客户端补充下载。"

        reply = QMessageBox.question(
            self, "导入整合包", f"{details}\n\n确认导入？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        mc = self.config.get_minecraft_dir()
        pack_name = info["name"]

        # 先保存整合包名称映射（即使后续安装部分失败，名字也会保留）
        if pack_name:
            names = self.config.get("modpack_names", {})
            if info["mc_version"]:
                names[info["mc_version"]] = pack_name
            if fmt == "mrpack":
                try:
                    lv = minecraft_launcher_lib.mrpack.get_mrpack_launch_version(path)
                    if lv:
                        names[lv] = pack_name
                except Exception:
                    pass
            self.config.set("modpack_names", names)

        def task(cb):
            if fmt == "mrpack":
                modpack.install_mrpack(path, mc, cb)
            elif fmt == "curseforge":
                modpack.install_curseforge_zip(path, mc, cb)
            elif fmt == "mmc":
                modpack.install_mmc_zip(path, mc, cb)
            elif fmt == "generic":
                modpack.install_generic_zip(path, mc, cb)

        d = ProgressDialog(f"导入 {pack_name}", task, self)
        d.start()
        self._refresh_installed()
        if d.success:
            QMessageBox.information(self, "导入完成", f"整合包 {pack_name} 导入成功！")
        elif d.error_msg:
            QMessageBox.critical(self, "导入失败", d.error_msg)
