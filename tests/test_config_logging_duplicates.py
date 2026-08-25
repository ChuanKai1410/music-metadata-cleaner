from __future__ import annotations

import logging

from music_metadata_cleaner.config import AppConfig, load_config, save_config
from music_metadata_cleaner.domain.confidence import confidence_label
from music_metadata_cleaner.domain.models import AudioFingerprint, TrackMetadata
from music_metadata_cleaner.files.backup import create_backup, restore_backup
from music_metadata_cleaner.files.duplicates import FileSignature, detect_duplicates, sha256_file
from music_metadata_cleaner.logging_config import configure_logging


def test_config_round_trip(tmp_path):
    path = tmp_path / "config" / "preferences.json"
    config = AppConfig(acoustid_api_key="secret", auto_apply_confidence_threshold=97)

    save_config(path, config)

    loaded = load_config(path)
    assert loaded.acoustid_api_key == "secret"
    assert loaded.auto_apply_confidence_threshold == 97


def test_logging_creates_application_log(tmp_path):
    log_path = tmp_path / "logs" / "application.log"
    logger = configure_logging(log_path)

    logger.info("scan started")
    for handler in logger.handlers:
        handler.flush()

    assert "scan started" in log_path.read_text(encoding="utf-8")
    assert logger.level == logging.INFO


def test_backup_create_and_restore(tmp_path):
    source = tmp_path / "song.mp3"
    source.write_bytes(b"original")

    backup = create_backup(source, backup_folder=tmp_path / "MusicCleaner_Backup")
    source.write_bytes(b"changed")
    restore_backup(backup, source)

    assert backup.name == "song.mp3.backup"
    assert source.read_bytes() == b"original"


def test_duplicate_detection_exact_hash_and_fingerprint():
    first = FileSignature(
        path=__import__("pathlib").Path("a.mp3"),
        file_hash="same",
        duration=120,
        fingerprint="fp",
        metadata=TrackMetadata(artist="Artist", title="Title"),
    )
    second = FileSignature(
        path=__import__("pathlib").Path("b.mp3"),
        file_hash="same",
        duration=120,
        fingerprint="fp",
        metadata=TrackMetadata(artist="Artist", title="Title"),
    )
    third = FileSignature(
        path=__import__("pathlib").Path("c.mp3"),
        file_hash="different",
        duration=121,
        fingerprint="fp",
        metadata=TrackMetadata(artist="Artist", title="Title"),
    )

    findings = detect_duplicates([first, second, third])

    assert any(finding.kind == "exact" for finding in findings)
    assert any(finding.kind == "same-song" for finding in findings)


def test_sha256_file_and_confidence_label(tmp_path):
    path = tmp_path / "song.mp3"
    path.write_bytes(b"abc")

    assert sha256_file(path) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert confidence_label(95) == "high"
    assert confidence_label(80) == "review"
    assert confidence_label(20) == "low"
