"""Local MP3 discovery."""

from __future__ import annotations

from pathlib import Path


def discover_mp3_files(path: str | Path) -> list[Path]:
    """Return MP3 files for a file or folder without modifying anything."""

    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")

    if root.is_file():
        return [root] if root.suffix.lower() == ".mp3" else []

    if not root.is_dir():
        return []

    return sorted(
        (candidate for candidate in root.rglob("*") if candidate.is_file() and candidate.suffix.lower() == ".mp3"),
        key=lambda candidate: str(candidate).casefold(),
    )

