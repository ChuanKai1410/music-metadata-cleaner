"""Backup and recovery helpers for MP3 modification."""

from __future__ import annotations

from pathlib import Path
import shutil


def create_backup(path: str | Path, *, backup_folder: str | Path | None = None) -> Path:
    source = Path(path)
    if backup_folder is None:
        backup_path = source.with_name(f"{source.name}.backup")
    else:
        folder = Path(backup_folder)
        folder.mkdir(parents=True, exist_ok=True)
        backup_path = folder / f"{source.name}.backup"

    if backup_path.exists():
        raise FileExistsError(f"Backup already exists: {backup_path.name}")

    shutil.copy2(source, backup_path)
    return backup_path


def restore_backup(backup_path: str | Path, target_path: str | Path) -> None:
    shutil.copy2(Path(backup_path), Path(target_path))

