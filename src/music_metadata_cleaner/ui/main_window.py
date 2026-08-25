"""PySide6 desktop main window."""

from __future__ import annotations

from pathlib import Path

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
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from music_metadata_cleaner.app.workflow_service import (
    ApplySettings,
    BatchProgress,
    CancellationToken,
    MusicCleanerWorkflowService,
    WorkflowTrack,
)


COLUMNS = [
    "Current Filename",
    "Detected Artist",
    "Detected Title",
    "Album",
    "Confidence Score",
    "Metadata Status",
    "Lyrics Status",
    "Cover Status",
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

    def __init__(self, workflow_service: MusicCleanerWorkflowService) -> None:
        super().__init__()
        self.workflow_service = workflow_service
        self.tracks: list[WorkflowTrack] = []
        self.processing_thread: QThread | None = None
        self.processing_worker: ProcessingWorker | None = None
        self.cancellation_token: CancellationToken | None = None

        self.setWindowTitle("Music Metadata Cleaner")
        self.resize(1180, 760)
        self._build_ui()
        self._connect_signals()
        self._refresh_table()
        self._refresh_detail_panel()

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)

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
        side_layout.addWidget(settings_group)

        self.message_box = QPlainTextEdit()
        self.message_box.setReadOnly(True)
        self.message_box.setMaximumHeight(120)
        side_layout.addWidget(self.message_box)
        splitter.addWidget(side_panel)
        splitter.setSizes([760, 420])
        root_layout.addWidget(splitter, 1)

        progress_layout = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_label = QLabel("Idle")
        progress_layout.addWidget(self.progress_bar, 1)
        progress_layout.addWidget(self.progress_label)
        root_layout.addLayout(progress_layout)

        action_layout = QHBoxLayout()
        action_layout.addStretch(1)
        self.preview_button = QPushButton("Preview Changes")
        self.apply_selected_button = QPushButton("Apply Selected")
        self.apply_high_confidence_button = QPushButton("Apply All High Confidence")
        self.history_button = QPushButton("View History")
        self.undo_button = QPushButton("Undo Last Batch")
        self.cancel_button = QPushButton("Cancel Processing")
        self.cancel_button.setEnabled(False)
        for button in (
            self.preview_button,
            self.apply_selected_button,
            self.apply_high_confidence_button,
            self.history_button,
            self.undo_button,
            self.cancel_button,
        ):
            action_layout.addWidget(button)
        root_layout.addLayout(action_layout)

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
        self.history_button.clicked.connect(self.view_history)
        self.undo_button.clicked.connect(self.undo_last_batch)
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.table.itemSelectionChanged.connect(self._refresh_detail_panel)

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
        self._refresh_table()

    @Slot()
    def remove_selected_files(self) -> None:
        rows = sorted(self._selected_rows(), reverse=True)
        for row in rows:
            self.tracks.pop(row)
        self._refresh_table()

    @Slot()
    def clear_files(self) -> None:
        self.tracks.clear()
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
        self._apply_tracks(tracks)

    def _apply_tracks(self, tracks: list[WorkflowTrack]) -> None:
        reply = QMessageBox.question(
            self,
            "Apply Changes",
            f"Apply selected changes to {len(tracks)} file(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        results = self.workflow_service.apply_tracks(tracks, self._apply_settings())
        success_count = sum(1 for result in results if result.success)
        failure_count = len(results) - success_count
        self._log(f"Apply complete: {success_count} succeeded, {failure_count} failed.")
        for result in results:
            if not result.success:
                self._log(f"{result.path.name}: {result.message}")

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
        ):
            label.setText("-")

    def _selected_rows(self) -> list[int]:
        return sorted({index.row() for index in self.table.selectionModel().selectedRows()})

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

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "Music Metadata Cleaner", message)

    def closeEvent(self, event) -> None:
        self.cancel_processing()
        super().closeEvent(event)


def _dash(value: object | None) -> str:
    return str(value) if value not in {None, ""} else "-"


def run_desktop_app(workflow_service: MusicCleanerWorkflowService) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(workflow_service)
    window.show()
    return app.exec()
