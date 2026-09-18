"""Cross-platform preferences; obsolete recognition keys are ignored."""

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import sys


def app_directory(kind: str = "config") -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        fallback = Path.home() / (".config" if kind == "config" else ".cache")
        base = Path(
            os.environ.get(
                "XDG_CONFIG_HOME" if kind == "config" else "XDG_CACHE_HOME", fallback
            )
        )
    return base / "MusicMetadataCleaner"


@dataclass(frozen=True)
class AppConfig:
    searxng_url: str = ""
    search_timeout_seconds: int = 10
    search_provider: str = "SearXNG"
    maximum_search_results: int = 8
    automatic_search: bool = True
    search_cache_ttl_seconds: int = 86400
    user_agent: str = "MusicMetadataCleaner/0.9 (local desktop app)"
    default_music_folder: str = ""
    filename_format: str = "{artist} - {title}.mp3"
    artist_language: str = "Original"
    enable_backup_before_modification: bool = True
    backup_folder_name: str = "MusicCleaner_Backup"
    database_path: str = field(
        default_factory=lambda: str(app_directory() / "history.sqlite3")
    )
    log_path: str = field(
        default_factory=lambda: str(app_directory("cache") / "application.log")
    )
    default_update_id3_metadata: bool = True
    default_add_lyrics: bool = True
    preserve_existing_lyrics: bool = True
    overwrite_existing_lyrics: bool = False
    default_rename_file: bool = True


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        return AppConfig()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return AppConfig()
    return AppConfig(
        **{
            key: value
            for key, value in payload.items()
            if key in AppConfig.__dataclass_fields__
        }
    )


def save_config(path: str | Path, config: AppConfig) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_runtime_config(path: str | Path) -> AppConfig:
    """Keep existing installations attached to their history without moving data."""
    from dataclasses import replace

    path = Path(path)
    if path.exists():
        return load_config(path)
    legacy_path = Path.cwd() / "config" / "preferences.json"
    config = load_config(legacy_path) if legacy_path.exists() else AppConfig()
    legacy_db = Path.cwd() / "music_metadata_cleaner.sqlite3"
    if legacy_path.exists():
        raw = json.loads(legacy_path.read_text(encoding="utf-8"))
        db = Path(raw.get("database_path", legacy_db))
        config = replace(
            config,
            database_path=str(db.resolve()),
            log_path=str(Path(config.log_path).resolve()),
        )
    elif legacy_db.exists():
        config = replace(config, database_path=str(legacy_db.resolve()))
    return config
