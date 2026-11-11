"""设置 — 一块可滚动玻璃板，字段都有可见标签。"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QSpinBox, QFileDialog, QMessageBox, QCheckBox, QComboBox, QListWidget,
    QListWidgetItem, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon

from core import java_utils
from ui.widgets.common import make_sheet, page_title, labeled_field
from ui.tokens import SPACE_XL, SPACE_LG, SPACE_MD, SPACE_SM, HIT_MIN


class SettingsPage(QWidget):
    def __init__(self, config, ctx=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.ctx = ctx
        # 测速 / 扫描各自独立持有线程引用，互不覆盖（覆盖会导致
        # "QThread: Destroyed while thread is still running" 直接 abort）
        self._speed_thread = None
        self._scan_thread = None
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        outer.setSpacing(SPACE_MD)
        outer.addWidget(page_title("设置", "Java、内存和游戏目录。改完请保存。"))

        sheet = make_sheet()
        sheet_l = QVBoxLayout(sheet)
        sheet_l.setContentsMargins(0, 0, 0, 0)
        sheet_l.setSpacing(0)

        # 滚动区必须整体透明：QScrollArea 的 viewport 默认用 Fusion 浅色
        # palette 铺底，深色主题下会露出浅灰白，无法阅读。
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("scrollArea")
        scroll.setAutoFillBackground(False)
        scroll.viewport().setAutoFillBackground(False)

        c = QWidget()
        c.setObjectName("scrollBody")
        c.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        c.setAutoFillBackground(False)
        lay = QVBoxLayout(c)
        lay.setContentsMargins(SPACE_LG, SPACE_LG, SPACE_LG, SPACE_LG)
        lay.setSpacing(SPACE_LG)

        lay.addWidget(self._sec("Java"))
        self.java_input = QLineEdit()
        self.java_input.setPlaceholderText("javaw.exe 的完整路径")
        self.java_input.setAccessibleName("Java 路径")
        row = QHBoxLayout()
        row.setSpacing(SPACE_SM)
        row.addWidget(self.java_input, 1)
        b1 = QPushButton("浏览")
        b1.setCursor(Qt.CursorShape.PointingHandCursor)
        b1.setFixedHeight(HIT_MIN)
        b1.clicked.connect(self._browse_java)
        b2 = QPushButton("检测")
        b2.setCursor(Qt.CursorShape.PointingHandCursor)
        b2.setFixedHeight(HIT_MIN)
        b2.clicked.connect(self._detect_java)
        row.addWidget(b1)
        row.addWidget(b2)
        wrap = QWidget()
        wrap.setLayout(row)
        lay.addWidget(labeled_field("Java 路径", wrap, "留空则启动时尝试自动检测。"))

        self.scan_btn = QPushButton("扫描本机 Java")
        self.scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scan_btn.setFixedHeight(HIT_MIN)
        self.scan_btn.clicked.connect(self._scan_java)
        lay.addWidget(self.scan_btn)
        self.java_list = QListWidget()
        self.java_list.setMaximumHeight(100)
        self.java_list.setAccessibleName("扫描到的 Java")
        self.java_list.itemDoubleClicked.connect(self._pick_java)
        self.java_list.hide()
        lay.addWidget(self.java_list)

        lay.addWidget(self._sec("内存与性能"))

        self.chk_auto_perf = QCheckBox("自动优化（根据系统配置自动分配内存和 JVM 参数）")
        self.chk_auto_perf.stateChanged.connect(self._on_auto_perf)
        lay.addWidget(self.chk_auto_perf)

        # 说明自动优化与手动内存的从属关系（配置语义不变，只补 UI 文案）
        self.auto_hint = QLabel("")
        self.auto_hint.setObjectName("mutedLabel")
        self.auto_hint.setWordWrap(True)
        lay.addWidget(self.auto_hint)

        self.perf_info = QLabel("")
        self.perf_info.setObjectName("statusLabel")
        self.perf_info.setWordWrap(True)
        lay.addWidget(self.perf_info)

        self.manual_ram_widget = QWidget()
        ram_lay = QVBoxLayout(self.manual_ram_widget)
        ram_lay.setContentsMargins(0, 0, 0, 0)
        ram_lay.setSpacing(SPACE_SM)
        manual_hint = QLabel("手动模式：自行设置内存范围")
        manual_hint.setObjectName("fieldLabel")
        ram_lay.addWidget(manual_hint)
        ram_row = QHBoxLayout()
        ram_row.setSpacing(SPACE_LG)
        self.ram_min = QSpinBox()
        self.ram_min.setRange(256, 32768)
        self.ram_min.setSingleStep(256)
        self.ram_min.setSuffix(" MB")
        self.ram_min.setFixedHeight(HIT_MIN)
        self.ram_min.setAccessibleName("最小内存")
        self.ram_max = QSpinBox()
        self.ram_max.setRange(512, 32768)
        self.ram_max.setSingleStep(256)
        self.ram_max.setSuffix(" MB")
        self.ram_max.setFixedHeight(HIT_MIN)
        self.ram_max.setAccessibleName("最大内存")
        ram_row.addWidget(labeled_field("最小", self.ram_min))
        ram_row.addWidget(labeled_field("最大", self.ram_max))
        ram_row.addStretch()
        ram_lay.addLayout(ram_row)
        lay.addWidget(self.manual_ram_widget)

        lay.addWidget(self._sec("JVM"))
        self.jvm_input = QLineEdit()
        self.jvm_input.setPlaceholderText("-XX:+UseG1GC")
        self.jvm_input.setAccessibleName("JVM 参数")
        lay.addWidget(labeled_field("附加参数", self.jvm_input, "会拼在内存参数后面。不懂可留空。"))

        lay.addWidget(self._sec("目录"))
        self.mc_input = QLineEdit()
        self.mc_input.setPlaceholderText(".minecraft 文件夹")
        self.mc_input.setAccessibleName("游戏目录")
        r4 = QHBoxLayout()
        r4.setSpacing(SPACE_SM)
        r4.addWidget(self.mc_input, 1)
        b4 = QPushButton("浏览")
        b4.setCursor(Qt.CursorShape.PointingHandCursor)
        b4.setFixedHeight(HIT_MIN)
        b4.clicked.connect(self._browse_mc)
        r4.addWidget(b4)
        wrap4 = QWidget()
        wrap4.setLayout(r4)
        lay.addWidget(labeled_field("游戏目录", wrap4))

        lay.addWidget(self._sec("本地皮肤 (需安装 CustomSkinLoader Mod)"))

        skin_row = QHBoxLayout()
        skin_row.setSpacing(8)
        self.skin_input = QLineEdit()
        self.skin_input.setPlaceholderText("皮肤 PNG 文件路径（留空不使用）")
        skin_row.addWidget(self.skin_input, 1)
        skin_browse = QPushButton("浏览")
        skin_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        skin_browse.setFixedHeight(HIT_MIN)
        skin_browse.clicked.connect(lambda: self._browse_png(self.skin_input))
        skin_row.addWidget(skin_browse)
        skin_wrap = QWidget()
        skin_wrap.setLayout(skin_row)
        lay.addWidget(labeled_field("皮肤文件", skin_wrap))

        cape_row = QHBoxLayout()
        cape_row.setSpacing(8)
        self.cape_input = QLineEdit()
        self.cape_input.setPlaceholderText("披风 PNG 文件路径（留空不使用）")
        cape_row.addWidget(self.cape_input, 1)
        cape_browse = QPushButton("浏览")
        cape_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        cape_browse.setFixedHeight(HIT_MIN)
        cape_browse.clicked.connect(lambda: self._browse_png(self.cape_input))
        cape_row.addWidget(cape_browse)
        cape_wrap = QWidget()
        cape_wrap.setLayout(cape_row)
        lay.addWidget(labeled_field("披风文件", cape_wrap))

        self.model_combo = QComboBox()
        self.model_combo.setFixedHeight(HIT_MIN)
        self.model_combo.addItem("Steve (标准手臂)", "default")
        self.model_combo.addItem("Alex (纤细手臂)", "slim")
        lay.addWidget(labeled_field("角色模型", self.model_combo))

        lay.addWidget(self._sec("行为"))
        self.chk_close = QCheckBox("启动游戏后关闭启动器")
        lay.addWidget(self.chk_close)

        lay.addWidget(self._sec("下载"))

        src_row = QHBoxLayout()
        src_row.setSpacing(8)
        self.source_combo = QComboBox()
        self.source_combo.setFixedHeight(36)
        from core.mirror import SOURCES
        self.source_combo.addItem("自动 (测速选最快)", "auto")
        for key, s in SOURCES.items():
            self.source_combo.addItem(s["name"], key)
        src_row.addWidget(self.source_combo, 1)

        self.speed_test_btn = QPushButton("测速")
        self.speed_test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.speed_test_btn.setFixedHeight(36)
        self.speed_test_btn.clicked.connect(self._run_speed_test)
        src_row.addWidget(self.speed_test_btn)

        src_wrap = QWidget()
        src_wrap.setLayout(src_row)

        self.speed_result = QLabel("")
        self.speed_result.setObjectName("statusLabel")
        self.speed_result.setWordWrap(True)

        src_field = labeled_field(
            "下载源",
            src_wrap,
            "「自动」会测速选最快源。镜像文件与官方完全一致，使用镜像是用户自愿选择。"
        )
        src_field.layout().addWidget(self.speed_result)
        lay.addWidget(src_field)

        lay.addWidget(self._sec("外观"))
        self.theme_combo = QComboBox()
        self.theme_combo.setFixedHeight(36)
        from ui.background import THEMES, random_swatch, theme_swatch
        self.theme_combo.addItem(QIcon(random_swatch(16)), "随机 (每次启动随机)", "random")
        for key, t in THEMES.items():
            if key == "mushroom":
                # 分组：前 6 套是 v0.5 就有的经典主题，后面是 v0.8 新增
                self.theme_combo.insertSeparator(self.theme_combo.count())
            self.theme_combo.addItem(QIcon(theme_swatch(key, 16)), t["name"], key)
        self.theme_combo.currentIndexChanged.connect(self._preview_theme)
        lay.addWidget(labeled_field(
            "背景主题", self.theme_combo, "点开即预览，保存后记住。共 14 套主题。"))

        # 界面语言：写 config["lang"]，由 main.py 启动时 set_lang 生效
        self.lang_combo = QComboBox()
        self.lang_combo.setFixedHeight(36)
        self.lang_combo.setAccessibleName("界面语言")
        self.lang_combo.addItem("中文", "zh")
        self.lang_combo.addItem("English", "en")
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        self.lang_hint = QLabel("")
        self.lang_hint.setObjectName("mutedLabel")
        self.lang_hint.setWordWrap(True)
        lang_field = labeled_field(
            "界面语言", self.lang_combo, "切换后重启启动器生效。")
        lang_field.layout().addWidget(self.lang_hint)
        lay.addWidget(lang_field)

        lay.addStretch()

        scroll.setWidget(c)
        sheet_l.addWidget(scroll, 1)

        foot = QHBoxLayout()
        foot.setContentsMargins(SPACE_LG, SPACE_SM, SPACE_LG, SPACE_LG)
        foot.addStretch()
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setObjectName("btnPrimary")
        self.save_btn.setFixedHeight(HIT_MIN + 2)
        self.save_btn.setMinimumWidth(120)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._save)
        foot.addWidget(self.save_btn)
        sheet_l.addLayout(foot)

        outer.addWidget(sheet, 1)

    def _on_lang_changed(self, _index=None):
        """选完立即落盘；文案不会热更新，提示重启生效。"""
        key = self.lang_combo.currentData() or "zh"
        try:
            self.config.set("lang", key)
        except Exception as e:
            self.lang_hint.setText(f"保存失败：{e}")
            return
        self.lang_hint.setText("已保存，重启启动器后界面语言生效。")

    def _preview_theme(self, _index=None):
        """切到哪个主题就先看哪个（只有保存才会写进配置）。"""
        key = self.theme_combo.currentData()
        if not key:
            return
        win = self.window()
        bg = getattr(win, "_bg", None)
        if bg is None:
            return
        if key == "random":
            import random as _random
            from ui.background import THEME_KEYS
            bg.set_theme(_random.choice(THEME_KEYS))
        else:
            bg.set_theme(key)

    def _run_speed_test(self):
        # 防重入：同名线程还在跑就不再起第二个
        if self._speed_thread is not None and self._speed_thread.isRunning():
            return
        self.speed_test_btn.setEnabled(False)
        self.speed_test_btn.setText("测速中…")
        self.speed_result.setText("正在并发测试所有下载源…")

        class T(QThread):
            done = pyqtSignal(list)
            def run(self):
                from core.mirror import test_all_sources
                self.done.emit(test_all_sources(timeout=5))

        self._speed_thread = T()
        self._speed_thread.done.connect(self._speed_done)
        self._speed_thread.finished.connect(self._on_speed_thread_finished)
        self._speed_thread.start()

    def _on_speed_thread_finished(self):
        """线程结束后才释放引用（运行中就丢引用会 abort 进程）。"""
        t = self._speed_thread
        if t is not None and not t.isRunning():
            self._speed_thread = None

    def _speed_done(self, results):
        self.speed_test_btn.setEnabled(True)
        self.speed_test_btn.setText("测速")
        from core.mirror import SOURCES
        lines = []
        for key, ms in results:
            name = SOURCES.get(key, {}).get("name", key)
            if ms > 0:
                lines.append(f"  {name}: {ms}ms ✓")
            else:
                lines.append(f"  {name}: 不可用 ✗")
        self.speed_result.setText("\n".join(lines))

    def _sec(self, t):
        l = QLabel(t)
        l.setObjectName("sectionLabel")
        return l

    def refresh(self):
        self.java_input.setText(self.config.get("java_path", ""))
        self.ram_min.setValue(self.config.get("ram_min", 512))
        self.ram_max.setValue(self.config.get("ram_max", 2048))
        self.jvm_input.setText(self.config.get("jvm_args", ""))
        self.mc_input.setText(self.config.get_minecraft_dir())
        self.chk_close.setChecked(self.config.get("close_on_launch", False))

        auto = self.config.get("auto_performance", True)
        self.chk_auto_perf.setChecked(auto)
        self.manual_ram_widget.setVisible(not auto)
        self._update_auto_hint(auto)
        if auto:
            from core.performance import get_system_info, get_optimization_summary
            info = get_system_info()
            self.perf_info.setText(get_optimization_summary(info, has_mods=True))

        self.skin_input.setText(self.config.get("local_skin_path", ""))
        self.cape_input.setText(self.config.get("local_cape_path", ""))
        model_idx = self.model_combo.findData(self.config.get("skin_model", "default"))
        if model_idx >= 0:
            self.model_combo.setCurrentIndex(model_idx)

        src = self.config.get("download_source", "auto")
        idx_src = self.source_combo.findData(src)
        if idx_src >= 0:
            self.source_combo.setCurrentIndex(idx_src)

        lang = self.config.get("lang", "zh") or "zh"
        idx_lang = self.lang_combo.findData(lang)
        if idx_lang >= 0:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx_lang)
            self.lang_combo.blockSignals(False)
        self.lang_hint.setText("")

        saved = self.config.get("theme", "random")
        idx = self.theme_combo.findData(saved)
        if idx >= 0:
            # 刷新时只回填选中值，不要触发预览（否则每次进设置页都换一次背景）
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)

    def _on_auto_perf(self, state):
        auto = state == Qt.CheckState.Checked.value
        self.manual_ram_widget.setVisible(not auto)
        self._update_auto_hint(auto)
        if auto:
            from core.performance import get_system_info, get_optimization_summary
            info = get_system_info()
            self.perf_info.setText(get_optimization_summary(info, has_mods=True))
        else:
            self.perf_info.setText("")

    def _update_auto_hint(self, auto: bool):
        """说明两种内存模式的关系，避免用户误以为手填值仍然生效。"""
        if auto:
            self.auto_hint.setText(
                "自动优化已开启：按本机内存自动分配内存与 JVM 参数，忽略下方手动内存值。"
            )
        else:
            self.auto_hint.setText(
                "自动优化已关闭：使用下方「手动模式」自行设置的最小 / 最大内存。"
            )

    def _browse_png(self, line_edit):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 PNG 文件", "", "PNG 图片 (*.png);;All (*)")
        if p:
            line_edit.setText(p)

    def _browse_java(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择 Java", "", "Java (javaw.exe java.exe);;All (*)")
        if p:
            self.java_input.setText(p)

    def _browse_mc(self):
        p = QFileDialog.getExistingDirectory(self, "选择 .minecraft")
        if p:
            self.mc_input.setText(p)

    def _detect_java(self):
        jp = java_utils.auto_detect_java()
        if jp:
            self.java_input.setText(jp)
            v = java_utils.get_java_version(jp) or "?"
            QMessageBox.information(self, "检测到", f"Java {v}\n{jp}")
        else:
            QMessageBox.warning(self, "未找到", "没有检测到 Java，请手动浏览 javaw.exe。")

    def _scan_java(self):
        # 防重入：扫描线程还在跑就直接返回
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("扫描中…")
        self.java_list.clear()
        self.java_list.show()

        class T(QThread):
            done = pyqtSignal(list)

            def run(self):
                self.done.emit(java_utils.find_java_in_common_locations())

        self._scan_thread = T()
        self._scan_thread.done.connect(self._scan_done)
        self._scan_thread.finished.connect(self._on_scan_thread_finished)
        self._scan_thread.start()

    def _on_scan_thread_finished(self):
        """线程结束后才释放引用。"""
        t = self._scan_thread
        if t is not None and not t.isRunning():
            self._scan_thread = None

    def _scan_done(self, js):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("扫描本机 Java")
        self.java_list.clear()
        for j in js:
            it = QListWidgetItem(f"Java {j['version']}  —  {j['path']}")
            it.setData(Qt.ItemDataRole.UserRole, j["path"])
            self.java_list.addItem(it)
        if not js:
            self.java_list.addItem("没有在常见目录找到 Java。")

    def _pick_java(self, item):
        p = item.data(Qt.ItemDataRole.UserRole)
        if p:
            self.java_input.setText(p)

    def _save(self):
        jp = self.java_input.text().strip()
        if jp and not java_utils.validate_java(jp):
            if QMessageBox.question(
                self, "Java 可能无效",
                f"这个路径看起来不是可用的 Java：\n{jp}\n仍然保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
        mn, mx = self.ram_min.value(), self.ram_max.value()
        if mn > mx:
            QMessageBox.warning(self, "无法保存", "最小内存不能大于最大内存。")
            self.ram_min.setFocus()
            return
        mc_dir = self.mc_input.text().strip()
        if not mc_dir:
            # 空目录会让后续所有路径拼成相对路径，必须拦住
            QMessageBox.warning(
                self, "无法保存",
                "游戏目录不能为空，请选择 .minecraft 文件夹。",
            )
            self.mc_input.setFocus()
            return
        if not os.path.isdir(mc_dir):
            if QMessageBox.question(
                self, "目录不存在",
                f"这个目录不存在：\n{mc_dir}\n仍然保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) != QMessageBox.StandardButton.Yes:
                return
        self.config.set("java_path", jp)
        self.config.set("ram_min", mn)
        self.config.set("ram_max", mx)
        self.config.set("jvm_args", self.jvm_input.text().strip())
        self.config.set("minecraft_directory", mc_dir)
        self.config.set("close_on_launch", self.chk_close.isChecked())
        self.config.set("auto_performance", self.chk_auto_perf.isChecked())
        self.config.set("local_skin_path", self.skin_input.text().strip())
        self.config.set("local_cape_path", self.cape_input.text().strip())
        self.config.set("skin_model", self.model_combo.currentData() or "default")

        source_key = self.source_combo.currentData() or "auto"
        self.config.set("download_source", source_key)
        from core import mirror
        if source_key == "auto":
            mirror.activate_auto()
        else:
            mirror.activate(source_key)

        self.config.set("lang", self.lang_combo.currentData() or "zh")

        theme_key = self.theme_combo.currentData() or "random"
        self.config.set("theme", theme_key)
        win = self.window()
        if hasattr(win, "_bg"):
            if theme_key == "random":
                win._bg.set_random_theme()
            else:
                win._bg.set_theme(theme_key)

        self.save_btn.setText("已保存")
        QTimer.singleShot(1500, lambda: self.save_btn.setText("保存设置"))
        QMessageBox.information(self, "完成", "设置已保存。")
