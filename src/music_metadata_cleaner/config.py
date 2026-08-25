"""User configuration for Music Metadata Cleaner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    acoustid_api_key: str = ""
    user_agent: str = "MusicMetadataCleaner/0.1 (local desktop app)"
    default_music_folder: str = ""
    filename_format: str = "{artist} - {title}.mp3"
    artist_language: str = "Original"
    auto_apply_confidence_threshold: int = 95
    enable_backup_before_modification: bool = True
    backup_folder_name: str = "MusicCleaner_Backup"
    database_path: str = "music_metadata_cleaner.sqlite3"
    log_path: str = "logs/application.log"


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = {field.name for field in AppConfig.__dataclass_fields__.values()}
    return AppConfig(**{key: value for key, value in payload.items() if key in allowed})


def save_config(path: str | Path, config: AppConfig) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8")

