"""Canonical metadata enrichment orchestration."""

from __future__ import annotations

from typing import Protocol

from music_metadata_cleaner.domain.models import MusicBrainzMetadata
from music_metadata_cleaner.providers.musicbrainz import MusicBrainzClient


class RecordingMetadataProvider(Protocol):
    def get_recording_metadata(self, recording_id: str) -> MusicBrainzMetadata:
        """Return canonical metadata for a MusicBrainz recording ID."""


class MetadataEnrichmentService:
    """Enrich confirmed MusicBrainz recording IDs without touching local files."""

    def __init__(self, provider: RecordingMetadataProvider) -> None:
        self.provider = provider

    @classmethod
    def for_musicbrainz(cls, *, user_agent: str) -> "MetadataEnrichmentService":
        return cls(MusicBrainzClient(user_agent=user_agent))

    def enrich_musicbrainz_recording(self, recording_id: str) -> MusicBrainzMetadata:
        return self.provider.get_recording_metadata(recording_id)
