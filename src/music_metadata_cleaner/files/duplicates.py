"""Duplicate detection helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Callable

from music_metadata_cleaner.domain.models import AudioFingerprint, TrackMetadata
from music_metadata_cleaner.id3.reader import read_id3_metadata


@dataclass(frozen=True)
class FileSignature:
    path: Path
    file_hash: str
    duration: int | None
    fingerprint: str | None
    metadata: TrackMetadata


@dataclass(frozen=True)
class DuplicateFinding:
    first: Path
    second: Path
    kind: str
    reason: str


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def build_file_signature(
    path: str | Path,
    *,
    metadata_reader: Callable[[str | Path], TrackMetadata] = read_id3_metadata,
    fingerprinter: Callable[[str | Path], AudioFingerprint] | None = None,
) -> FileSignature:
    mp3_path = Path(path)
    fingerprint_result = fingerprinter(mp3_path) if fingerprinter is not None else None
    return FileSignature(
        path=mp3_path,
        file_hash=sha256_file(mp3_path),
        duration=fingerprint_result.duration if fingerprint_result is not None else None,
        fingerprint=fingerprint_result.fingerprint if fingerprint_result is not None else None,
        metadata=metadata_reader(mp3_path),
    )


def detect_duplicates(signatures: list[FileSignature]) -> list[DuplicateFinding]:
    findings: list[DuplicateFinding] = []
    for index, first in enumerate(signatures):
        for second in signatures[index + 1 :]:
            if first.file_hash == second.file_hash:
                findings.append(DuplicateFinding(first.path, second.path, "exact", "Same file hash."))
            elif first.fingerprint and first.fingerprint == second.fingerprint:
                if first.duration is not None and second.duration is not None and abs(first.duration - second.duration) <= 2:
                    findings.append(
                        DuplicateFinding(first.path, second.path, "same-song", "Same fingerprint and similar duration.")
                    )
                else:
                    findings.append(
                        DuplicateFinding(first.path, second.path, "different-version", "Same fingerprint with duration gap.")
                    )
            elif _metadata_similarity(first.metadata, second.metadata) >= 0.8:
                findings.append(DuplicateFinding(first.path, second.path, "possible", "Similar artist/title metadata."))
    return findings


def _metadata_similarity(first: TrackMetadata, second: TrackMetadata) -> float:
    checks = [
        (_norm(first.artist), _norm(second.artist)),
        (_norm(first.title), _norm(second.title)),
        (_norm(first.album), _norm(second.album)),
    ]
    available = [(left, right) for left, right in checks if left and right]
    if not available:
        return 0.0
    matches = sum(1 for left, right in available if left == right)
    return matches / len(available)


def _norm(value: str | None) -> str | None:
    return " ".join(value.casefold().split()) if value else None

