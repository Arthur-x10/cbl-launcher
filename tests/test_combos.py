"""core.providers.java.combos 的兼容性数据测试。

锁死的是**已经用官方出处核实过**的行为，不是本项目的偏好：

  · 1.7.10 / 1.12.2 上 Forge + LiteLoader + OptiFine 的三件套必须能装
  · Forge×Fabric（Fabric FAQ 明文 No）、Fabric×Quilt、Forge×NeoForge、
    OptiFine×NeoForge（optifine.net 全站没有 NeoForge 版）必须 blocked
  · Fabric 最小 1.14（1.13.2 上没有），LiteLoader 最大 1.12.2
  · 版本元组不能假设首段是 1（2026 年起是 26.2 这种年代版本号）

数据层一旦写错，合成台（ui/widgets/crafting.py）就会放行一个装不出来的组合，
所以这里逐条钉住，而不是只测「函数能跑」。
"""

import pytest

from core.providers.java import combos


# ═══════════════════ 常量层级 ═══════════════════

def test_level_and_kind_literals():
    """这些字符串是 UI 直接 switch 的字面量（crafting._render_issues、library_page
    过滤 i.level == "blocked"），改值等于改协议。"""
    assert (combos.BLOCKED, combos.WARN, combos.NOTE) == ("blocked", "warn", "note")
    assert (combos.PRIMARY, combos.ADDON, combos.PATCH) == ("primary", "addon", "patch")


# ═══════════════════ 版本比较 ═══════════════════

class TestVersionTuple:
    def test_era_version_first_part_is_not_1(self):
        """"26.2" 是年代版本号：不能假设首段是 1。"""
        assert combos.version_tuple("26.2") == (26, 2)

    def test_three_part_version(self):
        assert combos.version_tuple("1.7.10") == (1, 7, 10)
        assert combos.version_tuple("1.21.11") == (1, 21, 11)

    def test_era_version_sorts_above_legacy(self):
        assert combos.version_tuple("26.2") > combos.version_tuple("1.21.11")
        assert combos.version_tuple("1.7.10") < combos.version_tuple("1.12.2")

    def test_empty_is_zero_tuple(self):
        assert combos.version_tuple("") == (0,)
        assert combos.version_tuple(None) == (0,)

    def test_era_version_actually_drives_range_checks(self):
        """年代版本号必须真的参与范围判断，而不只是能被解析。"""
        assert combos.availability("forge", "26.2") == (True, "")        # Forge 无上下限
        assert combos.availability("liteloader", "26.2")[0] is False     # 26.2 远大于 1.12.2
        assert combos.availability("fabric", "26.2")[0] is True          # 26.2 大于 min 1.14


# ═══════════════════ 加载器清单 ═══════════════════

class TestLoaders:
    def test_kinds_partition(self):
        assert [l.id for l in combos.loaders_of(combos.PRIMARY)] == [
            "forge", "neoforge", "fabric", "quilt"]
        assert [l.id for l in combos.loaders_of(combos.ADDON)] == ["liteloader"]
        assert [l.id for l in combos.loaders_of(combos.PATCH)] == ["optifine"]

    def test_loaders_of_unknown_kind_is_empty(self):
        assert combos.loaders_of("shader") == []

    def test_loader_by_id_covers_all_and_is_identity(self):
        assert set(combos.LOADER_BY_ID) == {l.id for l in combos.LOADERS}
        for loader in combos.LOADERS:
            assert combos.LOADER_BY_ID[loader.id] is loader

    def test_unknown_loader_unavailable(self):
        ok, why = combos.availability("atlauncher", "1.12.2")
        assert ok is False
        assert "atlauncher" in why


# ═══════════════════ 自身可用性（版本范围） ═══════════════════

class TestAvailability:
    @pytest.mark.parametrize("mc,expected", [
        ("1.13.2", False), ("1.13", False), ("1.12.2", False),
        ("1.14", True), ("1.14.4", True), ("1.21.11", True),
    ])
    def test_fabric_min_is_1_14(self, mc, expected):
        ok, why = combos.availability("fabric", mc)
        assert ok is expected
        if not expected:
            assert "1.14" in why

    @pytest.mark.parametrize("mc,expected", [
        ("1.7.10", True), ("1.12", True), ("1.12.2", True),
        ("1.13", False), ("1.20.1", False),
    ])
    def test_liteloader_max_is_1_12_2(self, mc, expected):
        ok, why = combos.availability("liteloader", mc)
        assert ok is expected
        if not expected:
            assert "1.12.2" in why

    def test_neoforge_lower_bound_is_this_launchers_library_limit(self):
        """NeoForge 官方有 1.20.1 的 47.x，是**本启动器安装库**只做到 1.20.2，
        数据里用 limit_note 说明了。1.20.1 上判不可用是已知且有意的限制。"""
        ok, why = combos.availability("neoforge", "1.20.1")
        assert ok is False
        assert "1.20.2" in why
        assert combos.availability("neoforge", "1.20.2")[0] is True
        assert combos.availability("neoforge", "1.21.11")[0] is True

    def test_quilt_min_is_1_14_4(self):
        """Quilt 官方 meta 里最老的一条是 1.14.4，1.14 ~ 1.14.3 不在清单里。"""
        assert combos.availability("quilt", "1.13.2")[0] is False
        assert combos.availability("quilt", "1.14")[0] is False
        assert combos.availability("quilt", "1.14.3")[0] is False
        assert combos.availability("quilt", "1.14.4")[0] is True

    @pytest.mark.parametrize("mc", ["1.7.10", "1.12.2", "1.21.11", "26.2"])
    def test_forge_has_no_bounds(self, mc):
        assert combos.availability("forge", mc) == (True, "")

    @pytest.mark.parametrize("mc", ["1.7.10", "1.12.2", "1.21.11"])
    def test_optifine_has_no_bounds(self, mc):
        assert combos.availability("optifine", mc) == (True, "")


# ═══════════════════ classic 三件套 ═══════════════════

CLASSIC_TRIOS = {
    "1.12.2": {"forge": "14.23.5.2859", "liteloader": "1.12.2", "optifine": "HD_U_G5"},
    "1.7.10": {"forge": "10.13.4.1614", "liteloader": "1.7.10_04", "optifine": "HD_U_E7"},
}


class TestClassicTrio:
    @pytest.mark.parametrize("mc", list(CLASSIC_TRIOS))
    def test_can_install(self, mc):
        """Forge + LiteLoader + OptiFine 是 1.7.10/1.12.2 的经典三件套，必须可装。"""
        issues = combos.check_combo(mc, CLASSIC_TRIOS[mc])
        assert combos.can_install(issues) is True
        assert combos.blocking_issues(issues) == []

    @pytest.mark.parametrize("mc", list(CLASSIC_TRIOS))
    def test_only_warn_and_note_levels(self, mc):
        issues = combos.check_combo(mc, CLASSIC_TRIOS[mc])
        assert {i.level for i in issues} <= {combos.WARN, combos.NOTE}
        assert issues, "三件套应当带出提示（OptiFine 要走 Forge 版等）"


# ═══════════════════ 互斥组合 ═══════════════════

BLOCKED_PAIRS = [
    # (a, b, 两个加载器自身都可用的 mc 版本)
    ("forge", "fabric", "1.20.1"),
    ("fabric", "quilt", "1.20.1"),
    ("forge", "neoforge", "1.21.1"),
    ("optifine", "neoforge", "1.21.1"),
]


class TestBlockedPairs:
    @pytest.mark.parametrize("a,b,mc", BLOCKED_PAIRS,
                             ids=[f"{a}+{b}" for a, b, _ in BLOCKED_PAIRS])
    def test_pair_is_blocked_in_both_dict_orders(self, a, b, mc):
        """选中的字典顺序不该影响判定。"""
        for chosen in ({a: "1.0", b: "2.0"}, {b: "2.0", a: "1.0"}):
            issues = combos.check_combo(mc, chosen)
            blocked = combos.blocking_issues(issues)
            assert blocked, f"{a} + {b} @ {mc} 必须 blocked"
            assert combos.can_install(issues) is False
            assert any(set(i.involving) == {a, b} for i in blocked), \
                f"{a} + {b} 的 blocked 应当指名涉及哪两个加载器"

    @pytest.mark.parametrize("a,b,mc", BLOCKED_PAIRS,
                             ids=[f"{a}+{b}" for a, b, _ in BLOCKED_PAIRS])
    def test_rule_is_order_independent(self, a, b, mc):
        rule = combos.rule_between(a, b)
        assert rule is not None
        assert rule.level == combos.BLOCKED
        assert combos.rule_between(b, a) is rule   # frozenset 键：不分先后

    def test_forge_fabric_cites_fabric_faq(self):
        """Fabric 官方 FAQ 明文 "No"，这是最硬的一条。"""
        rule = combos.rule_between("forge", "fabric")
        assert rule.level == combos.BLOCKED
        assert rule.verified is True
        assert "fabricmc.net" in rule.source

    def test_optifine_neoforge_cites_optifine_downloads(self):
        """optifine.net 全站没有 NeoForge 版。"""
        rule = combos.rule_between("optifine", "neoforge")
        assert rule.level == combos.BLOCKED
        assert rule.verified is True
        assert "optifine.net" in rule.source

    def test_forge_neoforge_rule_mentions_fork(self):
        rule = combos.rule_between("forge", "neoforge")
        assert rule.level == combos.BLOCKED
        assert "NeoForge" in rule.reason

    def test_fabric_quilt_rule(self):
        rule = combos.rule_between("fabric", "quilt")
        assert rule.level == combos.BLOCKED
        assert "Quilt" in rule.reason

    def test_forge_neoforge_also_blocked_on_1_20_1(self):
        """1.20.1 上还有 NeoForge 的 min_mc 挡着 —— 无论如何都不该放行。"""
        issues = combos.check_combo("1.20.1", {"forge": "47.4.0", "neoforge": "20.4.0"})
        assert combos.can_install(issues) is False
        assert any("NeoForge" in i.reason for i in combos.blocking_issues(issues))


# ═══════════════════ verified 标记（决定 UI 用红色断言还是金色提示） ═══════════════════

VERIFIED_PAIRS = [
    ("forge", "fabric"),
    ("optifine", "neoforge"),
    ("optifine", "forge"),
    ("forge", "liteloader"),
    ("liteloader", "optifine"),
]
INFERRED_PAIRS = [
    ("fabric", "quilt"),
    ("forge", "neoforge"),
    ("liteloader", "fabric"),
    ("liteloader", "quilt"),
]


class TestVerifiedFlags:
    @pytest.mark.parametrize("a,b", VERIFIED_PAIRS, ids=[f"{a}+{b}" for a, b in VERIFIED_PAIRS])
    def test_official_rules_carry_source(self, a, b):
        rule = combos.rule_between(a, b)
        assert rule is not None
        assert rule.verified is True
        assert rule.source.startswith("http")
        assert rule.reason

    @pytest.mark.parametrize("a,b", INFERRED_PAIRS, ids=[f"{a}+{b}" for a, b in INFERRED_PAIRS])
    def test_inferred_rules_are_not_verified(self, a, b):
        """从 fork 关系推出来的结论不能标成官方明文（UI 会加「推论」后缀）。"""
        rule = combos.rule_between(a, b)
        assert rule is not None
        assert rule.verified is False


# ═══════════════════ check_combo / 汇总 ═══════════════════

class TestCheckCombo:
    def test_empty_choice_has_no_issues(self):
        assert combos.check_combo("1.12.2", {}) == []

    def test_unknown_keys_are_ignored(self):
        assert combos.check_combo("1.12.2", {"shaders_mod": "1.0"}) == []

    def test_unavailable_loader_becomes_verified_blocked(self):
        issues = combos.check_combo("1.12.2", {"fabric": "0.15.11"})
        blocked = combos.blocking_issues(issues)
        assert len(blocked) == 1
        assert "Fabric" in blocked[0].reason
        assert "1.14" in blocked[0].reason
        assert blocked[0].verified is True      # 版本范围是硬事实，不是推论
        assert blocked[0].involving == ("fabric",)

    def test_optifine_forge_emits_warn_plus_version_note(self):
        issues = combos.check_combo("1.12.2", {"forge": "14.23.5.2859", "optifine": "HD_U_G5"})
        assert combos.can_install(issues) is True
        warns = [i for i in issues if i.level == combos.WARN]
        notes = [i for i in issues
                 if i.level == combos.NOTE and set(i.involving) == {"forge", "optifine"}]
        assert len(warns) == 1
        assert len(notes) == 1
        # 版本级提示要把两边的版本号带出来，UI 直接显示
        assert "14.23.5.2859" in notes[0].hint
        assert "HD_U_G5" in notes[0].hint

    def test_optifine_liteloader_is_note_not_block(self):
        issues = combos.check_combo("1.12.2", {"liteloader": "1.12.2", "optifine": "HD_U_G5"})
        assert combos.can_install(issues) is True
        assert [i.level for i in issues] == [combos.NOTE]

    def test_issue_fields(self):
        issue = combos.Issue(combos.WARN, "原因", "提示", "https://x", True, ("a", "b"))
        assert (issue.level, issue.reason, issue.hint, issue.source,
                issue.verified, issue.involving) == (
            combos.WARN, "原因", "提示", "https://x", True, ("a", "b"))


class TestBlockingHelpers:
    def test_warn_and_note_never_block(self):
        issues = [combos.Issue(combos.WARN, "w"), combos.Issue(combos.NOTE, "n")]
        assert combos.blocking_issues(issues) == []
        assert combos.can_install(issues) is True

    def test_blocked_blocks(self):
        blocked = combos.Issue(combos.BLOCKED, "b")
        assert combos.blocking_issues([blocked]) == [blocked]
        assert combos.can_install([blocked]) is False

    def test_empty_list_can_install(self):
        assert combos.blocking_issues([]) == []
        assert combos.can_install([]) is True


class TestSummarize:
    def test_order_is_primary_addon_patch(self):
        chosen = {"optifine": "HD_U_E7", "liteloader": "1.7.10_04", "forge": "47.4.23"}
        assert combos.summarize(chosen) == "Forge 47.4.23 · LiteLoader 1.7.10_04 · OptiFine HD_U_E7"

    def test_empty(self):
        assert combos.summarize({}) == ""

    def test_unknown_keys_ignored(self):
        assert combos.summarize({"shaders": "x"}) == ""


class TestDefaultName:
    def test_fact_pinned(self):
        assert combos.default_name("1.7.10", {"forge": "47.4.23"}) == "1.7.10 · Forge"

    def test_version_only(self):
        assert combos.default_name("1.12.2", {}) == "1.12.2"

    def test_addon_does_not_join_the_name(self):
        """实例名只跟主加载器走，附加/补丁不进去。"""
        assert combos.default_name("1.12.2", {"liteloader": "1.12.2"}) == "1.12.2"
        assert combos.default_name("1.12.2", {"optifine": "HD_U_G5"}) == "1.12.2"

    def test_primary_wins_in_declared_order(self):
        assert combos.default_name("1.14", {"quilt": "0.26", "fabric": "0.15"}) == "1.14 · Fabric"

    def test_empty_everything(self):
        assert combos.default_name("", {}) == "新实例"


class TestTagFromOptifineJar:
    def test_fact_pinned(self):
        assert combos.tag_from_optifine_jar("C:/dl/OptiFine_1.12.2_HD_U_G5.jar") == "HD_U_G5"

    def test_windows_backslashes(self):
        assert combos.tag_from_optifine_jar(
            r"C:\dl\OptiFine_1.12.2_HD_U_G5.jar") == "HD_U_G5"

    def test_bare_filename(self):
        assert combos.tag_from_optifine_jar("OptiFine_1.7.10_HD_U_E7.jar") == "HD_U_E7"

    def test_era_version_filename(self):
        assert combos.tag_from_optifine_jar(
            "C:/dl/OptiFine_1.21.11_HD_U_K1.jar") == "HD_U_K1"

    def test_not_an_optifine_jar(self):
        """取不出来就返回去扩展名的名字，不撒谎。"""
        assert combos.tag_from_optifine_jar("C:/dl/random.jar") == "random"

    def test_empty(self):
        assert combos.tag_from_optifine_jar("") == ""
        assert combos.tag_from_optifine_jar(None) == ""
