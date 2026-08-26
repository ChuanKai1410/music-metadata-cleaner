from __future__ import annotations

from pathlib import Path

from music_metadata_cleaner.app.fallback_recognition_service import FallbackRecognitionService, StaticSegmentContext
from music_metadata_cleaner.audio_segments import AudioSegment
from music_metadata_cleaner.domain.models import AudioRecognitionSegmentResult
from music_metadata_cleaner.domain.recognition import build_recognition_consensus, normalize_identity_text


def _segment(index: int, start: int = 0) -> AudioSegment:
    return AudioSegment(index=index, start_seconds=start, path=Path(f"clip-{index}.mp3"))


def _result(index: int, artist: str = "Ado", title: str = "唱") -> AudioRecognitionSegmentResult:
    return AudioRecognitionSegmentResult(
        segment_index=index,
        start_seconds=index * 60,
        artist=artist,
        title=title,
        provider="AudD",
        provider_confidence=0.9,
        raw_status="success",
    )


class FakeRecognizer:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def recognize_file(self, path, *, segment_index, start_seconds):
        self.calls.append(segment_index)
        return self.results.get(segment_index)


def test_normalize_identity_preserves_cjk_while_removing_punctuation():
    assert normalize_identity_text(" Ado - 唱!! ") == "ado 唱"


def test_consensus_prefers_majority_result_and_flags_conflicts():
    consensus = build_recognition_consensus(
        [_result(1, "Ado", "唱"), _result(2, "Other", "Song"), _result(3, "Ado", "唱")],
        total_segments=3,
        provider="AudD",
    )

    assert consensus.artist == "Ado"
    assert consensus.title == "唱"
    assert consensus.matched_segments == 2
    assert consensus.review_reasons


def test_fallback_service_stops_after_two_matching_segments():
    recognizer = FakeRecognizer({1: _result(1), 2: _result(2), 3: _result(3, "Other", "Song")})
    service = FallbackRecognitionService(
        recognizer,
        segment_extractor=lambda path, *, duration_seconds: StaticSegmentContext([_segment(1), _segment(2), _segment(3)]),
    )

    result = service.recognize("song.mp3", duration_seconds=240)

    assert result.artist == "Ado"
    assert result.title == "唱"
    assert result.matched_segments == 2
    assert recognizer.calls == [1, 2]


def test_fallback_service_returns_none_when_no_segments_match():
    recognizer = FakeRecognizer({1: None, 2: None})
    service = FallbackRecognitionService(
        recognizer,
        segment_extractor=lambda path, *, duration_seconds: StaticSegmentContext([_segment(1), _segment(2)]),
    )

    assert service.recognize("song.mp3", duration_seconds=100) is None
