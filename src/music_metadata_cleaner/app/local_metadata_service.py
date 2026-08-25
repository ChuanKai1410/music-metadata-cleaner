"""Read-only local metadata workflow helpers."""

from __future__ import annotations

from pathlib import Path

from music_metadata_cleaner.domain.models import DryRunResult
from music_metadata_cleaner.files.safe_paths import propose_mp3_path
from music_metadata_cleaner.files.scanner import discover_mp3_files
from music_metadata_cleaner.id3.reader import read_id3_metadata


def dry_run_local_metadata(path: str | Path) -> list[DryRunResult]:
    """Discover MP3 files, read ID3 tags, and propose filenames without writing."""

    results: list[DryRunResult] = []
    for mp3_path in discover_mp3_files(path):
        metadata = read_id3_metadata(mp3_path)
        proposed_path = propose_mp3_path(mp3_path, metadata.artist, metadata.title)
        warnings: list[str] = []

        if proposed_path is None:
            warnings.append("Missing artist or title; filename cannot be proposed.")
        elif proposed_path.exists() and proposed_path.resolve() != mp3_path.resolve():
            warnings.append("Proposed filename already exists; no rename should be applied automatically.")

        results.append(
            DryRunResult(
                path=mp3_path,
                metadata=metadata,
                proposed_filename=proposed_path.name if proposed_path is not None else None,
                proposed_path=proposed_path,
                warnings=tuple(warnings),
            )
        )

    return results

