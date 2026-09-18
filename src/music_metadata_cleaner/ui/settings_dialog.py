"""Preferences for text search, plain lyrics and local file safety."""

from music_metadata_cleaner.ui.theme import style_dialog, SPACE, MARGIN

from dataclasses import replace
import os
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from music_metadata_cleaner.config import AppConfig, save_config
from music_metadata_cleaner.app.search_service import test_search_connection


class ConnectionTestWorker(QThread):
    result = Signal(str)

    def __init__(self, url, timeout, parent=None):
        super().__init__(parent)
        self.url = url
        self.timeout = timeout

    def run(self):
        try:
            status = test_search_connection(self.url, self.timeout)
        except Exception:
            status = "INVALID_RESPONSE"
        self.result.emit(status)


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        config_path: str | Path,
        workflow_service=None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.config_path = Path(config_path)
        self.workflow_service = workflow_service
        self.test_worker = None
        self.setWindowTitle("Settings")
        self.resize(680, 480)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        general = self._tab("General")
        self.default_music_folder_edit = QLineEdit(config.default_music_folder)
        folder = QWidget()
        row = QHBoxLayout(folder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACE)
        row.addWidget(self.default_music_folder_edit)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_folder)
        row.addWidget(browse)
        general.addRow("Default music folder", folder)
        self.filename_format_edit = QLineEdit("{artist} - {title}.mp3")
        self.filename_format_edit.setReadOnly(True)
        general.addRow("Filename format", self.filename_format_edit)
        general.addRow(
            "Language preference",
            QLabel("Preserve original-language evidence (no translation)"),
        )
        search = self._tab("Search")
        search.addRow("Provider", QLabel("SearXNG"))
        self.searxng_url_edit = QLineEdit(config.searxng_url)
        self.searxng_url_edit.setPlaceholderText("http://localhost:8080")
        search.addRow("SearXNG URL", self.searxng_url_edit)
        if os.environ.get("SEARXNG_URL", "").strip():
            search.addRow(
                QLabel("SEARXNG_URL environment variable overrides the saved URL.")
            )
        self.maximum_results_spin = QSpinBox()
        self.maximum_results_spin.setRange(1, 20)
        self.maximum_results_spin.setValue(config.maximum_search_results)
        search.addRow("Maximum results", self.maximum_results_spin)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 60)
        self.timeout_spin.setSuffix(" seconds")
        self.timeout_spin.setValue(config.search_timeout_seconds)
        search.addRow("Search timeout", self.timeout_spin)
        self.automatic_search_checkbox = self._check(
            search, "Automatic search", config.automatic_search
        )
        self.test_connection_button = QPushButton("Test Connection")
        self.test_connection_button.clicked.connect(self._test_connection)
        self.connection_status = QLabel("Not tested")
        self.connection_status.setWordWrap(True)
        search.addRow(self.test_connection_button, self.connection_status)
        lyrics = self._tab("Lyrics")
        self.retrieve_lyrics_checkbox = self._check(
            lyrics, "Retrieve plain lyrics", config.default_add_lyrics
        )
        self.preserve_lyrics_checkbox = self._check(
            lyrics, "Preserve existing lyrics", config.preserve_existing_lyrics
        )
        self.overwrite_lyrics_checkbox = self._check(
            lyrics,
            "Overwrite existing lyrics",
            config.overwrite_existing_lyrics and not config.preserve_existing_lyrics,
        )
        self.preserve_lyrics_checkbox.toggled.connect(self._preserve_changed)
        self._preserve_changed(self.preserve_lyrics_checkbox.isChecked())
        safety = self._tab("Files && Safety")
        self.rename_checkbox = self._check(
            safety, "Rename files", config.default_rename_file
        )
        self.update_id3_checkbox = self._check(
            safety, "Update ID3", config.default_update_id3_metadata
        )
        self.backup_checkbox = self._check(
            safety,
            "Backup before modification",
            config.enable_backup_before_modification,
        )
        safety.addRow(
            QLabel(
                "Every apply requires confirmation. History is recorded before changes."
            )
        )
        advanced = self._tab("Advanced")
        self.cache_ttl_spin = QSpinBox()
        self.cache_ttl_spin.setRange(0, 365 * 86400)
        self.cache_ttl_spin.setSuffix(" seconds")
        self.cache_ttl_spin.setValue(config.search_cache_ttl_seconds)
        advanced.addRow("Search cache expiration", self.cache_ttl_spin)
        self.clear_cache_button = QPushButton("Clear search cache")
        self.clear_cache_button.clicked.connect(self._clear_cache)
        advanced.addRow(self.clear_cache_button)
        for name, value in (
            ("History database", config.database_path),
            ("Logs", config.log_path),
        ):
            label = QLabel(value)
            label.setWordWrap(True)
            advanced.addRow(name, label)
        advanced.addRow(
            QLabel("Diagnostics: select a track, then View Search Evidence.")
        )
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        style_dialog(self, root, self.buttons)

    def _tab(self, title):
        widget = QWidget()
        form = QFormLayout(widget)
        form.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        form.setSpacing(SPACE)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.tabs.addTab(widget, title)
        return form

    def _check(self, form, label, checked):
        checkbox = QCheckBox(label)
        checkbox.setChecked(checked)
        form.addRow(checkbox)
        return checkbox

    def _preserve_changed(self, checked):
        if checked:
            self.overwrite_lyrics_checkbox.setChecked(False)
        self.overwrite_lyrics_checkbox.setEnabled(not checked)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Default music folder", self.default_music_folder_edit.text()
        )
        if folder:
            self.default_music_folder_edit.setText(folder)

    def _test_connection(self):
        if self.test_worker is not None:
            return
        url = (
            os.environ.get("SEARXNG_URL", "").strip()
            or self.searxng_url_edit.text().strip()
        )
        self.test_worker = ConnectionTestWorker(url, self.timeout_spin.value(), self)
        self.test_worker.result.connect(self.connection_status.setText)
        self.test_worker.finished.connect(self._test_finished)
        self.test_connection_button.setEnabled(False)
        self.connection_status.setText("Testing...")
        self.test_worker.start()

    def _test_finished(self):
        self.test_worker.deleteLater()
        self.test_worker = None
        self.test_connection_button.setEnabled(True)

    def _clear_cache(self):
        if self.workflow_service is not None:
            self.workflow_service.clear_search_cache()
            self.clear_cache_button.setText("Search cache cleared")

    def save(self):
        self.config = replace(
            self.config,
            searxng_url=self.searxng_url_edit.text().strip(),
            maximum_search_results=self.maximum_results_spin.value(),
            search_timeout_seconds=self.timeout_spin.value(),
            automatic_search=self.automatic_search_checkbox.isChecked(),
            search_cache_ttl_seconds=self.cache_ttl_spin.value(),
            default_music_folder=self.default_music_folder_edit.text().strip(),
            filename_format="{artist} - {title}.mp3",
            artist_language="Original",
            default_add_lyrics=self.retrieve_lyrics_checkbox.isChecked(),
            preserve_existing_lyrics=self.preserve_lyrics_checkbox.isChecked(),
            overwrite_existing_lyrics=self.overwrite_lyrics_checkbox.isChecked(),
            default_rename_file=self.rename_checkbox.isChecked(),
            default_update_id3_metadata=self.update_id3_checkbox.isChecked(),
            enable_backup_before_modification=self.backup_checkbox.isChecked(),
        )
        save_config(self.config_path, self.config)
        self.accept()

    def done(self, result):
        if self.test_worker is not None and self.test_worker.isRunning():
            self.connection_status.setText(
                "Wait for the connection test to finish before closing."
            )
            return
        super().done(result)
