"""PySide6 desktop main window."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable
import webbrowser

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QInputDialog,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from music_metadata_cleaner.app.service_factory import CONFIG_PATH
from music_metadata_cleaner.app.workflow_service import (
    ApplyResult,
    BatchProgress,
    CancellationToken,
    MusicCleanerWorkflowService,
    WorkflowTrack,
)
from music_metadata_cleaner.config import load_config
from music_metadata_cleaner.files.safe_paths import generate_mp3_filename
from music_metadata_cleaner.ui.settings_dialog import SettingsDialog


COLUMNS = ["File", "Artist", "Title", "Confidence", "Lyrics", "Recognition", "Status"]


class ProcessingWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        service: MusicCleanerWorkflowService,
        tracks: list[WorkflowTrack],
        token: CancellationToken,
    ) -> None:
        super().__init__()
        self.service = service
        self.tracks = tracks
        self.token = token

    @Slot()
    def run(self) -> None:
        results = self.service.process_tracks(self.tracks, cancellation_token=self.token, progress_callback=self.progress.emit)
        self.finished.emit(results)


class MainWindow(QMainWindow):
    """Main desktop workflow window."""

    def __init__(
        self,
        workflow_service: MusicCleanerWorkflowService,
        *,
        workflow_service_factory: Callable[[], MusicCleanerWorkflowService] | None = None,
    ) -> None:
        super().__init__()
        self.workflow_service = workflow_service
        self.workflow_service_factory = workflow_service_factory
        self.tracks: list[WorkflowTrack] = []
        self.processing_thread: QThread | None = None
        self.processing_worker: ProcessingWorker | None = None
        self.cancellation_token: CancellationToken | None = None
        self.applied_high_confidence_paths: set[Path] = set()

        self.setWindowTitle("Music Metadata Cleaner")
        self.resize(1180, 760)
        self._build_ui()
        self._connect_signals()
        self._refresh_table()
        self._refresh_detail_panel()

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(12, 10, 12, 10)
        root_layout.setSpacing(8)

        header_layout = QHBoxLayout()
        title = QLabel("Music Metadata Cleaner")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.history_button = QPushButton("History")
        self.settings_button = QPushButton("Settings")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        header_layout.addWidget(self.history_button)
        header_layout.addWidget(self.settings_button)
        root_layout.addLayout(header_layout)

        toolbar_layout = QHBoxLayout()
        self.add_files_button = QPushButton("Add MP3 Files")
        self.add_folder_button = QPushButton("Add Folder")
        self.remove_files_button = QPushButton("Remove")
        self.clear_files_button = QPushButton("Clear")
        self.scan_button = QPushButton("Scan")
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_files_button,
            self.clear_files_button,
            self.scan_button,
        ):
            toolbar_layout.addWidget(button)
        toolbar_layout.addStretch(1)
        root_layout.addLayout(toolbar_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.table)

        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.setContentsMargins(8, 0, 0, 0)
        side_layout.setSpacing(8)
        self.detail_group = QGroupBox("Selected Track")
        detail_layout = QVBoxLayout(self.detail_group)

        compare_layout = QGridLayout()
        compare_layout.setHorizontalSpacing(18)
        compare_layout.addWidget(_section_label("Current"), 0, 1)
        compare_layout.addWidget(_section_label("Proposed"), 0, 2)
        self.current_filename = QLabel("-")
        self.current_artist = QLabel("-")
        self.current_title = QLabel("-")
        self.current_album = QLabel("-")
        self.current_year = QLabel("-")
        self.proposed_filename = QLabel("-")
        self.proposed_artist = QLabel("-")
        self.proposed_title = QLabel("-")
        self.proposed_album = QLabel("-")
        self.proposed_year = QLabel("-")
        rows = [
            ("Filename", self.current_filename, self.proposed_filename),
            ("Artist", self.current_artist, self.proposed_artist),
            ("Title", self.current_title, self.proposed_title),
            ("Album", self.current_album, self.proposed_album),
            ("Year", self.current_year, self.proposed_year),
        ]
        for row, (name, current, proposed) in enumerate(rows, start=1):
            compare_layout.addWidget(QLabel(name), row, 0)
            compare_layout.addWidget(current, row, 1)
            compare_layout.addWidget(proposed, row, 2)
            current.setWordWrap(True)
            proposed.setWordWrap(True)
        detail_layout.addLayout(compare_layout)

        summary_group = QGroupBox("Recognition")
        summary_layout = QGridLayout(summary_group)
        self.recognition_source = QLabel("-")
        self.confidence_summary = QLabel("-")
        self.youtube_summary = QLabel("-")
        self.lyrics_summary = QLabel("-")
        summary_layout.addWidget(QLabel("Source"), 0, 0)
        summary_layout.addWidget(self.recognition_source, 0, 1)
        summary_layout.addWidget(QLabel("Confidence"), 1, 0)
        summary_layout.addWidget(self.confidence_summary, 1, 1)
        summary_layout.addWidget(QLabel("YouTube"), 2, 0)
        summary_layout.addWidget(self.youtube_summary, 2, 1)
        summary_layout.addWidget(QLabel("Lyrics"), 3, 0)
        summary_layout.addWidget(self.lyrics_summary, 3, 1)
        detail_layout.addWidget(summary_group)

        detail_buttons = QHBoxLayout()
        self.diagnostics_button = QPushButton("Diagnostics")
        self.open_youtube_button = QPushButton("Open YouTube Result")
        self.select_youtube_button = QPushButton("Select YouTube Candidate")
        self.diagnostics_button.setEnabled(False)
        self.open_youtube_button.setEnabled(False)
        self.select_youtube_button.setEnabled(False)
        detail_buttons.addWidget(self.diagnostics_button)
        detail_buttons.addWidget(self.open_youtube_button)
        detail_buttons.addWidget(self.select_youtube_button)
        detail_buttons.addStretch(1)
        detail_layout.addLayout(detail_buttons)
        side_layout.addWidget(self.detail_group)
        side_layout.addStretch(1)
        splitter.addWidget(side_panel)
        splitter.setSizes([820, 360])
        root_layout.addWidget(splitter, 1)

        action_layout = QHBoxLayout()
        self.preview_button = QPushButton("Preview Changes")
        self.apply_selected_button = QPushButton("Apply Selected")
        self.apply_high_confidence_button = QPushButton("Apply All High Confidence")
        self.remove_high_confidence_button = QPushButton("Remove All High Confidence")
        self.undo_button = QPushButton("Undo Last Batch")
        self.cancel_button = QPushButton("Cancel")
        self.remove_high_confidence_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        action_layout.addStretch(1)
        for button in (
            self.preview_button,
            self.apply_selected_button,
            self.apply_high_confidence_button,
            self.remove_high_confidence_button,
            self.undo_button,
            self.cancel_button,
        ):
            action_layout.addWidget(button)
        root_layout.addLayout(action_layout)

        progress_layout = QHBoxLayout()
        self.progress_label = QLabel("Idle")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.status_label = QLabel("Ready")
        self.show_log_button = QPushButton("Show Log")
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.status_label)
        progress_layout.addWidget(self.show_log_button)
        root_layout.addLayout(progress_layout)

        self.message_box = QPlainTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setMaximumHeight(110)
        self.message_box.setVisible(False)
        root_layout.addWidget(self.message_box)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.add_files_button.clicked.connect(self.add_files)
        self.add_folder_button.clicked.connect(self.add_folder)
        self.remove_files_button.clicked.connect(self.remove_selected_files)
        self.clear_files_button.clicked.connect(self.clear_files)
        self.scan_button.clicked.connect(self.scan_files)
        self.preview_button.clicked.connect(self.preview_changes)
        self.apply_selected_button.clicked.connect(self.apply_selected)
        self.apply_high_confidence_button.clicked.connect(self.apply_all_high_confidence)
        self.remove_high_confidence_button.clicked.connect(self.remove_applied_high_confidence)
        self.open_youtube_button.clicked.connect(self.open_youtube_result)
        self.select_youtube_button.clicked.connect(self.select_youtube_candidate)
        self.diagnostics_button.clicked.connect(self.view_track_diagnostics)
        self.history_button.clicked.connect(self.view_history)
        self.undo_button.clicked.connect(self.undo_last_batch)
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.settings_button.clicked.connect(self.open_settings)
        self.show_log_button.clicked.connect(self.toggle_log)
        self.table.itemSelectionChanged.connect(self._refresh_detail_panel)

    @Slot()
    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add MP3 Files", "", "MP3 Files (*.mp3)")
        if paths:
            self._add_paths([Path(path) for path in paths])

    @Slot()
    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add Folder")
        if path:
            self._add_paths([Path(path)])

    def _add_paths(self, paths: list[Path]) -> None:
        discovered = self.workflow_service.discover(paths)
        existing = {track.path.resolve() for track in self.tracks}
        self.tracks.extend(track for track in discovered if track.path.resolve() not in existing)
        self._clear_applied_high_confidence_paths()
        self._refresh_table()
        self._set_status(f"Added {len(discovered)} MP3 file(s).")

    @Slot()
    def remove_selected_files(self) -> None:
        rows = sorted(self._selected_rows(), reverse=True)
        for row in rows:
            self.tracks.pop(row)
        self._sync_applied_high_confidence_paths()
        self._refresh_table()
        self._refresh_detail_panel()
        self._set_status(f"Removed {len(rows)} row(s).")

    @Slot()
    def clear_files(self) -> None:
        self.tracks.clear()
        self._clear_applied_high_confidence_paths()
        self._refresh_table()
        self._refresh_detail_panel()
        self._set_status("List cleared.")

    @Slot()
    def scan_files(self) -> None:
        self.preview_changes()

    @Slot()
    def preview_changes(self) -> None:
        if not self.tracks:
            self._show_info("Add MP3 files or a folder first.")
            return
        if self.processing_thread is not None:
            return
        self._reload_workflow_service()

        self.cancellation_token = CancellationToken()
        self.processing_thread = QThread()
        self.processing_worker = ProcessingWorker(self.workflow_service, self.tracks, self.cancellation_token)
        self.processing_worker.moveToThread(self.processing_thread)
        self.processing_thread.started.connect(self.processing_worker.run)
        self.processing_worker.progress.connect(self._handle_progress)
        self.processing_worker.finished.connect(self._handle_processing_finished)
        self.processing_worker.finished.connect(self.processing_thread.quit)
        self.processing_worker.finished.connect(self.processing_worker.deleteLater)
        self.processing_thread.finished.connect(self.processing_thread.deleteLater)
        self.processing_thread.finished.connect(self._clear_processing_thread)

        self.cancel_button.setEnabled(True)
        self.preview_button.setEnabled(False)
        self.scan_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting")
        self._set_status("Scanning...")
        self.processing_thread.start()

    @Slot()
    def cancel_processing(self) -> None:
        if self.cancellation_token is not None:
            self.cancellation_token.cancel()
            self._set_status("Cancelling...")

    @Slot(object)
    def _handle_progress(self, progress: BatchProgress) -> None:
        value = round((progress.processed / progress.total) * 100) if progress.total else 0
        self.progress_bar.setValue(value)
        current = progress.current_path.name if progress.current_path is not None else "-"
        self.progress_label.setText(f"Scanning {progress.processed} / {progress.total}")
        self.status_label.setText(f"Current: {current}")

    @Slot(object)
    def _handle_processing_finished(self, tracks: list[WorkflowTrack]) -> None:
        self.tracks = tracks
        self._clear_applied_high_confidence_paths()
        self.cancel_button.setEnabled(False)
        self.preview_button.setEnabled(True)
        self.scan_button.setEnabled(True)
        self.progress_bar.setValue(100 if tracks else 0)
        self.progress_label.setText("Complete")
        ready = sum(1 for track in tracks if _status_text(track) == "Ready")
        review = sum(1 for track in tracks if _status_text(track) == "Review")
        failed = sum(1 for track in tracks if _status_text(track) == "Failed")
        self._refresh_table()
        self._refresh_detail_panel()
        self._set_status(f"{len(tracks)} processed - {ready} ready, {review} review, {failed} failed.")

    @Slot()
    def _clear_processing_thread(self) -> None:
        self.processing_thread = None
        self.processing_worker = None
        self.cancellation_token = None

    @Slot()
    def apply_selected(self) -> None:
        selected = [self.tracks[row] for row in self._selected_rows()]
        if not selected:
            self._show_info("Select one or more rows first.")
            return
        self._apply_tracks(selected)

    @Slot()
    def apply_all_high_confidence(self) -> None:
        tracks = [track for track in self.tracks if track.confidence_score >= 90 and not track.requires_review]
        if not tracks:
            self._show_info("No high-confidence ready tracks are available.")
            return
        results = self._apply_tracks(tracks)
        self.applied_high_confidence_paths = {result.path.resolve() for result in results if result.success}
        self.remove_high_confidence_button.setEnabled(bool(self.applied_high_confidence_paths))

    @Slot()
    def remove_applied_high_confidence(self) -> None:
        if not self.applied_high_confidence_paths:
            return
        before_count = len(self.tracks)
        self.tracks = [
            track for track in self.tracks if track.path.resolve() not in self.applied_high_confidence_paths
        ]
        removed_count = before_count - len(self.tracks)
        self._clear_applied_high_confidence_paths()
        self._refresh_table()
        self._refresh_detail_panel()
        self._set_status(f"Removed {removed_count} applied high-confidence row(s).")

    def _apply_tracks(self, tracks: list[WorkflowTrack]) -> list[ApplyResult]:
        reply = QMessageBox.question(
            self,
            "Apply Changes",
            f"Apply configured changes to {len(tracks)} file(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return []

        results = self.workflow_service.apply_tracks(tracks, self.workflow_service.default_apply_settings)
        success_count = sum(1 for result in results if result.success)
        failure_count = len(results) - success_count
        self._set_status(f"Apply complete: {success_count} succeeded, {failure_count} failed.")
        for result in results:
            if not result.success:
                self._log(f"{result.path.name}: {result.message}")
        return results

    @Slot()
    def open_settings(self) -> None:
        dialog = SettingsDialog(
            config=load_config(CONFIG_PATH),
            config_path=CONFIG_PATH,
            workflow_service=self.workflow_service,
            parent=self,
        )
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self._reload_workflow_service()
            self._set_status("Settings saved.")

    @Slot()
    def view_history(self) -> None:
        operations = self.workflow_service.list_operations(limit=25)
        if not operations:
            self._show_info("No operation history is available.")
            return
        lines = [
            f"{operation.created_at} | {operation.status} | {operation.original_filename} -> {operation.new_filename or '-'}"
            for operation in operations
        ]
        QMessageBox.information(self, "Recent Operations", "\n".join(lines))

    @Slot()
    def undo_last_batch(self) -> None:
        reply = QMessageBox.question(
            self,
            "Undo Last Batch",
            "Restore original metadata and filenames for the last applied batch?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        results = self.workflow_service.undo_last_batch()
        if not results:
            self._show_info("No applied batch is available to undo.")
            return
        success_count = sum(1 for result in results if result.success)
        failure_count = len(results) - success_count
        self._set_status(f"Undo complete: {success_count} restored, {failure_count} failed.")

    @Slot()
    def view_track_diagnostics(self) -> None:
        track = self._selected_track()
        if track is None:
            return
        proposed = track.proposed
        lines = [
            f"File: {track.path.name}",
            f"Status: {_status_text(track)}",
            f"Recognition: {_recognition_text(track)}",
            f"YouTube: {_youtube_text(track)}",
            "",
            track.diagnostic_status or "No detailed diagnostics are available.",
        ]
        if proposed and proposed.confidence_breakdown:
            lines.extend(["", "Evidence:", *proposed.confidence_breakdown])
        QMessageBox.information(self, "Track Diagnostics", "\n".join(lines))

    @Slot()
    def open_youtube_result(self) -> None:
        track = self._selected_track()
        candidate = track.proposed.youtube_candidate if track and track.proposed else None
        if candidate is None:
            self._show_info("No YouTube result is available for the selected row.")
            return
        webbrowser.open(candidate.video_url)

    @Slot()
    def select_youtube_candidate(self) -> None:
        row = self._selected_rows()[0] if self._selected_rows() else None
        if row is None:
            self._show_info("Select a row first.")
            return

        track = self.tracks[row]
        if track.proposed is None or not track.proposed.youtube_candidates:
            self._show_info("No YouTube candidates are available for the selected row.")
            return

        labels = [
            self._youtube_choice_label(index, candidate)
            for index, candidate in enumerate(track.proposed.youtube_candidates, start=1)
        ]
        choice, accepted = QInputDialog.getItem(self, "Select YouTube Candidate", "Use this candidate:", labels, 0, False)
        if not accepted or not choice:
            return

        candidate = track.proposed.youtube_candidates[labels.index(choice)]
        proposed = replace(
            track.proposed,
            artist=candidate.inferred_artist or track.proposed.artist,
            title=candidate.inferred_song_title or track.proposed.title,
            duration=candidate.duration_seconds or track.proposed.duration,
            filename=(
                generate_mp3_filename(candidate.inferred_artist, candidate.inferred_song_title)
                if candidate.inferred_artist and candidate.inferred_song_title
                else track.proposed.filename
            ),
            youtube_candidate=candidate,
            confidence_breakdown=(*track.proposed.confidence_breakdown, "YouTube candidate manually selected by user."),
        )
        self.tracks[row] = replace(track, proposed=proposed, youtube_status="Matched", requires_review=False, processing_status="Ready")
        self._refresh_table()
        self.table.selectRow(row)
        self._refresh_detail_panel()
        self._set_status(f"Selected YouTube candidate for {track.path.name}.")

    @Slot()
    def toggle_log(self) -> None:
        visible = not self.message_box.isVisible()
        self.message_box.setVisible(visible)
        self.show_log_button.setText("Hide Log" if visible else "Show Log")

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.tracks))
        for row, track in enumerate(self.tracks):
            proposed = track.proposed
            values = [
                track.path.name,
                _dash(proposed.artist if proposed else track.current_metadata.artist),
                _dash(proposed.title if proposed else track.current_metadata.title),
                self._confidence_text(track),
                _lyrics_text(track),
                _recognition_text(track),
                _status_text(track),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(self._confidence_tooltip(track))
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def _refresh_detail_panel(self) -> None:
        rows = self._selected_rows()
        track = self.tracks[rows[0]] if rows else None
        if track is None:
            self._set_detail_empty()
            return

        current = track.current_metadata
        proposed = track.proposed
        self.current_filename.setText(track.path.name)
        self.current_artist.setText(_dash(current.artist))
        self.current_title.setText(_dash(current.title))
        self.current_album.setText(_dash(current.album))
        self.current_year.setText(_dash(current.release_date))
        self.proposed_filename.setText(_dash(proposed.filename if proposed else None))
        self.proposed_artist.setText(_dash(proposed.artist if proposed else None))
        self.proposed_title.setText(_dash(proposed.title if proposed else None))
        self.proposed_album.setText(_dash(proposed.album if proposed else None))
        self.proposed_year.setText(_dash(proposed.release_date if proposed else None))
        self.recognition_source.setText(_recognition_summary(track))
        self.confidence_summary.setText(self._confidence_text(track))
        self.youtube_summary.setText(_youtube_text(track))
        self.lyrics_summary.setText(_lyrics_text(track))
        youtube = proposed.youtube_candidate if proposed is not None else None
        self.open_youtube_button.setEnabled(youtube is not None)
        self.select_youtube_button.setEnabled(bool(proposed and proposed.youtube_candidates))
        self.diagnostics_button.setEnabled(bool(track.diagnostic_status or (proposed and proposed.confidence_breakdown)))

    def _set_detail_empty(self) -> None:
        for label in (
            self.current_filename,
            self.current_artist,
            self.current_title,
            self.current_album,
            self.current_year,
            self.proposed_filename,
            self.proposed_artist,
            self.proposed_title,
            self.proposed_album,
            self.proposed_year,
            self.recognition_source,
            self.confidence_summary,
            self.youtube_summary,
            self.lyrics_summary,
        ):
            label.setText("-")
        self.open_youtube_button.setEnabled(False)
        self.select_youtube_button.setEnabled(False)
        self.diagnostics_button.setEnabled(False)

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectionModel().selectedRows()})

    def _selected_track(self) -> WorkflowTrack | None:
        rows = self._selected_rows()
        return self.tracks[rows[0]] if rows else None

    def _confidence_text(self, track: WorkflowTrack) -> str:
        return f"{track.confidence_score}%" if track.proposed is not None else "-"

    def _confidence_tooltip(self, track: WorkflowTrack) -> str:
        if track.confidence_score >= 90 and not track.requires_review:
            return "High confidence; eligible for automatic apply."
        if track.confidence_score >= 70:
            return "Review recommended."
        return "Low confidence; automatic apply disabled."

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
        self._log(message)

    def _log(self, message: str) -> None:
        current = self.message_box.toPlainText()
        if current and current.splitlines()[-1] == message:
            return
        self.message_box.appendPlainText(message)

    def _reload_workflow_service(self) -> None:
        if self.workflow_service_factory is not None:
            self.workflow_service = self.workflow_service_factory()

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "Music Metadata Cleaner", message)

    def _youtube_choice_label(self, index: int, candidate) -> str:
        return f"{index}. {candidate.title} | {candidate.channel_name or '-'} | {_format_duration(candidate.duration_seconds)} | {candidate.score}%"

    def _clear_applied_high_confidence_paths(self) -> None:
        self.applied_high_confidence_paths.clear()
        self.remove_high_confidence_button.setEnabled(False)

    def _sync_applied_high_confidence_paths(self) -> None:
        current_paths = {track.path.resolve() for track in self.tracks}
        self.applied_high_confidence_paths.intersection_update(current_paths)
        self.remove_high_confidence_button.setEnabled(bool(self.applied_high_confidence_paths))

    def closeEvent(self, event) -> None:
        self.cancel_processing()
        super().closeEvent(event)


def _dash(value: object | None) -> str:
    return str(value) if value not in {None, ""} else "-"


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: 600;")
    return label


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    minutes, remaining = divmod(seconds, 60)
    return f"{minutes}:{remaining:02d}"


def _lyrics_text(track: WorkflowTrack) -> str:
    proposed = track.proposed
    lyrics = proposed.lyrics if proposed is not None else None
    if lyrics is not None and lyrics.has_synced_lyrics:
        return "Synced"
    if lyrics is not None and lyrics.has_plain_lyrics:
        return "Plain"
    if track.lyrics_status in {"Existing", "Found", "Review", "Missing"}:
        return track.lyrics_status
    return "Missing" if track.proposed is not None else "-"


def _recognition_text(track: WorkflowTrack) -> str:
    status = track.recognition_status
    if status.startswith("AudD fallback"):
        return "AudD"
    if status == "AcoustID + AudD":
        return "AcoustID + AudD"
    if status == "AcoustID":
        return "AcoustID"
    if "not configured" in status or "disabled" in status:
        return "-"
    if status.startswith("AudD:"):
        return "AudD"
    return status if status not in {"Not checked", ""} else "-"


def _recognition_summary(track: WorkflowTrack) -> str:
    source = _recognition_text(track)
    if source == "AudD" and track.proposed and track.proposed.musicbrainz_recording_id:
        return "AudD + MusicBrainz"
    if source == "AcoustID" and track.proposed and track.proposed.musicbrainz_recording_id:
        return "AcoustID + MusicBrainz"
    return source


def _youtube_text(track: WorkflowTrack) -> str:
    if track.youtube_status == "Matched":
        return "Verified"
    if track.youtube_status in {"Not checked", "Not configured"}:
        return "-"
    if track.youtube_status == "Candidates rejected":
        return "Review"
    return track.youtube_status


def _status_text(track: WorkflowTrack) -> str:
    if track.processing_status == "Invalid MP3" or track.metadata_status == "Failed":
        return "Failed"
    if track.processing_status == "Processing":
        return "Processing"
    if track.requires_review:
        return "Review"
    if track.processing_status == "Ready":
        return "Ready"
    if track.proposed is not None and track.confidence_score >= 90:
        return "Ready"
    return "Review" if track.proposed is not None else "Pending"


def run_desktop_app(
    workflow_service: MusicCleanerWorkflowService,
    *,
    workflow_service_factory: Callable[[], MusicCleanerWorkflowService] | None = None,
) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(workflow_service, workflow_service_factory=workflow_service_factory)
    window.show()
    return app.exec()
