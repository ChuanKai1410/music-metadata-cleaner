"""GUI-facing workflow orchestration for batch processing."""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable, Protocol

from music_metadata_cleaner.app.lyrics_service import build_lrc_export_filename
from music_metadata_cleaner.audio_segments import check_ffmpeg_available, temporary_audio_segments
from music_metadata_cleaner.db.history import HistoryRepository, OperationRecord
from music_metadata_cleaner.domain.models import (
    AudioRecognitionResult,
    CandidateRecording,
    Lyrics,
    LyricsLookup,
    LyricsResult,
    MetadataUpdate,
    MusicBrainzMetadata,
    MusicBrainzIdentifiers,
    ProposedTrackChanges,
    TrackMetadata,
    YouTubeCandidate,
)
from music_metadata_cleaner.domain.recognition import recognition_confidence_score
from music_metadata_cleaner.domain.youtube import (
    build_youtube_search_queries,
    rank_youtube_candidates,
    youtube_confidence_contribution,
)
from music_metadata_cleaner.files.backup import create_backup, restore_backup
from music_metadata_cleaner.files.safe_paths import generate_mp3_filename
from music_metadata_cleaner.files.scanner import discover_mp3_files
from music_metadata_cleaner.id3.reader import read_id3_metadata
from music_metadata_cleaner.id3.snapshot import restore_id3_metadata
from music_metadata_cleaner.id3.writer import write_id3_metadata
from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


class IdentifierService(Protocol):
    def identify(self, path: str | Path) -> list[CandidateRecording]:
        """Identify candidate recordings for a local MP3."""


class MetadataService(Protocol):
    def enrich_musicbrainz_recording(self, recording_id: str) -> MusicBrainzMetadata:
        """Return canonical metadata for a confirmed MusicBrainz recording."""

    def find_musicbrainz_recording(
        self,
        *,
        artist: str,
        title: str,
        duration: int | None = None,
    ) -> CandidateRecording | None:
        """Return a likely MusicBrainz recording for recognized artist/title text."""


class LyricsLookupService(Protocol):
    def get_lyrics(self, lookup: LyricsLookup, *, existing_lyrics: Lyrics | None = None) -> LyricsResult | None:
        """Return existing or online lyrics."""


class YouTubeLookupService(Protocol):
    def search(self, query: str) -> list[YouTubeCandidate]:
        """Return normalized YouTube candidates for a search query."""


class FallbackRecognitionServiceProtocol(Protocol):
    def recognize(self, path: str | Path, *, duration_seconds: int | None = None) -> AudioRecognitionResult | None:
        """Return fallback recognition consensus for a local MP3."""


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
    youtube_status: str = "Not checked"
    recognition_status: str = "Not checked"
    diagnostic_status: str = ""
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


@dataclass(frozen=True)
class RecognitionSetupCheck:
    name: str
    status: str
    detail: str = ""


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
        youtube_service: YouTubeLookupService | None = None,
        fallback_recognition_service: FallbackRecognitionServiceProtocol | None = None,
        fallback_recognition_enabled: bool = False,
        fallback_recognition_threshold: int = 70,
        fallback_verify_medium_confidence: bool = False,
        audd_token_present: bool = False,
        audd_token_source: str = "None",
        ffmpeg_executable: str = "ffmpeg",
        ffmpeg_available: bool = False,
        ffmpeg_status: str = "Unknown",
        youtube_configured: bool = False,
        default_apply_settings: ApplySettings | None = None,
        always_use_youtube_verification: bool = False,
        youtube_search_below_confidence: int = 90,
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
        self.youtube_service = youtube_service
        self.fallback_recognition_service = fallback_recognition_service
        self.fallback_recognition_enabled = fallback_recognition_enabled
        self.fallback_recognition_threshold = max(0, min(100, fallback_recognition_threshold))
        self.fallback_verify_medium_confidence = fallback_verify_medium_confidence
        self.audd_token_present = audd_token_present
        self.audd_token_source = audd_token_source
        self.ffmpeg_executable = ffmpeg_executable
        self.ffmpeg_available = ffmpeg_available
        self.ffmpeg_status = ffmpeg_status
        self.youtube_configured = youtube_configured
        self.default_apply_settings = default_apply_settings or ApplySettings()
        self.always_use_youtube_verification = always_use_youtube_verification
        self.youtube_search_below_confidence = max(0, min(100, youtube_search_below_confidence))
        self.metadata_reader = metadata_reader
        self.metadata_writer = metadata_writer or self._write_metadata
        self.metadata_restorer = metadata_restorer
        self.history_repository = history_repository
        self.backup_folder = Path(backup_folder) if backup_folder is not None else None
        self.logger = logger or logging.getLogger("music_metadata_cleaner")
        self._last_youtube_checked = False
        self._last_youtube_unavailable = False
        self._last_audd_state = "NOT_CHECKED"
        self._last_audd_requests_attempted = 0
        self.logger.info("recognition.audd_provider_initialized=%s", self.fallback_recognition_service is not None)
        self.logger.info("recognition.audd_fallback_enabled=%s", self.fallback_recognition_enabled)

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
                recognition = self._fallback_recognition(track, None, None)
                if recognition is not None and recognition.has_identity:
                    return self._fallback_from_audio_recognition(track, recognition, audio_candidate=None)
                youtube_candidates = self._youtube_candidates(track, None, None, None, force=True)
                if youtube_candidates:
                    return self._fallback_from_youtube(track, youtube_candidates)
                return self._fallback_from_current_tags(
                    track,
                    "No metadata found",
                    youtube_status=self._youtube_status(None, (), checked=self._last_youtube_checked),
                    recognition_status=self._recognition_status(None, recognition),
                )

            base_confidence = self._confidence_from_candidate(candidate, None)
            recognition = self._fallback_recognition(track, candidate, base_confidence)
            if recognition is not None and recognition.has_identity and (
                not (candidate.artist and candidate.title) or recognition_confidence_score(recognition) >= base_confidence
            ):
                return self._fallback_from_audio_recognition(track, recognition, audio_candidate=candidate)

            try:
                metadata = self._metadata_for_candidate(candidate)
            except Exception:
                self.logger.exception("MusicBrainz enrichment failed for %s; falling back to candidate metadata.", track.path)
                metadata = self._metadata_from_candidate(candidate)
            metadata_has_identity = bool(metadata.artist and metadata.title)
            youtube_checked = self._should_use_youtube(base_confidence) or not metadata_has_identity
            youtube_candidates = self._youtube_candidates(
                track,
                candidate,
                metadata,
                base_confidence,
                force=not metadata_has_identity,
            )
            if not metadata_has_identity and youtube_candidates:
                return self._fallback_from_youtube(track, youtube_candidates, audio_candidate=candidate)
            lyrics = self._lyrics_for_metadata(metadata, track.current_metadata.lyrics)
            proposed = self._build_proposed_changes(metadata, lyrics, youtube_candidates)
            confidence = self._confidence_from_candidate(candidate, lyrics)
            if not proposed.artist or not proposed.title or not proposed.filename:
                confidence = min(confidence, 69)
            contribution, reason = youtube_confidence_contribution(proposed.youtube_candidate)
            if proposed.youtube_candidate is not None:
                confidence = min(100, confidence + contribution)
            requires_review = (
                confidence < 90
                or not proposed.artist
                or not proposed.title
                or not proposed.filename
                or (lyrics.requires_review if lyrics is not None else False)
            )
            confidence_breakdown = (
                f"Audio fingerprint: {round(candidate.acoustid_score * 100)}%",
                f"MusicBrainz: {'strong' if metadata.identifiers.recording_id else 'not available'}",
                reason,
                *self._youtube_breakdown(proposed.youtube_candidate),
            )
            proposed = replace(proposed, confidence_breakdown=confidence_breakdown)

            return replace(
                track,
                proposed=proposed,
                confidence_score=confidence,
                metadata_status="Found",
                lyrics_status=self._lyrics_status(lyrics),
                cover_status=proposed.cover_source or "Not found",
                youtube_status=self._youtube_status(proposed.youtube_candidate, youtube_candidates, checked=youtube_checked),
                recognition_status=self._recognition_status(candidate, recognition),
                diagnostic_status=self._diagnostic_status(candidate, recognition, proposed.youtube_candidate),
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
            if settings.rename_file and not track.proposed.filename:
                results.append(ApplyResult(track.path, False, "No proposed filename is available for this file."))
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

    def runtime_recognition_configuration(self) -> tuple[str, ...]:
        available, resolved, status = check_ffmpeg_available(self.ffmpeg_executable)
        return (
            "Runtime Recognition Configuration",
            f"AudD provider: {'Initialized' if self.fallback_recognition_service is not None else 'Not initialized'}",
            f"AudD token: {'Loaded' if self.audd_token_present else 'Not loaded'}",
            f"AudD token source: {self.audd_token_source}",
            f"AudD fallback: {'Enabled' if self.fallback_recognition_enabled else 'Disabled'}",
            f"Multi-segment: {'Enabled' if getattr(self.fallback_recognition_service, 'max_segments', 1) > 1 else 'Disabled'}",
            f"Maximum segments: {getattr(self.fallback_recognition_service, 'max_segments', 1)}",
            f"FFmpeg: {'Available' if available else status}",
            f"FFmpeg executable: {resolved}",
            f"YouTube: {'Configured' if self.youtube_configured else 'Not configured'}",
        )

    def test_recognition_setup(self) -> list[RecognitionSetupCheck]:
        checks = [
            RecognitionSetupCheck(
                "AudD configuration",
                "PASS" if self.audd_token_present else "FAIL",
                f"source={self.audd_token_source}",
            ),
            RecognitionSetupCheck(
                "AudD provider initialized",
                "PASS" if self.fallback_recognition_service is not None else "FAIL",
                "enabled" if self.fallback_recognition_enabled else "fallback disabled",
            ),
        ]
        ffmpeg_available, ffmpeg_path, ffmpeg_status = check_ffmpeg_available(self.ffmpeg_executable)
        checks.append(RecognitionSetupCheck("FFmpeg path", "PASS" if ffmpeg_available else "FAIL", ffmpeg_path))
        checks.append(RecognitionSetupCheck("FFmpeg execution", "PASS" if ffmpeg_available else "FAIL", ffmpeg_status))

        extraction_check, test_clip, cleanup_dir = (
            self._test_temporary_audio_extraction(ffmpeg_path)
            if ffmpeg_available
            else (RecognitionSetupCheck("Temporary audio extraction", "FAIL", "ffmpeg unavailable"), None, None)
        )
        checks.append(extraction_check)

        try:
            if self.fallback_recognition_service is None or test_clip is None:
                checks.append(RecognitionSetupCheck("AudD authentication", "FAIL", self._audd_display_state()))
                return checks

            try:
                self._last_audd_requests_attempted += 1
                self.logger.info("audd.request_attempted=true")
                result = self.fallback_recognition_service.recognizer.recognize_file(
                    test_clip,
                    segment_index=0,
                    start_seconds=0,
                )
            except Exception as exc:
                state = self._audd_state_from_exception(exc)
                self._last_audd_state = state
                checks.append(RecognitionSetupCheck("AudD authentication", "FAIL", state))
                return checks

            self._last_audd_state = "MATCHED" if result else "NO_MATCH"
            self.logger.info("audd.result=%s", "match" if result else "no_match")
            checks.append(RecognitionSetupCheck("AudD authentication", "PASS", "SUCCESS" if result else "NO_MATCH"))
            return checks
        finally:
            if cleanup_dir is not None:
                shutil.rmtree(cleanup_dir, ignore_errors=True)

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

        return self._metadata_from_candidate(candidate)

    def _metadata_from_candidate(self, candidate: CandidateRecording) -> MusicBrainzMetadata:
        recording_id = candidate.musicbrainz_recording_id or candidate.recording_id
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
        youtube_candidates: list[YouTubeCandidate] | None = None,
        audio_recognition: AudioRecognitionResult | None = None,
    ) -> ProposedTrackChanges:
        filename = generate_mp3_filename(metadata.artist, metadata.title) if metadata.artist and metadata.title else None
        youtube_candidates = youtube_candidates or []
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
            youtube_candidate=youtube_candidates[0] if youtube_candidates else None,
            youtube_candidates=tuple(youtube_candidates),
            audio_recognition=audio_recognition,
        )

    def _fallback_from_current_tags(
        self,
        track: WorkflowTrack,
        status: str,
        *,
        youtube_status: str | None = None,
        recognition_status: str | None = None,
    ) -> WorkflowTrack:
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
            youtube_status=youtube_status or "Not checked",
            recognition_status=recognition_status or "AcoustID: no match",
            diagnostic_status="No audio provider produced a usable artist/title.",
            processing_status="Needs review",
            requires_review=True,
        )

    def _fallback_from_audio_recognition(
        self,
        track: WorkflowTrack,
        recognition: AudioRecognitionResult,
        *,
        audio_candidate: CandidateRecording | None,
    ) -> WorkflowTrack:
        musicbrainz_candidate = self._musicbrainz_candidate_for_recognition(recognition, audio_candidate)
        metadata = MusicBrainzMetadata(
            artist=recognition.artist,
            title=recognition.title,
            album=recognition.album,
            release_date=recognition.release_date,
            track_number=None,
            duration=(
                musicbrainz_candidate.duration
                if musicbrainz_candidate is not None
                else audio_candidate.duration if audio_candidate is not None else None
            ),
            identifiers=MusicBrainzIdentifiers(
                recording_id=(
                    musicbrainz_candidate.musicbrainz_recording_id or musicbrainz_candidate.recording_id
                    if musicbrainz_candidate is not None
                    else audio_candidate.musicbrainz_recording_id or audio_candidate.recording_id
                    if audio_candidate is not None
                    else ""
                )
            ),
        )
        if musicbrainz_candidate is not None:
            try:
                metadata = self._metadata_for_candidate(musicbrainz_candidate)
            except Exception:
                self.logger.exception("MusicBrainz enrichment failed for AudD fallback %s", track.path)
        base_confidence = recognition_confidence_score(recognition)
        youtube_candidates = self._youtube_candidates(
            track,
            audio_candidate,
            metadata,
            base_confidence,
            force=base_confidence < 90,
        )
        lyrics = self._lyrics_for_metadata(metadata, track.current_metadata.lyrics)
        proposed = self._build_proposed_changes(metadata, lyrics, youtube_candidates, audio_recognition=recognition)
        contribution, youtube_reason = youtube_confidence_contribution(proposed.youtube_candidate)
        confidence = min(100, base_confidence + (contribution if proposed.youtube_candidate else 0))
        requires_review = confidence < 90 or bool(recognition.review_reasons)
        proposed = replace(
            proposed,
            confidence_breakdown=(
                "Audio fingerprint: incomplete match" if audio_candidate is not None else "Audio fingerprint: no match",
                f"AudD: {recognition.matched_segments}/{recognition.total_segments} segments matched",
                f"MusicBrainz: {'confirmed' if metadata.identifiers.recording_id else 'not available'}",
                youtube_reason,
                *recognition.review_reasons,
                *self._youtube_breakdown(proposed.youtube_candidate),
            ),
        )
        return replace(
            track,
            proposed=proposed,
            confidence_score=confidence,
            metadata_status="Found",
            lyrics_status=self._lyrics_status(lyrics),
            cover_status=proposed.cover_source or "Not found",
            youtube_status=self._youtube_status(proposed.youtube_candidate, youtube_candidates, checked=self._last_youtube_checked),
            recognition_status=self._recognition_status(audio_candidate, recognition),
            diagnostic_status=self._diagnostic_status(audio_candidate, recognition, proposed.youtube_candidate),
            processing_status="Needs review" if requires_review else "Ready",
            requires_review=requires_review,
        )

    def _fallback_from_youtube(
        self,
        track: WorkflowTrack,
        youtube_candidates: list[YouTubeCandidate],
        *,
        audio_candidate: CandidateRecording | None = None,
    ) -> WorkflowTrack:
        youtube_candidate = youtube_candidates[0]
        artist = youtube_candidate.inferred_artist or track.current_metadata.artist
        title = youtube_candidate.inferred_song_title or track.current_metadata.title or youtube_candidate.title
        metadata = MusicBrainzMetadata(
            artist=artist,
            title=title,
            album=track.current_metadata.album,
            release_date=track.current_metadata.release_date,
            track_number=track.current_metadata.track_number,
            duration=youtube_candidate.duration_seconds,
            identifiers=MusicBrainzIdentifiers(
                recording_id=audio_candidate.musicbrainz_recording_id or audio_candidate.recording_id
                if audio_candidate is not None
                else ""
            ),
        )
        lyrics = self._lyrics_for_metadata(metadata, track.current_metadata.lyrics)
        proposed = self._build_proposed_changes(metadata, lyrics, youtube_candidates)
        confidence = min(89, max(0, youtube_candidate.score))
        proposed = replace(
            proposed,
            confidence_breakdown=(
                "Audio fingerprint: incomplete match" if audio_candidate is not None else "Audio fingerprint: no match",
                "MusicBrainz: not available",
                "YouTube: fallback discovery",
                *self._youtube_breakdown(youtube_candidate),
            ),
        )
        return replace(
            track,
            proposed=proposed,
            confidence_score=confidence,
            metadata_status="YouTube fallback",
            lyrics_status=self._lyrics_status(lyrics),
            cover_status=proposed.cover_source or "Not found",
            youtube_status=self._youtube_status(youtube_candidate, youtube_candidates, checked=True),
            recognition_status=self._recognition_status(audio_candidate, None),
            diagnostic_status=self._diagnostic_status(audio_candidate, None, youtube_candidate),
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

    def _youtube_candidates(
        self,
        track: WorkflowTrack,
        candidate: CandidateRecording | None,
        metadata: MusicBrainzMetadata | None,
        confidence: int | None,
        *,
        force: bool = False,
    ) -> list[YouTubeCandidate]:
        if self.youtube_service is None:
            self._last_youtube_checked = False
            self.logger.info("YouTube status: NOT_CONFIGURED for %s", track.path.name)
            return []
        if not force and not self._should_use_youtube(confidence):
            self._last_youtube_checked = False
            return []

        self._last_youtube_checked = True
        self._last_youtube_unavailable = False
        queries = build_youtube_search_queries(
            filename=track.path.name,
            metadata=track.current_metadata,
            candidate=candidate,
            musicbrainz=metadata,
        )
        if not queries:
            self.logger.info("YouTube status: EMPTY_QUERY for %s", track.path.name)
            return []
        all_candidates: list[YouTubeCandidate] = []
        seen_video_ids: set[str] = set()
        for query in queries:
            try:
                self.logger.info("YouTube status: SEARCHING query=%r file=%s", query, track.path.name)
                for youtube_candidate in self.youtube_service.search(query):
                    if youtube_candidate.video_id in seen_video_ids:
                        continue
                    seen_video_ids.add(youtube_candidate.video_id)
                    all_candidates.append(youtube_candidate)
            except Exception as exc:
                self.logger.warning("YouTube lookup unavailable for %s: %s", track.path, self._friendly_error(exc))
                self._last_youtube_unavailable = True
                return []

        ranked = rank_youtube_candidates(
            all_candidates,
            expected_artist=metadata.artist if metadata else candidate.artist if candidate else track.current_metadata.artist,
            expected_title=metadata.title if metadata else candidate.title if candidate else track.current_metadata.title,
            filename=track.path.name,
            id3_metadata=track.current_metadata,
            expected_duration=metadata.duration if metadata else candidate.duration if candidate else None,
        )
        if not ranked:
            self.logger.info("YouTube status: NO_RESULTS for %s", track.path.name)
        elif ranked[0].score >= 70:
            self.logger.info("YouTube status: MATCHED score=%s file=%s", ranked[0].score, track.path.name)
        else:
            self.logger.info("YouTube status: CANDIDATES_REJECTED best_score=%s file=%s", ranked[0].score, track.path.name)
        return ranked

    def _youtube_status(
        self,
        youtube_candidate: YouTubeCandidate | None,
        youtube_candidates: list[YouTubeCandidate] | tuple[YouTubeCandidate, ...],
        *,
        checked: bool,
    ) -> str:
        if not checked:
            return "Not checked"
        if self._last_youtube_unavailable:
            return "API error"
        if youtube_candidate is not None and youtube_candidate.score >= 70:
            return "Matched"
        if youtube_candidates:
            return "Candidates rejected"
        return "Not configured" if self.youtube_service is None else "No results"

    def _should_use_youtube(self, confidence: int | None) -> bool:
        if self.youtube_service is None:
            return False
        if self.always_use_youtube_verification:
            return True
        return confidence is None or confidence < self.youtube_search_below_confidence

    def _youtube_breakdown(self, youtube_candidate: YouTubeCandidate | None) -> tuple[str, ...]:
        if youtube_candidate is None:
            return ()
        return (
            f"YouTube score: {youtube_candidate.score}%",
            *youtube_candidate.score_breakdown,
        )

    def _fallback_recognition(
        self,
        track: WorkflowTrack,
        candidate: CandidateRecording | None,
        confidence: int | None,
    ) -> AudioRecognitionResult | None:
        if not self.fallback_recognition_enabled or self.fallback_recognition_service is None:
            self._last_audd_state = "DISABLED" if self.audd_token_present else "NOT_CONFIGURED"
            self.logger.info("recognition.fallback_triggered=false state=%s", self._last_audd_state)
            return None
        candidate_has_identity = bool(candidate and candidate.artist and candidate.title)
        should_run = (
            candidate is None
            or not candidate_has_identity
            or confidence is None
            or confidence < self.fallback_recognition_threshold
            or (self.fallback_verify_medium_confidence and confidence < 90)
        )
        if not should_run:
            self._last_audd_state = "READY"
            self.logger.info("recognition.fallback_triggered=false state=READY confidence=%s", confidence)
            return None
        try:
            self._last_audd_state = "READY"
            self.logger.info("recognition.fallback_triggered=true")
            self.logger.info("worker.audd_provider_available=%s", self.fallback_recognition_service is not None)
            result = self.fallback_recognition_service.recognize(
                track.path,
                duration_seconds=candidate.duration if candidate is not None else None,
            )
            self._last_audd_requests_attempted = getattr(self.fallback_recognition_service, "last_requests_attempted", 0)
            self.logger.info("audd.requests_attempted=%s", self._last_audd_requests_attempted)
            if result is None:
                self._last_audd_state = "NO_MATCH"
                self.logger.info("AudD fallback: no result for %s", track.path.name)
            else:
                self._last_audd_state = "MATCHED"
                self.logger.info(
                    "AudD fallback: %s/%s segments matched for %s",
                    result.matched_segments,
                    result.total_segments,
                    track.path.name,
                )
            return result
        except Exception as exc:
            self._last_audd_state = self._audd_state_from_exception(exc)
            self.logger.warning("AudD fallback unavailable for %s: %s", track.path.name, self._friendly_error(exc))
            return None

    def _musicbrainz_candidate_for_recognition(
        self,
        recognition: AudioRecognitionResult,
        audio_candidate: CandidateRecording | None,
    ) -> CandidateRecording | None:
        if audio_candidate is not None and audio_candidate.musicbrainz_recording_id and audio_candidate.artist and audio_candidate.title:
            return audio_candidate
        if self.metadata_service is None or not recognition.artist or not recognition.title:
            return None
        try:
            return self.metadata_service.find_musicbrainz_recording(
                artist=recognition.artist,
                title=recognition.title,
                duration=audio_candidate.duration if audio_candidate is not None else None,
            )
        except Exception:
            self.logger.exception("MusicBrainz search failed for AudD recognition.")
            return None

    def _recognition_status(
        self,
        candidate: CandidateRecording | None,
        recognition: AudioRecognitionResult | None,
    ) -> str:
        acoustid = "AcoustID" if candidate is not None and candidate.artist and candidate.title else None
        audd = (
            f"AudD fallback ({recognition.matched_segments}/{recognition.total_segments})"
            if recognition is not None and recognition.has_identity
            else None
        )
        if acoustid and audd:
            return "AcoustID + AudD"
        if audd:
            return audd
        if acoustid:
            return "AcoustID"
        if not self.audd_token_present:
            return "AudD: not configured"
        if not self.fallback_recognition_enabled:
            return "AudD: disabled"
        if self.fallback_recognition_service is None:
            return "AudD: provider unavailable"
        if self._last_audd_state not in {"NOT_CHECKED", "READY"}:
            return f"AudD: {self._audd_display_state()}"
        return "No audio match"

    def _diagnostic_status(
        self,
        candidate: CandidateRecording | None,
        recognition: AudioRecognitionResult | None,
        youtube_candidate: YouTubeCandidate | None,
    ) -> str:
        parts = ["AcoustID: match" if candidate is not None else "AcoustID: no match"]
        if candidate is not None and not (candidate.artist and candidate.title):
            parts.append("AcoustID identity incomplete")
        if recognition is None:
            parts.append(f"AudD: {self._audd_display_state()}")
        else:
            parts.append(f"AudD: {recognition.matched_segments}/{recognition.total_segments}")
        parts.append(f"Fallback triggered: {'Yes' if self._last_audd_state in {'MATCHED', 'NO_MATCH'} else 'No'}")
        parts.append(f"AudD requests attempted: {self._last_audd_requests_attempted}")
        parts.append("YouTube: matched" if youtube_candidate is not None else "YouTube: not matched")
        return " | ".join(parts)

    def _test_temporary_audio_extraction(self, ffmpeg_path: str) -> tuple[RecognitionSetupCheck, Path | None, Path | None]:
        temp_dir = Path(tempfile.mkdtemp(prefix="music-cleaner-recognition-test-"))
        source = temp_dir / "source.wav"
        try:
            generated = subprocess.run(
                [
                    ffmpeg_path,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=44100:cl=mono",
                    "-t",
                    "2",
                    str(source),
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
            if generated.returncode != 0 or not source.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                return RecognitionSetupCheck("Temporary audio extraction", "FAIL", "could not create test audio"), None, None
            with temporary_audio_segments(source, duration_seconds=2, ffmpeg_executable=ffmpeg_path, max_segments=1, clip_seconds=1) as segments:
                if not segments:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    return RecognitionSetupCheck("Temporary audio extraction", "FAIL", "no segment created"), None, None
                persistent_clip = temp_dir / "recognition-test.mp3"
                shutil.copyfile(segments[0].path, persistent_clip)
            return RecognitionSetupCheck("Temporary audio extraction", "PASS", "temporary clip created"), persistent_clip, temp_dir
        except Exception as exc:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return RecognitionSetupCheck("Temporary audio extraction", "FAIL", self._friendly_error(exc)), None, None

    def _audd_state_from_exception(self, exc: Exception) -> str:
        if isinstance(exc, (ProviderTimeoutError, ProviderNetworkError)):
            return "NETWORK_ERROR"
        if isinstance(exc, ProviderRateLimitError):
            return "RATE_LIMITED"
        if isinstance(exc, ProviderResponseError):
            text = str(exc).casefold()
            if "token" in text or "auth" in text or "invalid" in text or "permitted" in text:
                return "AUTH_FAILED"
            return "API_ERROR"
        text = str(exc).casefold()
        if "ffmpeg_invalid_path" in text or "ffmpeg" in text:
            return "FFMPEG_INVALID_PATH"
        return "REQUEST_FAILED"

    def _audd_display_state(self) -> str:
        labels = {
            "NOT_CONFIGURED": "not configured",
            "DISABLED": "disabled",
            "READY": "ready",
            "AUTH_FAILED": "authentication failed",
            "NETWORK_ERROR": "network error",
            "RATE_LIMITED": "rate limited",
            "API_ERROR": "API error",
            "REQUEST_FAILED": "request failed",
            "NO_MATCH": "no match",
            "MATCHED": "matched",
            "FFMPEG_INVALID_PATH": "ffmpeg invalid path",
            "NOT_CHECKED": "not checked",
        }
        if not self.audd_token_present:
            return labels["NOT_CONFIGURED"]
        if not self.fallback_recognition_enabled:
            return labels["DISABLED"]
        return labels.get(self._last_audd_state, self._last_audd_state.lower().replace("_", " "))

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
