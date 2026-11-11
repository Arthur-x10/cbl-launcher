"""
CBL Cube Launcher — Minecraft 主题样式
风格: MC 经典 UI 浮雕按钮 + 深色面板 + §a绿主色 + 方角像素风
"""

MAIN_STYLE = """

/* ═══════════════════ 全局 ═══════════════════ */
QWidget {
    color: #FFFFFF;
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow {
    background: transparent;
}

/* Minecraft 经典紫色 Tooltip */
QToolTip {
    background-color: #100010;
    color: #FFFFFF;
    border: 1px solid #5000AA;
    border-radius: 0;
    padding: 4px 8px;
}


/* ═══════════════════ 顶部条 ═══════════════════ */
#topStrip {
    background-color: rgba(0, 0, 0, 0.30);
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

#brandTitle {
    color: #55FF55;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 1px;
}

#brandSub {
    color: #555555;
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 3px;
}

#topUser {
    color: #AAAAAA;
    font-size: 12px;
    font-weight: 600;
}

#topAuth {
    color: #8888AA;
    font-size: 11px;
}

#logoutBtn {
    background-color: #3A2020;
    color: #FF5555;
    border-top: 1px solid #5A3030;
    border-left: 1px solid #5A3030;
    border-bottom: 1px solid #2A1010;
    border-right: 1px solid #2A1010;
    border-radius: 0;
    padding: 3px 10px;
    font-size: 11px;
}
#logoutBtn:hover {
    background-color: #4A2828;
    border-top-color: #6A3838;
    border-left-color: #6A3838;
}


/* ═══════════════════ 窗口控件（关闭/最小/最大化） ═══════════════════ */
#winClose, #winMin, #winMax {
    background-color: #3A3A4A;
    color: #AAAAAA;
    border-top: 1px solid #5A5A6A;
    border-left: 1px solid #5A5A6A;
    border-bottom: 1px solid #2A2A3A;
    border-right: 1px solid #2A2A3A;
    border-radius: 0;
    font-size: 13px;
    padding: 0;
}
#winMin:hover, #winMax:hover {
    background-color: #4A4A5A;
    color: #FFFF55;
    border-top-color: #6A6A7A;
    border-left-color: #6A6A7A;
}
#winClose:hover {
    background-color: #6A2020;
    color: #FF5555;
    border-top-color: #8A3030;
    border-left-color: #8A3030;
}
#winClose:pressed, #winMin:pressed, #winMax:pressed {
    border-top: 1px solid #2A2A3A;
    border-left: 1px solid #2A2A3A;
    border-bottom: 1px solid #5A5A6A;
    border-right: 1px solid #5A5A6A;
    background-color: #2A2A3A;
}


/* ═══════════════════ 底部导航栏 ═══════════════════ */
#navBar {
    background-color: rgba(0, 0, 0, 0.45);
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}

#navTab {
    background-color: #606078;
    color: #FFFFFF;
    border-top: 2px solid #8888A0;
    border-left: 2px solid #8888A0;
    border-bottom: 2px solid #303048;
    border-right: 2px solid #303048;
    border-radius: 0;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: 600;
}
#navTab:hover {
    background-color: #707088;
    color: #FFFF55;
    border-top-color: #9898B0;
    border-left-color: #9898B0;
}
#navTab[active="true"] {
    background-color: #2E6A1A;
    color: #55FF55;
    border-top: 2px solid #44AA2E;
    border-left: 2px solid #44AA2E;
    border-bottom: 2px solid #164A08;
    border-right: 2px solid #164A08;
    font-weight: 700;
}
#navTab:pressed {
    background-color: #484860;
    border-top: 2px solid #303048;
    border-left: 2px solid #303048;
    border-bottom: 2px solid #8888A0;
    border-right: 2px solid #8888A0;
}
#navTab:disabled {
    background-color: #363650;
    color: #555566;
    border-top-color: #4A4A60;
    border-left-color: #4A4A60;
    border-bottom-color: #222238;
    border-right-color: #222238;
}


/* ═══════════════════ 内容区 ═══════════════════ */
#contentStack {
    background: transparent;
}


/* ═══════════════════ MC 浮雕面板 ═══════════════════ */
#panel {
    background-color: #383555;
    border-top: 2px solid #504D6E;
    border-left: 2px solid #504D6E;
    border-bottom: 2px solid #222040;
    border-right: 2px solid #222040;
    border-radius: 0;
}

#panelDark {
    background-color: #2E2B45;
    border-top: 2px solid #403D58;
    border-left: 2px solid #403D58;
    border-bottom: 2px solid #1A1830;
    border-right: 2px solid #1A1830;
    border-radius: 0;
}

#loginSheet {
    background-color: #403C5C;
    border-top: 3px solid #565275;
    border-left: 3px solid #565275;
    border-bottom: 3px solid #242044;
    border-right: 3px solid #242044;
    border-radius: 0;
}


/* ═══════════════════ 登录分段按钮 ═══════════════════ */
#segment {
    background-color: #1E1B28;
    border-top: 2px solid #0E0C1E;
    border-left: 2px solid #0E0C1E;
    border-bottom: 2px solid #3A3748;
    border-right: 2px solid #3A3748;
    border-radius: 0;
}

#segBtn {
    background-color: #3A3848;
    border-top: 1px solid #5A5868;
    border-left: 1px solid #5A5868;
    border-bottom: 1px solid #2A2838;
    border-right: 1px solid #2A2838;
    color: #AAAAAA;
    border-radius: 0;
    padding: 8px;
    font-size: 13px;
    font-weight: 500;
}
#segBtn:hover {
    background-color: #444458;
    color: #FFFFFF;
}
#segBtn:checked {
    background-color: #1E3A12;
    color: #55FF55;
    border-top: 1px solid #2E5A1E;
    border-left: 1px solid #2E5A1E;
    border-bottom: 1px solid #0E2A08;
    border-right: 1px solid #0E2A08;
}


/* ═══════════════════ MC 浮雕按钮 ═══════════════════ */
QPushButton {
    background-color: #484858;
    color: #FFFFFF;
    border-top: 2px solid #6A6A7A;
    border-left: 2px solid #6A6A7A;
    border-bottom: 2px solid #282838;
    border-right: 2px solid #282838;
    border-radius: 0;
    padding: 6px 14px;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #585868;
    border-top-color: #7A7A8A;
    border-left-color: #7A7A8A;
    color: #FFFF55;
}
QPushButton:pressed {
    background-color: #383848;
    border-top: 2px solid #282838;
    border-left: 2px solid #282838;
    border-bottom: 2px solid #6A6A7A;
    border-right: 2px solid #6A6A7A;
}
QPushButton:disabled {
    background-color: #2A2A3A;
    color: #555555;
    border-top-color: #3A3A4A;
    border-left-color: #3A3A4A;
    border-bottom-color: #1A1A2A;
    border-right-color: #1A1A2A;
}

/* 绿色主要按钮 */
#btnPrimary {
    background-color: #3C7A20;
    color: #FFFFFF;
    border-top: 2px solid #55AA30;
    border-left: 2px solid #55AA30;
    border-bottom: 2px solid #1E4010;
    border-right: 2px solid #1E4010;
    font-weight: 600;
}
#btnPrimary:hover {
    background-color: #4C8A30;
    border-top-color: #65BA40;
    border-left-color: #65BA40;
    color: #FFFF55;
}
#btnPrimary:pressed {
    background-color: #2C6A10;
    border-top: 2px solid #1E4010;
    border-left: 2px solid #1E4010;
    border-bottom: 2px solid #55AA30;
    border-right: 2px solid #55AA30;
}

/* 次要按钮 */
#btnSecondary {
    background-color: #3A3A4A;
    color: #AAAAAA;
    border-top: 2px solid #5A5A6A;
    border-left: 2px solid #5A5A6A;
    border-bottom: 2px solid #2A2A3A;
    border-right: 2px solid #2A2A3A;
    font-weight: 500;
}
#btnSecondary:hover {
    background-color: #4A4A5A;
    color: #FFFFFF;
}

/* 幽灵按钮 */
#btnGhost {
    background-color: #2A2A3A;
    color: #AAAAAA;
    border-top: 2px solid #3A3A4A;
    border-left: 2px solid #3A3A4A;
    border-bottom: 2px solid #1A1A2A;
    border-right: 2px solid #1A1A2A;
    border-radius: 0;
}
#btnGhost:hover {
    background-color: #3A3A4A;
    color: #FFFF55;
}

/* 蓝色按钮（钻石蓝） */
#btnBlue {
    background-color: #1A5A7A;
    color: #FFFFFF;
    border-top: 2px solid #2A7A9A;
    border-left: 2px solid #2A7A9A;
    border-bottom: 2px solid #0A3A5A;
    border-right: 2px solid #0A3A5A;
    font-weight: 600;
}
#btnBlue:hover {
    background-color: #2A6A8A;
    color: #55FFFF;
}


/* ═══════════════════ 启动按钮（绿色 MC 大按钮） ═══════════════════ */
#launchBtn {
    background-color: #3C7A20;
    color: #FFFFFF;
    border-top: 3px solid #55AA30;
    border-left: 3px solid #55AA30;
    border-bottom: 3px solid #1E4010;
    border-right: 3px solid #1E4010;
    font-size: 16px;
    font-weight: 700;
    border-radius: 0;
    padding: 14px 52px;
    min-width: 220px;
    letter-spacing: 1px;
}
#launchBtn:hover {
    background-color: #4C8A30;
    border-top-color: #65BA40;
    border-left-color: #65BA40;
    color: #FFFF55;
}
#launchBtn:pressed {
    background-color: #2C6A10;
    border-top: 3px solid #1E4010;
    border-left: 3px solid #1E4010;
    border-bottom: 3px solid #55AA30;
    border-right: 3px solid #55AA30;
}
#launchBtn:disabled {
    background-color: #2A2A3A;
    color: #555555;
    border-top-color: #3A3A4A;
    border-left-color: #3A3A4A;
    border-bottom-color: #1A1A2A;
    border-right-color: #1A1A2A;
}


/* ═══════════════════ 首页英雄区 ═══════════════════ */
#heroTitle {
    font-size: 28px;
    font-weight: 700;
    color: #FFFFFF;
    letter-spacing: 1px;
}

#heroMeta {
    color: #9999BB;
    font-size: 13px;
}

/* 版本选择器（凹槽风格） */
/* 版本选择器 — 木板抽屉风格 */
#ghostCombo {
    background-color: #5A4228;
    border-top: 3px solid #7A6240;
    border-left: 3px solid #7A6240;
    border-bottom: 3px solid #2E1E0E;
    border-right: 3px solid #2E1E0E;
    border-radius: 0;
    padding: 8px 16px;
    color: #FFE8C0;
    font-size: 14px;
    min-width: 360px;
    min-height: 22px;
}
#ghostCombo:hover {
    background-color: #6A5238;
    border-top-color: #8A7250;
    border-left-color: #8A7250;
}
#ghostCombo::drop-down {
    border-left: 2px solid #3E2E18;
    width: 28px;
    background: #4A3420;
}
#ghostCombo::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #FFAA00;
    margin-right: 8px;
}
/* 下拉列表 — 箱子内部 */
#ghostCombo QAbstractItemView {
    background-color: #3E2C18;
    color: #FFE8C0;
    border-top: 3px solid #2A1A08;
    border-left: 3px solid #2A1A08;
    border-bottom: 3px solid #6A5238;
    border-right: 3px solid #6A5238;
    border-radius: 0;
    padding: 4px;
    outline: none;
    selection-background-color: #5A4020;
    selection-color: #FFFF55;
    min-width: 360px;
    max-height: 360px;
}
#ghostCombo QAbstractItemView::item {
    padding: 8px 14px;
    min-height: 28px;
    border-bottom: 1px solid #2A1A08;
}
#ghostCombo QAbstractItemView::item:hover {
    background-color: #4E3820;
    color: #FFFF55;
}
/* 分隔线 */
#ghostCombo QAbstractItemView::separator {
    height: 2px;
    background: #6A5238;
    margin: 4px 8px;
}


/* ═══════════════════ 输入框（凹槽/物品栏风格） ═══════════════════ */
QLineEdit {
    background-color: #222040;
    color: #FFFFFF;
    border-top: 2px solid #141230;
    border-left: 2px solid #141230;
    border-bottom: 2px solid #444260;
    border-right: 2px solid #444260;
    border-radius: 0;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: #1E3A12;
    selection-color: #55FF55;
}
QLineEdit:focus {
    border-top-color: #0A3A06;
    border-left-color: #0A3A06;
    border-bottom-color: #55AA30;
    border-right-color: #55AA30;
}
QLineEdit::placeholder {
    color: #555555;
}


/* ═══════════════════ 下拉框（凹槽风格） ═══════════════════ */
QComboBox {
    background-color: #1A172A;
    color: #FFFFFF;
    border-top: 2px solid #0E0C1E;
    border-left: 2px solid #0E0C1E;
    border-bottom: 2px solid #3A3748;
    border-right: 2px solid #3A3748;
    border-radius: 0;
    padding: 7px 10px;
    font-size: 13px;
}
QComboBox:hover {
    background-color: #22202E;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #AAAAAA;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background-color: #1E1B28;
    color: #FFFFFF;
    border: 2px solid #3A3748;
    border-radius: 0;
    padding: 2px;
    outline: none;
    selection-background-color: #1E3A12;
    selection-color: #55FF55;
}
QComboBox QAbstractItemView::item {
    padding: 5px 10px;
    min-height: 26px;
}
QComboBox QAbstractItemView::item:hover {
    background-color: #2E2B3A;
}


/* ═══════════════════ 列表（凹槽风格） ═══════════════════ */
QListWidget {
    background-color: #1A172A;
    color: #AAAAAA;
    border-top: 2px solid #0E0C1E;
    border-left: 2px solid #0E0C1E;
    border-bottom: 2px solid #3A3748;
    border-right: 2px solid #3A3748;
    border-radius: 0;
    outline: none;
    padding: 2px;
}
QListWidget::item {
    padding: 6px 10px;
    border: none;
    margin: 1px 0;
}
QListWidget::item:selected {
    background-color: #1E3A12;
    color: #55FF55;
}
QListWidget::item:hover:!selected {
    background-color: #2A2838;
    color: #FFFFFF;
}


/* ═══════════════════ 经验条进度条 ═══════════════════ */
QProgressBar {
    background-color: #1A172A;
    border-top: 2px solid #0E0C1E;
    border-left: 2px solid #0E0C1E;
    border-bottom: 2px solid #3A3748;
    border-right: 2px solid #3A3748;
    border-radius: 0;
    height: 8px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #55FF55, stop:1 #80FF20);
    border-radius: 0;
}


/* ═══════════════════ 复选框 ═══════════════════ */
QCheckBox {
    color: #AAAAAA;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-top: 2px solid #0E0C1E;
    border-left: 2px solid #0E0C1E;
    border-bottom: 2px solid #3A3748;
    border-right: 2px solid #3A3748;
    background: #1A172A;
    border-radius: 0;
}
QCheckBox::indicator:checked {
    background: #1E3A12;
    border-top: 2px solid #0E2A08;
    border-left: 2px solid #0E2A08;
    border-bottom: 2px solid #55AA30;
    border-right: 2px solid #55AA30;
}
QCheckBox::indicator:hover {
    background: #22202E;
}


/* ═══════════════════ 选项卡 ═══════════════════ */
QTabWidget::pane {
    background-color: #2A2735;
    border: 2px solid #3A3748;
    border-radius: 0;
    top: -2px;
}
QTabBar::tab {
    background: #3A3848;
    color: #AAAAAA;
    padding: 7px 18px;
    border-top: 1px solid #5A5868;
    border-left: 1px solid #5A5868;
    border-bottom: none;
    border-right: 1px solid #2A2838;
    border-radius: 0;
    font-weight: 500;
}
QTabBar::tab:selected {
    background: #2A2735;
    color: #55FF55;
    border-bottom: 2px solid #55FF55;
}
QTabBar::tab:hover:!selected {
    background: #444458;
    color: #FFFFFF;
}


/* ═══════════════════ SpinBox ═══════════════════ */
QSpinBox {
    background-color: #1A172A;
    color: #FFFFFF;
    border-top: 2px solid #0E0C1E;
    border-left: 2px solid #0E0C1E;
    border-bottom: 2px solid #3A3748;
    border-right: 2px solid #3A3748;
    border-radius: 0;
    padding: 5px 10px;
}
QSpinBox:focus {
    border-top-color: #0A3A06;
    border-left-color: #0A3A06;
    border-bottom-color: #55AA30;
    border-right-color: #55AA30;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: #3A3848;
    border: 1px solid #2A2838;
    width: 20px;
    border-radius: 0;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {
    background: #4A4858;
}


/* ═══════════════════ GroupBox ═══════════════════ */
QGroupBox {
    background-color: #2A2735;
    border-top: 2px solid #3A3748;
    border-left: 2px solid #3A3748;
    border-bottom: 2px solid #1A172A;
    border-right: 2px solid #1A172A;
    border-radius: 0;
    margin-top: 14px;
    padding: 20px 16px 16px 16px;
    font-weight: 600;
    color: #AAAAAA;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: #55FF55;
}


/* ═══════════════════ 滚动条 ═══════════════════ */
QScrollBar:vertical {
    background: #1A172A;
    width: 8px;
    margin: 0;
    border-radius: 0;
}
QScrollBar::handle:vertical {
    background: #4A4858;
    min-height: 24px;
    border-radius: 0;
}
QScrollBar::handle:vertical:hover {
    background: #5A5868;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

QScrollBar:horizontal {
    background: #1A172A;
    height: 8px;
    border-radius: 0;
}
QScrollBar::handle:horizontal {
    background: #4A4858;
    min-width: 24px;
    border-radius: 0;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }


/* ═══════════════════ ScrollArea ═══════════════════ */
/* 滚动区这一层必须整体透明：QScrollArea 的 viewport 与内部容器默认用
   Fusion 浅色 palette 铺底，深色主题下会出现整块浅灰白、文字几乎不可读。
   只限定在 QScrollArea 及其 viewport / 内容容器，不动全局 QWidget。 */
QScrollArea, QScrollArea > QWidget#qt_scrollarea_viewport {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
#scrollArea, #scrollBody {
    background: transparent;
    border: none;
}


/* ═══════════════════ 对话框 ═══════════════════ */
QDialog {
    background-color: #1E1B28;
}
QMessageBox {
    background-color: #1E1B28;
}
QMessageBox QLabel {
    color: #FFFFFF;
}
QMessageBox QPushButton {
    min-width: 72px;
}


/* ═══════════════════ 标签 ═══════════════════ */
QLabel {
    background: transparent;
}

#title {
    font-size: 20px;
    font-weight: 700;
    color: #FFFFFF;
}

#subtitle {
    color: #8888AA;
    font-size: 12px;
}

#sectionLabel {
    font-size: 14px;
    font-weight: 600;
    color: #55FF55;
}

#fieldLabel {
    color: #BBBBCC;
    font-size: 12px;
    font-weight: 500;
}

#mutedLabel {
    color: #7777AA;
    font-size: 12px;
}

#statusLabel {
    color: #8888AA;
    font-size: 12px;
}

"""
