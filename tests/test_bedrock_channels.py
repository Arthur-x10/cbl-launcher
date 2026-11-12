"""基岩版其他获取渠道的解析（不联网）。"""

import pytest

from core.providers.bedrock import channels as C


@pytest.fixture(autouse=True)
def _clear_cache():
    C._cache = {}
    yield
    C._cache = {}


class TestResolve:
    def test_follows_aka_redirect_to_real_file(self, monkeypatch):
        monkeypatch.setattr(C, "_resolve", lambda aka, hops=6, timeout=20.0: {
            "url": "https://launcher.mojang.com/download/MinecraftInstaller.msi",
            "file_name": "MinecraftInstaller.msi",
            "size_bytes": 2248704,
        })
        items = C.list_channels()
        msi = next(i for i in items if i["id"] == "launcher_msi")
        assert msi["resolved"] is True
        assert msi["size_text"] == "2.14 MB"
        assert msi["file_name"] == "MinecraftInstaller.msi"

    def test_unresolved_channel_is_kept_but_marked(self, monkeypatch):
        monkeypatch.setattr(C, "_resolve", lambda aka, hops=6, timeout=20.0: {})
        items = C.list_channels()
        assert len(items) == len(C.CHANNELS)
        assert all(i["resolved"] is False for i in items)
        assert all(i["size_text"] == "" for i in items)

    def test_three_downloadable_channels(self):
        ids = [c["id"] for c in C.CHANNELS]
        assert ids == ["launcher_msi", "launcher_exe", "education"]

    def test_links_only_are_not_downloadable(self):
        ids = [c["id"] for c in C.LINKS_ONLY]
        assert "netease" in ids and "google_play" in ids
        assert all(not c.get("aka") for c in C.LINKS_ONLY)


class TestCacheAndLookup:
    def test_second_call_hits_cache(self, monkeypatch):
        calls = {"n": 0}
        def counting(aka, hops=6, timeout=20.0):
            calls["n"] += 1
            return {"url": "https://x/f.exe", "file_name": "f.exe", "size_bytes": 1}
        monkeypatch.setattr(C, "_resolve", counting)
        C.list_channels()
        C.list_channels()
        assert calls["n"] == len(C.CHANNELS)

    def test_force_bypasses_cache(self, monkeypatch):
        calls = {"n": 0}
        def counting(aka, hops=6, timeout=20.0):
            calls["n"] += 1
            return {"url": "https://x/f.exe", "file_name": "f.exe", "size_bytes": 1}
        monkeypatch.setattr(C, "_resolve", counting)
        C.list_channels()
        C.list_channels(force=True)
        assert calls["n"] == 2 * len(C.CHANNELS)

    def test_find_channel(self, monkeypatch):
        monkeypatch.setattr(C, "_resolve", lambda aka, hops=6, timeout=20.0: {
            "url": "https://x/a.exe", "file_name": "a.exe", "size_bytes": 10})
        assert C.find_channel("education")["id"] == "education"
        assert C.find_channel("nope") == {}


class TestDownloadGuard:
    def test_refuses_channel_without_url(self, tmp_path):
        with pytest.raises(ValueError):
            C.download({"id": "x", "url": ""}, str(tmp_path / "a.bin"))

    def test_human_size(self):
        assert C.human_size(2248704) == "2.14 MB"
        assert C.human_size(1249697232) == "1.16 GB"
        assert C.human_size(0) == ""
