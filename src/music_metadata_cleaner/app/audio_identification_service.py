"""Audio identification orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from music_metadata_cleaner.domain.models import AudioFingerprint, CandidateRecording
from music_metadata_cleaner.fingerprinting.fpcalc import FpcalcFingerprinter
from music_metadata_cleaner.providers.acoustid import AcoustIDClient


class Fingerprinter(Protocol):
    def fingerprint(self, path: str | Path) -> AudioFingerprint:
        """Generate a fingerprint for an audio file."""


class RecordingLookup(Protocol):
    def lookup(self, fingerprint: AudioFingerprint) -> list[CandidateRecording]:
        """Return normalized recording candidates for a fingerprint."""


class AudioIdentificationService:
    """Identify candidate recordings from a local MP3 without modifying it."""

    def __init__(self, fingerprinter: Fingerprinter, lookup_provider: RecordingLookup) -> None:
        self.fingerprinter = fingerprinter
        self.lookup_provider = lookup_provider

    @classmethod
    def for_acoustid(
        cls,
        api_key: str,
        *,
        fpcalc_executable: str = "fpcalc",
        fpcalc_timeout_seconds: float = 30.0,
        acoustid_timeout_seconds: float = 10.0,
    ) -> "AudioIdentificationService":
        return cls(
            fingerprinter=FpcalcFingerprinter(
                executable=fpcalc_executable,
                timeout_seconds=fpcalc_timeout_seconds,
            ),
            lookup_provider=AcoustIDClient(
                api_key=api_key,
                timeout_seconds=acoustid_timeout_seconds,
            ),
        )

    def identify(self, path: str | Path) -> list[CandidateRecording]:
        fingerprint = self.fingerprinter.fingerprint(path)
        return self.lookup_provider.lookup(fingerprint)
