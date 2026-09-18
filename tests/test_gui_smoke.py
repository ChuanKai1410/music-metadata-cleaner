"""Offscreen GUI regression coverage; all search operations are mocked."""

import os
import time
from pathlib import Path
import pytest
from music_metadata_cleaner.app.workflow_service import (
    MusicCleanerWorkflowService,
    WorkflowTrack,
)
from music_metadata_cleaner.domain.models import TrackMetadata
from music_metadata_cleaner.config import AppConfig, load_config
from music_metadata_cleaner.domain.search import SearchResult

if os.environ.get("RUN_QT_GUI_TESTS") != "1":
    pytest.skip(
        "Set RUN_QT_GUI_TESTS=1 for offscreen PySide6 tests.", allow_module_level=True
    )
QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
from music_metadata_cleaner.ui.main_window import MainWindow
from music_metadata_cleaner.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class Search:
    def search(self, query, count=8):
        return [
            SearchResult("Ado - 唱", "https://youtube.com/1"),
            SearchResult("唱 by Ado", "https://spotify.com/1"),
            SearchResult("Ado - 唱 Lyrics | Genius", "https://genius.com/1"),
        ]


def wait_for(app, predicate):
    deadline = time.monotonic() + 5
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert predicate()


def test_main_window_has_six_columns_and_no_obsolete_controls(app):
    window = MainWindow(MusicCleanerWorkflowService())
    assert [
        window.table.horizontalHeaderItem(i).text()
        for i in range(window.table.columnCount())
    ] == ["File", "Artist", "Title", "Confidence", "Lyrics", "Status"]
    assert window.manual_search_button.text() == "Search"
    assert window.diagnostics_button.text() == "View Search Evidence"
    labels = " ".join(w.text() for w in window.findChildren(QtWidgets.QLabel))
    buttons = " ".join(w.text() for w in window.findChildren(QtWidgets.QPushButton))
    for obsolete in [
        "AudD",
        "AcoustID",
        "MusicBrainz",
        "YouTube",
        "Synced",
        "LRC",
        "Recognition",
    ]:
        assert obsolete not in labels + buttons
    window.close()


def test_manual_search_uses_background_worker_and_displays_preview(app):
    window = MainWindow(
        MusicCleanerWorkflowService(search_provider=Search(), retrieve_lyrics=False)
    )
    window.tracks = [WorkflowTrack(Path("track001.mp3"), TrackMetadata())]
    window._refresh_table()
    window.table.selectRow(0)
    window.search_keywords.setText("Ado 唱")
    window.manual_search()
    assert not window.apply_selected_button.isEnabled()
    wait_for(app, lambda: window.processing_thread is None)
    assert window.tracks[0].proposed.artist == "Ado"
    assert window.table.item(0, 3).text() == "High"
    assert window.proposed_filename.text() == "Ado - 唱.mp3"
    assert window.diagnostics_button.isEnabled()
    window.close()


def test_insufficient_information_shows_low_and_no_identity(app):
    service = MusicCleanerWorkflowService()
    window = MainWindow(service)
    window.tracks = [
        service.process_track(WorkflowTrack(Path("track001.mp3"), TrackMetadata()))
    ]
    window._refresh_table()
    window.table.selectRow(0)
    assert window.table.item(0, 1).text() == "-"
    assert window.table.item(0, 3).text() == "Low"
    assert window.table.item(0, 5).text() == "Insufficient Information"
    window.close()


def test_settings_roundtrip_has_no_keys_or_recognition_controls(app, tmp_path):
    path = tmp_path / "preferences.json"
    dialog = SettingsDialog(AppConfig(), path)
    assert [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())] == [
        "General",
        "Search",
        "Lyrics",
        "Files & Safety",
        "Advanced",
    ]
    assert dialog.preserve_lyrics_checkbox.isChecked()
    assert not dialog.overwrite_lyrics_checkbox.isEnabled()
    dialog.searxng_url_edit.setText("http://search.example:8080")
    dialog.maximum_results_spin.setValue(9)
    dialog.timeout_spin.setValue(12)
    dialog.save()
    config = load_config(path)
    assert config.searxng_url == "http://search.example:8080"
    assert config.maximum_search_results == 9
    assert config.search_timeout_seconds == 12
    assert config.preserve_existing_lyrics
    assert "api_key" not in path.read_text()


def test_connection_button_runs_off_main_thread(app, tmp_path, monkeypatch):
    from music_metadata_cleaner.ui import settings_dialog

    monkeypatch.setattr(settings_dialog, "test_search_connection", lambda *args: "PASS")
    dialog = SettingsDialog(
        AppConfig(searxng_url="http://search.example"), tmp_path / "prefs.json"
    )
    dialog._test_connection()
    wait_for(app, lambda: dialog.test_worker is None)
    assert dialog.connection_status.text() == "PASS"
    dialog.close()


def test_candidate_selection_is_user_confirmed(app, monkeypatch):
    class WeakSearch(Search):
        def search(self, query, count=8):
            return super().search(query, count)[:1]

    service = MusicCleanerWorkflowService(
        search_provider=WeakSearch(), retrieve_lyrics=False
    )
    track = service.manual_search(
        WorkflowTrack(Path("track001.mp3"), TrackMetadata()), "Ado 唱"
    )
    assert track.requires_review
    window = MainWindow(service)
    window.tracks = [track]
    window._refresh_table()
    window.table.selectRow(0)
    monkeypatch.setattr(
        QtWidgets.QInputDialog, "getItem", lambda *args: (args[3][0], True)
    )
    window.use_candidate()
    wait_for(app, lambda: window.processing_thread is None)
    assert window.tracks[0].manually_reviewed
    assert not window.tracks[0].requires_review
    window.close()


def test_apply_and_undo_update_displayed_paths(app, tmp_path, monkeypatch):
    from mutagen.id3 import ID3, TIT2, TPE1
    from music_metadata_cleaner.db.connection import connect_database
    from music_metadata_cleaner.db.schema import initialize_schema
    from music_metadata_cleaner.db.history import HistoryRepository

    path = tmp_path / "Ado 唱.mp3"
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="唱"))
    tags.add(TPE1(encoding=3, text="Ado"))
    tags.save(path)
    conn = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(conn)
    service = MusicCleanerWorkflowService(
        search_provider=Search(),
        retrieve_lyrics=False,
        history_repository=HistoryRepository(conn),
    )
    window = MainWindow(service)
    window.tracks = [service.process_track(service.discover([path])[0])]
    window._refresh_table()
    window.table.selectRow(0)
    monkeypatch.setattr(
        QtWidgets.QMessageBox,
        "question",
        lambda *args: QtWidgets.QMessageBox.StandardButton.Yes,
    )
    window.apply_all_high_confidence()
    assert window.tracks[0].path.name == "Ado - 唱.mp3"
    assert window.tracks[0].proposed is None
    assert window.remove_high_confidence_button.isEnabled()
    window.undo_last_batch()
    assert path.exists()
    assert window.tracks[0].path == path
    window.close()


def test_manual_editor_dropdown_preview_and_validation(app):
    from music_metadata_cleaner.ui.manual_edit_dialog import ManualEditDialog

    track = WorkflowTrack(Path("Artist - Song (Live).mp3"), TrackMetadata())
    dialog = ManualEditDialog(track)
    assert "Artist" in [
        dialog.artist_combo.itemText(i) for i in range(dialog.artist_combo.count())
    ]
    assert "Song (Live)" in [
        dialog.title_combo.itemText(i) for i in range(dialog.title_combo.count())
    ]
    dialog._save()
    assert dialog.result() != dialog.DialogCode.Accepted
    dialog.artist_combo.setEditText("Artist")
    dialog.title_combo.setEditText("Song (Live)")
    assert dialog.filename_label.text() == "Artist - Song (Live).mp3"
    dialog._swap()
    assert dialog.artist_combo.currentText() == "Song (Live)"
    dialog._swap()
    dialog.edit_lyrics.setChecked(True)
    dialog.lyrics_edit.setPlainText("user plain lyrics")
    dialog._save()
    assert dialog.result() == dialog.DialogCode.Accepted


def test_manual_edit_button_handles_no_search_results(app, monkeypatch):
    from music_metadata_cleaner.ui.manual_edit_dialog import ManualEditDialog

    window = MainWindow(MusicCleanerWorkflowService())
    window.tracks = [
        WorkflowTrack(
            Path("track001.mp3"),
            TrackMetadata(),
            processing_status="Insufficient Information",
        )
    ]
    window._refresh_table()
    window.table.selectRow(0)
    assert window.edit_metadata_button.isEnabled()

    def accept(dialog):
        dialog.artist_combo.setEditText("Ado")
        dialog.title_combo.setEditText("唱")
        return dialog.DialogCode.Accepted

    monkeypatch.setattr(ManualEditDialog, "exec", accept)
    window.edit_metadata()
    assert window.tracks[0].proposed.filename == "Ado - 唱.mp3"
    assert window.table.item(0, 3).text() == "Manual confirmed"
    window.close()
