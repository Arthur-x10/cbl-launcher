"""合成台 —— 把「基础版本 + 主加载器 + 补丁」当材料放进槽位，右边出成品。

为什么不是下拉框：
    原来的安装面板是「不安装加载器 / Forge / Fabric / …」单选下拉，一次只能说一件事。
    真实需求是「1.12.2 + Forge + LiteLoader + OptiFine」这种多材料组合，而且有些材料
    天生不能同框。下拉框表达不了「互斥」这个概念 —— 你选了 Forge，Fabric 就消失了，
    用户不知道是被隐藏还是根本不存在。

    合成台把这件事摆到台面上：所有材料都看得见，放不进去的会让成品格变红并说明原因。

三种槽位（规则数据来自 core.providers.java.combos，UI 不写死任何一条）
    primary  主加载器，四选一：Forge / NeoForge / Fabric / Quilt
    addon    附加层：LiteLoader（已停更，本启动器只认不装）
    patch    渲染补丁：OptiFine（选本地 jar，装完塞进 mods/）

只读模式给实例详情页用：同一个组件，不许点，只显示这个实例是用什么材料合成的。
"""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLayout, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from core.providers.java import combos
from ui.tokens import (
    HIT_MIN, MC_AQUA, MC_DARK_GRAY, MC_GOLD, MC_GRAY, MC_GREEN, MC_RED,
    SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XS,
)

_SLOT_W = 108
_SLOT_H = 56

_EMBOSS_DARK = "#1A172A"
_EMBOSS_LIGHT = "#3A3748"


def _slot_qss() -> str:
    return (
        "QPushButton {"
        " background-color: rgba(0, 0, 0, 0.34);"
        " color: " + MC_GRAY + ";"
        " border-top: 3px solid " + _EMBOSS_DARK + ";"
        " border-left: 3px solid " + _EMBOSS_DARK + ";"
        " border-bottom: 3px solid " + _EMBOSS_LIGHT + ";"
        " border-right: 3px solid " + _EMBOSS_LIGHT + ";"
        " border-radius: 0;"
        " font-weight: 700;"
        " font-size: 12px;"
        " padding: 2px;"
        "}"
        "QPushButton:hover { color: " + MC_GREEN + ";"
        " background-color: rgba(85, 255, 85, 0.10); }"
        "QPushButton[ro=\"true\"]:hover { color: " + MC_GRAY + ";"
        " background-color: rgba(0, 0, 0, 0.34); }"
        "QPushButton:checked {"
        " background-color: rgba(85, 255, 85, 0.16);"
        " color: " + MC_GREEN + ";"
        " border-top: 3px solid #2A6A1A;"
        " border-left: 3px solid #2A6A1A;"
        " border-bottom: 3px solid " + MC_GREEN + ";"
        " border-right: 3px solid " + MC_GREEN + ";"
        "}"
        "QPushButton:disabled { color: #4A4A5A;"
        " background-color: rgba(0, 0, 0, 0.52); }"
        "QPushButton:disabled:hover { color: #4A4A5A;"
        " background-color: rgba(0, 0, 0, 0.52); }"
    )


def _result_qss(ok: bool) -> str:
    edge = MC_GREEN if ok else MC_RED
    return ("QFrame { background-color: rgba(0, 0, 0, 0.38); border: 2px solid "
            + edge + "; border-radius: 0; }")


# ═══════════════════ 单个槽位 ═══════════════════

class LoaderSlot(QFrame):
    """一个材料格：方块按钮。版本选择在合成台下方的材料清单里。"""

    toggled = pyqtSignal(str, bool)

    def __init__(self, loader, read_only: bool = False, parent=None):
        super().__init__(parent)
        self.loader = loader
        self.read_only = read_only
        self._state = "ok"      # ok / manual / na
        self._version = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.btn = QPushButton()
        # 只读模式下也必须 checkable：Qt 对不可 check 的按钮会**静默忽略** setChecked(True)，
        # 那样实例详情页摆进来的材料全变成"没选中"，只读合成台永远是"原版"。
        # 只读的"不许改"靠 _on_click 里直接 return 实现，不靠禁用按钮。
        self.btn.setCheckable(True)
        if read_only:
            self.btn.setProperty("ro", "true")
            self.btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.btn.setFixedSize(_SLOT_W, _SLOT_H)
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setStyleSheet(_slot_qss())
        self.btn.setAccessibleName(loader.name)
        self.btn.clicked.connect(self._on_click)
        lay.addWidget(self.btn)
        self._repaint()

    def _repaint(self) -> None:
        if self._version:
            short = self._version if len(self._version) <= 14 else self._version[:13] + "…"
            self.btn.setText(self.loader.name + "\n" + short)
        elif self._state == "manual":
            self.btn.setText(self.loader.name + "\n🔒 需手动")
        elif self._state == "na":
            self.btn.setText(self.loader.name + "\n✖ 不适用")
        else:
            self.btn.setText(self.loader.name + "\n＋ 加入")

    def set_state(self, state: str, reason: str = "") -> None:
        """ok=可装 / manual=本启动器不代装（能选，但会给出警告）/ na=当前版本没有。

        三种都可以点：让用户放进去再看到红色原因，比让按钮变灰需要猜要有用得多。
        """
        self._state = state
        self.btn.setToolTip(reason)
        self._repaint()

    def set_version(self, text: str) -> None:
        self._version = str(text or "")
        self._repaint()

    def version(self) -> str:
        return self._version

    def is_active(self) -> bool:
        return self.btn.isChecked()

    def set_active(self, on: bool) -> None:
        self.btn.blockSignals(True)
        self.btn.setChecked(bool(on))
        self.btn.blockSignals(False)

    def _on_click(self) -> None:
        if self.read_only:
            # QPushButton 是先翻转 checked 再发 clicked 的，只 return 不够，得拨回去
            self.btn.setChecked(bool(self._version))
            return
        self.toggled.emit(self.loader.id, self.btn.isChecked())


# ═══════════════════ 合成台 ═══════════════════

class CraftingBench(QWidget):
    """槽位 + 材料清单 + 成品格 + 规则提示。所有判断都委托给 combos 模块。"""

    changed = pyqtSignal()
    needOptions = pyqtSignal(str)     # 需要某个 mc 版本的加载器版本表

    def __init__(self, read_only: bool = False, parent=None):
        super().__init__(parent)
        self.read_only = read_only
        self.mc_version = ""
        self._slots: dict[str, LoaderSlot] = {}
        self._combos: dict[str, QComboBox] = {}
        self._options: dict = {}
        self._optifine_path = ""
        self._requested = ""
        self._busy = False
        self._pinning = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(SPACE_SM)
        # 布局比分配到的空间高时，Qt 不会裁剪子控件 —— 它会画到框外压住上面的列表。
        # 这条约束让合成台永远不少于自己要的高度。
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        bench = QHBoxLayout()
        bench.setSpacing(SPACE_LG)

        # ── 左：材料格（2 行：主加载器 / 附加） ──
        grid_wrap = QWidget()
        grid = QGridLayout(grid_wrap)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(SPACE_SM)
        grid.setVerticalSpacing(SPACE_SM)

        # 3 列 × 2 行的合成格：横向铺开，竖向省高度（安装面板下面还有版本列表要地方）
        every = (combos.loaders_of(combos.PRIMARY)
                 + combos.loaders_of(combos.ADDON)
                 + combos.loaders_of(combos.PATCH))
        for i, loader in enumerate(every):
            slot = LoaderSlot(loader, read_only)
            slot.toggled.connect(self._on_toggled)
            self._slots[loader.id] = slot
            grid.addWidget(slot, i // 3, i % 3)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(0)
        left.addWidget(grid_wrap, 0, Qt.AlignmentFlag.AlignTop)
        left.addStretch(1)
        bench.addLayout(left, 0)

        arrow = QLabel("▶")
        arrow.setStyleSheet("color: " + MC_GOLD + "; font-size: 20px; font-weight: 700;")
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setFixedHeight(_SLOT_H)
        arrow_box = QVBoxLayout()
        arrow_box.setContentsMargins(0, 0, 0, 0)
        arrow_box.addWidget(arrow, 0, Qt.AlignmentFlag.AlignTop)
        arrow_box.addStretch(1)
        bench.addLayout(arrow_box, 0)

        # ── 右：成品格 ──
        self.result_frame = QFrame()
        self.result_frame.setStyleSheet(_result_qss(True))
        self.result_frame.setMinimumWidth(216)
        rf = QVBoxLayout(self.result_frame)
        rf.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        rf.setSpacing(SPACE_XS)

        cap = QLabel("成品")
        cap.setStyleSheet("color: " + MC_DARK_GRAY + "; font-size: 11px; font-weight: 700;")
        rf.addWidget(cap)

        self.result_label = QLabel("")
        self.result_label.setStyleSheet(
            "color: " + MC_GRAY + "; font-size: 15px; font-weight: 700;")
        self.result_label.setWordWrap(True)
        rf.addWidget(self.result_label)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: " + MC_DARK_GRAY + "; font-size: 11px;")
        self.detail_label.setWordWrap(True)
        rf.addWidget(self.detail_label)

        self.name_edit = QLineEdit()
        self.name_edit.setFixedHeight(HIT_MIN)
        self.name_edit.setAccessibleName("实例名")
        self.name_edit.setVisible(not read_only)
        rf.addWidget(self.name_edit)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addWidget(self.result_frame, 0, Qt.AlignmentFlag.AlignTop)
        right.addStretch(1)
        bench.addLayout(right, 1)

        root.addLayout(bench)

        # ── 下：材料清单（每个激活的槽一行，选版本） ──
        self.mat_box = QWidget()
        self.mat_lay = QVBoxLayout(self.mat_box)
        self.mat_lay.setContentsMargins(0, 0, 0, 0)
        self.mat_lay.setSpacing(SPACE_XS)
        root.addWidget(self.mat_box)

        # ── 最下：规则提示 ──
        self.issue_box = QWidget()
        self.issue_lay = QVBoxLayout(self.issue_box)
        self.issue_lay.setContentsMargins(0, 0, 0, 0)
        self.issue_lay.setSpacing(2)
        root.addWidget(self.issue_box)
        self._issue_labels: list[QLabel] = []
        self._mat_rows: list[QWidget] = []

        self._refresh()

    # ── 外部接口 ──
    def set_version(self, mc_version: str, force: bool = False) -> None:
        mc_version = (mc_version or "").strip()
        if mc_version == self.mc_version and not force:
            return
        self.mc_version = mc_version
        self._requested = ""
        self._options = {}
        for slot in self._slots.values():
            slot.set_active(False)
            slot.set_version("")
        self._refresh()
        self._maybe_request()

    def apply_options(self, mc_version: str, options: dict) -> None:
        if (mc_version or "").strip() != self.mc_version:
            return   # 迟到的结果，丢掉
        self._options = options if isinstance(options, dict) else {}
        self._rebuild_materials()
        self._refresh()

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._refresh()

    def set_read_only_state(self, mc_version: str, chosen: dict) -> None:
        """实例详情页用：把已有实例的材料摆进来，不给动。"""
        self.set_version(mc_version, force=True)
        for lid, slot in self._slots.items():
            ver = str((chosen or {}).get(lid) or "")
            slot.set_version(ver)
            slot.set_active(bool(ver))
        self._rebuild_materials()
        self._refresh()

    def active_materials(self) -> list:
        """格子里的材料，按 主加载器 → 附加 → 补丁 的顺序。"""
        out = []
        for kind in (combos.PRIMARY, combos.ADDON, combos.PATCH):
            for loader in combos.loaders_of(kind):
                slot = self._slots.get(loader.id)
                if slot is not None and slot.is_active():
                    out.append(loader.id)
        return out

    def chosen(self) -> dict:
        """材料 → 版本号。版本号可能是空串（LiteLoader 不代装、或版本表还没回来）。"""
        return {lid: self._slots[lid].version() for lid in self.active_materials()}

    def issues(self):
        issues = list(combos.check_combo(self.mc_version, self.chosen()))
        for lid in self.manual_only():
            issues.append(combos.Issue(
                combos.WARN,
                f"{combos.LOADER_BY_ID[lid].name} 不会自动安装",
                "本启动器只做兼容性判断；装完这个版本后请按 LiteLoader 官方说明手动加进去",
                "https://www.mcmod.cn/class/610.html", True, (lid,)))
        return issues

    def manual_only(self) -> list:
        """选中了、但本启动器不负责下载安装的材料。"""
        return [lid for lid, slot in self._slots.items()
                if slot.is_active() and lid == "liteloader"]

    def can_compose(self) -> bool:
        if self.read_only:
            return True
        if not self.mc_version:
            return False
        if not any(slot.is_active() for slot in self._slots.values()):
            return True   # 纯原版也是一个合法成品
        if not combos.can_install(self.issues()):
            return False
        # 选了主加载器但版本还没拿到，不算合成成功
        for loader in combos.loaders_of(combos.PRIMARY):
            if self._slots[loader.id].is_active() and not self._slots[loader.id].version():
                return False
        if self._slots["optifine"].is_active() and not self._optifine_path:
            return False
        return True

    def instance_name(self) -> str:
        text = self.name_edit.text().strip()
        if text:
            return text
        return _composite_name(self.mc_version, self.active_materials())

    def optifine_jar(self) -> str:
        return self._optifine_path

    def install_plan(self) -> dict:
        """交给 _do_install 的成品配方。"""
        chosen = self.chosen()
        loader = ""
        loader_version = ""
        for l in combos.loaders_of(combos.PRIMARY):
            if chosen.get(l.id):
                loader, loader_version = l.id, chosen[l.id]
                break
        return {
            "loader": loader,
            "loader_version": loader_version,
            "extra_jars": [self._optifine_path] if self._optifine_path else [],
            "manual": self.manual_only(),
            "name": self.instance_name(),
        }

    # ── 内部 ──
    def _maybe_request(self) -> None:
        if self.read_only or not self.mc_version:
            return
        if self._requested == self.mc_version:
            return
        self._requested = self.mc_version
        self.needOptions.emit(self.mc_version)

    def _on_toggled(self, loader_id: str, checked: bool) -> None:
        if checked and combos.LOADER_BY_ID[loader_id].kind == combos.PRIMARY:
            for other_id, other in self._slots.items():
                if other_id != loader_id and combos.LOADER_BY_ID[other_id].kind == combos.PRIMARY:
                    other.set_active(False)
                    other.set_version("")
        if not checked:
            self._slots[loader_id].set_version("")
            if loader_id == "optifine":
                self._optifine_path = ""
        self._rebuild_materials()
        self._refresh()
        self._maybe_request()
        self.changed.emit()

    def _clear_layout(self, lay, store) -> None:
        for w in store:
            w.setParent(None)
            w.deleteLater()
        store.clear()

    def _rebuild_materials(self) -> None:
        self._clear_layout(self.mat_lay, self._mat_rows)
        self._combos.clear()
        if self.read_only:
            return
        for lid, slot in self._slots.items():
            if not slot.is_active() or lid == "liteloader":
                continue
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(SPACE_SM)

            tag = QLabel(combos.LOADER_BY_ID[lid].name + " 版本")
            tag.setStyleSheet("color: " + MC_GRAY + "; font-size: 12px;")
            tag.setFixedWidth(96)
            hl.addWidget(tag)

            if lid == "optifine":
                label = (self._optifine_path.rsplit("\\", 1)[-1]
                         if self._optifine_path else "选择 OptiFine 的 jar…")
                btn = QPushButton(label)
                btn.setFixedHeight(HIT_MIN)
                btn.setStyleSheet("text-align: left; padding-left: 8px;")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                if self._optifine_path:
                    btn.setToolTip(self._optifine_path + "（点击更换）")
                btn.setFixedWidth(340)
                btn.clicked.connect(lambda _c=False, l=lid: self._pick_jar(l))
                hl.addWidget(btn, 0)
                hl.addStretch(1)
            else:
                combo = QComboBox()
                combo.setFixedHeight(HIT_MIN)
                combo.setFixedWidth(260)
                combo.setAccessibleName(combos.LOADER_BY_ID[lid].name + " 版本")
                versions = self._options.get(lid) if isinstance(self._options, dict) else None
                if isinstance(versions, list) and versions:
                    for v in versions:
                        combo.addItem(str(v), str(v))
                else:
                    combo.addItem("正在取版本列表…", "")
                combo.currentIndexChanged.connect(
                    lambda _i, l=lid, c=combo: self._on_version(l, c))
                hl.addWidget(combo, 0)
                hl.addStretch(1)
                self._combos[lid] = combo
                if slot.version():
                    idx = combo.findData(slot.version())
                    if idx >= 0:
                        combo.blockSignals(True)
                        combo.setCurrentIndex(idx)
                        combo.blockSignals(False)
                    else:
                        combo.blockSignals(True)
                        combo.insertItem(0, slot.version(), slot.version())
                        combo.setCurrentIndex(0)
                        combo.blockSignals(False)
                elif combo.currentData():
                    slot.set_version(str(combo.currentData()))
            self.mat_lay.addWidget(row)
            self._mat_rows.append(row)
            row.setFixedHeight(HIT_MIN)

    def _on_version(self, lid: str, combo: QComboBox) -> None:
        self._slots[lid].set_version(str(combo.currentData() or ""))
        self._refresh()
        self.changed.emit()

    def _pick_jar(self, lid: str) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 " + combos.LOADER_BY_ID[lid].name + " 的 jar", "", "Java 模组 (*.jar)")
        if not path:
            return
        self._optifine_path = path
        self._slots[lid].set_version(combos.tag_from_optifine_jar(path))
        self._rebuild_materials()
        self._refresh()
        self.changed.emit()

    def _refresh(self) -> None:
        chosen = self.chosen()

        # 自身可用性：只有 LiteLoader 真禁用；版本不支持的槽仍可点，点了会变红说明原因
        for lid, slot in self._slots.items():
            if lid == "liteloader":
                slot.set_state(
                    "manual", "LiteLoader 已停更（最后支持 1.12.2），本启动器只做兼容性提示、不自动安装")
                continue
            if not self.mc_version:
                slot.set_state("ok", "")
                continue
            ok, why = combos.availability(lid, self.mc_version)
            slot.set_state("ok" if ok else "na", why or "")

        issues = combos.check_combo(self.mc_version, chosen) if self.mc_version else []
        blocked = combos.blocking_issues(issues)

        active = self.active_materials()
        if blocked:
            text = "✖ 无法合成"
        else:
            text = _composite_name(self.mc_version, active)
        color = MC_RED if blocked else (MC_GREEN if active else MC_GRAY)
        self.result_label.setText(text)
        self.result_label.setStyleSheet(
            "color: " + color + "; font-size: 15px; font-weight: 700;")
        self.result_frame.setStyleSheet(_result_qss(not blocked))

        bits = []
        if self.mc_version:
            bits.append("基础 " + self.mc_version)
        if self._busy:
            bits.append("正在安装…")
        if not self.read_only and not self.name_edit.text().strip():
            self.name_edit.setPlaceholderText(self.instance_name())
        self.detail_label.setText(" · ".join(bits))

        self._render_issues(issues)
        # 把钉高度推迟到本轮事件循环之后：刚 new 出来的 QComboBox 还没 polish，
        # 立刻算 sizeHint 会少算一行，于是材料行被挤没。
        QTimer.singleShot(0, self._pin_height)

    def _pin_height(self) -> None:
        """把高度钉死成内容需要的高度。

        不加这句会出事：安装面板的 QVBoxLayout 分给合成台的高度由 sizeHint 猜，
        猜小了 Qt 不会裁剪子控件，而是把材料行画到框外面去 —— 表现就是
        「选了 Forge，但选版本的下拉框看不见」。
        """
        if self._pinning:
            return
        self._pinning = True
        try:
            lay = self.layout()
            if lay is None:
                return
            lay.activate()
            need = lay.totalSizeHint().height()
            if need > 0 and need != self.height():
                self.setFixedHeight(need)
                self.updateGeometry()
                # 定完高度再让它自己摆一次，避免子控件还是旧几何
                lay.activate()
        finally:
            self._pinning = False

    def _render_issues(self, issues) -> None:
        self._clear_layout(self.issue_lay, self._issue_labels)
        for issue in issues or []:
            mark = {"blocked": "✖", "warn": "⚠", "note": "·"}.get(issue.level, "·")
            color = {"blocked": MC_RED, "warn": MC_GOLD, "note": MC_AQUA}.get(issue.level, MC_GRAY)
            text = mark + " " + issue.reason
            if issue.hint:
                text += " —— " + issue.hint
            if not issue.verified:
                text += "（推论，未见官方明文）"
            lab = QLabel(text)
            lab.setWordWrap(True)
            lab.setStyleSheet("color: " + color + "; font-size: 11px;")
            if issue.source:
                lab.setToolTip("出处：" + issue.source)
            self.issue_lay.addWidget(lab)
            self._issue_labels.append(lab)


def _composite_name(mc_version: str, active_ids) -> str:
    """成品名：版本 + 材料名（技术版本号留给下面的材料清单）。"""
    names = [combos.LOADER_BY_ID[i].name for i in (active_ids or [])
             if i in combos.LOADER_BY_ID]
    head = mc_version or "原版"
    return head + (" · " + " + ".join(names) if names else " · 原版")
