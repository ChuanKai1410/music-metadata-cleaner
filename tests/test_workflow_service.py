from __future__ import annotations

from mutagen.id3 import ID3, TIT2, TPE1

from music_metadata_cleaner.app.workflow_service import ApplySettings, MusicCleanerWorkflowService, WorkflowTrack
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.domain.models import (
    CandidateRecording,
    LyricsResult,
    MusicBrainzIdentifiers,
    MusicBrainzMetadata,
    TrackMetadata,
)


class FakeIdentifier:
    def identify(self, path):
        return [
            CandidateRecording(
                recording_id="recording-id",
                artist="Fallback Artist",
                title="Fallback Title",
                duration=255,
                acoustid_score=0.98,
                musicbrainz_recording_id="recording-id",
            )
        ]


class FakeMetadataService:
    def enrich_musicbrainz_recording(self, recording_id):
        return MusicBrainzMetadata(
            artist="米津玄師",
            title="Lemon",
            album="STRAY SHEEP",
            release_date="2020-08-05",
            track_number="8",
            duration=255,
            identifiers=MusicBrainzIdentifiers(recording_id=recording_id),
        )


class FakeLyricsService:
    def get_lyrics(self, lookup, *, existing_lyrics=None):
        return LyricsResult(
            source="online",
            plain_lyrics="plain lyrics",
            synced_lyrics="[00:01.00] plain lyrics",
            confidence=1.0,
        )


def test_workflow_processes_tracks_with_mocked_services(tmp_path):
    mp3_path = tmp_path / "messy.mp3"
    mp3_path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Old Title"))
    tags.add(TPE1(encoding=3, text="Old Artist"))
    tags.save(mp3_path, v2_version=3)

    service = MusicCleanerWorkflowService(
        identifier=FakeIdentifier(),
        metadata_service=FakeMetadataService(),
        lyrics_service=FakeLyricsService(),
    )

    tracks = service.discover([mp3_path])
    processed = service.process_tracks(tracks)

    assert len(processed) == 1
    assert processed[0].proposed is not None
    assert processed[0].proposed.artist == "米津玄師"
    assert processed[0].proposed.title == "Lemon"
    assert processed[0].proposed.filename == "米津玄師 - Lemon.mp3"
    assert processed[0].confidence_score == 98
    assert processed[0].lyrics_status == "Found"
    assert processed[0].processing_status == "Ready"


def test_workflow_apply_uses_writer_and_does_not_require_ui(tmp_path):
    writes = []
    track = _track(tmp_path / "song.mp3")
    connection = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(connection)

    service = MusicCleanerWorkflowService(
        metadata_reader=lambda path: TrackMetadata(),
        metadata_writer=lambda path, update: writes.append((path, update)),
        metadata_restorer=lambda path, metadata: None,
        history_repository=HistoryRepository(connection),
    )

    results = service.apply_tracks([track], ApplySettings(rename_file=False, export_lrc=False))

    assert results[0].success is True
    assert len(writes) == 1
    assert writes[0][1].title == "Lemon"
    assert writes[0][1].artist == "米津玄師"


def test_workflow_blocks_low_confidence_automatic_apply(tmp_path):
    track = _track(tmp_path / "song.mp3", confidence_score=42, requires_review=True)
    connection = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(connection)
    service = MusicCleanerWorkflowService(
        metadata_writer=lambda path, update: None,
        history_repository=HistoryRepository(connection),
    )

    results = service.apply_tracks([track], ApplySettings())

    assert results[0].success is False
    assert "Low-confidence" in results[0].message


def test_workflow_requires_history_before_apply(tmp_path):
    track = _track(tmp_path / "song.mp3")
    service = MusicCleanerWorkflowService(metadata_writer=lambda path, update: None)

    results = service.apply_tracks([track], ApplySettings())

    assert results[0].success is False
    assert "History database is required" in results[0].message


def _track(path, *, confidence_score=98, requires_review=False):
    from music_metadata_cleaner.domain.models import ProposedTrackChanges

    path.write_bytes(b"")
    return WorkflowTrack(
        path=path,
        current_metadata=TrackMetadata(),
        proposed=ProposedTrackChanges(
            artist="米津玄師",
            title="Lemon",
            album="STRAY SHEEP",
            release_date="2020-08-05",
            track_number="8",
            filename="米津玄師 - Lemon.mp3",
            lyrics=LyricsResult(source="online", plain_lyrics="plain lyrics"),
            cover_source="Not implemented",
            musicbrainz_recording_id="recording-id",
        ),
        confidence_score=confidence_score,
        processing_status="Ready",
        requires_review=requires_review,
    )
