"""Filename sanitization and dry-run rename planning."""

from __future__ import annotations

import re
import os
from pathlib import Path


WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

INVALID_FILENAME_CHARS = '<>:"/\\|?*'
CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f]")
WHITESPACE_RE = re.compile(r"\s+")


def sanitize_filename_component(value: str, replacement: str = " ") -> str:
    """Sanitize one filename component while preserving readable Unicode text."""

    cleaned = CONTROL_CHAR_RE.sub(replacement, value)
    cleaned = "".join(replacement if char in INVALID_FILENAME_CHARS else char for char in cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip(" .")

    if not cleaned:
        cleaned = "Unknown"

    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_"

    return cleaned


def generate_mp3_filename(artist: str, title: str) -> str:
    """Generate the canonical dry-run filename: Artist - Title.mp3."""

    safe_artist = sanitize_filename_component(artist)
    safe_title = sanitize_filename_component(title)
    return f"{safe_artist} - {safe_title}.mp3"


def propose_mp3_path(current_path: Path, artist: str | None, title: str | None) -> Path | None:
    """Return a proposed sibling path when artist and title are available."""

    if not artist or not artist.strip() or not title or not title.strip():
        return None

    return current_path.with_name(generate_mp3_filename(artist, title))


def rename_without_overwrite(source: Path, target: Path) -> None:
    """Rename within one folder without POSIX rename's overwrite race.

    Hard-link creation exclusively claims the target name. Removing the old name
    then leaves the same file at the new name. Unsupported filesystems fail safely.
    """
    if source.parent.resolve() != target.parent.resolve():
        raise ValueError("Rename must stay in the original folder.")
    if source.resolve() == target.resolve():
        return
    if source.is_symlink():
        raise ValueError("Symbolic links require manual file handling.")
    os.link(source, target)
    try:
        source.unlink()
    except Exception:
        target.unlink()
        raise
