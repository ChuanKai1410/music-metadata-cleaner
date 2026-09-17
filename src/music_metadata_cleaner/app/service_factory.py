"""Production composition root: SearXNG and plain LRCLIB only."""

import os
from music_metadata_cleaner.app.lyrics_service import LyricsService
from music_metadata_cleaner.app.workflow_service import (
    MusicCleanerWorkflowService,
    ApplySettings,
)
from music_metadata_cleaner.config import (
    app_directory,
    load_config,
    save_config,
    load_runtime_config,
)
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.db.request_cache import RequestCache
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.env_loader import load_dotenv
from music_metadata_cleaner.logging_config import configure_logging
from music_metadata_cleaner.providers.lrclib import LRCLIBClient
from music_metadata_cleaner.providers.search import SearXNGProvider

CONFIG_PATH = app_directory() / "preferences.json"


def create_default_workflow_service() -> MusicCleanerWorkflowService:
    load_dotenv()
    config = load_runtime_config(CONFIG_PATH)
    if not CONFIG_PATH.exists():
        save_config(CONFIG_PATH, config)
    connection = connect_database(config.database_path)
    initialize_schema(connection)
    cache = RequestCache(connection)
    return MusicCleanerWorkflowService(
        search_provider=SearXNGProvider(
            os.environ.get("SEARXNG_URL", "").strip() or config.searxng_url,
            request_cache=cache,
            timeout_seconds=config.search_timeout_seconds,
            cache_ttl_seconds=config.search_cache_ttl_seconds,
        ),
        lyrics_service=LyricsService(
            LRCLIBClient(user_agent=config.user_agent, request_cache=cache)
        ),
        maximum_results=config.maximum_search_results,
        automatic_search=config.automatic_search,
        retrieve_lyrics=config.default_add_lyrics,
        preserve_existing_lyrics=config.preserve_existing_lyrics,
        overwrite_existing_lyrics=config.overwrite_existing_lyrics,
        default_apply_settings=ApplySettings(
            update_id3_metadata=config.default_update_id3_metadata,
            add_lyrics=config.default_add_lyrics,
            rename_file=config.default_rename_file,
            enable_backup=config.enable_backup_before_modification,
        ),
        history_repository=HistoryRepository(connection),
        backup_folder=config.backup_folder_name,
        logger=configure_logging(config.log_path),
    )
