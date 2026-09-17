"""PySide6 desktop main window."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QInputDialog,
    QLineEdit,
    QDialog,
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
from music_metadata_cleaner.ui.settings_dialog import SettingsDialog


COLUMNS = ["File", "Artist", "Title", "Confidence", "Lyrics", "Status"]


class ProcessingWorker(QObject):
    progress = Signal(object)
    finished = Signal(object)

    def __init__(
        self,
        service: MusicCleanerWorkflowService,
        tracks: list[WorkflowTrack],
        token: CancellationToken,
        candidate_index: int | None = None,
    ) -> None:
        super().__init__()
        self.service = service
        self.tracks = tracks
        self.token = token
        self.candidate_index = candidate_index

    @Slot()
    def run(self) -> None:
        try:
            results = (
                [self.service.use_candidate(self.tracks[0], self.candidate_index)]
                if self.candidate_index is not None
                else self.service.process_tracks(
                    self.tracks,
                    cancellation_token=self.token,
                    progress_callback=self.progress.emit,
                )
            )
        except Exception:
            results = [
                replace(
                    track,
                    proposed=None,
                    processing_status="Search Failed",
                    error_message="Search could not complete.",
                )
                for track in self.tracks
            ]
        self.finished.emit(results)


class MainWindow(QMainWindow):
    """Main desktop workflow window."""

    def __init__(
        self,
        workflow_service: MusicCleanerWorkflowService,
        *,
        workflow_service_factory: (
            Callable[[], MusicCleanerWorkflowService] | None
        ) = None,
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
        splitter.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
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
            current.setTextFormat(Qt.TextFormat.PlainText)
            proposed.setTextFormat(Qt.TextFormat.PlainText)
            current.setWordWrap(True)
            proposed.setWordWrap(True)
        detail_layout.addLayout(compare_layout)

        summary_group = QGroupBox("Search Evidence")
        summary_layout = QGridLayout(summary_group)
        self.search_query = QLabel("-")
        self.search_query.setWordWrap(True)
        self.confidence_summary = QLabel("-")
        self.sources_summary = QLabel("-")
        self.lyrics_summary = QLabel("-")
        summary_layout.addWidget(QLabel("Query"), 0, 0)
        summary_layout.addWidget(self.search_query, 0, 1)
        summary_layout.addWidget(QLabel("Confidence"), 1, 0)
        summary_layout.addWidget(self.confidence_summary, 1, 1)
        summary_layout.addWidget(QLabel("Sources found"), 2, 0)
        summary_layout.addWidget(self.sources_summary, 2, 1)
        summary_layout.addWidget(QLabel("Lyrics"), 3, 0)
        summary_layout.addWidget(self.lyrics_summary, 3, 1)
        detail_layout.addWidget(summary_group)

        detail_buttons = QHBoxLayout()
        self.diagnostics_button = QPushButton("View Search Evidence")
        self.use_candidate_button = QPushButton("Use Candidate")
        detail_buttons.addWidget(self.diagnostics_button)
        detail_buttons.addWidget(self.use_candidate_button)
        detail_layout.addLayout(detail_buttons)
        detail_layout.addWidget(QLabel("Search keywords:"))
        self.search_keywords = QLineEdit()
        self.search_keywords.setPlaceholderText(
            "Artist, title, or other known song details"
        )
        self.manual_search_button = QPushButton("Search")
        detail_layout.addWidget(self.search_keywords)
        detail_layout.addWidget(self.manual_search_button)
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
        self.apply_high_confidence_button.clicked.connect(
            self.apply_all_high_confidence
        )
        self.remove_high_confidence_button.clicked.connect(
            self.remove_applied_high_confidence
        )
        self.manual_search_button.clicked.connect(self.manual_search)
        self.use_candidate_button.clicked.connect(self.use_candidate)
        self.diagnostics_button.clicked.connect(self.view_track_diagnostics)
        self.history_button.clicked.connect(self.view_history)
        self.undo_button.clicked.connect(self.undo_last_batch)
        self.cancel_button.clicked.connect(self.cancel_processing)
        self.settings_button.clicked.connect(self.open_settings)
        self.show_log_button.clicked.connect(self.toggle_log)
        self.table.itemSelectionChanged.connect(self._refresh_detail_panel)

    @Slot()
    def add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add MP3 Files",
            load_config(CONFIG_PATH).default_music_folder,
            "MP3 Files (*.mp3)",
        )
        if paths:
            self._add_paths([Path(path) for path in paths])

    @Slot()
    def add_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Add Folder", load_config(CONFIG_PATH).default_music_folder
        )
        if path:
            self._add_paths([Path(path)])

    def _add_paths(self, paths: list[Path]) -> None:
        discovered = self.workflow_service.discover(paths)
        existing = {track.path.resolve() for track in self.tracks}
        self.tracks.extend(
            track for track in discovered if track.path.resolve() not in existing
        )
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
        self._start_processing(self.tracks, list(range(len(self.tracks))))

    def _start_processing(self, tracks, rows, candidate_index=None):
        self._reload_workflow_service()
        self._processing_rows = rows
        self._set_busy(True)
        self.cancellation_token = CancellationToken()
        self.processing_thread = QThread()
        self.processing_worker = ProcessingWorker(
            self.workflow_service, tracks, self.cancellation_token, candidate_index
        )
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
        value = (
            round((progress.processed / progress.total) * 100) if progress.total else 0
        )
        self.progress_bar.setValue(value)
        current = (
            progress.current_path.name if progress.current_path is not None else "-"
        )
        self.progress_label.setText(f"Scanning {progress.processed} / {progress.total}")
        self.status_label.setText(f"Current: {current}")

    @Slot(object)
    def _handle_processing_finished(self, tracks: list[WorkflowTrack]) -> None:
        for row, track in zip(self._processing_rows, tracks):
            self.tracks[row] = track
        self._clear_applied_high_confidence_paths()
        self.cancel_button.setEnabled(False)
        self.preview_button.setEnabled(True)
        self.scan_button.setEnabled(True)
        self.progress_bar.setValue(100 if tracks else 0)
        self.progress_label.setText("Complete")
        ready = sum(1 for track in tracks if _status_text(track) == "Ready")
        review = sum(1 for track in tracks if _status_text(track) == "Review")
        failed = sum(
            1
            for track in tracks
            if _status_text(track) in {"Search Failed", "Invalid MP3"}
        )
        self._refresh_table()
        self._refresh_detail_panel()
        self._set_status(
            f"{len(tracks)} processed - {ready} ready, {review} review, {failed} failed."
        )

    @Slot()
    def _clear_processing_thread(self) -> None:
        self.processing_thread = None
        self.processing_worker = None
        self.cancellation_token = None
        self._set_busy(False)
        self._refresh_detail_panel()
        self.remove_high_confidence_button.setEnabled(
            bool(self.applied_high_confidence_paths)
        )

    def _set_busy(self, busy):
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_files_button,
            self.clear_files_button,
            self.apply_selected_button,
            self.apply_high_confidence_button,
            self.undo_button,
            self.settings_button,
            self.manual_search_button,
            self.use_candidate_button,
            self.remove_high_confidence_button,
        ):
            button.setEnabled(not busy)

    @Slot()
    def apply_selected(self) -> None:
        selected = [self.tracks[row] for row in self._selected_rows()]
        if not selected:
            self._show_info("Select one or more rows first.")
            return
        self._apply_tracks(selected)

    @Slot()
    def apply_all_high_confidence(self) -> None:
        tracks = [
            track
            for track in self.tracks
            if track.confidence_score >= 80 and not track.requires_review
        ]
        if not tracks:
            self._show_info("No high-confidence ready tracks are available.")
            return
        results = self._apply_tracks(tracks)
        self.applied_high_confidence_paths = (
            getattr(self, "_last_applied_paths", set()) if results else set()
        )
        self.remove_high_confidence_button.setEnabled(
            bool(self.applied_high_confidence_paths)
        )

    @Slot()
    def remove_applied_high_confidence(self) -> None:
        if not self.applied_high_confidence_paths:
            return
        before_count = len(self.tracks)
        self.tracks = [
            track
            for track in self.tracks
            if track.path.resolve() not in self.applied_high_confidence_paths
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

        results = self.workflow_service.apply_tracks(
            tracks, self.workflow_service.default_apply_settings
        )
        success_count = sum(1 for result in results if result.success)
        failure_count = len(results) - success_count
        self._set_status(
            f"Apply complete: {success_count} succeeded, {failure_count} failed."
        )
        self._last_applied_paths = set()
        for result in results:
            if not result.success:
                self._log(f"{result.path.name}: {result.message}")
                continue
            for index, track in enumerate(self.tracks):
                if track.path == result.path:
                    path = (
                        track.path.with_name(track.proposed.filename)
                        if self.workflow_service.default_apply_settings.rename_file
                        and track.proposed
                        else track.path
                    )
                    self._last_applied_paths.add(path.resolve())
                    refreshed = self.workflow_service.discover([path])
                    self.tracks[index] = (
                        replace(refreshed[0], processing_status="Applied")
                        if refreshed
                        else replace(
                            track, path=path, proposed=None, processing_status="Applied"
                        )
                    )
        self._refresh_table()
        self._refresh_detail_panel()
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
        paths = [track.path for track in self.tracks if track.path.exists()] + [
            result.path for result in results if result.success
        ]
        self.tracks = self.workflow_service.discover(paths)
        self._refresh_table()
        self._refresh_detail_panel()
        self._set_status(
            f"Undo complete: {success_count} restored, {failure_count} failed."
        )

    @Slot()
    def view_track_diagnostics(self) -> None:
        track = self._selected_track()
        if track is None:
            return
        lines = [
            f"Original filename: {track.path.name}",
            f"Cleaned filename: {track.cleaned_filename}",
            "Queries:",
            *track.search_queries,
            f"Resolver decision: {track.diagnostic_status}",
            f"Confidence: {track.confidence}",
        ]
        for candidate in track.candidates:
            lines.extend(
                [
                    "",
                    f"Candidate: {candidate.artist} - {candidate.title}",
                    f"Score: {candidate.internal_score} ({candidate.confidence})",
                    *candidate.evidence_breakdown,
                ]
            )
        for result in track.search_results:
            lines.extend(
                [
                    "",
                    f"Result {result.rank}: {result.domain} (engines: {result.engine})",
                    result.title,
                    result.url,
                    result.snippet,
                ]
            )
        dialog = QDialog(self)
        dialog.setWindowTitle("Search Evidence")
        dialog.resize(720, 500)
        layout = QVBoxLayout(dialog)
        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText("\n".join(lines))
        layout.addWidget(details)
        dialog.exec()

    @Slot()
    def manual_search(self) -> None:
        rows = self._selected_rows()
        if not rows or self.processing_thread is not None:
            return
        keywords = self.search_keywords.text().strip()
        if not keywords:
            self._show_info("Enter search keywords first.")
            return
        row = rows[0]
        self.tracks[row] = replace(self.tracks[row], manual_keywords=keywords)
        self._start_processing([self.tracks[row]], [row])

    @Slot()
    def use_candidate(self) -> None:
        track = self._selected_track()
        if track is None or not track.candidates or self.processing_thread is not None:
            return
        choices = [
            f"{i + 1}. {candidate.artist} - {candidate.title} ({candidate.confidence}; {len(candidate.evidence)} supporting results)"
            for i, candidate in enumerate(track.candidates)
        ]
        choice, accepted = QInputDialog.getItem(
            self,
            "Use Candidate",
            "Review sources, then select Artist + Title:",
            choices,
            0,
            False,
        )
        if accepted:
            row = self._selected_rows()[0]
            self._start_processing(
                [track], [row], candidate_index=choices.index(choice)
            )

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
                _dash(
                    proposed.artist
                    if proposed
                    else (
                        None
                        if track.processing_status == "Insufficient Information"
                        else track.current_metadata.artist
                    )
                ),
                _dash(
                    proposed.title
                    if proposed
                    else (
                        None
                        if track.processing_status == "Insufficient Information"
                        else track.current_metadata.title
                    )
                ),
                self._confidence_text(track),
                _lyrics_text(track),
                _status_text(track),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(self._confidence_tooltip(track))
                self.table.setItem(row, column, item)

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
        self.search_query.setText("; ".join(track.search_queries) or "-")
        self.confidence_summary.setText(self._confidence_text(track))
        self.sources_summary.setText(
            str(len(track.resolved_identity.evidence) if track.resolved_identity else 0)
        )
        self.lyrics_summary.setText(_lyrics_text(track))
        self.use_candidate_button.setEnabled(
            bool(track.candidates) and self.processing_thread is None
        )
        self.manual_search_button.setEnabled(self.processing_thread is None)
        self.diagnostics_button.setEnabled(
            bool(track.search_queries or track.diagnostic_status)
        )

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
            self.search_query,
            self.confidence_summary,
            self.sources_summary,
            self.lyrics_summary,
        ):
            label.setText("-")
        self.use_candidate_button.setEnabled(False)
        self.manual_search_button.setEnabled(False)
        self.diagnostics_button.setEnabled(False)

    def _selected_rows(self) -> list[int]:
        return sorted(
            {index.row() for index in self.table.selectionModel().selectedRows()}
        )

    def _selected_track(self) -> WorkflowTrack | None:
        rows = self._selected_rows()
        return self.tracks[rows[0]] if rows else None

    def _confidence_text(self, track: WorkflowTrack) -> str:
        return track.confidence

    def _confidence_tooltip(self, track: WorkflowTrack) -> str:
        if track.confidence_score >= 80 and not track.requires_review:
            return "High confidence; eligible for confirmed batch apply."
        if track.confidence_score >= 60:
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
            previous = self.workflow_service
            self.workflow_service = self.workflow_service_factory()
            previous.close()

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, "Music Metadata Cleaner", message)

    def _clear_applied_high_confidence_paths(self) -> None:
        self.applied_high_confidence_paths.clear()
        self.remove_high_confidence_button.setEnabled(False)

    def _sync_applied_high_confidence_paths(self) -> None:
        current_paths = {track.path.resolve() for track in self.tracks}
        self.applied_high_confidence_paths.intersection_update(current_paths)
        self.remove_high_confidence_button.setEnabled(
            bool(self.applied_high_confidence_paths)
        )

    def closeEvent(self, event) -> None:
        if self.processing_thread is not None:
            self.cancel_processing()
            self._set_status("Waiting for the current search to finish before closing.")
            event.ignore()
            return
        self.workflow_service.close()
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
    return track.lyrics_status


def _status_text(track: WorkflowTrack) -> str:
    return track.processing_status


def run_desktop_app(
    workflow_service: MusicCleanerWorkflowService,
    *,
    workflow_service_factory: Callable[[], MusicCleanerWorkflowService] | None = None,
) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        workflow_service, workflow_service_factory=workflow_service_factory
    )
    window.show()
    return app.exec()
