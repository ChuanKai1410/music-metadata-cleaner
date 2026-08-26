from __future__ import annotations

import os
from pathlib import Path

import pytest

from music_metadata_cleaner.app.workflow_service import ApplyResult, MusicCleanerWorkflowService, WorkflowTrack
from music_metadata_cleaner.config import AppConfig, load_config, save_config
from music_metadata_cleaner.domain.models import ProposedTrackChanges, TrackMetadata, YouTubeCandidate

if os.environ.get("RUN_QT_GUI_TESTS") != "1":
    pytest.skip("Set RUN_QT_GUI_TESTS=1 to run PySide6 GUI smoke tests.", allow_module_level=True)

QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
MainWindow = pytest.importorskip("music_metadata_cleaner.ui.main_window", exc_type=ImportError).MainWindow
SettingsDialog = pytest.importorskip("music_metadata_cleaner.ui.settings_dialog", exc_type=ImportError).SettingsDialog
QApplication = QtWidgets.QApplication
QMessageBox = QtWidgets.QMessageBox


class FakeApplyWorkflowService(MusicCleanerWorkflowService):
    def __init__(self):
        super().__init__()
        self.applied = []
        self.undo_called = False

    def apply_tracks(self, tracks, settings):
        self.applied.append((tracks, settings))
        return [ApplyResult(track.path, True, "Applied selected changes.") for track in tracks]

    def undo_last_batch(self):
        self.undo_called = True
        return [ApplyResult(Path("song.mp3"), True, "Restored.")]


def test_main_window_smoke_instantiates_clean_core_widgets():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MusicCleanerWorkflowService())

    assert window.windowTitle() == "Music Metadata Cleaner"
    assert window.table.columnCount() == 7
    assert [window.table.horizontalHeaderItem(i).text() for i in range(7)] == [
        "File",
        "Artist",
        "Title",
        "Confidence",
        "Lyrics",
        "Recognition",
        "Status",
    ]
    assert window.scan_button.text() == "Scan"
    assert window.settings_button.text() == "Settings"
    assert window.remove_high_confidence_button.text() == "Remove All High Confidence"
    assert window.remove_high_confidence_button.isEnabled() is False
    assert not hasattr(window, "add_cover_checkbox")
    assert not hasattr(window, "proposed_cover")
    assert app is not None


def test_main_window_displays_simplified_track_preview(tmp_path):
    app = QApplication.instance() or QApplication([])
    mp3_path = tmp_path / "messy.mp3"
    mp3_path.write_bytes(b"")
    window = MainWindow(MusicCleanerWorkflowService())
    window.tracks = [
        WorkflowTrack(
            path=mp3_path,
            current_metadata=TrackMetadata(artist="Old Artist", title="Old Title", album="Old Album"),
            proposed=ProposedTrackChanges(
                artist="米津玄師",
                title="Lemon",
                album="STRAY SHEEP",
                release_date="2020-08-05",
                filename="米津玄師 - Lemon.mp3",
                youtube_candidate=YouTubeCandidate(
                    video_id="youtube-id",
                    video_url="https://www.youtube.com/watch?v=youtube-id",
                    title="米津玄師 - Lemon",
                    channel_name="Kenshi Yonezu 米津玄師",
                    duration_seconds=255,
                    score=92,
                ),
                musicbrainz_recording_id="recording-id",
            ),
            confidence_score=98,
            metadata_status="Found",
            lyrics_status="Found",
            recognition_status="AudD fallback (3/3)",
            diagnostic_status="AcoustID: no match | AudD: 3/3 | YouTube: matched",
            youtube_status="Matched",
            processing_status="Ready",
        )
    ]

    window._refresh_table()
    window.table.selectRow(0)
    window._refresh_detail_panel()

    assert window.table.item(0, 1).text() == "米津玄師"
    assert window.table.item(0, 3).text() == "98%"
    assert window.table.item(0, 5).text() == "AudD"
    assert window.table.item(0, 6).text() == "Ready"
    assert window.proposed_filename.text() == "米津玄師 - Lemon.mp3"
    assert window.recognition_source.text() == "AudD + MusicBrainz"
    assert window.youtube_summary.text() == "Verified"
    assert window.open_youtube_button.isEnabled() is True
    assert window.diagnostics_button.isEnabled() is True
    assert app is not None


def test_apply_selected_apply_all_and_undo_still_work(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    high_path = tmp_path / "high.mp3"
    low_path = tmp_path / "low.mp3"
    high_path.write_bytes(b"")
    low_path.write_bytes(b"")
    service = FakeApplyWorkflowService()
    window = MainWindow(service)
    window.tracks = [
        _workflow_track(high_path, confidence_score=98, requires_review=False),
        _workflow_track(low_path, confidence_score=82, requires_review=True),
    ]
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    window._refresh_table()
    window.table.selectRow(0)
    window.apply_selected()
    window.apply_all_high_confidence()
    assert window.remove_high_confidence_button.isEnabled() is True
    window.remove_applied_high_confidence()
    assert window.remove_high_confidence_button.isEnabled() is False
    assert len(window.tracks) == 1
    window.undo_last_batch()

    assert len(service.applied) == 2
    assert service.undo_called is True
    assert app is not None


def test_settings_dialog_loads_and_persists_values_without_revealing_secrets(tmp_path):
    app = QApplication.instance() or QApplication([])
    config_path = tmp_path / "preferences.json"
    save_config(
        config_path,
        AppConfig(
            audd_api_token="secret-audd",
            youtube_api_key="secret-youtube",
            ffmpeg_path="C:\\Tools\\ffmpeg\\bin\\ffmpeg.exe",
            fallback_recognition_enabled=True,
            multi_segment_recognition_enabled=True,
            max_recognition_segments=3,
            fallback_recognition_threshold=70,
        ),
    )
    dialog = SettingsDialog(
        config=load_config(config_path),
        config_path=config_path,
        workflow_service=MusicCleanerWorkflowService(),
    )

    assert dialog.audd_status.text() == "Configured"
    assert dialog.youtube_status.text() == "Configured"
    assert dialog.audd_token_input.text() == ""
    assert dialog.youtube_key_input.text() == ""

    dialog.enable_audd_checkbox.setChecked(False)
    dialog.multi_segment_checkbox.setChecked(False)
    dialog.max_segments_spin.setValue(1)
    dialog.fallback_threshold_spin.setValue(65)
    dialog.ffmpeg_input.setText("D:\\ffmpeg\\bin\\ffmpeg.exe")
    dialog.rename_file_checkbox.setChecked(True)
    dialog.save()
    loaded = load_config(config_path)

    assert loaded.audd_api_token == "secret-audd"
    assert loaded.youtube_api_key == "secret-youtube"
    assert loaded.fallback_recognition_enabled is False
    assert loaded.multi_segment_recognition_enabled is False
    assert loaded.max_recognition_segments == 1
    assert loaded.fallback_recognition_threshold == 65
    assert loaded.ffmpeg_path == "D:\\ffmpeg\\bin\\ffmpeg.exe"
    assert loaded.default_rename_file is True
    assert app is not None


def _workflow_track(path, *, confidence_score, requires_review):
    return WorkflowTrack(
        path=path,
        current_metadata=TrackMetadata(),
        proposed=ProposedTrackChanges(
            artist="Artist",
            title=path.stem,
            album="Album",
            filename=f"Artist - {path.stem}.mp3",
        ),
        confidence_score=confidence_score,
        metadata_status="Found",
        lyrics_status="Found",
        recognition_status="AcoustID",
        processing_status="Ready",
        requires_review=requires_review,
    )
