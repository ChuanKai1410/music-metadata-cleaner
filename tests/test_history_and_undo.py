from __future__ import annotations

from mutagen.id3 import ID3, TIT2, TPE1

from music_metadata_cleaner.app.workflow_service import ApplySettings, MusicCleanerWorkflowService, WorkflowTrack
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.domain.models import LyricsResult, ProposedTrackChanges, TrackMetadata
from music_metadata_cleaner.id3.reader import read_id3_metadata


def test_apply_creates_history_before_modifying_metadata_and_undo_restores(tmp_path):
    mp3_path = tmp_path / "old.mp3"
    mp3_path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Old Title"))
    tags.add(TPE1(encoding=3, text="Old Artist"))
    tags.save(mp3_path, v2_version=3)

    connection = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(connection)
    history = HistoryRepository(connection)
    service = MusicCleanerWorkflowService(history_repository=history, backup_folder=tmp_path / "MusicCleaner_Backup")
    track = WorkflowTrack(
        path=mp3_path,
        current_metadata=read_id3_metadata(mp3_path),
        proposed=ProposedTrackChanges(
            artist="New Artist",
            title="New Title",
            album="New Album",
            filename="New Artist - New Title.mp3",
            lyrics=LyricsResult(source="online", plain_lyrics="New lyrics"),
        ),
        confidence_score=98,
    )

    results = service.apply_tracks([track], ApplySettings(rename_file=True, add_lyrics=True))

    new_path = tmp_path / "New Artist - New Title.mp3"
    assert results[0].success is True
    assert new_path.exists()
    assert history.list_operations()[0].status == "applied"

    undo_results = service.undo_last_batch()

    restored = read_id3_metadata(mp3_path)
    assert undo_results[0].success is True
    assert mp3_path.exists()
    assert not new_path.exists()
    assert restored.title == "Old Title"
    assert restored.artist == "Old Artist"


def test_apply_rolls_back_when_lrc_export_would_overwrite(tmp_path):
    mp3_path = tmp_path / "song.mp3"
    mp3_path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Old Title"))
    tags.add(TPE1(encoding=3, text="Old Artist"))
    tags.save(mp3_path, v2_version=3)
    (tmp_path / "New Artist - New Title.lrc").write_text("existing", encoding="utf-8")

    connection = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(connection)
    history = HistoryRepository(connection)
    service = MusicCleanerWorkflowService(history_repository=history, backup_folder=tmp_path / "MusicCleaner_Backup")
    track = WorkflowTrack(
        path=mp3_path,
        current_metadata=read_id3_metadata(mp3_path),
        proposed=ProposedTrackChanges(
            artist="New Artist",
            title="New Title",
            filename="New Artist - New Title.mp3",
            lyrics=LyricsResult(source="online", plain_lyrics="New lyrics", synced_lyrics="[00:01.00] New lyrics"),
        ),
        confidence_score=98,
    )

    results = service.apply_tracks([track], ApplySettings(rename_file=True, export_lrc=True))

    restored = read_id3_metadata(mp3_path)
    assert results[0].success is False
    assert mp3_path.exists()
    assert restored.title == "Old Title"
    assert history.list_operations()[0].status == "failed"

