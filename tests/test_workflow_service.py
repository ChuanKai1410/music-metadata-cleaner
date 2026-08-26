from __future__ import annotations

from mutagen.id3 import ID3, TIT2, TPE1

from music_metadata_cleaner.app.workflow_service import ApplySettings, MusicCleanerWorkflowService, WorkflowTrack
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.domain.models import (
    AudioRecognitionResult,
    AudioRecognitionSegmentResult,
    CandidateRecording,
    LyricsResult,
    MusicBrainzIdentifiers,
    MusicBrainzMetadata,
    TrackMetadata,
    YouTubeCandidate,
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

    def find_musicbrainz_recording(self, *, artist, title, duration=None):
        return CandidateRecording(
            recording_id="recording-id",
            artist=artist,
            title=title,
            duration=duration,
            acoustid_score=0.98,
            musicbrainz_recording_id="recording-id",
        )


class FakeLyricsService:
    def get_lyrics(self, lookup, *, existing_lyrics=None):
        return LyricsResult(
            source="online",
            plain_lyrics="plain lyrics",
            synced_lyrics="[00:01.00] plain lyrics",
            confidence=1.0,
        )


class FakeYouTubeService:
    def __init__(self):
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return [
            YouTubeCandidate(
                video_id="youtube-id",
                video_url="https://www.youtube.com/watch?v=youtube-id",
                title="米津玄師 - Lemon",
                channel_id="channel-id",
                channel_name="Kenshi Yonezu 米津玄師",
                duration_seconds=255,
            )
        ]


class EmptyYouTubeService:
    def __init__(self):
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return []


class FakeFallbackRecognitionService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def recognize(self, path, *, duration_seconds=None):
        self.calls.append((path, duration_seconds))
        return self.result


def _recognition(artist="Ado", title="唱", matched=3, total=3, confidence=0.95):
    return AudioRecognitionResult(
        artist=artist,
        title=title,
        album="Album",
        release_date="2023-09-06",
        provider="AudD",
        matched_segments=matched,
        total_segments=total,
        provider_confidence=confidence,
        segment_results=(
            AudioRecognitionSegmentResult(1, 60, artist=artist, title=title, provider="AudD", provider_confidence=0.9),
        ),
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


def test_workflow_skips_youtube_for_high_confidence_by_default(tmp_path):
    youtube = FakeYouTubeService()
    mp3_path = _tagged_mp3(tmp_path / "messy.mp3")
    service = MusicCleanerWorkflowService(
        identifier=FakeIdentifier(),
        metadata_service=FakeMetadataService(),
        lyrics_service=FakeLyricsService(),
        youtube_service=youtube,
    )

    processed = service.process_tracks(service.discover([mp3_path]))

    assert processed[0].youtube_status == "Not checked"
    assert youtube.queries == []


def test_workflow_uses_youtube_to_boost_medium_confidence_match(tmp_path):
    class MediumIdentifier(FakeIdentifier):
        def identify(self, path):
            candidate = super().identify(path)[0]
            return [CandidateRecording(candidate.recording_id, candidate.artist, candidate.title, candidate.duration, 0.82, candidate.musicbrainz_recording_id)]

    youtube = FakeYouTubeService()
    mp3_path = _tagged_mp3(tmp_path / "messy.mp3")
    service = MusicCleanerWorkflowService(
        identifier=MediumIdentifier(),
        metadata_service=FakeMetadataService(),
        lyrics_service=FakeLyricsService(),
        youtube_service=youtube,
    )

    processed = service.process_tracks(service.discover([mp3_path]))

    assert processed[0].confidence_score >= 90
    assert processed[0].youtube_status == "Matched"
    assert processed[0].proposed.youtube_candidate.video_id == "youtube-id"


def test_workflow_reports_youtube_no_match_when_search_was_attempted(tmp_path):
    class EmptyIdentifier:
        def identify(self, path):
            return []

    youtube = EmptyYouTubeService()
    mp3_path = _tagged_mp3(tmp_path / "messy.mp3")
    service = MusicCleanerWorkflowService(identifier=EmptyIdentifier(), youtube_service=youtube)

    processed = service.process_tracks(service.discover([mp3_path]))

    assert youtube.queries
    assert processed[0].youtube_status == "No results"
    assert processed[0].metadata_status == "No metadata found"


def test_workflow_uses_candidate_metadata_when_musicbrainz_enrichment_fails(tmp_path):
    class BrokenMetadataService:
        def enrich_musicbrainz_recording(self, recording_id):
            raise RuntimeError("missing recording")

    mp3_path = _tagged_mp3(tmp_path / "messy.mp3")
    service = MusicCleanerWorkflowService(
        identifier=FakeIdentifier(),
        metadata_service=BrokenMetadataService(),
        lyrics_service=FakeLyricsService(),
        youtube_service=FakeYouTubeService(),
        always_use_youtube_verification=True,
    )

    processed = service.process_tracks(service.discover([mp3_path]))

    assert processed[0].metadata_status == "Found"
    assert processed[0].processing_status in {"Ready", "Needs review"}
    assert processed[0].proposed.artist == "Fallback Artist"


def test_workflow_uses_youtube_as_review_only_fallback_when_audio_has_no_match(tmp_path):
    class EmptyIdentifier:
        def identify(self, path):
            return []

    mp3_path = _tagged_mp3(tmp_path / "messy.mp3")
    service = MusicCleanerWorkflowService(
        identifier=EmptyIdentifier(),
        lyrics_service=FakeLyricsService(),
        youtube_service=FakeYouTubeService(),
    )

    processed = service.process_tracks(service.discover([mp3_path]))

    assert processed[0].metadata_status == "YouTube fallback"
    assert processed[0].confidence_score < 90
    assert processed[0].requires_review is True
    assert processed[0].proposed.youtube_candidate.video_id == "youtube-id"


def test_workflow_uses_youtube_when_high_score_audio_match_has_no_identity(tmp_path):
    class IncompleteIdentifier:
        def identify(self, path):
            return [CandidateRecording("acoustid-only", None, None, 255, 0.94, None)]

    class FilenameYouTubeService:
        def search(self, query):
            return [
                YouTubeCandidate(
                    video_id="youtube-id",
                    video_url="https://www.youtube.com/watch?v=youtube-id",
                    title="Just Kiddin x Camden Cox - Stay The Night",
                    channel_name="Just Kiddin",
                    duration_seconds=255,
                )
            ]

    mp3_path = _tagged_mp3(tmp_path / "tomp3.cc - Just Kiddin x Camden Cox  Stay The Night.mp3")
    service = MusicCleanerWorkflowService(
        identifier=IncompleteIdentifier(),
        youtube_service=FilenameYouTubeService(),
    )

    processed = service.process_tracks(service.discover([mp3_path]))

    assert processed[0].metadata_status == "YouTube fallback"
    assert processed[0].requires_review is True
    assert processed[0].proposed.artist == "Just Kiddin x Camden Cox"
    assert processed[0].proposed.title == "Stay The Night"
    assert processed[0].proposed.filename == "Just Kiddin x Camden Cox - Stay The Night.mp3"


def test_workflow_does_not_mark_incomplete_acoustid_identity_as_found_ready(tmp_path):
    class IncompleteIdentifier:
        def identify(self, path):
            return [CandidateRecording("acoustid-only", None, None, 255, 0.94, None)]

    mp3_path = _tagged_mp3(tmp_path / "unknown.mp3")
    service = MusicCleanerWorkflowService(identifier=IncompleteIdentifier())

    processed = service.process_tracks(service.discover([mp3_path]))

    assert processed[0].confidence_score == 69
    assert processed[0].requires_review is True
    assert processed[0].proposed.artist is None
    assert processed[0].recognition_status == "AudD: not configured"


def test_workflow_uses_audd_fallback_when_acoustid_has_no_match(tmp_path):
    class EmptyIdentifier:
        def identify(self, path):
            return []

    fallback = FakeFallbackRecognitionService(_recognition())
    mp3_path = _tagged_mp3(tmp_path / "流行歌曲推荐TikTok.mp3")
    service = MusicCleanerWorkflowService(
        identifier=EmptyIdentifier(),
        fallback_recognition_service=fallback,
        fallback_recognition_enabled=True,
    )

    processed = service.process_tracks(service.discover([mp3_path]))

    assert fallback.calls
    assert processed[0].proposed.artist == "Ado"
    assert processed[0].proposed.title == "唱"
    assert processed[0].proposed.filename == "Ado - 唱.mp3"
    assert processed[0].recognition_status == "AudD fallback (3/3)"
    assert processed[0].confidence_score >= 90


def test_workflow_enriches_audd_fallback_with_musicbrainz_when_available(tmp_path):
    class EmptyIdentifier:
        def identify(self, path):
            return []

    fallback = FakeFallbackRecognitionService(_recognition("Ado", "唱"))
    mp3_path = _tagged_mp3(tmp_path / "流行歌曲推荐TikTok.mp3")
    service = MusicCleanerWorkflowService(
        identifier=EmptyIdentifier(),
        metadata_service=FakeMetadataService(),
        fallback_recognition_service=fallback,
        fallback_recognition_enabled=True,
    )

    processed = service.process_tracks(service.discover([mp3_path]))

    assert processed[0].proposed.artist == "米津玄師"
    assert processed[0].proposed.title == "Lemon"
    assert processed[0].proposed.musicbrainz_recording_id == "recording-id"
    assert "MusicBrainz: confirmed" in processed[0].proposed.confidence_breakdown


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


def test_workflow_blocks_rename_when_no_proposed_filename(tmp_path):
    from music_metadata_cleaner.domain.models import ProposedTrackChanges

    path = tmp_path / "song.mp3"
    path.write_bytes(b"")
    track = WorkflowTrack(
        path=path,
        current_metadata=TrackMetadata(),
        proposed=ProposedTrackChanges(),
    )
    connection = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(connection)
    service = MusicCleanerWorkflowService(
        metadata_writer=lambda path, update: None,
        history_repository=HistoryRepository(connection),
    )

    results = service.apply_tracks([track], ApplySettings(rename_file=True))

    assert results[0].success is False
    assert "No proposed filename" in results[0].message


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


def _tagged_mp3(path):
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Old Title"))
    tags.add(TPE1(encoding=3, text="Old Artist"))
    tags.save(path, v2_version=3)
    return path
