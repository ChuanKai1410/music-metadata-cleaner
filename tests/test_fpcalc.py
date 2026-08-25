from __future__ import annotations

import subprocess

import pytest

from music_metadata_cleaner.fingerprinting.errors import (
    FingerprintGenerationError,
    FingerprintTimeoutError,
    FpcalcNotFoundError,
)
from music_metadata_cleaner.fingerprinting.fpcalc import FpcalcFingerprinter, parse_fpcalc_json


def test_parse_fpcalc_json_returns_duration_and_fingerprint():
    fingerprint = parse_fpcalc_json('{"duration": 213.7, "fingerprint": "abc123"}')

    assert fingerprint.duration == 214
    assert fingerprint.fingerprint == "abc123"


def test_parse_fpcalc_json_rejects_missing_fingerprint():
    with pytest.raises(FingerprintGenerationError):
        parse_fpcalc_json('{"duration": 213}')


def test_fpcalc_fingerprinter_runs_fpcalc_with_json_output(monkeypatch, tmp_path):
    mp3_path = tmp_path / "song.mp3"
    mp3_path.write_bytes(b"")
    calls = {}

    def fake_which(executable):
        return f"C:/tools/{executable}.exe"

    def fake_run(command, **kwargs):
        calls["command"] = command
        calls["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0, stdout='{"duration": 120, "fingerprint": "fp"}', stderr="")

    monkeypatch.setattr("music_metadata_cleaner.fingerprinting.fpcalc.shutil.which", fake_which)
    monkeypatch.setattr("music_metadata_cleaner.fingerprinting.fpcalc.subprocess.run", fake_run)

    result = FpcalcFingerprinter(timeout_seconds=5).fingerprint(mp3_path)

    assert calls["command"] == ["C:/tools/fpcalc.exe", "-json", str(mp3_path)]
    assert calls["kwargs"]["timeout"] == 5
    assert result.duration == 120
    assert result.fingerprint == "fp"


def test_fpcalc_fingerprinter_reports_missing_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr("music_metadata_cleaner.fingerprinting.fpcalc.shutil.which", lambda executable: None)

    with pytest.raises(FpcalcNotFoundError):
        FpcalcFingerprinter().fingerprint(tmp_path / "song.mp3")


def test_fpcalc_fingerprinter_reports_timeout(monkeypatch, tmp_path):
    mp3_path = tmp_path / "song.mp3"
    mp3_path.write_bytes(b"")
    monkeypatch.setattr("music_metadata_cleaner.fingerprinting.fpcalc.shutil.which", lambda executable: executable)

    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=kwargs["timeout"])

    monkeypatch.setattr("music_metadata_cleaner.fingerprinting.fpcalc.subprocess.run", fake_run)

    with pytest.raises(FingerprintTimeoutError):
        FpcalcFingerprinter(timeout_seconds=1).fingerprint(mp3_path)


def test_fpcalc_fingerprinter_reports_nonzero_exit(monkeypatch, tmp_path):
    mp3_path = tmp_path / "song.mp3"
    mp3_path.write_bytes(b"")
    monkeypatch.setattr("music_metadata_cleaner.fingerprinting.fpcalc.shutil.which", lambda executable: executable)
    monkeypatch.setattr(
        "music_metadata_cleaner.fingerprinting.fpcalc.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 2, stdout="", stderr="bad file"),
    )

    with pytest.raises(FingerprintGenerationError):
        FpcalcFingerprinter().fingerprint(mp3_path)

