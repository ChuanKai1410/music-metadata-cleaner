"""Core domain models for local MP3 metadata workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CoverArt:
    """Embedded cover artwork extracted from or prepared for ID3 tags."""

    mime_type: str
    data: bytes
    description: str = ""


@dataclass(frozen=True)
class Lyrics:
    """Lyrics metadata stored in an MP3 or proposed for writing."""

    text: str | None = None
    language: str = "und"
    description: str = ""
    synchronized: bool = False

    @property
    def has_text(self) -> bool:
        return bool(self.text and self.text.strip())


@dataclass(frozen=True)
class TrackMetadata:
    """User-visible MP3 metadata fields supported by the local adapter."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    release_date: str | None = None
    track_number: str | None = None
    cover_art: CoverArt | None = None
    lyrics: Lyrics | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def has_filename_identity(self) -> bool:
        return bool(self.artist and self.artist.strip() and self.title and self.title.strip())


@dataclass(frozen=True)
class LocalMp3File:
    """A discovered local MP3 and its currently readable metadata."""

    path: Path
    metadata: TrackMetadata


@dataclass(frozen=True)
class MetadataUpdate:
    """Confirmed metadata values to write to an MP3 file."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    release_date: str | None = None
    track_number: str | None = None
    cover_art: CoverArt | None = None
    lyrics: Lyrics | None = None


@dataclass(frozen=True)
class DryRunResult:
    """Read-only preview data for a local MP3."""

    path: Path
    metadata: TrackMetadata
    proposed_filename: str | None
    proposed_path: Path | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class AudioFingerprint:
    """Chromaprint fingerprint data for an audio file."""

    duration: int
    fingerprint: str


@dataclass(frozen=True)
class CandidateRecording:
    """Normalized recording candidate returned by audio identification."""

    recording_id: str
    artist: str | None
    title: str | None
    duration: int | None
    acoustid_score: float
    musicbrainz_recording_id: str | None = None
