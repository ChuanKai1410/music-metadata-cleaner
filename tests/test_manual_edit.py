from pathlib import Path
from dataclasses import replace
import pytest
from music_metadata_cleaner.domain.manual_edit import manual_options
from music_metadata_cleaner.domain.models import TrackMetadata, Lyrics, LyricsResult
from music_metadata_cleaner.app.workflow_service import (
    MusicCleanerWorkflowService,
    WorkflowTrack,
    ApplySettings,
)
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.id3.reader import read_id3_metadata
from mutagen.id3 import ID3, TIT2, TPE1, USLT


@pytest.mark.parametrize(
    "filename,parts",
    [
        ("Imagine Dragons - Warriors (Lyrics).mp3", ("Imagine Dragons", "Warriors")),
        ("tomp3.cc - 是你  夢然.mp3", ("是你", "夢然")),
        (
            "Lizm Ladyhao - 紙短情長『我的故事都是關於你呀。』【動態歌詞Lyrics】.mp3",
            ("Lizm Ladyhao", "紙短情長"),
        ),
        (
            "Lil Nas X - MONTERO (Call Me By Your Name).mp3",
            ("Lil Nas X", "MONTERO (Call Me By Your Name)"),
        ),
        ("Artist - Song (Live).mp3", ("Artist", "Song (Live)")),
    ],
)
def test_filename_dropdown_fragments(filename, parts):
    options = manual_options(filename, TrackMetadata())
    for part in parts:
        assert part in options.artists and part in options.titles


def test_manual_identity_offline_preview_and_lyrics_independence():
    service = MusicCleanerWorkflowService()
    track = WorkflowTrack(Path("track001.mp3"), TrackMetadata())
    first = service.manual_edit(track, artist="Ado", title="唱")
    second = service.manual_edit(
        track, artist="Ado", title="唱", plain_lyrics="manual text"
    )
    assert first.confidence_score == second.confidence_score == 0
    assert first.manually_reviewed and second.manually_reviewed
    assert first.identity_manually_edited
    assert first.lyrics_status == "Not Found" and second.lyrics_status == "Found"
    assert second.proposed.filename == "Ado - 唱.mp3"
    with pytest.raises(ValueError):
        service.manual_edit(track, artist="", title="唱")


def test_manual_apply_overwrite_and_undo(tmp_path):
    path = tmp_path / "track001.mp3"
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="old"))
    tags.add(TPE1(encoding=3, text="old"))
    tags.add(USLT(encoding=3, lang="und", text="keep"))
    tags.save(path)
    conn = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(conn)
    service = MusicCleanerWorkflowService(history_repository=HistoryRepository(conn))
    track = service.discover([path])[0]
    before = path.read_bytes()
    with pytest.raises(ValueError):
        service.manual_edit(track, artist="New", title="Song", plain_lyrics="new")
    preview = service.manual_edit(
        track,
        artist="New",
        title="Song",
        plain_lyrics="new",
        overwrite_existing_lyrics=True,
    )
    assert path.read_bytes() == before
    assert service.apply_tracks([preview], ApplySettings(add_lyrics=False))[0].success
    assert read_id3_metadata(tmp_path / "New - Song.mp3").lyrics.text == "new"
    assert service.undo_last_batch()[0].success
    assert read_id3_metadata(path) == track.current_metadata
    service.close()


def test_manual_identity_change_drops_old_online_lyrics():
    from music_metadata_cleaner.domain.models import ProposedTrackChanges

    track = WorkflowTrack(
        Path("a.mp3"),
        TrackMetadata(),
        proposed=ProposedTrackChanges(
            artist="Old",
            title="Song",
            lyrics=LyricsResult(source="online", plain_lyrics="wrong song"),
        ),
    )
    edited = MusicCleanerWorkflowService().manual_edit(
        track, artist="New", title="Different"
    )
    assert edited.proposed.lyrics is None


def test_online_lyrics_never_change_identity_confidence():
    from tests.test_search_resolution import FakeSearch

    class Provider:
        def __init__(self, result):
            self.result = result

        def get_lyrics(self, *args, **kwargs):
            return self.result

    track = WorkflowTrack(Path("米津玄師 Lemon.mp3"), TrackMetadata())
    scores = []
    for lyrics in [
        None,
        LyricsResult(source="online", plain_lyrics="text"),
        LyricsResult(source="online", plain_lyrics="wrong", requires_review=True),
    ]:
        service = MusicCleanerWorkflowService(
            search_provider=FakeSearch(), lyrics_service=Provider(lyrics)
        )
        preview = service.process_track(track)
        scores.append(preview.confidence_score)
        assert not preview.requires_review
    assert len(set(scores)) == 1


def test_manual_lyrics_only_preserves_search_score():
    from tests.test_search_resolution import FakeSearch

    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(), retrieve_lyrics=False
    )
    preview = service.process_track(
        WorkflowTrack(Path("米津玄師 Lemon.mp3"), TrackMetadata())
    )
    edited = service.manual_edit(
        preview,
        artist=preview.proposed.artist,
        title=preview.proposed.title,
        plain_lyrics="typed",
    )
    assert edited.confidence_score == preview.confidence_score
    assert edited.resolved_identity == preview.resolved_identity
    assert not edited.identity_manually_edited
