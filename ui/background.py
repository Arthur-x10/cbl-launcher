"""Minecraft 动态主题背景 — 多主题 + 高帧率粒子动画。"""

import math
import random

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPen, QLinearGradient
from PyQt6.QtCore import Qt, QTimer


# ═══════════════════ 主题定义 ═══════════════════

THEMES = {
    "grass_block": {
        "name": "草方块",
        "top": (82, 158, 42),
        "bot": (105, 78, 52),
        "top_ratio": 0.10,
        "jag": (82, 158, 42),
        "overlay": 95,
        "orbs":  [(85,255,85), (120,255,60), (100,255,120)],
        "dust":  [(255,250,230), (255,255,190), (240,240,215)],
        "flies": [(180,255,50), (255,230,50), (200,255,100)],
        "grad_top": None,
    },
    "the_end": {
        "name": "末地",
        "top": (15, 10, 25),
        "bot": (205, 200, 160),
        "top_ratio": 0.35,
        "jag": None,
        "overlay": 105,
        "orbs":  [(200,100,255), (180,80,230), (160,60,220)],
        "dust":  [(200,180,255), (180,160,240), (220,200,255)],
        "flies": [(255,50,255), (200,100,255), (230,130,255)],
        "grad_top": [(10,5,20), (25,15,45)],
    },
    "nether": {
        "name": "下界",
        "top": (80, 25, 18),
        "bot": (110, 50, 40),
        "top_ratio": 0.0,
        "jag": None,
        "overlay": 85,
        "orbs":  [(255,160,50), (255,120,30), (255,200,60)],
        "dust":  [(255,200,140), (255,180,100), (255,160,80)],
        "flies": [(255,100,20), (255,180,50), (255,60,10)],
        "grad_top": None,
    },
    "ocean": {
        "name": "深海",
        "top": (15, 40, 85),
        "bot": (20, 55, 75),
        "top_ratio": 0.0,
        "jag": None,
        "overlay": 75,
        "orbs":  [(80,200,255), (100,220,255), (60,180,230)],
        "dust":  [(180,220,255), (200,240,255), (160,210,245)],
        "flies": [(50,255,200), (100,255,230), (80,230,200)],
        "grad_top": [(10,25,60), (20,50,90)],
    },
    "twilight": {
        "name": "暮色森林",
        "top": (18, 45, 35),
        "bot": (40, 32, 22),
        "top_ratio": 0.25,
        "jag": (25, 55, 38),
        "overlay": 90,
        "orbs":  [(100,255,150), (80,230,120), (120,255,180)],
        "dust":  [(200,255,220), (180,240,200), (220,255,235)],
        "flies": [(255,220,80), (255,200,50), (240,255,100)],
        "grad_top": None,
    },
    "cherry": {
        "name": "樱花林",
        "top": (180, 140, 160),
        "bot": (90, 65, 50),
        "top_ratio": 0.20,
        "jag": (160, 120, 140),
        "overlay": 85,
        "orbs":  [(255,150,200), (255,180,220), (240,130,180)],
        "dust":  [(255,230,240), (255,220,235), (255,210,230)],
        "flies": [(255,180,220), (255,200,230), (255,160,200)],
        "grad_top": None,
    },

    # ── v0.8 新增 ──
    "mushroom": {
        "name": "蘑菇岛",
        "top": (128, 116, 128),
        "bot": (104, 82, 96),
        "top_ratio": 0.12,
        "jag": (116, 104, 116),
        "overlay": 92,
        "orbs":  [(242, 240, 250), (222, 204, 232), (255, 236, 244)],
        "dust":  [(232, 226, 238), (212, 202, 222), (245, 240, 248)],
        "flies": [(255, 132, 148), (206, 162, 255), (255, 168, 180)],
        "grad_top": None,
    },
    "snowy": {
        "name": "雪原",
        "top": (226, 236, 246),
        "bot": (150, 178, 200),
        "top_ratio": 0.18,
        "jag": (208, 226, 240),
        "overlay": 120,
        "orbs":  [(255, 255, 255), (204, 232, 255), (170, 210, 245)],
        "dust":  [(255, 255, 255), (226, 242, 255), (196, 226, 250)],
        "flies": [(140, 220, 255), (180, 240, 255), (110, 200, 240)],
        "grad_top": None,
    },
    "desert": {
        "name": "沙漠",
        "top": (220, 196, 130),
        "bot": (186, 148, 96),
        "top_ratio": 0.10,
        "jag": (205, 180, 120),
        "overlay": 104,
        "orbs":  [(255, 236, 170), (242, 212, 142), (255, 250, 200)],
        "dust":  [(255, 245, 210), (250, 226, 172), (255, 250, 224)],
        "flies": [(255, 200, 60), (255, 226, 120), (230, 170, 40)],
        "grad_top": None,
    },
    "deep_dark": {
        "name": "深暗之域",
        "top": (16, 38, 44),
        "bot": (10, 24, 30),
        "top_ratio": 0.0,
        "jag": None,
        "overlay": 78,
        "orbs":  [(42, 182, 172), (32, 142, 150), (60, 208, 190)],
        "dust":  [(124, 222, 212), (92, 192, 190), (150, 236, 226)],
        "flies": [(0, 255, 212), (60, 224, 200), (120, 255, 230)],
        "grad_top": [(8, 20, 26), (18, 42, 48)],
    },
    "badlands": {
        "name": "恶地",
        "top": (176, 88, 52),
        "bot": (126, 62, 42),
        "top_ratio": 0.22,
        "jag": (156, 76, 46),
        "overlay": 88,
        "orbs":  [(255, 170, 90), (230, 132, 62), (255, 200, 130)],
        "dust":  [(255, 200, 150), (240, 162, 112), (255, 218, 176)],
        "flies": [(255, 220, 120), (255, 190, 80), (240, 150, 60)],
        "grad_top": None,
    },
    "lush_caves": {
        "name": "繁茂洞穴",
        "top": (72, 112, 62),
        "bot": (44, 52, 40),
        "top_ratio": 0.16,
        "jag": (62, 100, 54),
        "overlay": 90,
        "orbs":  [(150, 230, 120), (120, 210, 100), (186, 246, 150)],
        "dust":  [(200, 245, 180), (170, 230, 150), (216, 250, 200)],
        "flies": [(170, 255, 120), (200, 255, 160), (130, 230, 96)],
        "grad_top": None,
    },
    "amethyst": {
        "name": "紫水晶洞",
        "top": (122, 98, 172),
        "bot": (58, 52, 78),
        "top_ratio": 0.14,
        "jag": (104, 82, 150),
        "overlay": 95,
        "orbs":  [(202, 162, 255), (172, 132, 240), (228, 196, 255)],
        "dust":  [(230, 210, 255), (202, 182, 250), (240, 226, 255)],
        "flies": [(170, 120, 255), (206, 168, 255), (140, 96, 236)],
        "grad_top": None,
    },
    "mangrove": {
        "name": "红树林",
        "top": (84, 56, 48),
        "bot": (44, 62, 46),
        "top_ratio": 0.20,
        "jag": (74, 50, 42),
        "overlay": 92,
        "orbs":  [(255, 170, 110), (206, 124, 82), (255, 200, 150)],
        "dust":  [(230, 200, 170), (202, 182, 150), (244, 220, 196)],
        "flies": [(255, 230, 120), (255, 206, 90), (220, 176, 70)],
        "grad_top": None,
    },
}

THEME_KEYS = list(THEMES.keys())


def theme_swatch(key: str, size: int = 16) -> QPixmap:
    """主题选择器用的像素色块：上=天空/草皮，下=地面，可选锯齿带。"""
    t = THEMES.get(key, THEMES["grass_block"])
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    cell = max(1, size // 4)
    rows = max(2, size // cell)
    half = max(1, rows // 2)
    top = QColor(*t["top"])
    bot = QColor(*t["bot"])
    for r in range(rows):
        for c in range(rows):
            base = top if r < half else bot
            v = ((r * 7 + c * 13) % 17) - 8
            p.fillRect(c * cell, r * cell, cell, cell, QColor(
                max(0, min(255, base.red() + v)),
                max(0, min(255, base.green() + v)),
                max(0, min(255, base.blue() + v)),
            ))
    if t.get("jag"):
        jc = QColor(*t["jag"])
        y = (half - 1) * cell
        for c in range(rows):
            if (c * 5) % 3 == 0:
                p.fillRect(c * cell, y, cell, cell, jc)
    p.end()
    return pm


def random_swatch(size: int = 16) -> QPixmap:
    """“随机”项的四色块（取四个代表主题的顶部色）。"""
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    picks = ["grass_block", "the_end", "nether", "cherry"]
    w = max(1, size // len(picks))
    for i, key in enumerate(picks):
        p.fillRect(i * w, 0, w, size, QColor(*THEMES[key]["top"]))
    p.fillRect(0, size // 2, size, max(1, size // 4), QColor(0, 0, 0, 60))
    p.end()
    return pm


# ═══════════════════ 背景组件 ═══════════════════

class BackgroundWidget(QWidget):
    """多主题 Minecraft 像素背景 + 60 粒子三层动画。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._draw_border = True
        self._rng = random.Random()
        self._scroll_x = 0.0
        self._frame = 0
        self._theme_key = ""
        self._top_tile = None
        self._bot_tile = None
        self._theme = THEMES["grass_block"]
        self._particles: list[dict] = []

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(20)

    def set_animating(self, enabled: bool):
        """窗口最小化/不可见时停掉 50fps 全窗重绘，别再空转烧 CPU。"""
        if enabled:
            if not self._timer.isActive():
                self._timer.start(20)
        else:
            self._timer.stop()

    def set_theme(self, key: str):
        """切换主题。"""
        if key not in THEMES:
            key = "grass_block"
        if key == self._theme_key:
            return
        self._theme_key = key
        self._theme = THEMES[key]
        t = self._theme
        self._top_tile = self._make_tile(*t["top"])
        self._bot_tile = self._make_tile(*t["bot"])
        self._particles.clear()
        for _ in range(26):
            self._particles.append(self._orb(init=True))
        for _ in range(22):
            self._particles.append(self._dust(init=True))
        for _ in range(18):
            self._particles.append(self._firefly(init=True))
        self.update()

    def set_random_theme(self):
        self.set_theme(self._rng.choice(THEME_KEYS))

    def current_theme_key(self) -> str:
        return self._theme_key

    # ── 纹理 ──

    @staticmethod
    def _make_tile(base_r, base_g, base_b, var=12, size=48, px=6) -> QPixmap:
        pm = QPixmap(size, size)
        rng = random.Random(base_r * 100 + base_g * 10 + base_b)
        p = QPainter(pm)
        for y in range(0, size, px):
            for x in range(0, size, px):
                v = rng.randint(-var, var)
                p.fillRect(x, y, px, px, QColor(
                    max(0, min(255, base_r + v)),
                    max(0, min(255, base_g + v)),
                    max(0, min(255, base_b + v)),
                ))
        p.end()
        return pm

    # ── 粒子 ──

    def _orb(self, init=False) -> dict:
        w, h = max(self.width(), 500), max(self.height(), 500)
        return {
            "t": "orb",
            "x": self._rng.uniform(0, w),
            "y": self._rng.uniform(0, h) if init else h + self._rng.randint(10, 80),
            "vx": self._rng.uniform(-0.3, 0.3),
            "vy": -self._rng.uniform(0.4, 0.9),
            "sz": self._rng.randint(3, 6),
            "a": float(self._rng.randint(120, 240)),
            "c": self._rng.choice(self._theme["orbs"]),
            "ph": self._rng.uniform(0, math.tau),
            "sw": self._rng.uniform(0.3, 0.7),
        }

    def _dust(self, init=False) -> dict:
        w, h = max(self.width(), 500), max(self.height(), 500)
        return {
            "t": "dust",
            "x": self._rng.uniform(0, w),
            "y": self._rng.uniform(0, h) if init else h + self._rng.randint(5, 50),
            "vx": self._rng.uniform(-0.15, 0.15),
            "vy": -self._rng.uniform(0.06, 0.25),
            "sz": self._rng.randint(1, 3),
            "a": float(self._rng.randint(40, 110)),
            "c": self._rng.choice(self._theme["dust"]),
        }

    def _firefly(self, init=False) -> dict:
        w, h = max(self.width(), 500), max(self.height(), 500)
        return {
            "t": "fly",
            "x": self._rng.uniform(w * 0.02, w * 0.98),
            "y": self._rng.uniform(h * 0.08, h * 0.92) if init else self._rng.uniform(h * 0.1, h * 0.9),
            "vx": self._rng.uniform(-0.4, 0.4),
            "vy": self._rng.uniform(-0.3, 0.3),
            "sz": self._rng.randint(3, 6),
            "ba": self._rng.randint(40, 140),
            "c": self._rng.choice(self._theme["flies"]),
            "ph": self._rng.uniform(0, math.tau),
            "ps": self._rng.uniform(0.03, 0.08),
        }

    # ── 帧更新 (50fps) ──

    def _tick(self):
        self._frame += 1
        self._scroll_x = (self._scroll_x + 0.15) % 48

        w = max(self.width(), 100)
        h = max(self.height(), 100)

        for i, pt in enumerate(self._particles):
            k = pt["t"]
            if k == "orb":
                pt["ph"] += 0.06
                pt["x"] += pt["vx"] + pt["sw"] * math.sin(pt["ph"])
                pt["y"] += pt["vy"]
                pt["a"] -= self._rng.uniform(0.1, 0.5)
                if pt["y"] < -20 or pt["a"] <= 0:
                    self._particles[i] = self._orb()
            elif k == "dust":
                pt["x"] += pt["vx"] + self._rng.uniform(-0.05, 0.05)
                pt["y"] += pt["vy"]
                pt["a"] -= self._rng.uniform(0, 0.18)
                if pt["y"] < -10 or pt["a"] <= 0:
                    self._particles[i] = self._dust()
            elif k == "fly":
                pt["ph"] += pt["ps"]
                pt["vx"] += self._rng.uniform(-0.03, 0.03)
                pt["vy"] += self._rng.uniform(-0.03, 0.03)
                pt["vx"] = max(-0.5, min(0.5, pt["vx"]))
                pt["vy"] = max(-0.4, min(0.4, pt["vy"]))
                pt["x"] += pt["vx"]
                pt["y"] += pt["vy"]
                if pt["x"] < 5 or pt["x"] > w - 5:
                    pt["vx"] = -pt["vx"] * 0.8
                    pt["x"] = max(5, min(w - 5, pt["x"]))
                if pt["y"] < h * 0.05 or pt["y"] > h * 0.95:
                    pt["vy"] = -pt["vy"] * 0.8
                    pt["y"] = max(h * 0.05, min(h * 0.95, pt["y"]))

        self.update()

    # ── 绘制 ──

    def paintEvent(self, event):
        if not self._top_tile:
            return

        p = QPainter(self)
        w, h = self.width(), self.height()
        t = self._theme
        ox = int(self._scroll_x)

        top_h = max(0, int(h * t["top_ratio"]))

        if t.get("grad_top"):
            c1, c2 = t["grad_top"]
            # top_ratio=0 时也要留出天空带，否则底部纹理会把渐变整体盖掉
            sky_h = top_h if top_h > 0 else int(h * 0.3)
            grad = QLinearGradient(0, 0, 0, sky_h)
            grad.setColorAt(0, QColor(*c1))
            grad.setColorAt(1, QColor(*c2))
            p.fillRect(0, 0, w, sky_h, grad)
            p.drawTiledPixmap(-ox, sky_h, w + 48, h - sky_h, self._bot_tile)
        else:
            if top_h > 0:
                p.drawTiledPixmap(0, 0, w, top_h, self._top_tile)
            p.drawTiledPixmap(-ox, top_h, w + 48, h - top_h, self._bot_tile)

        if t["jag"] and top_h > 0:
            jr, jg, jb = t["jag"]
            jag = random.Random(77)
            for x in range(0, w, 6):
                hang = jag.randint(0, 4) * 6
                if hang > 0:
                    v = jag.randint(-8, 8)
                    p.fillRect(x, top_h, 6, hang,
                               QColor(jr + v, jg + v, jb + v))

        p.fillRect(0, 0, w, h, QColor(0, 0, 0, t["overlay"]))

        for pt in self._particles:
            cr, cg, cb = pt["c"]
            px, py, sz = int(pt["x"]), int(pt["y"]), pt["sz"]
            if pt["t"] == "fly":
                a = int(pt["ba"] + 100 * math.sin(pt["ph"]))
                a = max(0, min(255, a))
                p.fillRect(px - 2, py - 2, sz + 4, sz + 4, QColor(cr, cg, cb, a // 5))
                p.fillRect(px - 1, py - 1, sz + 2, sz + 2, QColor(cr, cg, cb, a // 3))
                p.fillRect(px, py, sz, sz, QColor(cr, cg, cb, a))
            elif pt["t"] == "orb":
                a = max(0, min(255, int(pt["a"])))
                p.fillRect(px - 1, py - 1, sz + 2, sz + 2, QColor(cr, cg, cb, a // 4))
                p.fillRect(px, py, sz, sz, QColor(cr, cg, cb, a))
            else:
                a = max(0, min(255, int(pt["a"])))
                p.fillRect(px, py, sz, sz, QColor(cr, cg, cb, a))

        if self._draw_border:
            p.setPen(QPen(QColor(70, 65, 90), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(0, 0, w - 1, h - 1)

        p.end()
