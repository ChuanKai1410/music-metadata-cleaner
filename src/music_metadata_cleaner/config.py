"""User configuration for Music Metadata Cleaner."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    acoustid_api_key: str = ""
    audd_api_token: str = ""
    youtube_api_key: str = ""
    user_agent: str = "MusicMetadataCleaner/0.1 (local desktop app)"
    default_music_folder: str = ""
    filename_format: str = "{artist} - {title}.mp3"
    artist_language: str = "Original"
    auto_apply_confidence_threshold: int = 95
    enable_backup_before_modification: bool = True
    backup_folder_name: str = "MusicCleaner_Backup"
    database_path: str = "music_metadata_cleaner.sqlite3"
    log_path: str = "logs/application.log"
    fpcalc_path: str = "fpcalc"
    ffmpeg_path: str = "ffmpeg"
    fallback_recognition_enabled: bool = False
    fallback_recognition_threshold: int = 70
    fallback_verify_medium_confidence: bool = False
    multi_segment_recognition_enabled: bool = True
    max_recognition_segments: int = 3
    always_use_youtube_verification: bool = False
    youtube_search_below_confidence: int = 90
    default_update_id3_metadata: bool = True
    default_add_lyrics: bool = True
    default_export_lrc: bool = False
    default_rename_file: bool = True


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload = _normalize_config_payload(payload)
    allowed = {field.name for field in AppConfig.__dataclass_fields__.values()}
    return AppConfig(**{key: value for key, value in payload.items() if key in allowed})


def save_config(path: str | Path, config: AppConfig) -> None:
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(asdict(config), indent=2, ensure_ascii=False), encoding="utf-8")


def _normalize_config_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {}

    normalized = dict(payload)
    aliases = {
        "audd_api_key": "audd_api_token",
        "audd_token": "audd_api_token",
        "AUDD_API_KEY": "audd_api_token",
        "AUDD_API_TOKEN": "audd_api_token",
        "ffmpeg_executable": "ffmpeg_path",
        "FFMPEG_PATH": "ffmpeg_path",
    }
    for old_key, canonical_key in aliases.items():
        if canonical_key not in normalized and old_key in normalized:
            normalized[canonical_key] = normalized[old_key]
    return normalized
