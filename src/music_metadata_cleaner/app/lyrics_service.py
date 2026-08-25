"""Lyrics retrieval orchestration."""

from __future__ import annotations

from typing import Protocol

from music_metadata_cleaner.domain.models import Lyrics, LyricsLookup, LyricsResult
from music_metadata_cleaner.providers.lrclib import LRCLIBClient


class LyricsProvider(Protocol):
    def get_lyrics(self, lookup: LyricsLookup) -> LyricsResult | None:
        """Retrieve lyrics for a confirmed song identity."""


class LyricsService:
    """Retrieve lyrics without overwriting existing lyrics automatically."""

    def __init__(self, provider: LyricsProvider) -> None:
        self.provider = provider

    @classmethod
    def for_lrclib(cls, *, user_agent: str) -> "LyricsService":
        return cls(LRCLIBClient(user_agent=user_agent))

    def get_lyrics(
        self,
        lookup: LyricsLookup,
        *,
        existing_lyrics: Lyrics | None = None,
    ) -> LyricsResult | None:
        if existing_lyrics is not None and existing_lyrics.has_text:
            return LyricsResult(
                source="existing",
                plain_lyrics=existing_lyrics.text,
                synced_lyrics=existing_lyrics.text if existing_lyrics.synchronized else None,
                confidence=1.0,
                requires_review=False,
            )

        return self.provider.get_lyrics(lookup)


def build_lrc_export_filename(artist: str, title: str) -> str:
    """Return the conventional LRC filename without writing a file."""

    from music_metadata_cleaner.files.safe_paths import generate_mp3_filename

    return generate_mp3_filename(artist, title).removesuffix(".mp3") + ".lrc"
