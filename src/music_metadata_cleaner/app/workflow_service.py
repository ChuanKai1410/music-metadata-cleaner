"""GUI-facing workflow orchestration for batch processing."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from pathlib import Path
from typing import Callable, Protocol

from music_metadata_cleaner.app.lyrics_service import build_lrc_export_filename
from music_metadata_cleaner.db.history import HistoryRepository, OperationRecord
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
from music_metadata_cleaner.files.backup import create_backup, restore_backup
from music_metadata_cleaner.files.safe_paths import generate_mp3_filename
from music_metadata_cleaner.files.scanner import discover_mp3_files
from music_metadata_cleaner.id3.reader import read_id3_metadata
from music_metadata_cleaner.id3.snapshot import restore_id3_metadata
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
    enable_backup: bool = True


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
        metadata_restorer: Callable[[str | Path, TrackMetadata], None] = restore_id3_metadata,
        history_repository: HistoryRepository | None = None,
        backup_folder: str | Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.identifier = identifier
        self.metadata_service = metadata_service
        self.lyrics_service = lyrics_service
        self.metadata_reader = metadata_reader
        self.metadata_writer = metadata_writer or self._write_metadata
        self.metadata_restorer = metadata_restorer
        self.history_repository = history_repository
        self.backup_folder = Path(backup_folder) if backup_folder is not None else None
        self.logger = logger or logging.getLogger("music_metadata_cleaner")

    def discover(self, paths: list[str | Path]) -> list[WorkflowTrack]:
        tracks: list[WorkflowTrack] = []
        seen: set[Path] = set()

        for path in paths:
            self.logger.info("Scanning path: %s", path)
            for mp3_path in discover_mp3_files(path):
                resolved = mp3_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    metadata = self.metadata_reader(mp3_path)
                    tracks.append(WorkflowTrack(path=mp3_path, current_metadata=metadata))
                except Exception:
                    self.logger.exception("Failed to read MP3 metadata: %s", mp3_path)
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
                self.logger.info("No metadata candidate found: %s", track.path)
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
            self.logger.exception("Processing failed for %s", track.path)
            return replace(
                track,
                metadata_status="Failed",
                processing_status=self._friendly_error(exc),
                error_message=self._friendly_error(exc),
            )

    def apply_tracks(self, tracks: list[WorkflowTrack], settings: ApplySettings) -> list[ApplyResult]:
        results: list[ApplyResult] = []
        if self.history_repository is None:
            return [ApplyResult(track.path, False, "History database is required before modifying files.") for track in tracks]

        batch_id = self.history_repository.begin_batch()
        for track in tracks:
            if track.proposed is None:
                results.append(ApplyResult(track.path, False, "No previewed changes are available."))
                continue
            if track.requires_review and track.confidence_score < 70:
                results.append(ApplyResult(track.path, False, "Low-confidence changes require manual review."))
                continue

            try:
                operation_id = self._create_history_record(batch_id, track, settings)
                self._apply_track(track, settings, operation_id)
            except Exception as exc:
                self.logger.exception("Apply failed for %s", track.path)
                results.append(ApplyResult(track.path, False, self._friendly_error(exc)))
            else:
                results.append(ApplyResult(track.path, True, "Applied selected changes."))

        self.history_repository.mark_batch(batch_id, "applied" if all(result.success for result in results) else "partial")
        return results

    def list_operations(self, limit: int = 100) -> list[OperationRecord]:
        if self.history_repository is None:
            return []
        return self.history_repository.list_operations(limit)

    def undo_last_batch(self) -> list[ApplyResult]:
        if self.history_repository is None:
            return []
        batch_id = self.history_repository.latest_applied_batch_id()
        if batch_id is None:
            return []

        results: list[ApplyResult] = []
        for operation in self.history_repository.operations_for_batch(batch_id):
            current_path = operation.file_path.with_name(operation.new_filename) if operation.new_filename else operation.file_path
            try:
                if not current_path.exists():
                    raise FileNotFoundError("The modified file could not be found for undo.")
                self.metadata_restorer(current_path, operation.original_metadata)
                original_path = operation.file_path.with_name(operation.original_filename)
                if current_path.resolve() != original_path.resolve():
                    if original_path.exists():
                        raise FileExistsError("The original filename already exists; undo stopped.")
                    current_path.rename(original_path)
                self.history_repository.mark_operation(operation.operation_id, "undone")
                results.append(ApplyResult(original_path, True, "Undo restored original metadata and filename."))
                self.logger.info("Undo restored %s", original_path)
            except Exception as exc:
                self.history_repository.mark_operation(operation.operation_id, "undo_failed", self._friendly_error(exc))
                results.append(ApplyResult(current_path, False, self._friendly_error(exc)))
                self.logger.exception("Undo failed for %s", current_path)
        self.history_repository.mark_batch(batch_id, "undone" if all(result.success for result in results) else "undo_partial")
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

    def _create_history_record(self, batch_id: str, track: WorkflowTrack, settings: ApplySettings) -> str:
        new_metadata = self._metadata_update(track, settings)
        new_filename = track.proposed.filename if settings.rename_file and track.proposed is not None else None
        return self.history_repository.create_operation(
            batch_id=batch_id,
            file_path=track.path,
            original_metadata=track.current_metadata,
            new_metadata=new_metadata,
            new_filename=new_filename,
        )

    def _apply_track(self, track: WorkflowTrack, settings: ApplySettings, operation_id: str) -> None:
        proposed = track.proposed
        if proposed is None:
            return

        backup_path: Path | None = None
        current_path = track.path
        lrc_path: Path | None = None
        try:
            if settings.enable_backup:
                backup_path = create_backup(track.path, backup_folder=self.backup_folder)
                self.logger.info("Created backup %s", backup_path)

            if settings.update_id3_metadata:
                self.metadata_writer(track.path, self._metadata_update(track, settings))
                self.logger.info("Updated ID3 metadata for %s", track.path)

            if settings.export_lrc and proposed.lyrics is not None and proposed.lyrics.has_synced_lyrics:
                lrc_path = track.path.with_name(
                    build_lrc_export_filename(proposed.artist or "Unknown", proposed.title or "Unknown")
                )
                if lrc_path.exists():
                    raise FileExistsError("The .lrc export file already exists.")
                lrc_path.write_text(proposed.lyrics.synced_lyrics or "", encoding="utf-8")
                self.logger.info("Exported LRC file %s", lrc_path)

            if settings.rename_file and proposed.filename:
                target = track.path.with_name(proposed.filename)
                if target.parent.resolve() != track.path.parent.resolve():
                    raise ValueError("Target rename path must stay in the original folder.")
                if target.exists() and target.resolve() != track.path.resolve():
                    raise FileExistsError("The target filename already exists.")
                if target.resolve() != track.path.resolve():
                    track.path.rename(target)
                    current_path = target
                    self.logger.info("Renamed %s to %s", track.path, target)

            self.history_repository.mark_operation(operation_id, "applied")
        except Exception as exc:
            self.history_repository.mark_operation(operation_id, "failed", self._friendly_error(exc))
            if backup_path is not None and backup_path.exists():
                restore_backup(backup_path, current_path)
            else:
                self.metadata_restorer(current_path, track.current_metadata)
            if current_path.resolve() != track.path.resolve() and not track.path.exists():
                current_path.rename(track.path)
            if lrc_path is not None and lrc_path.exists():
                lrc_path.unlink()
            raise

    def _metadata_update(self, track: WorkflowTrack, settings: ApplySettings) -> MetadataUpdate:
        proposed = track.proposed
        if proposed is None:
            return MetadataUpdate()

        return MetadataUpdate(
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
        )

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
