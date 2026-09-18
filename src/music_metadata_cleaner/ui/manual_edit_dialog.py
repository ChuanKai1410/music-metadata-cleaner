"""Local editable identity/lyrics preview; no network or filesystem mutations."""

from music_metadata_cleaner.ui.theme import style_dialog, SPACE

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QPlainTextEdit,
    QCheckBox,
    QDialogButtonBox,
)
from music_metadata_cleaner.domain.manual_edit import manual_options
from music_metadata_cleaner.files.safe_paths import generate_mp3_filename


class ManualEditDialog(QDialog):
    def __init__(self, track, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Artist, Title and Plain Lyrics")
        self.resize(680, 560)
        self.track = track
        layout = QVBoxLayout(self)
        name = QLabel(track.path.name)
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setWordWrap(True)
        layout.addWidget(name)
        layout.addWidget(
            QLabel(
                "Suggestions are filename fragments, not verified identities. Select or type your own values."
            )
        )
        form = QFormLayout()
        form.setSpacing(SPACE)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        options = manual_options(
            track.path.name, track.current_metadata, track.candidates, track.proposed
        )
        self.artist_combo = QComboBox()
        self.artist_combo.setEditable(True)
        self.artist_combo.addItems(options.artists)
        self.title_combo = QComboBox()
        self.title_combo.setEditable(True)
        for combo in (self.artist_combo, self.title_combo):
            combo.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
            )
            combo.setMinimumContentsLength(16)
        self.title_combo.addItems(options.titles)
        self.artist_combo.setEditText(
            track.proposed.artist
            if track.proposed
            else track.current_metadata.artist or ""
        )
        self.title_combo.setEditText(
            track.proposed.title
            if track.proposed
            else track.current_metadata.title or ""
        )
        form.addRow("Artist", self.artist_combo)
        form.addRow("Title", self.title_combo)
        swap = QPushButton("Swap Artist / Title")
        swap.clicked.connect(self._swap)
        form.addRow(swap)
        self.filename_label = QLabel()
        self.filename_label.setTextFormat(Qt.TextFormat.PlainText)
        self.filename_label.setWordWrap(True)
        form.addRow("New filename", self.filename_label)
        self.artist_combo.currentTextChanged.connect(self._preview)
        self.title_combo.currentTextChanged.connect(self._preview)
        self.edit_lyrics = QCheckBox("Use manually entered plain lyrics")
        layout.addWidget(self.edit_lyrics)
        self.lyrics_edit = QPlainTextEdit()
        self.lyrics_edit.setPlaceholderText("Paste or type plain lyrics here")
        self.lyrics_edit.setPlainText(
            track.proposed.lyrics.plain_lyrics
            if track.proposed
            and track.proposed.lyrics
            and track.proposed.lyrics.plain_lyrics
            else (
                track.current_metadata.lyrics.text
                if track.current_metadata.lyrics
                and track.current_metadata.lyrics.has_text
                else ""
            )
        )
        self.lyrics_edit.setEnabled(False)
        self.edit_lyrics.toggled.connect(self.lyrics_edit.setEnabled)
        layout.addWidget(self.lyrics_edit)
        self.overwrite_lyrics = QCheckBox(
            "I confirm replacing existing lyrics for this file"
        )
        self.overwrite_lyrics.setVisible(
            bool(
                track.current_metadata.lyrics and track.current_metadata.lyrics.has_text
            )
        )
        layout.addWidget(self.overwrite_lyrics)
        self.error_label = QLabel()
        self.error_label.setProperty("role", "error")
        layout.addWidget(self.error_label)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText(
            "Save Preview"
        )
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        layout.addWidget(
            QLabel(
                "Save Preview does not modify the MP3. Apply Selected still requires confirmation."
            )
        )
        self._preview()
        style_dialog(self, layout, self.buttons)

    def _swap(self):
        artist, title = self.artist_combo.currentText(), self.title_combo.currentText()
        self.artist_combo.setEditText(title)
        self.title_combo.setEditText(artist)

    def _preview(self):
        artist, title = (
            self.artist_combo.currentText().strip(),
            self.title_combo.currentText().strip(),
        )
        self.filename_label.setText(
            generate_mp3_filename(artist, title)
            if artist and title
            else "Enter both Artist and Title"
        )

    def _save(self):
        if (
            not self.artist_combo.currentText().strip()
            or not self.title_combo.currentText().strip()
        ):
            self.error_label.setText("Artist and Title are required.")
            return
        if self.edit_lyrics.isChecked():
            if not self.lyrics_edit.toPlainText().strip():
                self.error_label.setText(
                    "Enter lyrics or leave manual lyrics unchecked."
                )
                return
            if (
                self.track.current_metadata.lyrics
                and self.track.current_metadata.lyrics.has_text
                and not self.overwrite_lyrics.isChecked()
            ):
                self.error_label.setText(
                    "Confirm replacement to change existing lyrics."
                )
                return
        self.accept()
