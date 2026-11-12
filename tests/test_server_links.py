"""官方 BDS 下载链接的解析（不联网）。"""

import pytest

from core.providers.server import links as L


FIXTURE = {
    "result": {
        "links": [
            {"downloadType": "serverBedrockWindows",
             "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-win/bedrock-server-1.26.63.1.zip"},
            {"downloadType": "serverBedrockPreviewWindows",
             "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-win-preview/bedrock-server-1.26.70.24.zip"},
            {"downloadType": "serverBedrockLinux",
             "downloadUrl": "https://www.minecraft.net/bedrockdedicatedserver/bin-linux/bedrock-server-1.26.63.1.zip"},
            {"downloadType": "serverJar",
             "downloadUrl": "https://piston-data.mojang.com/v1/objects/abc/server.jar"},
        ]
    }
}


@pytest.fixture(autouse=True)
def _clear_cache():
    L._cache = []
    L._cache_at = 0.0
    yield
    L._cache = []
    L._cache_at = 0.0


class TestVersionParsing:
    @pytest.mark.parametrize("url,expect", [
        ("https://x/bedrock-server-1.26.63.1.zip", "1.26.63.1"),
        ("https://x/bedrock-server-1.21.44.1.zip", "1.21.44.1"),
        ("https://x/bedrock-server-1.20.1.zip", "1.20.1"),
        ("https://x/whatever.zip", ""),
        ("", ""),
    ])
    def test_version_of(self, url, expect):
        assert L._version_of(url) == expect


class TestFetchLinks:
    def test_keeps_only_known_kinds(self, monkeypatch):
        monkeypatch.setattr(L, "_get_json", lambda url, timeout=20.0: FIXTURE)
        items = L.fetch_links()
        kinds = {i["kind"] for i in items}
        assert kinds == {"bds", "bds-preview", "bds-linux"}
        assert all(i["version"] for i in items)

    def test_windows_and_preview_are_marked(self, monkeypatch):
        monkeypatch.setattr(L, "_get_json", lambda url, timeout=20.0: FIXTURE)
        by_kind = {i["kind"]: i for i in L.fetch_links()}
        assert by_kind["bds"]["platform"] == "win"
        assert by_kind["bds"]["version"] == "1.26.63.1"
        assert by_kind["bds-preview"]["platform"] == "win"
        assert by_kind["bds-preview"]["version"] == "1.26.70.24"
        assert by_kind["bds-linux"]["platform"] == "linux"

    def test_failure_returns_empty(self, monkeypatch):
        import urllib.error
        def boom(url, timeout=20.0):
            raise urllib.error.URLError("offline")
        monkeypatch.setattr(L, "_get_json", boom)
        assert L.fetch_links() == []

    def test_find_by_version_and_kind(self, monkeypatch):
        monkeypatch.setattr(L, "_get_json", lambda url, timeout=20.0: FIXTURE)
        L.fetch_links()
        assert L.find("1.26.63.1")["kind"] == "bds"
        assert L.find("bds-preview")["version"] == "1.26.70.24"
        assert L.find("9.9.9") == {}


class TestServerProviderRemote:
    def _provider(self, monkeypatch):
        from core.providers.server import ServerProvider
        monkeypatch.setattr(L, "_get_json", lambda url, timeout=20.0: FIXTURE)
        return ServerProvider(ctx=None)

    def test_lists_only_windows_versions(self, monkeypatch):
        p = self._provider(monkeypatch)
        versions = p.list_remote()
        ids = [v.id for v in versions]
        assert "1.26.63.1" in ids
        assert "preview:1.26.70.24" in ids
        assert all("linux" not in v.id for v in versions)

    def test_preview_id_is_resolvable(self, monkeypatch):
        p = self._provider(monkeypatch)
        item = p._bds_item("preview:1.26.70.24")
        assert item["url"].endswith("bedrock-server-1.26.70.24.zip")
        assert p._bds_item("1.26.63.1")["url"].endswith("bedrock-server-1.26.63.1.zip")

    def test_unknown_version_resolves_to_nothing(self, monkeypatch):
        p = self._provider(monkeypatch)
        assert p._bds_item("0.0.1") == {}

    def test_capabilities_advertise_version_list(self, monkeypatch):
        from core.providers.base import CAP_VERSION_LIST
        p = self._provider(monkeypatch)
        assert CAP_VERSION_LIST in p.capabilities()
