"""Search-only orchestration, previews, explicit apply, and durable undo."""

from __future__ import annotations
from dataclasses import dataclass, replace
import logging
from pathlib import Path
from typing import Callable
from music_metadata_cleaner.domain.models import (
    Lyrics,
    LyricsLookup,
    LyricsResult,
    MetadataUpdate,
    ProposedTrackChanges,
    TrackMetadata,
)
from music_metadata_cleaner.domain.search import (
    SearchResult,
    ResolvedTrackIdentity,
    RuleBasedIdentityResolver,
    clean_filename,
    build_search_queries,
)
from music_metadata_cleaner.providers.search import SearchProvider, SearchError
from music_metadata_cleaner.db.history import HistoryRepository, OperationRecord
from music_metadata_cleaner.files.backup import create_backup, restore_backup
from music_metadata_cleaner.files.safe_paths import (
    generate_mp3_filename,
    rename_without_overwrite,
)
from music_metadata_cleaner.files.scanner import discover_mp3_files
from music_metadata_cleaner.id3.reader import read_id3_metadata
from music_metadata_cleaner.id3.writer import write_id3_metadata
from music_metadata_cleaner.id3.snapshot import restore_id3_metadata


@dataclass(frozen=True)
class ApplySettings:
    update_id3_metadata: bool = True
    update_title: bool = True
    update_artist: bool = True
    update_album: bool = False
    add_lyrics: bool = True
    rename_file: bool = True
    enable_backup: bool = True


@dataclass(frozen=True)
class WorkflowTrack:
    path: Path
    current_metadata: TrackMetadata
    proposed: ProposedTrackChanges | None = None
    confidence_score: int = 0
    metadata_status: str = "Not processed"
    lyrics_status: str = "Not checked"
    diagnostic_status: str = ""
    processing_status: str = "Pending"
    requires_review: bool = False
    error_message: str | None = None
    selected: bool = True
    cleaned_filename: str = ""
    search_queries: tuple[str, ...] = ()
    search_results: tuple[SearchResult, ...] = ()
    candidates: tuple[ResolvedTrackIdentity, ...] = ()
    resolved_identity: ResolvedTrackIdentity | None = None
    manually_reviewed: bool = False
    manual_keywords: str | None = None

    @property
    def confidence(self) -> str:
        return (
            "High"
            if self.confidence_score >= 80
            else "Medium" if self.confidence_score >= 60 else "Low"
        )


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
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class MusicCleanerWorkflowService:
    def __init__(
        self,
        *,
        search_provider: SearchProvider | None = None,
        resolver=None,
        lyrics_service=None,
        maximum_results=8,
        automatic_search=True,
        retrieve_lyrics=True,
        preserve_existing_lyrics=True,
        overwrite_existing_lyrics=False,
        default_apply_settings=None,
        metadata_reader=read_id3_metadata,
        metadata_writer=None,
        metadata_restorer=restore_id3_metadata,
        history_repository=None,
        backup_folder=None,
        logger=None,
    ):
        self.search_provider = search_provider
        self.resolver = resolver or RuleBasedIdentityResolver()
        self.lyrics_service = lyrics_service
        self.maximum_results = max(1, min(20, maximum_results))
        self.automatic_search = automatic_search
        self.retrieve_lyrics = retrieve_lyrics
        self.preserve_existing_lyrics = preserve_existing_lyrics
        self.overwrite_existing_lyrics = (
            overwrite_existing_lyrics and not preserve_existing_lyrics
        )
        self.default_apply_settings = default_apply_settings or ApplySettings()
        self.metadata_reader = metadata_reader
        self.metadata_writer = metadata_writer or self._write_metadata
        self.metadata_restorer = metadata_restorer
        self.history_repository = history_repository
        self.backup_folder = Path(backup_folder) if backup_folder is not None else None
        self.logger = logger or logging.getLogger("music_metadata_cleaner")

    def process_track(
        self,
        track: WorkflowTrack,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> WorkflowTrack:
        if track.processing_status == "Invalid MP3":
            return track
        # Clear stale previews so a failed retry can never apply an old identity.
        track = replace(
            track,
            proposed=None,
            candidates=(),
            resolved_identity=None,
            search_results=(),
            search_queries=(),
            confidence_score=0,
            requires_review=False,
            manually_reviewed=False,
            error_message=None,
            metadata_status="Not processed",
            lyrics_status="Not checked",
            cleaned_filename=clean_filename(track.path.name),
        )
        queries = build_search_queries(
            track.path.name, track.current_metadata, track.manual_keywords
        )
        if not queries:
            return replace(
                track,
                processing_status="Insufficient Information",
                diagnostic_status="Provide manual search keywords; no useful textual evidence.",
            )
        if not self.automatic_search and track.manual_keywords is None:
            return replace(
                track,
                processing_status="Review",
                diagnostic_status="Automatic search disabled. Use Manual Search.",
            )
        results = []
        attempted = []
        candidates = ()
        try:
            if self.search_provider is None:
                raise SearchError("INVALID_ENDPOINT")
            for query in queries:
                if cancellation_token and cancellation_token.cancelled:
                    return replace(track, processing_status="Cancelled")
                attempted.append(query)
                results.extend(
                    self.search_provider.search(query, count=self.maximum_results)
                )
                if cancellation_token and cancellation_token.cancelled:
                    return replace(track, processing_status="Cancelled")
                results = list({r.url: r for r in results}.values())
                candidates = self.resolver.resolve(
                    track.manual_keywords or track.cleaned_filename,
                    track.current_metadata,
                    results,
                    query,
                )
                if len(candidates) == 1 and candidates[0].confidence == "High":
                    break
        except Exception as exc:
            status = exc.status if isinstance(exc, SearchError) else "INVALID_RESPONSE"
            return replace(
                track,
                search_queries=tuple(attempted),
                search_results=tuple(results),
                processing_status="Search Failed",
                error_message="Search is unavailable. Check Search settings or try again later.",
                diagnostic_status=status,
            )
        track = replace(
            track,
            search_queries=tuple(attempted),
            search_results=tuple(results),
            candidates=candidates,
        )
        if not candidates:
            return replace(
                track,
                processing_status="Review",
                requires_review=True,
                diagnostic_status="No supported Artist + Title found. Try manual keywords.",
            )
        if len(candidates) > 1:
            return replace(
                track,
                processing_status="Review",
                requires_review=True,
                diagnostic_status="Conflicting identities. Choose a candidate after reviewing sources.",
            )
        return self._preview_identity(track, candidates[0])

    def manual_search(self, track: WorkflowTrack, keywords: str) -> WorkflowTrack:
        if not keywords.strip():
            raise ValueError("Search keywords are required.")
        return self.process_track(replace(track, manual_keywords=keywords.strip()))

    def use_candidate(self, track: WorkflowTrack, index: int) -> WorkflowTrack:
        if not 0 <= index < len(track.candidates):
            raise ValueError("Select a candidate from this search.")
        return self._preview_identity(track, track.candidates[index], reviewed=True)

    def _preview_identity(self, track, identity, reviewed=False):
        lyrics = None
        existing = track.current_metadata.lyrics
        if existing and existing.has_text and not self.overwrite_existing_lyrics:
            lyrics = LyricsResult(
                source="existing", plain_lyrics=existing.text, confidence=1
            )
        elif (
            self.retrieve_lyrics
            and self.lyrics_service
            and (reviewed or identity.confidence == "High")
        ):
            try:
                lyrics = self.lyrics_service.get_lyrics(
                    LyricsLookup(artist=identity.artist, title=identity.title),
                    existing_lyrics=None,
                )
            except Exception:
                # Lyrics failures never discard the resolved identity.
                lyrics = None
        lyrics_status = (
            "Existing"
            if lyrics and lyrics.source == "existing"
            else (
                "Review"
                if lyrics and lyrics.requires_review
                else (
                    "Found"
                    if lyrics and lyrics.has_plain_lyrics
                    else "Not Found" if self.retrieve_lyrics else "Disabled"
                )
            )
        )
        needs_review = not reviewed and identity.confidence != "High"
        proposed = ProposedTrackChanges(
            artist=identity.artist,
            title=identity.title,
            filename=generate_mp3_filename(identity.artist, identity.title),
            lyrics=lyrics,
            confidence_breakdown=identity.evidence_breakdown,
        )
        return replace(
            track,
            proposed=proposed,
            resolved_identity=identity,
            confidence_score=identity.internal_score,
            metadata_status="Found",
            lyrics_status=lyrics_status,
            processing_status=(
                "Review"
                if needs_review or lyrics_status == "Review"
                else "Lyrics Not Found" if lyrics_status == "Not Found" else "Ready"
            ),
            requires_review=needs_review,
            manually_reviewed=reviewed,
            diagnostic_status="; ".join(
                identity.source_summaries + identity.evidence_breakdown
            ),
        )

    def test_search(self) -> str:
        if self.search_provider is None:
            return "INVALID_ENDPOINT"
        try:
            if hasattr(self.search_provider, "test_connection"):
                return self.search_provider.test_connection()
            self.search_provider.search('"Lemon" "米津玄師" song', count=5)
            return "PASS"
        except SearchError as exc:
            return exc.status
        except Exception:
            return "INVALID_RESPONSE"

    def clear_search_cache(self) -> None:
        cache = getattr(self.search_provider, "request_cache", None)
        if cache is not None:
            cache.clear("searxng")

    def close(self) -> None:
        if self.history_repository is not None:
            self.history_repository.connection.close()

    def _write_metadata(self, path, update):
        write_id3_metadata(
            path, update, overwrite_lyrics=self.overwrite_existing_lyrics
        )

    def _friendly_error(self, exc):
        if isinstance(exc, FileExistsError):
            return (
                "A filename conflict prevents this operation. No file was overwritten."
            )
        return "The file operation failed; check diagnostics."

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
                    tracks.append(
                        WorkflowTrack(path=mp3_path, current_metadata=metadata)
                    )
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
                progress_callback(
                    BatchProgress(index - 1, total, track.path, "Processing")
                )

            processed_tracks.append(
                self.process_track(track, cancellation_token=cancellation_token)
            )

            if progress_callback is not None:
                progress_callback(BatchProgress(index, total, track.path, "Processed"))

        return processed_tracks

    def apply_tracks(
        self, tracks: list[WorkflowTrack], settings: ApplySettings
    ) -> list[ApplyResult]:
        results: list[ApplyResult] = []
        if self.history_repository is None:
            return [
                ApplyResult(
                    track.path,
                    False,
                    "History database is required before modifying files.",
                )
                for track in tracks
            ]

        batch_id = self.history_repository.begin_batch()
        for track in tracks:
            if track.proposed is None:
                results.append(
                    ApplyResult(
                        track.path, False, "No previewed changes are available."
                    )
                )
                continue
            if settings.rename_file and not track.proposed.filename:
                results.append(
                    ApplyResult(
                        track.path,
                        False,
                        "No proposed filename is available for this file.",
                    )
                )
                continue
            if track.requires_review and not track.manually_reviewed:
                results.append(
                    ApplyResult(
                        track.path,
                        False,
                        "Low-confidence changes require manual review.",
                    )
                )
                continue

            try:
                if self.metadata_reader(track.path) != track.current_metadata:
                    raise ValueError("The file changed since preview. Scan again.")
                operation_id = self._create_history_record(batch_id, track, settings)
                self._apply_track(track, settings, operation_id)
            except Exception as exc:
                self.logger.exception("Apply failed for %s", track.path)
                results.append(
                    ApplyResult(track.path, False, self._friendly_error(exc))
                )
            else:
                results.append(
                    ApplyResult(track.path, True, "Applied selected changes.")
                )

        self.history_repository.mark_batch(
            batch_id,
            "applied" if all(result.success for result in results) else "partial",
        )
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
            if operation.status not in {"applied", "undo_failed"}:
                continue
            current_path = (
                operation.file_path.with_name(operation.new_filename)
                if operation.new_filename
                else operation.file_path
            )
            try:
                if not current_path.exists():
                    raise FileNotFoundError(
                        "The modified file could not be found for undo."
                    )
                original_path = operation.file_path.with_name(
                    operation.original_filename
                )
                if current_path.resolve() != original_path.resolve():
                    if original_path.exists():
                        raise FileExistsError(
                            "The original filename already exists; undo stopped."
                        )
                self.metadata_restorer(current_path, operation.original_metadata)
                if current_path.resolve() != original_path.resolve():
                    rename_without_overwrite(current_path, original_path)
                self.history_repository.mark_operation(operation.operation_id, "undone")
                results.append(
                    ApplyResult(
                        original_path,
                        True,
                        "Undo restored original metadata and filename.",
                    )
                )
                self.logger.info("Undo restored %s", original_path)
            except Exception as exc:
                self.history_repository.mark_operation(
                    operation.operation_id, "undo_failed", self._friendly_error(exc)
                )
                results.append(
                    ApplyResult(current_path, False, self._friendly_error(exc))
                )
                self.logger.exception("Undo failed for %s", current_path)
        self.history_repository.mark_batch(
            batch_id,
            "undone" if all(result.success for result in results) else "undo_partial",
        )
        return results

    def _create_history_record(
        self, batch_id: str, track: WorkflowTrack, settings: ApplySettings
    ) -> str:
        new_metadata = self._metadata_update(track, settings)
        new_filename = (
            track.proposed.filename
            if settings.rename_file and track.proposed is not None
            else None
        )
        return self.history_repository.create_operation(
            batch_id=batch_id,
            file_path=track.path,
            original_metadata=track.current_metadata,
            new_metadata=new_metadata,
            new_filename=new_filename,
        )

    def _apply_track(
        self, track: WorkflowTrack, settings: ApplySettings, operation_id: str
    ) -> None:
        proposed = track.proposed
        if proposed is None:
            return

        backup_path: Path | None = None
        current_path = track.path
        metadata_attempted = False
        try:
            if settings.rename_file and proposed.filename:
                target = track.path.with_name(proposed.filename)
                if target.exists() and target.resolve() != track.path.resolve():
                    raise FileExistsError("The target filename already exists.")
            if settings.enable_backup:
                backup_path = create_backup(
                    track.path, backup_folder=self.backup_folder
                )
                self.logger.info("Created backup %s", backup_path)

            if settings.update_id3_metadata:
                metadata_attempted = True
                self.metadata_writer(track.path, self._metadata_update(track, settings))
                self.logger.info("Updated ID3 metadata for %s", track.path)

            if settings.rename_file and proposed.filename:
                target = track.path.with_name(proposed.filename)
                if target.parent.resolve() != track.path.parent.resolve():
                    raise ValueError(
                        "Target rename path must stay in the original folder."
                    )
                if target.exists() and target.resolve() != track.path.resolve():
                    raise FileExistsError("The target filename already exists.")
                if target.resolve() != track.path.resolve():
                    rename_without_overwrite(track.path, target)
                    current_path = target
                    self.logger.info("Renamed %s to %s", track.path, target)

            self.history_repository.mark_operation(operation_id, "applied")
        except Exception as exc:
            self.history_repository.mark_operation(
                operation_id, "failed", self._friendly_error(exc)
            )
            if backup_path is not None and backup_path.exists():
                restore_backup(backup_path, current_path)
            elif metadata_attempted:
                self.metadata_restorer(current_path, track.current_metadata)
            if (
                current_path.resolve() != track.path.resolve()
                and not track.path.exists()
            ):
                rename_without_overwrite(current_path, track.path)
            raise

    def _metadata_update(
        self, track: WorkflowTrack, settings: ApplySettings
    ) -> MetadataUpdate:
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
                if settings.add_lyrics
                and proposed.lyrics is not None
                and proposed.lyrics.source == "online"
                and not proposed.lyrics.requires_review
                and (
                    not track.current_metadata.lyrics
                    or not track.current_metadata.lyrics.has_text
                    or self.overwrite_existing_lyrics
                )
                else None
            ),
        )
