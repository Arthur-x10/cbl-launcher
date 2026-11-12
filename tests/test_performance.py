"""JVM / 内存自动调优。纯函数，不碰系统。"""

import pytest

from core import performance as P


def prof(**kw):
    base = dict(total_ram_mb=16384, cpu_cores=8, mc_version="1.20.1",
                loader="", mod_count=0, java_major=17)
    base.update(kw)
    return P.Profile(**base)


class TestRamTiers:
    def test_vanilla_smaller_than_modded(self):
        vanilla = P.calc_ram(prof(mod_count=0))[1]
        light = P.calc_ram(prof(mod_count=10))[1]
        heavy = P.calc_ram(prof(mod_count=200))[1]
        assert vanilla < light < heavy

    def test_more_mods_more_ram(self):
        values = [P.calc_ram(prof(mod_count=n))[1] for n in (0, 10, 50, 120, 300)]
        assert values == sorted(values)
        assert len(set(values)) >= 4

    def test_old_versions_are_capped(self):
        old = P.calc_ram(prof(mc_version="1.12.2", mod_count=300))[1]
        new = P.calc_ram(prof(mc_version="1.21.1", mod_count=300))[1]
        assert old <= P.LEGACY_CAP_MB
        assert new >= old

    def test_never_exceeds_half_the_machine(self):
        small = P.calc_ram(prof(total_ram_mb=8192, mod_count=300))[1]
        assert small <= 4096
        huge = P.calc_ram(prof(total_ram_mb=65536, mod_count=300))[1]
        assert huge <= P.HARD_MAX_MB

    def test_min_is_half_of_max_and_on_256_grid(self):
        for mods in (0, 10, 50, 120, 300):
            mn, mx, _ = P.calc_ram(prof(mod_count=mods))
            assert mn == max(512, mx // 2) or mn >= 512
            assert mx % 256 == 0 and mn % 256 == 0

    def test_loader_costs_a_bit(self):
        plain = P.calc_ram(prof(mod_count=30, loader=""))[1]
        forge = P.calc_ram(prof(mod_count=30, loader="forge"))[1]
        assert forge > plain

    def test_notes_explain_why(self):
        _mn, _mx, notes = P.calc_ram(prof(mod_count=120, loader="forge"))
        assert notes
        assert any("mod" in n for n in notes)


class TestArgs:
    def test_flags_never_disable_explicit_gc(self):
        """Netty 靠 System.gc() 回收直接内存，禁了会 native 内存泄漏。"""
        for java in (8, 11, 17, 21):
            args, _ = P.build_args(prof(java_major=java, mod_count=100))
            assert not any("DisableExplicitGC" in a for a in args)

    def test_xms_xmx_match_calc(self):
        p = prof(mod_count=60)
        mn, mx, _ = P.calc_ram(p)
        args, _ = P.build_args(p)
        assert "-Xms%dM" % mn in args
        assert "-Xmx%dM" % mx in args

    def test_java8_gets_no_experimental_g1_percentages(self):
        args, _ = P.build_args(prof(java_major=8, mod_count=60))
        assert not any("G1NewSizePercent" in a for a in args)
        assert not any("UnlockExperimentalVMOptions" in a for a in args)

    def test_java11_plus_gets_them(self):
        args, notes = P.build_args(prof(java_major=17, mod_count=60))
        assert "-XX:+UnlockExperimentalVMOptions" in args
        assert any("G1NewSizePercent" in a for a in args)
        assert notes

    def test_pre_touch_only_for_big_heaps(self):
        small, _ = P.build_args(prof(total_ram_mb=8192, mod_count=0))
        big, _ = P.build_args(prof(total_ram_mb=32768, mod_count=200, mc_version="1.21.1"))
        assert not any("AlwaysPreTouch" in a for a in small)
        assert any("AlwaysPreTouch" in a for a in big)

    def test_forge_flags_only_for_forge_family(self):
        fabric, _ = P.build_args(prof(loader="fabric", mod_count=10))
        forge, _ = P.build_args(prof(loader="forge", mod_count=10))
        assert not any("fml.ignoreInvalidMinecraftCertificates" in a for a in fabric)
        assert any("fml.ignoreInvalidMinecraftCertificates" in a for a in forge)


class TestPreviewAndCompat:
    def test_preview_rows_are_sane(self):
        rows = P.preview_rows(16384, 8)
        assert len(rows) == 5
        by_label = {label: (mn, mx) for label, mn, mx in rows}
        # 新版本原版比老版本原版要多一点（1.13+ 本身更吃内存）
        assert by_label["原版（新版本）"][1] > by_label["原版（老版本）"][1]
        # 整合包越大给得越多；且都落在合理区间
        assert by_label["大型整合"][1] > by_label["中量整合"][1] > by_label["轻量整合"][1]
        for _label, mn, mx in rows:
            assert 512 <= mn <= mx <= P.HARD_MAX_MB

    def test_legacy_helpers_still_work(self):
        mn, mx = P.calc_optimal_ram(16384, has_mods=True)
        assert 512 <= mn <= mx
        args = P.generate_jvm_args(16384, 8, has_mods=True, java_major=17)
        assert any(a.startswith("-Xmx") for a in args)

    def test_explain_is_human_readable(self):
        text = P.explain(prof(mod_count=42, loader="forge", mc_version="1.12.2"))
        assert "内存" in text and "mod" in text


class TestModCounting:
    def test_counts_only_jars_up_to_depth_2(self, tmp_path):
        mods = tmp_path / "mods"
        (mods / "1.7.10").mkdir(parents=True)
        (mods / "a.jar").write_bytes(b"x")
        (mods / "b.jar").write_bytes(b"x")
        (mods / "readme.txt").write_bytes(b"x")
        (mods / "1.7.10" / "c.jar").write_bytes(b"x")
        deep = mods / "x" / "y" / "z"
        deep.mkdir(parents=True)
        (deep / "d.jar").write_bytes(b"x")
        assert P.count_mod_jars(str(mods)) == 3

    def test_missing_dir_is_zero(self):
        assert P.count_mod_jars("", "C:/definitely/not/here") == 0
