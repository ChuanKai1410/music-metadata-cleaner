"""PySide6 desktop main window."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import webbrowser
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
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

from music_metadata_cleaner.app.workflow_service import (
    ApplySettings,
    ApplyResult,
    BatchProgress,
    CancellationToken,
    MusicCleanerWorkflowService,
    WorkflowTrack,
)
from music_metadata_cleaner.files.safe_paths import generate_mp3_filename


COLUMNS = [
    "Current Filename",
    "Detected Artist",
    "Detected Title",
    "Album",
    "Confidence Score",
    "Metadata Status",
    "Lyrics Status",
    "Cover Status",
    "Recognition",
    "YouTube Status",
    "Processing Status",
]


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
        root_layout.setStretch(0, 0)

        file_group = QGroupBox("File Management")
        file_layout = QHBoxLayout(file_group)
        self.add_files_button = QPushButton("Add MP3 Files")
        self.add_folder_button = QPushButton("Add Music Folder")
        self.remove_files_button = QPushButton("Remove Selected")
        self.clear_files_button = QPushButton("Clear List")
        self.scan_button = QPushButton("Scan")
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_files_button,
            self.clear_files_button,
            self.scan_button,
        ):
            file_layout.addWidget(button)
        file_layout.addStretch(1)
        root_layout.addWidget(file_group)

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
        self.detail_group = QGroupBox("Detail Preview")
        self.detail_layout = QFormLayout(self.detail_group)
        self.current_filename = QLabel("-")
        self.current_artist = QLabel("-")
        self.current_title = QLabel("-")
        self.current_album = QLabel("-")
        self.current_year = QLabel("-")
        self.current_lyrics = QLabel("-")
        self.proposed_artist = QLabel("-")
        self.proposed_title = QLabel("-")
        self.proposed_album = QLabel("-")
        self.proposed_filename = QLabel("-")
        self.proposed_lyrics = QLabel("-")
        self.proposed_cover = QLabel("-")
        self.recognition_source = QLabel("-")
        self.diagnostic_details = QLabel("-")
        self.youtube_candidate = QLabel("-")
        self.youtube_channel = QLabel("-")
        self.youtube_duration = QLabel("-")
        self.youtube_confidence = QLabel("-")
        for label in (
            self.current_filename,
            self.current_artist,
            self.current_title,
            self.current_album,
            self.current_year,
            self.current_lyrics,
            self.proposed_artist,
            self.proposed_title,
            self.proposed_album,
            self.proposed_filename,
            self.proposed_lyrics,
            self.proposed_cover,
            self.recognition_source,
            self.diagnostic_details,
            self.youtube_candidate,
            self.youtube_channel,
            self.youtube_duration,
            self.youtube_confidence,
        ):
            label.setWordWrap(True)
        self.detail_layout.addRow("Filename", self.current_filename)
        self.detail_layout.addRow("Current Artist", self.current_artist)
        self.detail_layout.addRow("Current Title", self.current_title)
        self.detail_layout.addRow("Current Album", self.current_album)
        self.detail_layout.addRow("Current Year", self.current_year)
        self.detail_layout.addRow("Existing Lyrics", self.current_lyrics)
        self.detail_layout.addRow("New Artist", self.proposed_artist)
        self.detail_layout.addRow("New Title", self.proposed_title)
        self.detail_layout.addRow("New Album", self.proposed_album)
        self.detail_layout.addRow("New Filename", self.proposed_filename)
        self.detail_layout.addRow("Lyrics Source", self.proposed_lyrics)
        self.detail_layout.addRow("Cover Source", self.proposed_cover)
        self.detail_layout.addRow("Recognition", self.recognition_source)
        self.detail_layout.addRow("Diagnostics", self.diagnostic_details)
        self.detail_layout.addRow("YouTube Candidate", self.youtube_candidate)
        self.detail_layout.addRow("YouTube Channel", self.youtube_channel)
        self.detail_layout.addRow("YouTube Duration", self.youtube_duration)
        self.detail_layout.addRow("YouTube Evidence", self.youtube_confidence)
        youtube_button_layout = QHBoxLayout()
        self.open_youtube_button = QPushButton("Open YouTube Result")
        self.select_youtube_button = QPushButton("Select YouTube Candidate")
        self.open_youtube_button.setEnabled(False)
        self.select_youtube_button.setEnabled(False)
        youtube_button_layout.addWidget(self.open_youtube_button)
        youtube_button_layout.addWidget(self.select_youtube_button)
        self.detail_layout.addRow(youtube_button_layout)
        side_layout.addWidget(self.detail_group)

        settings_group = QGroupBox("Apply Settings")
        settings_layout = QVBoxLayout(settings_group)
        self.update_id3_checkbox = QCheckBox("Update ID3 metadata")
        self.update_title_checkbox = QCheckBox("Update title")
        self.update_artist_checkbox = QCheckBox("Update artist")
        self.update_album_checkbox = QCheckBox("Update album")
        self.add_cover_checkbox = QCheckBox("Add cover artwork")
        self.add_lyrics_checkbox = QCheckBox("Add lyrics")
        self.export_lrc_checkbox = QCheckBox("Export .lrc")
        self.rename_file_checkbox = QCheckBox("Rename file")
        self.enable_backup_checkbox = QCheckBox("Enable backup before modification")
        for checkbox in (
            self.update_id3_checkbox,
            self.update_title_checkbox,
            self.update_artist_checkbox,
            self.update_album_checkbox,
            self.add_cover_checkbox,
            self.add_lyrics_checkbox,
            self.export_lrc_checkbox,
            self.rename_file_checkbox,
            self.enable_backup_checkbox,
        ):
            settings_layout.addWidget(checkbox)
        self.update_id3_checkbox.setChecked(True)
        self.update_title_checkbox.setChecked(True)
        self.update_artist_checkbox.setChecked(True)
        self.update_album_checkbox.setChecked(True)
        self.add_lyrics_checkbox.setChecked(True)
        self.enable_backup_checkbox.setChecked(True)
        self.test_recognition_button = QPushButton("Test Recognition Setup")
        settings_layout.addWidget(self.test_recognition_button)
        side_layout.addWidget(settings_group)

        runtime_group = QGroupBox("Runtime Recognition Configuration")
        runtime_layout = QVBoxLayout(runtime_group)
        self.runtime_config_text = QPlainTextEdit()
        self.runtime_config_text.setReadOnly(True)
        self.runtime_config_text.setMaximumHeight(120)
        runtime_layout.addWidget(self.runtime_config_text)
        side_layout.addWidget(runtime_group)

        self.message_box = QPlainTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setMaximumHeight(120)
        side_layout.addWidget(self.message_box)
        splitter.addWidget(side_panel)
        splitter.setSizes([760, 420])
        root_layout.addWidget(splitter, 1)

        footer = QWidget()
        footer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QLabel("Idle")
        self.progress_label.setMinimumWidth(120)
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.progress_label)
        footer_layout.addLayout(progress_layout)

        action_layout = QHBoxLayout()
        action_layout.addStretch(1)
        self.preview_button = QPushButton("Preview Changes")
        self.apply_selected_button = QPushButton("Apply Selected")
        self.apply_high_confidence_button = QPushButton("Apply All High Confidence")
        self.remove_high_confidence_button = QPushButton("Remove All High Confidence")
        self.history_button = QPushButton("View History")
        self.undo_button = QPushButton("Undo Last Batch")
        self.cancel_button = QPushButton("Cancel Processing")
        self.remove_high_confidence_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        for button in (
            self.preview_button,
            self.apply_selected_button,
            self.apply_high_confidence_button,
            self.remove_high_confidence_button,
            self.history_button,
            self.undo_button,
            self.cancel_button,
        ):
            action_layout.addWidget(button)
        footer_layout.addLayout(action_layout)
        root_layout.addWidget(footer, 0)

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
        self.history_button.clicked.connect(self.view_history)
        self.undo_button.clicked.connect(self.undo_last_batch)
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.test_recognition_button.clicked.connect(self.test_recognition_setup)
        self.table.itemSelectionChanged.connect(self._refresh_detail_panel)
        self._refresh_runtime_config()

    @Slot()
    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Add MP3 Files", "", "MP3 Files (*.mp3)")
        if paths:
            self._add_paths([Path(path) for path in paths])

    @Slot()
    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Add Music Folder")
        if path:
            self._add_paths([Path(path)])

    def _add_paths(self, paths: list[Path]) -> None:
        discovered = self.workflow_service.discover(paths)
        existing = {track.path.resolve() for track in self.tracks}
        self.tracks.extend(track for track in discovered if track.path.resolve() not in existing)
        self._log(f"Added {len(discovered)} MP3 file(s).")
        self._clear_applied_high_confidence_paths()
        self._refresh_table()

    @Slot()
    def remove_selected_files(self) -> None:
        rows = sorted(self._selected_rows(), reverse=True)
        for row in rows:
            self.tracks.pop(row)
        self._sync_applied_high_confidence_paths()
        self._refresh_table()

    @Slot()
    def clear_files(self) -> None:
        self.tracks.clear()
        self._clear_applied_high_confidence_paths()
        self._refresh_table()
        self._refresh_detail_panel()

    @Slot()
    def scan_files(self) -> None:
        self.preview_changes()

    @Slot()
    def preview_changes(self) -> None:
        if not self.tracks:
            self._show_info("Add MP3 files or a music folder first.")
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
        self.processing_thread.start()

    @Slot()
    def cancel_processing(self) -> None:
        if self.cancellation_token is not None:
            self.cancellation_token.cancel()
            self.progress_label.setText("Cancelling")

    @Slot(object)
    def _handle_progress(self, progress: BatchProgress) -> None:
        value = round((progress.processed / progress.total) * 100) if progress.total else 0
        self.progress_bar.setValue(value)
        current = progress.current_path.name if progress.current_path is not None else "-"
        self.progress_label.setText(f"{progress.processed}/{progress.total} files - {current}")

    @Slot(object)
    def _handle_processing_finished(self, tracks: list[WorkflowTrack]) -> None:
        self.tracks = tracks
        self._clear_applied_high_confidence_paths()
        self.cancel_button.setEnabled(False)
        self.preview_button.setEnabled(True)
        self.scan_button.setEnabled(True)
        self.progress_bar.setValue(100 if tracks else 0)
        self.progress_label.setText("Complete")
        self._refresh_table()
        self._refresh_detail_panel()
        self._log("Preview processing complete.")

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
        successful_paths = {result.path.resolve() for result in results if result.success}
        self.applied_high_confidence_paths = successful_paths
        self.remove_high_confidence_button.setEnabled(bool(successful_paths))

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
        self._log(f"Removed {removed_count} applied high-confidence row(s) from the list.")

    def _apply_tracks(self, tracks: list[WorkflowTrack]) -> list[ApplyResult]:
        reply = QMessageBox.question(
            self,
            "Apply Changes",
            f"Apply selected changes to {len(tracks)} file(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return []

        results = self.workflow_service.apply_tracks(tracks, self._apply_settings())
        success_count = sum(1 for result in results if result.success)
        failure_count = len(results) - success_count
        self._log(f"Apply complete: {success_count} succeeded, {failure_count} failed.")
        for result in results:
            if not result.success:
                self._log(f"{result.path.name}: {result.message}")
        return results

    def _apply_settings(self) -> ApplySettings:
        return ApplySettings(
            update_id3_metadata=self.update_id3_checkbox.isChecked(),
            update_title=self.update_title_checkbox.isChecked(),
            update_artist=self.update_artist_checkbox.isChecked(),
            update_album=self.update_album_checkbox.isChecked(),
            add_cover_art=self.add_cover_checkbox.isChecked(),
            add_lyrics=self.add_lyrics_checkbox.isChecked(),
            export_lrc=self.export_lrc_checkbox.isChecked(),
            rename_file=self.rename_file_checkbox.isChecked(),
            enable_backup=self.enable_backup_checkbox.isChecked(),
        )

    @Slot()
    def test_recognition_setup(self) -> None:
        self._reload_workflow_service()
        self._refresh_runtime_config()
        checks = self.workflow_service.test_recognition_setup()
        lines = ["Recognition setup test:"]
        for check in checks:
            detail = f" - {check.detail}" if check.detail else ""
            lines.append(f"{check.name}: {check.status}{detail}")
        self._log("\n".join(lines))
        self._refresh_runtime_config()

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
        self._log(f"Undo complete: {success_count} restored, {failure_count} failed.")

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
        choice, accepted = QInputDialog.getItem(
            self,
            "Select YouTube Candidate",
            "Use this candidate:",
            labels,
            0,
            False,
        )
        if not accepted or not choice:
            return

        selected_index = labels.index(choice)
        candidate = track.proposed.youtube_candidates[selected_index]
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
            confidence_breakdown=(
                *track.proposed.confidence_breakdown,
                "YouTube candidate manually selected by user.",
            ),
        )
        self.tracks[row] = replace(
            track,
            proposed=proposed,
            youtube_status="Matched",
            requires_review=False,
            processing_status="Ready",
        )
        self._refresh_table()
        self.table.selectRow(row)
        self._refresh_detail_panel()
        self._log(f"Selected YouTube candidate for {track.path.name}.")

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.tracks))
        for row, track in enumerate(self.tracks):
            proposed = track.proposed
            values = [
                track.path.name,
                _dash(proposed.artist if proposed else track.current_metadata.artist),
                _dash(proposed.title if proposed else track.current_metadata.title),
                _dash(proposed.album if proposed else track.current_metadata.album),
                self._confidence_text(track),
                track.metadata_status,
                track.lyrics_status,
                track.cover_status,
                track.recognition_status,
                track.youtube_status,
                track.processing_status,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 4:
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
        lyrics = proposed.lyrics if proposed is not None else None
        youtube = proposed.youtube_candidate if proposed is not None else None
        self.current_filename.setText(track.path.name)
        self.current_artist.setText(_dash(current.artist))
        self.current_title.setText(_dash(current.title))
        self.current_album.setText(_dash(current.album))
        self.current_year.setText(_dash(current.release_date))
        self.current_lyrics.setText("Existing" if current.lyrics and current.lyrics.has_text else "Missing")
        self.proposed_artist.setText(_dash(proposed.artist if proposed else None))
        self.proposed_title.setText(_dash(proposed.title if proposed else None))
        self.proposed_album.setText(_dash(proposed.album if proposed else None))
        self.proposed_filename.setText(_dash(proposed.filename if proposed else None))
        self.proposed_lyrics.setText(_dash(lyrics.source if lyrics else None))
        self.proposed_cover.setText(_dash(proposed.cover_source if proposed else None))
        self.recognition_source.setText(_dash(track.recognition_status))
        self.diagnostic_details.setText(_dash(track.diagnostic_status))
        self.youtube_candidate.setText(_dash(youtube.title if youtube else None))
        self.youtube_channel.setText(_dash(youtube.channel_name if youtube else None))
        self.youtube_duration.setText(_format_duration(youtube.duration_seconds) if youtube else "-")
        self.youtube_confidence.setText(_dash(_youtube_strength(youtube.score) if youtube else None))
        self.open_youtube_button.setEnabled(youtube is not None)
        self.select_youtube_button.setEnabled(bool(proposed and proposed.youtube_candidates))

    def _set_detail_empty(self) -> None:
        for label in (
            self.current_filename,
            self.current_artist,
            self.current_title,
            self.current_album,
            self.current_year,
            self.current_lyrics,
            self.proposed_artist,
            self.proposed_title,
            self.proposed_album,
            self.proposed_filename,
            self.proposed_lyrics,
            self.proposed_cover,
            self.recognition_source,
            self.diagnostic_details,
            self.youtube_candidate,
            self.youtube_channel,
            self.youtube_duration,
            self.youtube_confidence,
        ):
            label.setText("-")
        self.open_youtube_button.setEnabled(False)
        self.select_youtube_button.setEnabled(False)

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectionModel().selectedRows()})

    def _selected_track(self) -> WorkflowTrack | None:
        rows = self._selected_rows()
        return self.tracks[rows[0]] if rows else None

    def _confidence_text(self, track: WorkflowTrack) -> str:
        return f"{track.confidence_score}%"

    def _confidence_tooltip(self, track: WorkflowTrack) -> str:
        if track.confidence_score >= 90 and not track.requires_review:
            return "High confidence; eligible for automatic apply."
        if track.confidence_score >= 70:
            return "Medium confidence; review required."
        return "Low confidence; automatic apply disabled."

    def _log(self, message: str) -> None:
        self.message_box.appendPlainText(message)

    def _refresh_runtime_config(self) -> None:
        self.runtime_config_text.setPlainText("\n".join(self.workflow_service.runtime_recognition_configuration()))

    def _reload_workflow_service(self) -> None:
        if self.workflow_service_factory is None:
            return
        self.workflow_service = self.workflow_service_factory()
        self._refresh_runtime_config()

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "Music Metadata Cleaner", message)

    def _youtube_choice_label(self, index: int, candidate) -> str:
        return (
            f"{index}. {candidate.title} | {candidate.channel_name or '-'} | "
            f"{_format_duration(candidate.duration_seconds)} | {candidate.score}%"
        )

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


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "-"
    minutes, remaining = divmod(seconds, 60)
    return f"{minutes}:{remaining:02d}"


def _youtube_strength(score: int) -> str:
    if score >= 85:
        return "Strong"
    if score >= 70:
        return "Moderate"
    if score > 0:
        return "Weak"
    return "No match"


def run_desktop_app(
    workflow_service: MusicCleanerWorkflowService,
    *,
    workflow_service_factory: Callable[[], MusicCleanerWorkflowService] | None = None,
) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(workflow_service, workflow_service_factory=workflow_service_factory)
    window.show()
    return app.exec()
