"""Audio recognition consensus and identity normalization."""

from __future__ import annotations

from collections import defaultdict
import re
import unicodedata

from music_metadata_cleaner.domain.models import AudioRecognitionResult, AudioRecognitionSegmentResult


SEPARATOR_RE = re.compile(r"\s*(?:feat\.?|ft\.?|featuring|&|,|/|\+| x )\s*", flags=re.IGNORECASE)
PUNCT_RE = re.compile(r"[^\w\s\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]", flags=re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")


def normalize_identity_text(value: str | None) -> str:
    """Normalize for comparison while preserving CJK/Korean/Japanese text."""

    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value).casefold()
    text = SEPARATOR_RE.sub(" ", text)
    text = PUNCT_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def identity_key(artist: str | None, title: str | None) -> tuple[str, str]:
    return normalize_identity_text(artist), normalize_identity_text(title)


def build_recognition_consensus(
    results: list[AudioRecognitionSegmentResult],
    *,
    total_segments: int,
    provider: str,
) -> AudioRecognitionResult | None:
    """Return a consensus result from recognized segments."""

    recognized = [result for result in results if result.has_identity]
    if not recognized:
        return None

    grouped: dict[tuple[str, str], list[AudioRecognitionSegmentResult]] = defaultdict(list)
    for result in recognized:
        grouped[identity_key(result.artist, result.title)].append(result)

    best_key, best_results = sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), -sum(result.provider_confidence for result in item[1]), item[0]),
    )[0]
    conflicts = len(grouped) > 1
    confidence = _consensus_confidence(best_results, total_segments, conflicts)
    reasons: list[str] = []
    if conflicts:
        reasons.append("Fallback recognition returned conflicting segment identities.")
    if len(best_results) == 1 and total_segments > 1:
        reasons.append("Only one segment matched this identity.")

    representative = best_results[0]
    return AudioRecognitionResult(
        artist=representative.artist,
        title=representative.title,
        album=representative.album,
        release_date=representative.release_date,
        provider=provider,
        matched_segments=len(best_results),
        total_segments=total_segments,
        provider_confidence=confidence,
        segment_results=tuple(results),
        review_reasons=tuple(reasons),
    )


def recognition_confidence_score(result: AudioRecognitionResult | None) -> int:
    if result is None or not result.has_identity:
        return 0
    return max(0, min(100, round(result.provider_confidence * 100)))


def _consensus_confidence(
    best_results: list[AudioRecognitionSegmentResult],
    total_segments: int,
    conflicts: bool,
) -> float:
    matched = len(best_results)
    if total_segments <= 0:
        return 0.0
    coverage = matched / total_segments
    average_provider = sum(result.provider_confidence for result in best_results) / matched
    confidence = 0.35 + (0.45 * coverage) + (0.2 * average_provider)
    if matched >= 2:
        confidence += 0.08
    if conflicts:
        confidence -= 0.15
    return round(max(0.0, min(0.98, confidence)), 2)
