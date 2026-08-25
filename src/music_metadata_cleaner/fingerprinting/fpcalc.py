"""Chromaprint fpcalc integration."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from music_metadata_cleaner.domain.models import AudioFingerprint
from music_metadata_cleaner.fingerprinting.errors import (
    FingerprintGenerationError,
    FingerprintTimeoutError,
    FpcalcNotFoundError,
)


class FpcalcFingerprinter:
    """Generate Chromaprint fingerprints through the fpcalc executable."""

    def __init__(self, executable: str = "fpcalc", timeout_seconds: float = 30.0) -> None:
        self.executable = executable
        self.timeout_seconds = timeout_seconds

    def fingerprint(self, path: str | Path) -> AudioFingerprint:
        mp3_path = Path(path)
        executable = self._resolve_executable()

        try:
            result = subprocess.run(
                [executable, "-json", str(mp3_path)],
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise FingerprintTimeoutError(f"fpcalc timed out after {self.timeout_seconds} seconds.") from exc
        except OSError as exc:
            raise FingerprintGenerationError(f"fpcalc could not be executed: {exc}") from exc

        if result.returncode != 0:
            details = (result.stderr or result.stdout or "").strip()
            raise FingerprintGenerationError(f"fpcalc failed for {mp3_path}: {details}")

        return parse_fpcalc_json(result.stdout)

    def _resolve_executable(self) -> str:
        if Path(self.executable).is_file():
            return self.executable

        resolved = shutil.which(self.executable)
        if resolved is None:
            raise FpcalcNotFoundError(
                "fpcalc was not found. Install Chromaprint or configure the fpcalc executable path."
            )

        return resolved


def parse_fpcalc_json(output: str) -> AudioFingerprint:
    """Parse fpcalc JSON output into a domain fingerprint."""

    try:
        payload = json.loads(output)
    except json.JSONDecodeError as exc:
        raise FingerprintGenerationError("fpcalc returned invalid JSON output.") from exc

    fingerprint = str(payload.get("fingerprint") or "").strip()
    duration_value = payload.get("duration")

    if not fingerprint:
        raise FingerprintGenerationError("fpcalc output did not include a fingerprint.")

    try:
        duration = round(float(duration_value))
    except (TypeError, ValueError) as exc:
        raise FingerprintGenerationError("fpcalc output did not include a valid duration.") from exc

    if duration <= 0:
        raise FingerprintGenerationError("fpcalc output duration must be greater than zero.")

    return AudioFingerprint(duration=duration, fingerprint=fingerprint)

