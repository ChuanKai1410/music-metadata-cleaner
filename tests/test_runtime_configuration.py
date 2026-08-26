from __future__ import annotations

from pathlib import Path

from music_metadata_cleaner.app import service_factory
from music_metadata_cleaner.app.workflow_service import MusicCleanerWorkflowService, RecognitionSetupCheck, WorkflowTrack
from music_metadata_cleaner.config import AppConfig, load_config, save_config
from music_metadata_cleaner.domain.models import AudioRecognitionResult, CandidateRecording, TrackMetadata
from music_metadata_cleaner.providers.errors import ProviderResponseError


def test_legacy_audd_setting_names_load_into_canonical_token(tmp_path):
    config_path = tmp_path / "preferences.json"
    config_path.write_text('{"audd_api_key": "legacy-token"}', encoding="utf-8")

    config = load_config(config_path)

    assert config.audd_api_token == "legacy-token"


def test_persisted_audd_token_reaches_runtime_provider(tmp_path, monkeypatch):
    config_path = tmp_path / "config" / "preferences.json"
    save_config(config_path, AppConfig(audd_api_token="persisted-token", ffmpeg_path="ffmpeg"))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(service_factory, "CONFIG_PATH", config_path)
    monkeypatch.delenv("AUDD_API_TOKEN", raising=False)
    monkeypatch.delenv("AUDD_API_KEY", raising=False)
    monkeypatch.delenv("MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED", raising=False)

    service = service_factory.create_default_workflow_service()

    assert service.audd_token_present is True
    assert service.audd_token_source == "Application settings"
    assert service.fallback_recognition_enabled is True
    assert service.fallback_recognition_service is not None
    assert service.fallback_recognition_service.recognizer.api_token == "persisted-token"


def test_runtime_rebuild_sees_changed_persisted_token(tmp_path, monkeypatch):
    config_path = tmp_path / "config" / "preferences.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(service_factory, "CONFIG_PATH", config_path)
    monkeypatch.delenv("AUDD_API_TOKEN", raising=False)
    monkeypatch.delenv("AUDD_API_KEY", raising=False)
    monkeypatch.delenv("MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED", raising=False)

    save_config(config_path, AppConfig(audd_api_token="first-token"))
    first = service_factory.create_default_workflow_service()
    save_config(config_path, AppConfig(audd_api_token="second-token"))
    second = service_factory.create_default_workflow_service()

    assert first.fallback_recognition_service.recognizer.api_token == "first-token"
    assert second.fallback_recognition_service.recognizer.api_token == "second-token"


class AuthFailRecognizer:
    def recognize_file(self, path, *, segment_index, start_seconds):
        raise ProviderResponseError("AudD API token is invalid or not permitted.")


class FakeFallbackService:
    def __init__(self):
        self.recognizer = AuthFailRecognizer()
        self.max_segments = 3


def test_audd_auth_failure_is_not_reported_as_not_configured(tmp_path, monkeypatch):
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"audio")
    service = MusicCleanerWorkflowService(
        fallback_recognition_service=FakeFallbackService(),
        fallback_recognition_enabled=True,
        audd_token_present=True,
        audd_token_source="Application settings",
    )
    monkeypatch.setattr(
        "music_metadata_cleaner.app.workflow_service.check_ffmpeg_available",
        lambda ffmpeg_path: (True, str(clip), "READY"),
    )
    service._test_temporary_audio_extraction = lambda ffmpeg_path: (
        RecognitionSetupCheck("Temporary audio extraction", "PASS", "mocked"),
        clip,
        None,
    )

    checks = service.test_recognition_setup()

    auth = next(check for check in checks if check.name == "AudD authentication")
    assert auth.status == "FAIL"
    assert auth.detail == "AUTH_FAILED"
    assert service._recognition_status(None, None) == "AudD: authentication failed"


def test_incomplete_acoustid_triggers_audd_fallback(tmp_path):
    class IncompleteIdentifier:
        def identify(self, path):
            return [CandidateRecording("acoustid-only", None, None, 255, 0.94, None)]

    class Fallback:
        def __init__(self):
            self.calls = []

        def recognize(self, path, *, duration_seconds=None):
            self.calls.append((path, duration_seconds))
            return AudioRecognitionResult(
                artist="Ado",
                title="唱",
                provider="AudD",
                matched_segments=2,
                total_segments=3,
                provider_confidence=0.92,
            )

    fallback = Fallback()
    mp3_path = tmp_path / "unknown.mp3"
    mp3_path.write_bytes(b"")
    service = MusicCleanerWorkflowService(
        identifier=IncompleteIdentifier(),
        fallback_recognition_service=fallback,
        fallback_recognition_enabled=True,
        audd_token_present=True,
        metadata_reader=lambda path: TrackMetadata(),
    )

    processed = service.process_track(WorkflowTrack(path=mp3_path, current_metadata=TrackMetadata()))

    assert fallback.calls
    assert processed.proposed.artist == "Ado"
    assert processed.proposed.title == "唱"
    assert processed.recognition_status == "AudD fallback (2/3)"
