"""Application-wide visual tokens and stylesheet loading; no domain styling."""

from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QLabel

SPACE = 8
MARGIN = 16
PALETTE = {
    "background": "#202326",
    "surface": "#292d31",
    "secondary": "#30353a",
    "hover": "#383e44",
    "border": "#444c53",
    "text": "#e0e3e6",
    "secondaryText": "#b6bec5",
    "muted": "#919aa3",
    "accent": "#a4c4d6",
    "accentSurface": "#354e5d",
    "selection": "#3b505d",
    "success": "#aac6b1",
    "warning": "#d3bf97",
    "danger": "#d6a6a6",
}


def apply_theme():
    app = QApplication.instance()
    if app is None or app.property("musicCleanerTheme"):
        return
    # Fusion gives standard Qt subcontrols a consistent cross-platform baseline.
    app.setStyle("Fusion")
    palette = QPalette()
    for role, token in (
        (QPalette.ColorRole.Window, "background"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "secondary"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "secondary"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Highlight, "selection"),
        (QPalette.ColorRole.HighlightedText, "text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.ToolTipBase, "secondary"),
        (QPalette.ColorRole.ToolTipText, "text"),
    ):
        palette.setColor(role, QColor(PALETTE[token]))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(PALETTE["muted"]))
    app.setPalette(palette)
    qss = (Path(__file__).parent / "styles" / "app.qss").read_text(encoding="utf-8")
    for token, value in PALETTE.items():
        qss = qss.replace("@" + token + "@", value)
    qss = qss.replace("@styles@", (Path(__file__).parent / "styles").as_posix())
    app.setStyleSheet(qss)
    app.setProperty("musicCleanerTheme", True)


def set_role(widget, role):
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def style_dialog(dialog, layout, buttons=None):
    apply_theme()
    layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
    layout.setSpacing(SPACE)
    for label in dialog.findChildren(QLabel):
        label.setWordWrap(True)
    if buttons is not None:
        for button in buttons.buttons():
            if buttons.buttonRole(button) == QDialogButtonBox.ButtonRole.AcceptRole:
                set_role(button, "primary")
                button.setDefault(True)
