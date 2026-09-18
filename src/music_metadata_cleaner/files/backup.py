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

    # Exclusive creation also protects against another process creating a backup
    # between a preflight existence check and copying.
    with backup_path.open("xb") as destination:
        try:
            with source.open("rb") as original:
                shutil.copyfileobj(original, destination)
        except Exception:
            destination.close()
            backup_path.unlink()
            raise
    shutil.copystat(source, backup_path)
    return backup_path


def restore_backup(backup_path: str | Path, target_path: str | Path) -> None:
    shutil.copy2(Path(backup_path), Path(target_path))
