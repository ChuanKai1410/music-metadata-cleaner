"""Settings dialog for runtime configuration."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from music_metadata_cleaner.audio_segments import check_ffmpeg_available
from music_metadata_cleaner.app.workflow_service import MusicCleanerWorkflowService
from music_metadata_cleaner.config import AppConfig, save_config


class SettingsDialog(QDialog):
    """Edit persisted app settings without exposing saved secrets."""

    def __init__(
        self,
        *,
        config: AppConfig,
        config_path: str | Path,
        workflow_service: MusicCleanerWorkflowService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.config_path = Path(config_path)
        self.workflow_service = workflow_service
        self.setWindowTitle("Settings")
        self.resize(720, 520)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._general_tab(), "General")
        self.tabs.addTab(self._recognition_tab(), "Recognition")
        self.tabs.addTab(self._online_services_tab(), "Online Services")
        self.tabs.addTab(self._files_safety_tab(), "Files && Safety")
        self.tabs.addTab(self._advanced_tab(), "Advanced")
        root.addWidget(self.tabs, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.save)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

    def _general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        self.language_combo = QComboBox()
        self.language_combo.addItems(["Original language", "English / Romanized if supported"])
        self.filename_format_input = QLineEdit()
        self.default_folder_input = QLineEdit()
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_default_folder)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.default_folder_input, 1)
        folder_row.addWidget(browse)
        layout.addRow("Preferred metadata language", self.language_combo)
        layout.addRow("Default naming format", self.filename_format_input)
        layout.addRow("Default music folder", folder_row)
        return tab

    def _recognition_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        self.enable_audd_checkbox = QCheckBox("Enable AudD fallback")
        self.multi_segment_checkbox = QCheckBox("Enable multi-segment recognition")
        self.max_segments_spin = QSpinBox()
        self.max_segments_spin.setRange(1, 5)
        self.fallback_threshold_spin = QSpinBox()
        self.fallback_threshold_spin.setRange(0, 100)
        layout.addRow("", self.enable_audd_checkbox)
        layout.addRow("", self.multi_segment_checkbox)
        layout.addRow("Maximum recognition segments", self.max_segments_spin)
        layout.addRow("Fallback confidence threshold", self.fallback_threshold_spin)
        return tab

    def _online_services_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        self.audd_token_input = QLineEdit()
        self.audd_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.audd_status = QLabel("-")
        self.audd_test_button = QPushButton("Test")
        self.audd_test_button.clicked.connect(self._test_recognition_setup)
        self.youtube_key_input = QLineEdit()
        self.youtube_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.youtube_status = QLabel("-")
        self.youtube_test_button = QPushButton("Test")
        self.youtube_test_button.clicked.connect(self._test_youtube_config)
        self.ffmpeg_input = QLineEdit()
        ffmpeg_browse = QPushButton("Browse")
        ffmpeg_browse.clicked.connect(self._browse_ffmpeg)
        ffmpeg_test = QPushButton("Test")
        ffmpeg_test.clicked.connect(self._test_ffmpeg)
        self.ffmpeg_status = QLabel("-")
        ffmpeg_row = QHBoxLayout()
        ffmpeg_row.addWidget(self.ffmpeg_input, 1)
        ffmpeg_row.addWidget(ffmpeg_browse)
        ffmpeg_row.addWidget(ffmpeg_test)
        audd_status_row = QHBoxLayout()
        audd_status_row.addWidget(self.audd_status, 1)
        audd_status_row.addWidget(self.audd_test_button)
        youtube_status_row = QHBoxLayout()
        youtube_status_row.addWidget(self.youtube_status, 1)
        youtube_status_row.addWidget(self.youtube_test_button)
        layout.addRow("AudD API token", self.audd_token_input)
        layout.addRow("AudD status", audd_status_row)
        layout.addRow("YouTube API key", self.youtube_key_input)
        layout.addRow("YouTube status", youtube_status_row)
        layout.addRow("FFmpeg executable", ffmpeg_row)
        layout.addRow("FFmpeg status", self.ffmpeg_status)
        return tab

    def _files_safety_tab(self) -> QWidget:
        tab = QWidget()
        layout = QFormLayout(tab)
        self.update_metadata_checkbox = QCheckBox("Update ID3 metadata")
        self.add_lyrics_checkbox = QCheckBox("Add lyrics when available")
        self.export_lrc_checkbox = QCheckBox("Export synchronized .lrc")
        self.rename_file_checkbox = QCheckBox("Rename files")
        self.backup_checkbox = QCheckBox("Enable backup before modification")
        self.backup_folder_input = QLineEdit()
        layout.addRow("", self.update_metadata_checkbox)
        layout.addRow("", self.add_lyrics_checkbox)
        layout.addRow("", self.export_lrc_checkbox)
        layout.addRow("", self.rename_file_checkbox)
        layout.addRow("", self.backup_checkbox)
        layout.addRow("Backup folder name", self.backup_folder_input)
        return tab

    def _advanced_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.diagnostics_text = QPlainTextEdit()
        self.diagnostics_text.setReadOnly(True)
        test_button = QPushButton("Test Recognition Setup")
        test_button.clicked.connect(self._test_recognition_setup)
        layout.addWidget(self.diagnostics_text, 1)
        layout.addWidget(test_button)
        return tab

    def _load_values(self) -> None:
        self.language_combo.setCurrentIndex(0 if self.config.artist_language == "Original" else 1)
        self.filename_format_input.setText(self.config.filename_format or "{artist} - {title}.mp3")
        self.default_folder_input.setText(self.config.default_music_folder)
        self.enable_audd_checkbox.setChecked(self.config.fallback_recognition_enabled or bool(self.config.audd_api_token))
        self.multi_segment_checkbox.setChecked(self.config.multi_segment_recognition_enabled)
        self.max_segments_spin.setValue(self.config.max_recognition_segments)
        self.fallback_threshold_spin.setValue(self.config.fallback_recognition_threshold)
        self.audd_token_input.setPlaceholderText("Saved token configured" if self.config.audd_api_token else "")
        self.audd_status.setText("Configured" if self.config.audd_api_token else "Not configured")
        self.youtube_key_input.setPlaceholderText("Saved key configured" if self.config.youtube_api_key else "")
        self.youtube_status.setText("Configured" if self.config.youtube_api_key else "Not configured")
        self.ffmpeg_input.setText(self.config.ffmpeg_path)
        self.update_metadata_checkbox.setChecked(self.config.default_update_id3_metadata)
        self.add_lyrics_checkbox.setChecked(self.config.default_add_lyrics)
        self.export_lrc_checkbox.setChecked(self.config.default_export_lrc)
        self.rename_file_checkbox.setChecked(self.config.default_rename_file)
        self.backup_checkbox.setChecked(self.config.enable_backup_before_modification)
        self.backup_folder_input.setText(self.config.backup_folder_name)
        self._refresh_diagnostics()
        self._test_ffmpeg()

    def save(self) -> None:
        audd_token = self.audd_token_input.text().strip() or self.config.audd_api_token
        youtube_key = self.youtube_key_input.text().strip() or self.config.youtube_api_key
        updated = replace(
            self.config,
            artist_language="Original" if self.language_combo.currentIndex() == 0 else "English / Romanized",
            filename_format=self.filename_format_input.text().strip() or "{artist} - {title}.mp3",
            default_music_folder=self.default_folder_input.text().strip(),
            audd_api_token=audd_token,
            youtube_api_key=youtube_key,
            ffmpeg_path=self.ffmpeg_input.text().strip() or "ffmpeg",
            fallback_recognition_enabled=self.enable_audd_checkbox.isChecked(),
            multi_segment_recognition_enabled=self.multi_segment_checkbox.isChecked(),
            max_recognition_segments=self.max_segments_spin.value(),
            fallback_recognition_threshold=self.fallback_threshold_spin.value(),
            default_update_id3_metadata=self.update_metadata_checkbox.isChecked(),
            default_add_lyrics=self.add_lyrics_checkbox.isChecked(),
            default_export_lrc=self.export_lrc_checkbox.isChecked(),
            default_rename_file=self.rename_file_checkbox.isChecked(),
            enable_backup_before_modification=self.backup_checkbox.isChecked(),
            backup_folder_name=self.backup_folder_input.text().strip() or "MusicCleaner_Backup",
        )
        save_config(self.config_path, updated)
        self.config = updated
        self.accept()

    def _browse_default_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Default Music Folder", self.default_folder_input.text())
        if folder:
            self.default_folder_input.setText(folder)

    def _browse_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select ffmpeg.exe", "", "Executable (*.exe);;All Files (*)")
        if path:
            self.ffmpeg_input.setText(path)
            self._test_ffmpeg()

    def _test_ffmpeg(self) -> None:
        available, resolved, status = check_ffmpeg_available(self.ffmpeg_input.text().strip() or "ffmpeg")
        self.ffmpeg_status.setText(f"Available - {resolved}" if available else status)

    def _test_recognition_setup(self) -> None:
        lines = ["Recognition setup test:"]
        for check in self.workflow_service.test_recognition_setup():
            detail = f" - {check.detail}" if check.detail else ""
            lines.append(f"{check.name}: {check.status}{detail}")
        self.diagnostics_text.setPlainText("\n".join(lines))

    def _test_youtube_config(self) -> None:
        self.youtube_status.setText("Configured" if (self.youtube_key_input.text().strip() or self.config.youtube_api_key) else "Not configured")

    def _refresh_diagnostics(self) -> None:
        self.diagnostics_text.setPlainText("\n".join(self.workflow_service.runtime_recognition_configuration()))
