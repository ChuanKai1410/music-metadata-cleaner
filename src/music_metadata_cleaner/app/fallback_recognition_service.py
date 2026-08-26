"""Fallback multi-segment audio recognition orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from music_metadata_cleaner.audio_segments import AudioSegment, get_audio_duration_seconds, temporary_audio_segments
from music_metadata_cleaner.domain.models import AudioRecognitionResult, AudioRecognitionSegmentResult
from music_metadata_cleaner.domain.recognition import build_recognition_consensus, identity_key


class SegmentRecognizer(Protocol):
    def recognize_file(
        self,
        path: str | Path,
        *,
        segment_index: int,
        start_seconds: int,
    ) -> AudioRecognitionSegmentResult | None:
        """Recognize one audio segment."""


class SegmentExtractor(Protocol):
    def __call__(self, source_path: str | Path, *, duration_seconds: int | None) -> object:
        """Return a context manager yielding audio segments."""


class FallbackRecognitionService:
    """Run paid/external fallback recognition only when requested by the workflow."""

    def __init__(
        self,
        recognizer: SegmentRecognizer,
        *,
        segment_extractor: Callable[..., object] | None = None,
        ffmpeg_executable: str = "ffmpeg",
        max_segments: int = 3,
        clip_seconds: int = 15,
        stop_after_matching_segments: int = 2,
    ) -> None:
        self.recognizer = recognizer
        self.segment_extractor = segment_extractor
        self.ffmpeg_executable = ffmpeg_executable
        self.max_segments = max(1, max_segments)
        self.clip_seconds = max(1, clip_seconds)
        self.stop_after_matching_segments = max(1, stop_after_matching_segments)
        self.last_requests_attempted = 0

    def recognize(self, path: str | Path, *, duration_seconds: int | None = None) -> AudioRecognitionResult | None:
        duration = duration_seconds or get_audio_duration_seconds(path)
        extractor = self.segment_extractor or self._default_extractor
        results: list[AudioRecognitionSegmentResult] = []
        self.last_requests_attempted = 0

        with extractor(path, duration_seconds=duration) as segments:
            total_segments = len(segments)
            for segment in segments:
                self.last_requests_attempted += 1
                result = self.recognizer.recognize_file(
                    segment.path,
                    segment_index=segment.index,
                    start_seconds=segment.start_seconds,
                )
                if result is not None:
                    results.append(result)
                    if _has_early_consensus(results, self.stop_after_matching_segments):
                        break

        return build_recognition_consensus(results, total_segments=total_segments if "total_segments" in locals() else 0, provider="AudD")

    def _default_extractor(self, path: str | Path, *, duration_seconds: int | None):
        return temporary_audio_segments(
            path,
            duration_seconds=duration_seconds,
            ffmpeg_executable=self.ffmpeg_executable,
            max_segments=self.max_segments,
            clip_seconds=self.clip_seconds,
        )


def _has_early_consensus(results: list[AudioRecognitionSegmentResult], required_matches: int) -> bool:
    counts: dict[tuple[str, str], int] = {}
    for result in results:
        if not result.has_identity:
            continue
        key = identity_key(result.artist, result.title)
        counts[key] = counts.get(key, 0) + 1
    return any(count >= required_matches for count in counts.values())


class StaticSegmentContext:
    """Small test helper context manager for fake segments."""

    def __init__(self, segments: list[AudioSegment]) -> None:
        self.segments = segments

    def __enter__(self) -> list[AudioSegment]:
        return self.segments

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None
