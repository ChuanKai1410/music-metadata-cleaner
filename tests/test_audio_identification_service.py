from __future__ import annotations

from music_metadata_cleaner.app.audio_identification_service import AudioIdentificationService
from music_metadata_cleaner.domain.models import AudioFingerprint, CandidateRecording


class FakeFingerprinter:
    def __init__(self) -> None:
        self.paths = []

    def fingerprint(self, path):
        self.paths.append(path)
        return AudioFingerprint(duration=123, fingerprint="fp")


class FakeLookupProvider:
    def __init__(self) -> None:
        self.fingerprints = []

    def lookup(self, fingerprint):
        self.fingerprints.append(fingerprint)
        return [
            CandidateRecording(
                recording_id="mbid",
                artist="Artist",
                title="Title",
                duration=123,
                acoustid_score=0.95,
                musicbrainz_recording_id="mbid",
            )
        ]


def test_audio_identification_service_composes_fingerprint_and_lookup(tmp_path):
    mp3_path = tmp_path / "song.mp3"
    mp3_path.write_bytes(b"")
    fingerprinter = FakeFingerprinter()
    lookup_provider = FakeLookupProvider()

    candidates = AudioIdentificationService(fingerprinter, lookup_provider).identify(mp3_path)

    assert fingerprinter.paths == [mp3_path]
    assert lookup_provider.fingerprints == [AudioFingerprint(duration=123, fingerprint="fp")]
    assert candidates == [
        CandidateRecording(
            recording_id="mbid",
            artist="Artist",
            title="Title",
            duration=123,
            acoustid_score=0.95,
            musicbrainz_recording_id="mbid",
        )
    ]
