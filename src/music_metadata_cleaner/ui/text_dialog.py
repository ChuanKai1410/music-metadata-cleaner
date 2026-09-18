"""Consistent, bounded read-only evidence/history presentation."""

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout

from music_metadata_cleaner.ui.theme import style_dialog


class TextDialog(QDialog):
    def __init__(self, title, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlainText(text)
        layout.addWidget(self.details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        style_dialog(self, layout, buttons)
