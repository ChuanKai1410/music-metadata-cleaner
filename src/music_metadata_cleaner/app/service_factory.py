"""Application service factory."""

from __future__ import annotations

import os
from pathlib import Path

from music_metadata_cleaner.audio_segments import check_ffmpeg_available, resolve_ffmpeg_executable
from music_metadata_cleaner.app.audio_identification_service import AudioIdentificationService
from music_metadata_cleaner.app.fallback_recognition_service import FallbackRecognitionService
from music_metadata_cleaner.app.lyrics_service import LyricsService
from music_metadata_cleaner.app.metadata_enrichment_service import MetadataEnrichmentService
from music_metadata_cleaner.app.workflow_service import MusicCleanerWorkflowService
from music_metadata_cleaner.config import AppConfig, load_config, save_config
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.db.request_cache import RequestCache
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.env_loader import load_dotenv
from music_metadata_cleaner.fingerprinting.fpcalc import FpcalcFingerprinter
from music_metadata_cleaner.logging_config import configure_logging
from music_metadata_cleaner.providers.acoustid import AcoustIDClient
from music_metadata_cleaner.providers.audd import AudDClient
from music_metadata_cleaner.providers.lrclib import LRCLIBClient
from music_metadata_cleaner.providers.musicbrainz import MusicBrainzClient
from music_metadata_cleaner.providers.youtube import YouTubeClient


DEFAULT_USER_AGENT = "MusicMetadataCleaner/0.1 (local desktop app)"
CONFIG_PATH = Path("config/preferences.json")


def create_default_workflow_service() -> MusicCleanerWorkflowService:
    """Create a workflow service from optional environment configuration."""

    load_dotenv()
    config = _load_or_create_config()
    user_agent = _env_str("MUSIC_METADATA_CLEANER_USER_AGENT", config.user_agent or DEFAULT_USER_AGENT)
    acoustid_api_key = _env_str("ACOUSTID_API_KEY", config.acoustid_api_key)
    audd_api_token = _env_str("AUDD_API_TOKEN", _env_str("AUDD_API_KEY", config.audd_api_token))
    youtube_api_key = _env_str("YOUTUBE_API_KEY", config.youtube_api_key)
    fpcalc_path = _env_str("FPCALC_PATH", config.fpcalc_path)
    ffmpeg_path = resolve_ffmpeg_executable(_env_str("FFMPEG_PATH", config.ffmpeg_path))
    logger = configure_logging(config.log_path)
    connection = connect_database(config.database_path)
    initialize_schema(connection)
    request_cache = RequestCache(connection)
    ffmpeg_available, resolved_ffmpeg, ffmpeg_status = check_ffmpeg_available(ffmpeg_path)
    logger.info("settings.audd_token_present=%s", bool(audd_api_token))
    audd_token_source = _audd_token_source(audd_api_token, config.audd_api_token)
    logger.info("settings.audd_token_source=%s", audd_token_source)
    logger.info("ffmpeg.source=%s", "configured_path" if ffmpeg_path != "ffmpeg" else "path")
    logger.info("ffmpeg.available=%s", ffmpeg_available)

    identifier = None
    if acoustid_api_key:
        identifier = AudioIdentificationService(
            FpcalcFingerprinter(executable=fpcalc_path),
            AcoustIDClient(acoustid_api_key, request_cache=request_cache),
        )

    youtube_service = YouTubeClient(youtube_api_key, request_cache=request_cache) if youtube_api_key else None
    fallback_recognition_enabled = _fallback_enabled(config, audd_api_token)
    max_segments = _env_int("MUSIC_METADATA_CLEANER_MAX_RECOGNITION_SEGMENTS", config.max_recognition_segments)
    if not _env_bool(
        "MUSIC_METADATA_CLEANER_MULTI_SEGMENT_RECOGNITION_ENABLED",
        config.multi_segment_recognition_enabled,
    ):
        max_segments = 1
    fallback_recognition_service = (
        FallbackRecognitionService(
            AudDClient(audd_api_token),
            ffmpeg_executable=resolved_ffmpeg,
            max_segments=max_segments,
        )
        if audd_api_token and fallback_recognition_enabled
        else None
    )

    return MusicCleanerWorkflowService(
        identifier=identifier,
        metadata_service=MetadataEnrichmentService(MusicBrainzClient(user_agent=user_agent, request_cache=request_cache)),
        lyrics_service=LyricsService(LRCLIBClient(user_agent=user_agent, request_cache=request_cache)),
        youtube_service=youtube_service,
        fallback_recognition_service=fallback_recognition_service,
        fallback_recognition_enabled=fallback_recognition_enabled,
        fallback_recognition_threshold=_env_int(
            "MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_THRESHOLD",
            config.fallback_recognition_threshold,
        ),
        fallback_verify_medium_confidence=_env_bool(
            "MUSIC_METADATA_CLEANER_FALLBACK_VERIFY_MEDIUM_CONFIDENCE",
            config.fallback_verify_medium_confidence,
        ),
        always_use_youtube_verification=_env_bool(
            "MUSIC_METADATA_CLEANER_ALWAYS_USE_YOUTUBE_VERIFICATION",
            config.always_use_youtube_verification,
        ),
        youtube_search_below_confidence=_env_int(
            "MUSIC_METADATA_CLEANER_YOUTUBE_SEARCH_BELOW_CONFIDENCE",
            config.youtube_search_below_confidence,
        ),
        audd_token_present=bool(audd_api_token),
        audd_token_source=audd_token_source,
        ffmpeg_executable=resolved_ffmpeg,
        ffmpeg_available=ffmpeg_available,
        ffmpeg_status=ffmpeg_status,
        youtube_configured=bool(youtube_api_key),
        history_repository=HistoryRepository(connection),
        backup_folder=config.backup_folder_name if config.enable_backup_before_modification else None,
        logger=logger,
    )


def _load_or_create_config() -> AppConfig:
    config = load_config(CONFIG_PATH)
    if not CONFIG_PATH.exists():
        save_config(CONFIG_PATH, config)
    return config


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env_bool_explicit(name: str) -> bool | None:
    value = os.environ.get(name)
    if value is None:
        return None
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _fallback_enabled(config: AppConfig, audd_api_token: str) -> bool:
    explicit = _env_bool_explicit("MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED")
    if explicit is not None:
        return explicit
    return config.fallback_recognition_enabled or bool(audd_api_token)


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def _env_source(env_name: str, config_name: str, effective_value: str, config_value: str) -> str:
    if os.environ.get(env_name, "").strip():
        return "Environment"
    if effective_value and config_value:
        return "Application settings"
    return "None"


def _audd_token_source(effective_value: str, config_value: str) -> str:
    if os.environ.get("AUDD_API_TOKEN", "").strip():
        return "Environment"
    if os.environ.get("AUDD_API_KEY", "").strip():
        return "Environment legacy AUDD_API_KEY"
    if effective_value and config_value:
        return "Application settings"
    return "None"
