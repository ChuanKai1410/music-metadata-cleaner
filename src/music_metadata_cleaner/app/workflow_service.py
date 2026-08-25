"""GUI-facing workflow orchestration for batch processing."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Protocol

from music_metadata_cleaner.app.lyrics_service import build_lrc_export_filename
from music_metadata_cleaner.domain.models import (
    CandidateRecording,
    Lyrics,
    LyricsLookup,
    LyricsResult,
    MetadataUpdate,
    MusicBrainzMetadata,
    ProposedTrackChanges,
    TrackMetadata,
)
from music_metadata_cleaner.files.safe_paths import generate_mp3_filename
from music_metadata_cleaner.files.scanner import discover_mp3_files
from music_metadata_cleaner.id3.reader import read_id3_metadata
from music_metadata_cleaner.id3.writer import write_id3_metadata


class IdentifierService(Protocol):
    def identify(self, path: str | Path) -> list[CandidateRecording]:
        """Identify candidate recordings for a local MP3."""


class MetadataService(Protocol):
    def enrich_musicbrainz_recording(self, recording_id: str) -> MusicBrainzMetadata:
        """Return canonical metadata for a confirmed MusicBrainz recording."""


class LyricsLookupService(Protocol):
    def get_lyrics(self, lookup: LyricsLookup, *, existing_lyrics: Lyrics | None = None) -> LyricsResult | None:
        """Return existing or online lyrics."""


@dataclass(frozen=True)
class ApplySettings:
    update_id3_metadata: bool = True
    update_title: bool = True
    update_artist: bool = True
    update_album: bool = True
    add_cover_art: bool = False
    add_lyrics: bool = True
    export_lrc: bool = False
    rename_file: bool = False


@dataclass(frozen=True)
class WorkflowTrack:
    path: Path
    current_metadata: TrackMetadata
    proposed: ProposedTrackChanges | None = None
    confidence_score: int = 0
    metadata_status: str = "Not processed"
    lyrics_status: str = "Not checked"
    cover_status: str = "Not checked"
    processing_status: str = "Pending"
    requires_review: bool = False
    error_message: str | None = None
    selected: bool = True


@dataclass(frozen=True)
class BatchProgress:
    processed: int
    total: int
    current_path: Path | None
    message: str


@dataclass(frozen=True)
class ApplyResult:
    path: Path
    success: bool
    message: str


class CancellationToken:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class MusicCleanerWorkflowService:
    """Application service used by the desktop UI."""

    def __init__(
        self,
        *,
        identifier: IdentifierService | None = None,
        metadata_service: MetadataService | None = None,
        lyrics_service: LyricsLookupService | None = None,
        metadata_reader: Callable[[str | Path], TrackMetadata] = read_id3_metadata,
        metadata_writer: Callable[[str | Path, MetadataUpdate], None] | None = None,
    ) -> None:
        self.identifier = identifier
        self.metadata_service = metadata_service
        self.lyrics_service = lyrics_service
        self.metadata_reader = metadata_reader
        self.metadata_writer = metadata_writer or self._write_metadata

    def discover(self, paths: list[str | Path]) -> list[WorkflowTrack]:
        tracks: list[WorkflowTrack] = []
        seen: set[Path] = set()

        for path in paths:
            for mp3_path in discover_mp3_files(path):
                resolved = mp3_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    metadata = self.metadata_reader(mp3_path)
                    tracks.append(WorkflowTrack(path=mp3_path, current_metadata=metadata))
                except Exception:
                    tracks.append(
                        WorkflowTrack(
                            path=mp3_path,
                            current_metadata=TrackMetadata(),
                            metadata_status="Failed",
                            processing_status="Invalid MP3",
                            error_message="The MP3 metadata could not be read.",
                        )
                    )

        return tracks

    def process_tracks(
        self,
        tracks: list[WorkflowTrack],
        *,
        cancellation_token: CancellationToken | None = None,
        progress_callback: Callable[[BatchProgress], None] | None = None,
    ) -> list[WorkflowTrack]:
        processed_tracks: list[WorkflowTrack] = []
        total = len(tracks)

        for index, track in enumerate(tracks, start=1):
            if cancellation_token is not None and cancellation_token.cancelled:
                processed_tracks.append(replace(track, processing_status="Cancelled"))
                continue

            if progress_callback is not None:
                progress_callback(BatchProgress(index - 1, total, track.path, "Processing"))

            processed_tracks.append(self.process_track(track))

            if progress_callback is not None:
                progress_callback(BatchProgress(index, total, track.path, "Processed"))

        return processed_tracks

    def process_track(self, track: WorkflowTrack) -> WorkflowTrack:
        try:
            candidate = self._best_candidate(track)
            if candidate is None:
                return self._fallback_from_current_tags(track, "No metadata found")

            metadata = self._metadata_for_candidate(candidate)
            lyrics = self._lyrics_for_metadata(metadata, track.current_metadata.lyrics)
            proposed = self._build_proposed_changes(metadata, lyrics)
            confidence = self._confidence_from_candidate(candidate, lyrics)
            requires_review = confidence < 90 or (lyrics.requires_review if lyrics is not None else False)

            return replace(
                track,
                proposed=proposed,
                confidence_score=confidence,
                metadata_status="Found",
                lyrics_status=self._lyrics_status(lyrics),
                cover_status=proposed.cover_source or "Not found",
                processing_status="Needs review" if requires_review else "Ready",
                requires_review=requires_review,
                error_message=None,
            )
        except Exception as exc:
            return replace(
                track,
                metadata_status="Failed",
                processing_status=self._friendly_error(exc),
                error_message=self._friendly_error(exc),
            )

    def apply_tracks(self, tracks: list[WorkflowTrack], settings: ApplySettings) -> list[ApplyResult]:
        results: list[ApplyResult] = []
        for track in tracks:
            if track.proposed is None:
                results.append(ApplyResult(track.path, False, "No previewed changes are available."))
                continue
            if track.requires_review and track.confidence_score < 70:
                results.append(ApplyResult(track.path, False, "Low-confidence changes require manual review."))
                continue

            try:
                self._apply_track(track, settings)
            except Exception as exc:
                results.append(ApplyResult(track.path, False, self._friendly_error(exc)))
            else:
                results.append(ApplyResult(track.path, True, "Applied selected changes."))

        return results

    def _best_candidate(self, track: WorkflowTrack) -> CandidateRecording | None:
        if self.identifier is None:
            return None

        candidates = self.identifier.identify(track.path)
        if not candidates:
            return None

        return max(candidates, key=lambda candidate: candidate.acoustid_score)

    def _metadata_for_candidate(self, candidate: CandidateRecording) -> MusicBrainzMetadata:
        recording_id = candidate.musicbrainz_recording_id or candidate.recording_id
        if self.metadata_service is not None and recording_id:
            return self.metadata_service.enrich_musicbrainz_recording(recording_id)

        from music_metadata_cleaner.domain.models import MusicBrainzIdentifiers

        return MusicBrainzMetadata(
            artist=candidate.artist,
            title=candidate.title,
            album=None,
            release_date=None,
            track_number=None,
            duration=candidate.duration,
            identifiers=MusicBrainzIdentifiers(recording_id=recording_id),
        )

    def _lyrics_for_metadata(self, metadata: MusicBrainzMetadata, existing_lyrics: Lyrics | None) -> LyricsResult | None:
        if self.lyrics_service is None or not metadata.artist or not metadata.title:
            return LyricsResult(source="existing", plain_lyrics=existing_lyrics.text) if existing_lyrics else None

        return self.lyrics_service.get_lyrics(
            LyricsLookup(
                artist=metadata.artist,
                title=metadata.title,
                album=metadata.album,
                duration=metadata.duration,
            ),
            existing_lyrics=existing_lyrics,
        )

    def _build_proposed_changes(
        self,
        metadata: MusicBrainzMetadata,
        lyrics: LyricsResult | None,
    ) -> ProposedTrackChanges:
        filename = generate_mp3_filename(metadata.artist, metadata.title) if metadata.artist and metadata.title else None
        return ProposedTrackChanges(
            artist=metadata.artist,
            title=metadata.title,
            album=metadata.album,
            release_date=metadata.release_date,
            track_number=metadata.track_number,
            duration=metadata.duration,
            filename=filename,
            lyrics=lyrics,
            cover_source="Not implemented",
            musicbrainz_recording_id=metadata.identifiers.recording_id,
        )

    def _fallback_from_current_tags(self, track: WorkflowTrack, status: str) -> WorkflowTrack:
        metadata = track.current_metadata
        filename = generate_mp3_filename(metadata.artist, metadata.title) if metadata.artist and metadata.title else None
        proposed = ProposedTrackChanges(
            artist=metadata.artist,
            title=metadata.title,
            album=metadata.album,
            release_date=metadata.release_date,
            track_number=metadata.track_number,
            filename=filename,
            lyrics=LyricsResult(source="existing", plain_lyrics=metadata.lyrics.text) if metadata.lyrics else None,
            cover_source="Existing" if metadata.cover_art else "Not found",
        )
        return replace(
            track,
            proposed=proposed,
            confidence_score=0,
            metadata_status=status,
            lyrics_status="Existing" if metadata.lyrics and metadata.lyrics.has_text else "Missing",
            cover_status="Existing" if metadata.cover_art else "Not found",
            processing_status="Needs review",
            requires_review=True,
        )

    def _apply_track(self, track: WorkflowTrack, settings: ApplySettings) -> None:
        proposed = track.proposed
        if proposed is None:
            return

        if settings.update_id3_metadata:
            self.metadata_writer(
                track.path,
                MetadataUpdate(
                    title=proposed.title if settings.update_title else None,
                    artist=proposed.artist if settings.update_artist else None,
                    album=proposed.album if settings.update_album else None,
                    release_date=proposed.release_date,
                    track_number=proposed.track_number,
                    lyrics=(
                        Lyrics(text=proposed.lyrics.plain_lyrics)
                        if settings.add_lyrics and proposed.lyrics is not None and proposed.lyrics.source == "online"
                        else None
                    ),
                ),
            )

        if settings.export_lrc and proposed.lyrics is not None and proposed.lyrics.has_synced_lyrics:
            lrc_path = track.path.with_name(build_lrc_export_filename(proposed.artist or "Unknown", proposed.title or "Unknown"))
            if lrc_path.exists():
                raise FileExistsError("The .lrc export file already exists.")
            lrc_path.write_text(proposed.lyrics.synced_lyrics or "", encoding="utf-8")

        if settings.rename_file and proposed.filename:
            target = track.path.with_name(proposed.filename)
            if target.exists() and target.resolve() != track.path.resolve():
                raise FileExistsError("The target filename already exists.")
            if target.resolve() != track.path.resolve():
                track.path.rename(target)

    def _confidence_from_candidate(self, candidate: CandidateRecording, lyrics: LyricsResult | None) -> int:
        confidence = round(candidate.acoustid_score * 100)
        if lyrics is not None and lyrics.requires_review:
            confidence = min(confidence, round(lyrics.confidence * 100))
        return max(0, min(100, confidence))

    def _lyrics_status(self, lyrics: LyricsResult | None) -> str:
        if lyrics is None:
            return "Unavailable"
        if lyrics.source == "existing":
            return "Existing"
        if lyrics.requires_review:
            return "Review"
        if lyrics.has_plain_lyrics or lyrics.has_synced_lyrics:
            return "Found"
        if lyrics.instrumental:
            return "Instrumental"
        return "Unavailable"

    def _friendly_error(self, exc: Exception) -> str:
        text = exc.__class__.__name__
        lowered = text.lower()
        if "timeout" in lowered:
            return "The network request timed out."
        if "rate" in lowered:
            return "The service is rate limited. Try again later."
        if "fpcalc" in lowered or "fingerprint" in lowered:
            return "The audio fingerprint tool is unavailable or failed."
        if isinstance(exc, FileExistsError):
            return str(exc)
        return "Processing failed for this file."

    @staticmethod
    def _write_metadata(path: str | Path, update: MetadataUpdate) -> None:
        write_id3_metadata(path, update, overwrite_lyrics=False)
