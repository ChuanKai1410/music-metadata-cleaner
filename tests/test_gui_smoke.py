from __future__ import annotations

import os

import pytest

from music_metadata_cleaner.app.workflow_service import MusicCleanerWorkflowService, WorkflowTrack
from music_metadata_cleaner.domain.models import ProposedTrackChanges, TrackMetadata

if os.environ.get("RUN_QT_GUI_TESTS") != "1":
    pytest.skip("Set RUN_QT_GUI_TESTS=1 to run PySide6 GUI smoke tests.", allow_module_level=True)

QtWidgets = pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
MainWindow = pytest.importorskip("music_metadata_cleaner.ui.main_window", exc_type=ImportError).MainWindow
QApplication = QtWidgets.QApplication


def test_main_window_smoke_instantiates_core_widgets():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(MusicCleanerWorkflowService())

    assert window.windowTitle() == "Music Metadata Cleaner"
    assert window.table.columnCount() == 9
    assert window.scan_button.text() == "Scan"
    assert window.apply_selected_button.text() == "Apply Selected"
    assert app is not None


def test_main_window_displays_track_preview(tmp_path):
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
                filename="米津玄師 - Lemon.mp3",
                cover_source="Not implemented",
            ),
            confidence_score=98,
            metadata_status="Found",
            lyrics_status="Found",
            cover_status="Not implemented",
            processing_status="Ready",
        )
    ]

    window._refresh_table()
    window.table.selectRow(0)
    window._refresh_detail_panel()

    assert window.table.item(0, 1).text() == "米津玄師"
    assert window.table.item(0, 4).text() == "98%"
    assert window.proposed_filename.text() == "米津玄師 - Lemon.mp3"
    assert app is not None
