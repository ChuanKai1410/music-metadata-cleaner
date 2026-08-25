"""Application service factory."""

from __future__ import annotations

import os

from music_metadata_cleaner.app.audio_identification_service import AudioIdentificationService
from music_metadata_cleaner.app.lyrics_service import LyricsService
from music_metadata_cleaner.app.metadata_enrichment_service import MetadataEnrichmentService
from music_metadata_cleaner.app.workflow_service import MusicCleanerWorkflowService


DEFAULT_USER_AGENT = "MusicMetadataCleaner/0.1 (local desktop app)"


def create_default_workflow_service() -> MusicCleanerWorkflowService:
    """Create a workflow service from optional environment configuration."""

    user_agent = os.environ.get("MUSIC_METADATA_CLEANER_USER_AGENT", DEFAULT_USER_AGENT)
    acoustid_api_key = os.environ.get("ACOUSTID_API_KEY", "")

    identifier = None
    if acoustid_api_key:
        identifier = AudioIdentificationService.for_acoustid(acoustid_api_key)

    return MusicCleanerWorkflowService(
        identifier=identifier,
        metadata_service=MetadataEnrichmentService.for_musicbrainz(user_agent=user_agent),
        lyrics_service=LyricsService.for_lrclib(user_agent=user_agent),
    )

