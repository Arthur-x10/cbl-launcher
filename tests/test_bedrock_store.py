"""基岩版商店元数据的解析（不联网：把 HTTP 层换成假数据）。"""

import pytest

from core.providers.bedrock import store as S


CATALOG_FIXTURE = {
    "Product": {
        "ProductId": "9NBLGGH2JHXJ",
        "LocalizedProperties": [{
            "ProductTitle": "Minecraft for Windows",
            "ShortDescription": "  探索随机生成的世界  ",
        }],
        "DisplaySkuAvailabilities": [
            {"Sku": {"SkuId": "0011", "LastModifiedDate": "2026-11-06T21:40:56.81Z",
                     "Properties": {"Packages": [
                         {"PackageFormat": "MSIXVC", "MaxDownloadSizeInBytes": 2087247872}]}}},
            {"Sku": {"SkuId": "0017", "LastModifiedDate": "2026-10-01T00:00:00Z",
                     "Properties": {"Packages": [
                         {"PackageFormat": "MSIXVC", "MaxDownloadSizeInBytes": 100}]}}},
        ],
    }
}


@pytest.fixture(autouse=True)
def _clear_cache():
    S._cache = {}
    S._cache_at = 0.0
    yield
    S._cache = {}
    S._cache_at = 0.0


class TestHumanSize:
    @pytest.mark.parametrize("raw,expect", [
        (0, ""), (None, ""), ("x", ""), (-1, ""),
        (512, "512 B"), (2048, "2.00 KB"),
        (2087247872, "1.94 GB"),
    ])
    def test_formats(self, raw, expect):
        assert S.human_size(raw) == expect


class TestFetchInfo:
    def test_parses_catalog(self, monkeypatch):
        monkeypatch.setattr(S, "_get_json", lambda url, timeout=15.0: CATALOG_FIXTURE)
        info = S.fetch_info()
        assert info["product_id"] == "9NBLGGH2JHXJ"
        assert info["title"] == "Minecraft for Windows"
        assert info["description"] == "探索随机生成的世界"
        assert info["size_bytes"] == 2087247872
        assert info["size_text"] == "1.94 GB"
        # 取第一个 SKU 的时间，不被后面的旧时间覆盖
        assert info["updated_date"] == "2026-11-06"
        assert info["sku_ids"] == ["0011", "0017"]
        assert info["package_formats"] == ["MSIXVC"]
        assert info["delivery"] == "store"

    def test_failure_returns_empty_dict(self, monkeypatch):
        import urllib.error
        def boom(url, timeout=15.0):
            raise urllib.error.URLError("no network")
        monkeypatch.setattr(S, "_get_json", boom)
        assert S.fetch_info() == {}

    def test_cached_second_call_does_not_hit_network(self, monkeypatch):
        calls = {"n": 0}
        def counting(url, timeout=15.0):
            calls["n"] += 1
            return CATALOG_FIXTURE
        monkeypatch.setattr(S, "_get_json", counting)
        S.fetch_info()
        S.fetch_info()
        assert calls["n"] == 1

    def test_force_bypasses_cache(self, monkeypatch):
        calls = {"n": 0}
        def counting(url, timeout=15.0):
            calls["n"] += 1
            return CATALOG_FIXTURE
        monkeypatch.setattr(S, "_get_json", counting)
        S.fetch_info()
        S.fetch_info(force=True)
        assert calls["n"] == 2

    def test_falls_back_to_us_market(self, monkeypatch):
        seen = []
        def first_cn_fails(url, timeout=15.0):
            seen.append(url)
            if "market=CN" in url:
                raise OSError("CN 挂了")
            return CATALOG_FIXTURE
        monkeypatch.setattr(S, "_get_json", first_cn_fails)
        info = S.fetch_info()
        assert info["market"] == "US"
        assert len(seen) == 2


class TestOpenStore:
    def test_uris_point_at_the_right_product(self):
        assert "9NBLGGH2JHXJ" in S.STORE_PDP
        assert S.STORE_PDP.startswith("ms-windows-store://")
        assert S.STORE_UPDATES.startswith("ms-windows-store://")
