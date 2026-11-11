"""Minecraft 像素艺术图标 — QPainter 绘制，零外部依赖。"""

from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtGui import (
    QPainter, QColor, QPixmap, QIcon, QFont, QPainterPath, QPen,
)
from PyQt6.QtCore import Qt, QRect, QRectF


# ───────────── 像素渲染器 ─────────────

def _pixel_art(size: int, grid: list[list[int]], colors: list[QColor]) -> QPixmap:
    """将二维索引网格渲染为 QPixmap。0=透明, 1..N=colors[i-1]。"""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    if rows == 0 or cols == 0:
        return pm

    px = size / max(rows, cols)
    ox = (size - cols * px) / 2
    oy = (size - rows * px) / 2

    p = QPainter(pm)
    for r, row in enumerate(grid):
        for c, idx in enumerate(row):
            if 0 < idx <= len(colors):
                p.fillRect(
                    int(ox + c * px), int(oy + r * px),
                    int(px) + 1, int(px) + 1,
                    colors[idx - 1],
                )
    p.end()
    return pm


# ───────────── 草方块品牌 ─────────────

_GRASS_GRID = [
    [0, 1, 1, 1, 1, 1, 1, 0],
    [1, 1, 1, 1, 1, 1, 1, 1],
    [2, 1, 2, 1, 1, 2, 1, 2],
    [2, 2, 2, 2, 2, 2, 2, 2],
    [3, 2, 3, 2, 2, 3, 2, 3],
    [3, 3, 2, 3, 3, 2, 3, 3],
    [3, 3, 3, 3, 3, 3, 3, 3],
    [0, 3, 3, 3, 3, 3, 3, 0],
]
_GRASS_COLORS = [
    QColor(94, 168, 56),   # 草绿
    QColor(139, 104, 67),  # 泥土
    QColor(107, 76, 51),   # 深泥土
]


def _grass_pixmap(size: int = 24) -> QPixmap:
    return _pixel_art(size, _GRASS_GRID, _GRASS_COLORS)


class CubeMark(QLabel):
    """品牌图标：Minecraft 草方块。"""

    def __init__(self, size: int = 22, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setPixmap(_grass_pixmap(size))


# ───────────── 圆形头像（像素风格） ─────────────

class AvatarBadge(QWidget):
    """方形头像（Minecraft 不用圆形）。"""

    def __init__(self, size: int = 32, parent=None):
        super().__init__(parent)
        self._sz = size
        self._initial = "?"
        self._pixmap = None
        self.setFixedSize(size, size)

    def set_name(self, name: str):
        self._initial = (name[:1].upper() if name else "?")
        self._pixmap = None
        self.update()

    def set_pixmap(self, pixmap):
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        s = self._sz

        if self._pixmap:
            p.drawPixmap(0, 0, s, s, self._pixmap)
        else:
            p.fillRect(0, 0, s, s, QColor(60, 122, 32, 80))
            p.setPen(QColor(85, 255, 85, 200))
            f = QFont("Microsoft YaHei UI", max(8, int(s * 0.36)))
            f.setBold(True)
            p.setFont(f)
            p.drawText(QRect(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, self._initial)

        pen = QPen(QColor(85, 255, 85, 40), 1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, s - 1, s - 1)
        p.end()


# ───────────── 导航像素图标 ─────────────

_NAV_GRIDS = {
    "home": [
        [0, 0, 0, 1, 0, 0, 0],
        [0, 0, 1, 1, 1, 0, 0],
        [0, 1, 1, 1, 1, 1, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 1, 1, 0, 1, 1, 0],
        [0, 1, 1, 0, 1, 1, 0],
        [0, 1, 1, 1, 1, 1, 0],
    ],
    "versions": [
        [1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 1, 0, 0, 1],
        [1, 0, 0, 1, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1],
        [1, 0, 0, 0, 0, 0, 1],
        [1, 0, 0, 0, 0, 0, 1],
        [1, 1, 1, 1, 1, 1, 1],
    ],
    "mods": [
        [0, 1, 1, 0, 1, 1, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [1, 1, 0, 0, 0, 1, 1],
        [0, 1, 0, 0, 0, 1, 0],
        [1, 1, 0, 0, 0, 1, 1],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 1, 1, 0, 1, 1, 0],
    ],
    "settings": [
        [0, 1, 0, 1, 0, 1, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 1, 0, 0, 0, 1, 0],
        [1, 1, 0, 0, 0, 1, 1],
        [0, 1, 0, 0, 0, 1, 0],
        [1, 1, 1, 1, 1, 1, 1],
        [0, 1, 0, 1, 0, 1, 0],
    ],
}


def _nav_pm(key: str, active: bool, size: int = 18) -> QPixmap:
    grid = _NAV_GRIDS.get(key, [])
    c = QColor("#55FF55") if active else QColor(170, 170, 170)
    return _pixel_art(size, grid, [c])


def nav_icon(key: str, active: bool) -> QIcon:
    """返回导航像素图标 QIcon。"""
    return QIcon(_nav_pm(key, active))


def window_icon() -> QIcon:
    """应用窗口图标：草方块。"""
    return QIcon(_grass_pixmap(32))
