"""Runtime settings and historical-data compatibility for the search-only app."""

from dataclasses import asdict
import json
from pathlib import Path
import sys
from music_metadata_cleaner.app import service_factory
from music_metadata_cleaner.config import (
    AppConfig,
    load_config,
    save_config,
    load_runtime_config,
    app_directory,
)
from music_metadata_cleaner.providers.search import SearXNGProvider


def test_removed_settings_are_ignored(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text(
        json.dumps(
            {
                "audd_api_key": "old",
                "brave_api_key": "old",
                "ffmpeg_path": "old",
                "searxng_url": "http://search.example",
            }
        )
    )
    config = load_config(path)
    assert config.searxng_url == "http://search.example"
    assert not any(
        "key" in key or "token" in key or "ffmpeg" in key for key in asdict(config)
    )


def test_factory_uses_only_searxng_and_preserves_history(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "preferences.json"
    db = tmp_path / "history.sqlite3"
    save_config(
        path,
        AppConfig(
            searxng_url="http://search.example",
            database_path=str(db),
            log_path=str(tmp_path / "app.log"),
        ),
    )
    monkeypatch.setattr(service_factory, "CONFIG_PATH", path)
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    first = service_factory.create_default_workflow_service()
    assert isinstance(first.search_provider, SearXNGProvider)
    assert first.search_provider.base_url == "http://search.example"
    batch = first.history_repository.begin_batch()
    first.close()
    monkeypatch.setenv("SEARXNG_URL", "http://another.example:8888")
    second = service_factory.create_default_workflow_service()
    assert second.search_provider.base_url == "http://another.example:8888"
    assert second.history_repository.list_batches()[0].batch_id == batch
    second.close()


def test_legacy_database_path_reused_without_moving_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old_db = tmp_path / "music_metadata_cleaner.sqlite3"
    old_db.write_bytes(b"untouched")
    config = load_runtime_config(tmp_path / "new" / "preferences.json")
    assert Path(config.database_path) == old_db
    assert old_db.read_bytes() == b"untouched"
    assert not (tmp_path / "new").exists()


def test_legacy_settings_relative_history_is_resolved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/preferences.json").write_text(
        '{"database_path":"data/history.sqlite3", "audd_api_token":"ignored"}'
    )
    config = load_runtime_config(tmp_path / "new/preferences.json")
    assert config.database_path == str(tmp_path / "data/history.sqlite3")


def test_platform_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert app_directory() == tmp_path / "config/MusicMetadataCleaner"
    assert app_directory("cache") == tmp_path / "cache/MusicMetadataCleaner"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert app_directory() == tmp_path / "local/MusicMetadataCleaner"
