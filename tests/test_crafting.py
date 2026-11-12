"""ui/widgets/crafting.py 合成台的逻辑测试。

跑在 offscreen 平台，不需要显示器、不会弹窗：
    QT_QPA_PLATFORM 必须在创建 QApplication **之前**设好（见文件顶部）。
    offscreen 没有字体，控件上的中文会渲染成 tofu —— 所以这里只断言逻辑
    （chosen / can_compose / issues / install_plan / 槽位状态与可用性），
    不断言任何像素、文字渲染或 QSS 字符串。
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from core.providers.java import combos
from ui.widgets import crafting as crafting_mod
from ui.widgets.crafting import CraftingBench

FORGE_V = "14.23.5.2859"
OPTI_JAR = "C:/dl/OptiFine_1.12.2_HD_U_G5.jar"
OPTI_TAG = "HD_U_G5"

# apply_options 收到的版本表：{loader_id: [版本, …]}
OPTS = {
    "forge": [FORGE_V, "14.23.5.2860"],
    "fabric": ["0.15.11"],
    "neoforge": ["21.1.172"],
    "quilt": ["0.26.0"],
}


@pytest.fixture(scope="session", autouse=True)
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def make_bench(qapp):
    """造合成台；测试结束统一销毁（offscreen 下也要清 C++ 对象）。"""
    made = []

    def _make(mc="1.12.2", options=None, read_only=False):
        b = CraftingBench(read_only=read_only)
        if mc:
            b.set_version(mc)
            if options is not None:
                b.apply_options(mc, options)
        made.append(b)
        return b

    yield _make
    for b in made:
        b.close()
        b.deleteLater()
    qapp.processEvents()


class _FakeFileDialog:
    """替掉 QFileDialog，让 _pick_jar 不弹窗。"""

    path = OPTI_JAR

    @staticmethod
    def getOpenFileName(*_a, **_k):
        return (_FakeFileDialog.path, "Java 模组 (*.jar)")


@pytest.fixture()
def pick_optifine(monkeypatch):
    def _pick(b, path=OPTI_JAR):
        monkeypatch.setattr(crafting_mod, "QFileDialog", _FakeFileDialog)
        _FakeFileDialog.path = path
        b._pick_jar("optifine")
    return _pick


def slot(b, lid):
    return b._slots[lid]


def click(b, lid):
    """真的点一下槽位按钮：走 LoaderSlot.toggled → CraftingBench._on_toggled 的通路。"""
    slot(b, lid).btn.click()


# ═══════════════════ 成品判定 ═══════════════════

class TestCompose:
    def test_no_version_cannot_compose(self, make_bench):
        b = make_bench("", None)
        assert b.can_compose() is False

    def test_vanilla_is_a_valid_product(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        assert b.chosen() == {}
        assert b.can_compose() is True
        assert b.install_plan()["loader"] == ""
        assert b.install_plan()["extra_jars"] == []

    def test_forge_composes(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        assert b.chosen() == {"forge": FORGE_V}
        assert b.can_compose() is True
        plan = b.install_plan()
        assert plan["loader"] == "forge"
        assert plan["loader_version"] == FORGE_V
        assert plan["extra_jars"] == []
        assert not [i for i in b.issues() if i.level == combos.BLOCKED]

    def test_primary_without_version_cannot_compose(self, make_bench):
        """选了主加载器但版本表还没到 —— 不算合成成功。"""
        b = make_bench("1.12.2", {})          # 空版本表：只能给「正在取版本列表…」
        click(b, "forge")
        assert b.chosen() == {"forge": ""}
        assert b.can_compose() is False

    def test_optifine_needs_a_jar(self, make_bench, pick_optifine):
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        click(b, "optifine")
        assert "optifine" in b.chosen()
        assert b.can_compose() is False        # 选了补丁但没给文件
        assert b.optifine_jar() == ""

        pick_optifine(b)
        assert b.optifine_jar() == OPTI_JAR
        assert b.chosen()["optifine"] == OPTI_TAG
        assert b.can_compose() is True
        assert b.install_plan()["extra_jars"] == [OPTI_JAR]
        assert b.install_plan()["loader"] == "forge"

    def test_unpicking_optifine_forgets_the_jar(self, make_bench, pick_optifine):
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        click(b, "optifine")
        pick_optifine(b)
        click(b, "optifine")                   # 再点一次 = 取消
        assert b.optifine_jar() == ""
        assert "optifine" not in b.chosen()
        assert b.install_plan()["extra_jars"] == []


# ═══════════════════ classic 三件套 ═══════════════════

class TestClassicTrio:
    def test_forge_liteloader_optifine_on_1_12_2(self, make_bench, pick_optifine):
        """1.12.2 的三件套必须能合成出来（LiteLoader 那颗按钮在 UI 里是禁用的，
        见 TestSlotStates，所以这里按程序化置位 —— 数据层是允许的）。"""
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        slot(b, "liteloader").set_active(True)
        b._on_toggled("liteloader", True)
        click(b, "optifine")
        pick_optifine(b)

        assert set(b.chosen()) == {"forge", "liteloader", "optifine"}
        assert combos.can_install(b.issues()) is True
        assert b.can_compose() is True
        plan = b.install_plan()
        assert plan["loader"] == "forge"
        assert plan["extra_jars"] == [OPTI_JAR]

    def test_same_trio_on_1_7_10(self, make_bench, pick_optifine):
        b = make_bench("1.7.10", OPTS)
        click(b, "forge")
        slot(b, "liteloader").set_active(True)
        b._on_toggled("liteloader", True)
        click(b, "optifine")
        pick_optifine(b, "C:/dl/OptiFine_1.7.10_HD_U_E7.jar")

        assert combos.can_install(b.issues()) is True
        assert b.can_compose() is True
        assert b.chosen()["optifine"] == "HD_U_E7"


# ═══════════════════ 互斥 ═══════════════════

class TestExclusive:
    def test_primary_swap_keeps_one_loader(self, make_bench):
        b = make_bench("1.14", OPTS)
        click(b, "fabric")
        assert b.chosen() == {"fabric": "0.15.11"}
        click(b, "forge")                       # 换主加载器：旧的被清掉
        assert b.chosen() == {"forge": FORGE_V}
        assert slot(b, "fabric").is_active() is False
        assert slot(b, "fabric").version() == ""
        assert not [i for i in b.issues() if i.level == combos.BLOCKED]
        assert b.can_compose() is True

    def test_neoforge_plus_optifine_blocked_on_1_21_11(self, make_bench, pick_optifine):
        b = make_bench("1.21.11", {"neoforge": ["21.11.0"]})
        click(b, "neoforge")
        click(b, "optifine")
        pick_optifine(b, "C:/dl/OptiFine_1.21.11_HD_U_K1.jar")

        # jar 已经给了 —— 挡住它的只能是规则，不是缺文件
        assert b.optifine_jar().endswith(".jar")
        assert b.can_compose() is False
        blocked = [i for i in b.issues() if i.level == combos.BLOCKED]
        assert blocked
        assert any("NeoForge" in i.reason for i in blocked)

    def test_fabric_unavailable_on_1_13_2(self, make_bench):
        b = make_bench("1.13.2", OPTS)
        click(b, "fabric")
        assert b.can_compose() is False
        blocked = [i for i in b.issues() if i.level == combos.BLOCKED]
        assert blocked
        assert any("1.14" in i.reason for i in blocked)


# ═══════════════════ 槽位状态 ═══════════════════

class TestSlotStates:
    def test_all_loaders_have_a_slot(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        assert set(b._slots) == {l.id for l in combos.LOADERS}

    def test_liteloader_is_manual_but_clickable(self, make_bench):
        """LiteLoader 已停更、本启动器不代装，但槽位必须能点 —— 否则经典三件套凑不出来。"""
        b = make_bench("1.12.2", OPTS)
        ll = slot(b, "liteloader")
        assert ll._state == "manual"
        assert ll.btn.isEnabled() is True
        assert "不自动安装" in ll.btn.toolTip()

    def test_liteloader_chosen_warns_and_is_excluded_from_plan(self, make_bench):
        """选中 LiteLoader 会得到一条 warn，并且不进自动安装配方。"""
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        click(b, "liteloader")
        assert "liteloader" in b.chosen()        # 用户确实放上了（版本号是空的，不代装）
        assert b.can_compose() is True           # 不拦安装
        plan = b.install_plan()
        assert plan["loader"] == "forge"         # 主加载器没被它顶掉
        assert plan["manual"] == ["liteloader"]  # 但要提示手动装
        assert any("不会自动安装" in i.reason for i in b.issues())

    def test_unavailable_slot_is_na_but_clickable(self, make_bench):
        b = make_bench("1.13.2", OPTS)
        fabric = slot(b, "fabric")
        assert fabric._state == "na"
        assert fabric.btn.isEnabled() is True     # 仍可点，点了变红说明原因
        assert "1.14" in fabric.btn.toolTip()
        assert slot(b, "forge")._state == "ok"

    def test_fabric_ok_from_1_14(self, make_bench):
        b = make_bench("1.14", OPTS)
        assert slot(b, "fabric")._state == "ok"
        assert slot(b, "fabric").btn.toolTip() == ""

    def test_no_version_all_ok(self, make_bench):
        b = make_bench("", None)
        assert slot(b, "fabric")._state == "ok"
        assert slot(b, "forge")._state == "ok"

    def test_set_state_never_disables(self, make_bench):
        """三种状态都可以点：让用户放进去看到红色原因，比按钮变灰要猜有用。"""
        b = make_bench("1.12.2", OPTS)
        s = slot(b, "optifine")
        for state, why in (("manual", "只认不装"), ("na", "没这个版本"), ("ok", "")):
            s.set_state(state, why)
            assert s._state == state
            assert s.btn.isEnabled() is True
            assert s.btn.toolTip() == why


# ═══════════════════ 版本表 / 信号 ═══════════════════

class TestOptions:
    def test_stale_options_are_dropped(self, make_bench):
        """迟到的版本表（对应别的 mc 版本）必须丢掉，否则会串版本。"""
        b = make_bench("1.12.2", {"forge": ["A"]})
        b.apply_options("1.9", {"forge": ["B"]})
        click(b, "forge")
        assert b.chosen()["forge"] == "A"

    def test_need_options_once_per_version(self, make_bench):
        b = make_bench("", None)
        seen = []
        b.needOptions.connect(seen.append)
        b.set_version("1.12.2")
        b.set_version("1.12.2")         # 同版本不重复请求
        assert seen == ["1.12.2"]
        b.set_version("1.14")
        assert seen == ["1.12.2", "1.14"]

    def test_changing_version_clears_the_bench(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        b.set_version("1.14")
        assert b.chosen() == {}
        assert b.mc_version == "1.14"
        b.apply_options("1.14", OPTS)
        assert b.can_compose() is True   # 又是纯原版

    def test_set_version_force_reruns_even_for_same_version(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        b.set_version("1.12.2", force=True)
        assert b.chosen() == {}


# ═══════════════════ 名字与安装配方 ═══════════════════

class TestNameAndPlan:
    def test_default_name_follows_primary_loader(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        assert b.instance_name() == "1.12.2 · Forge"
        assert b.install_plan()["name"] == b.instance_name()

    def test_custom_name_wins(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        click(b, "forge")
        b.name_edit.setText("  我的 1.12.2 ")
        assert b.instance_name() == "我的 1.12.2"
        assert b.install_plan()["name"] == "我的 1.12.2"

    def test_plan_keys(self, make_bench):
        b = make_bench("1.12.2", OPTS)
        assert set(b.install_plan()) == {
            "loader", "loader_version", "extra_jars", "manual", "name"}


# ═══════════════════ 只读模式 ═══════════════════

class TestReadOnly:
    def test_never_requests_and_always_composes(self, make_bench):
        b = make_bench("1.12.2", OPTS, read_only=True)
        seen = []
        b.needOptions.connect(seen.append)
        b.set_version("1.14")
        assert seen == []
        assert b.can_compose() is True     # 只读模式永远不拦「看」

    def test_state_versions_are_written_into_slots(self, make_bench):
        b = make_bench("", None, read_only=True)
        b.set_read_only_state("1.12.2", {"forge": FORGE_V, "optifine": OPTI_TAG})
        assert b.mc_version == "1.12.2"
        assert slot(b, "forge").version() == FORGE_V
        assert slot(b, "optifine").version() == OPTI_TAG

    def test_state_restores_chosen(self, make_bench):
        """只读合成台必须能把实例的材料读回来。"""
        b = make_bench("", None, read_only=True)
        b.set_read_only_state("1.12.2", {"forge": FORGE_V, "optifine": OPTI_TAG})
        assert b.chosen() == {"forge": FORGE_V, "optifine": OPTI_TAG}

    def test_read_only_slots_ignore_clicks(self, make_bench):
        """只读不等于禁用：能显示选中态，但点了不许变。"""
        b = make_bench("", None, read_only=True)
        b.set_read_only_state("1.12.2", {"forge": FORGE_V})
        slot(b, "forge").btn.click()
        assert b.chosen() == {"forge": FORGE_V}
        b = make_bench("", None, read_only=True)
        b.set_read_only_state("1.12.2", {"forge": FORGE_V, "optifine": OPTI_TAG})
        assert b.chosen() == {"forge": FORGE_V, "optifine": OPTI_TAG}
