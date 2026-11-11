"""加载器 — 一块玻璃板，Forge / Fabric 左右分栏。"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core import mod_manager, version_manager
from ui.widgets.progress_dialog import ProgressDialog
from ui.widgets.common import make_sheet, page_title, labeled_field, vline
from ui.tokens import SPACE_XL, SPACE_LG, SPACE_MD, SPACE_SM, HIT_MIN


class ModsPage(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        root.setSpacing(SPACE_MD)
        root.addWidget(page_title(
            "加载器",
            "给已安装的原版加上 Forge 或 Fabric。请先在「版本」里下载对应原版。",
        ))

        sheet = make_sheet()
        body = QHBoxLayout(sheet)
        body.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        body.setSpacing(SPACE_LG)
        body.addLayout(self._forge_col(), 1)
        body.addWidget(vline())
        body.addLayout(self._fabric_col(), 1)
        root.addWidget(sheet, 1)

    def _forge_col(self):
        fl = QVBoxLayout()
        fl.setSpacing(SPACE_MD)
        fl.addWidget(self._sec("Forge"))

        self.forge_mc = QComboBox()
        self.forge_mc.setAccessibleName("Forge 对应的 MC 版本")
        self.forge_mc.currentTextChanged.connect(lambda _: self.forge_ver.clear())
        fl.addWidget(labeled_field("Minecraft 版本", self.forge_mc))

        self.forge_ver = QComboBox()
        self.forge_ver.setAccessibleName("Forge 版本")
        row = QHBoxLayout()
        row.setSpacing(SPACE_SM)
        row.addWidget(self.forge_ver, 1)
        self.forge_q = QPushButton("查询")
        self.forge_q.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forge_q.setFixedHeight(HIT_MIN)
        self.forge_q.clicked.connect(self._q_forge)
        row.addWidget(self.forge_q)
        wrap = QWidget()
        wrap.setLayout(row)
        fl.addWidget(labeled_field("Forge 版本", wrap, "点查询后才会列出。推荐项会标出来。"))

        fl.addStretch()
        self.forge_st = QLabel("")
        self.forge_st.setObjectName("statusLabel")
        fl.addWidget(self.forge_st)
        self.forge_inst = QPushButton("安装 Forge")
        self.forge_inst.setObjectName("btnPrimary")
        self.forge_inst.setCursor(Qt.CursorShape.PointingHandCursor)
        self.forge_inst.setFixedHeight(HIT_MIN)
        self.forge_inst.clicked.connect(self._inst_forge)
        fl.addWidget(self.forge_inst)
        return fl

    def _fabric_col(self):
        al = QVBoxLayout()
        al.setSpacing(SPACE_MD)
        al.addWidget(self._sec("Fabric"))

        self.fab_mc = QComboBox()
        self.fab_mc.setAccessibleName("Fabric 对应的 MC 版本")
        al.addWidget(labeled_field("Minecraft 版本", self.fab_mc))

        self.fab_loader = QComboBox()
        self.fab_loader.setAccessibleName("Fabric Loader")
        row = QHBoxLayout()
        row.setSpacing(SPACE_SM)
        row.addWidget(self.fab_loader, 1)
        self.fab_q = QPushButton("查询")
        self.fab_q.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fab_q.setFixedHeight(HIT_MIN)
        self.fab_q.clicked.connect(self._q_fabric)
        row.addWidget(self.fab_q)
        wrap = QWidget()
        wrap.setLayout(row)
        al.addWidget(labeled_field("Loader 版本", wrap))

        al.addStretch()
        self.fab_st = QLabel("")
        self.fab_st.setObjectName("statusLabel")
        al.addWidget(self.fab_st)
        self.fab_inst = QPushButton("安装 Fabric")
        self.fab_inst.setObjectName("btnPrimary")
        self.fab_inst.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fab_inst.setFixedHeight(HIT_MIN)
        self.fab_inst.clicked.connect(self._inst_fabric)
        al.addWidget(self.fab_inst)
        return al

    def _sec(self, t):
        l = QLabel(t)
        l.setObjectName("sectionLabel")
        return l

    def refresh(self):
        mc = self.config.get_minecraft_dir()
        vanilla = [
            v["id"] for v in version_manager.get_installed_versions(mc)
            if not any(t in v["id"].lower() for t in ("forge", "fabric", "quilt"))
        ]
        self.forge_mc.clear()
        self.fab_mc.clear()
        if vanilla:
            self.forge_mc.addItems(vanilla)
            self.fab_mc.addItems(vanilla)
        else:
            self.forge_st.setText("没有可用的原版，请先去「版本」下载。")
            self.fab_st.setText("没有可用的原版，请先去「版本」下载。")

    def _q_forge(self):
        mc = self.forge_mc.currentText()
        if not mc:
            QMessageBox.warning(self, "提示", "请先安装一个原版 Minecraft。")
            return
        self.forge_q.setEnabled(False)
        self.forge_q.setText("查询中")
        self.forge_st.setText("正在查询 Forge 版本…")

        class T(QThread):
            done = pyqtSignal(list, str)

            def __init__(s, v):
                super().__init__()
                s.v = v

            def run(s):
                rec = mod_manager.find_forge_version(s.v)
                vs = mod_manager.get_forge_versions(s.v)
                if rec and rec in vs:
                    vs.remove(rec)
                    vs.insert(0, rec)
                s.done.emit(vs, rec or "")

        self._ft = T(mc)
        self._ft.done.connect(self._forge_loaded)
        self._ft.start()

    def _forge_loaded(self, vs, rec):
        self.forge_q.setEnabled(True)
        self.forge_q.setText("查询")
        self.forge_ver.clear()
        for v in vs:
            tag = "（推荐）" if v == rec else ""
            self.forge_ver.addItem(f"{v}{tag}", v)
        self.forge_st.setText(f"{len(vs)} 个版本" if vs else "这个 MC 版本没有可用 Forge。")

    def _inst_forge(self):
        if not self.forge_ver.count():
            QMessageBox.warning(self, "提示", "请先查询 Forge 版本。")
            return
        fv = self.forge_ver.currentData() or self.forge_ver.currentText().replace("（推荐）", "")
        mc = self.config.get_minecraft_dir()
        if QMessageBox.question(
            self, "确认", f"安装 Forge {fv}？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def task(cb):
            mod_manager.install_forge(mc, fv, cb)

        d = ProgressDialog(f"安装 Forge {fv}", task, self)
        d.start()
        self.forge_st.setText("安装成功" if d.success else "安装失败")
        if d.success:
            QMessageBox.information(self, "完成", f"Forge {fv} 安装成功。")
        elif d.error_msg:
            QMessageBox.critical(self, "失败", d.error_msg)

    def _q_fabric(self):
        if not self.fab_mc.currentText():
            QMessageBox.warning(self, "提示", "请先安装一个原版 Minecraft。")
            return
        self.fab_q.setEnabled(False)
        self.fab_q.setText("查询中")
        self.fab_st.setText("正在查询 Fabric Loader…")

        class T(QThread):
            done = pyqtSignal(list)

            def run(s):
                s.done.emit(mod_manager.get_fabric_versions())

        self._at = T()
        self._at.done.connect(self._fab_loaded)
        self._at.start()

    def _fab_loaded(self, ls):
        self.fab_q.setEnabled(True)
        self.fab_q.setText("查询")
        self.fab_loader.clear()
        for l in ls[:20]:
            st = "（稳定）" if l.get("stable") else ""
            v = l.get("version", "")
            self.fab_loader.addItem(f"{v}{st}", v)
        self.fab_st.setText(f"{len(ls)} 个版本" if ls else "没有可用 Loader。")

    def _inst_fabric(self):
        mc_ver = self.fab_mc.currentText()
        if not mc_ver:
            QMessageBox.warning(self, "提示", "请先安装一个原版 Minecraft。")
            return
        lv = self.fab_loader.currentData()
        if not lv:
            QMessageBox.warning(self, "提示", "请先查询 Loader 版本。")
            return
        mc = self.config.get_minecraft_dir()
        if QMessageBox.question(
            self, "确认", f"为 {mc_ver} 安装 Fabric？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return

        def task(cb):
            mod_manager.install_fabric(mc, mc_ver, lv, cb)

        d = ProgressDialog(f"安装 Fabric（{mc_ver}）", task, self)
        d.start()
        self.fab_st.setText("安装成功" if d.success else "安装失败")
        if d.success:
            QMessageBox.information(self, "完成", "Fabric 安装成功。")
        elif d.error_msg:
            QMessageBox.critical(self, "失败", d.error_msg)
