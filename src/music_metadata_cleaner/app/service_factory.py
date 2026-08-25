"""Application service factory."""

from __future__ import annotations

import os
from pathlib import Path

from music_metadata_cleaner.app.audio_identification_service import AudioIdentificationService
from music_metadata_cleaner.app.lyrics_service import LyricsService
from music_metadata_cleaner.app.metadata_enrichment_service import MetadataEnrichmentService
from music_metadata_cleaner.app.workflow_service import MusicCleanerWorkflowService
from music_metadata_cleaner.config import AppConfig, load_config, save_config
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.db.request_cache import RequestCache
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.fingerprinting.fpcalc import FpcalcFingerprinter
from music_metadata_cleaner.logging_config import configure_logging
from music_metadata_cleaner.providers.acoustid import AcoustIDClient
from music_metadata_cleaner.providers.lrclib import LRCLIBClient
from music_metadata_cleaner.providers.musicbrainz import MusicBrainzClient


DEFAULT_USER_AGENT = "MusicMetadataCleaner/0.1 (local desktop app)"
CONFIG_PATH = Path("config/preferences.json")


def create_default_workflow_service() -> MusicCleanerWorkflowService:
    """Create a workflow service from optional environment configuration."""

    config = _load_or_create_config()
    user_agent = os.environ.get("MUSIC_METADATA_CLEANER_USER_AGENT", config.user_agent or DEFAULT_USER_AGENT)
    acoustid_api_key = os.environ.get("ACOUSTID_API_KEY", config.acoustid_api_key)
    fpcalc_path = os.environ.get("FPCALC_PATH", config.fpcalc_path)
    logger = configure_logging(config.log_path)
    connection = connect_database(config.database_path)
    initialize_schema(connection)
    request_cache = RequestCache(connection)

    identifier = None
    if acoustid_api_key:
        identifier = AudioIdentificationService(
            FpcalcFingerprinter(executable=fpcalc_path),
            AcoustIDClient(acoustid_api_key, request_cache=request_cache),
        )

    return MusicCleanerWorkflowService(
        identifier=identifier,
        metadata_service=MetadataEnrichmentService(MusicBrainzClient(user_agent=user_agent, request_cache=request_cache)),
        lyrics_service=LyricsService(LRCLIBClient(user_agent=user_agent, request_cache=request_cache)),
        history_repository=HistoryRepository(connection),
        backup_folder=config.backup_folder_name if config.enable_backup_before_modification else None,
        logger=logger,
    )


def _load_or_create_config() -> AppConfig:
    config = load_config(CONFIG_PATH)
    if not CONFIG_PATH.exists():
        save_config(CONFIG_PATH, config)
    return config
