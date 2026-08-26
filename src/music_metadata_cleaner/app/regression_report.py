"""Manual regression reporting for local real-world sample sets."""

from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path


@dataclass(frozen=True)
class RegressionSummary:
    total: int
    previous_high_confidence: int
    previous_failed_or_uncertain: int
    existing_high_confidence_still_correct: int
    previously_failed_recovered: int
    incorrect_youtube_matches: int
    correct_high_confidence: int = 0
    correct_medium_confidence: int = 0
    unresolved: int = 0
    incorrect_identifications: int = 0
    acoustid_resolved: int = 0
    audd_fallback_resolved: int = 0
    youtube_verified: int = 0


def summarize_regression_csv(path: str | Path) -> RegressionSummary:
    """Summarize a user-maintained before/after CSV without storing MP3 fixtures."""

    rows = list(csv.DictReader(Path(path).read_text(encoding="utf-8").splitlines()))
    previous_high = [row for row in rows if _truthy(row.get("before_high_confidence"))]
    previous_failed = [row for row in rows if not _truthy(row.get("before_high_confidence"))]
    still_correct = [row for row in previous_high if _truthy(row.get("after_correct"))]
    recovered = [
        row
        for row in previous_failed
        if _truthy(row.get("after_high_confidence")) and _truthy(row.get("after_correct"))
    ]
    incorrect_youtube = [
        row
        for row in rows
        if _truthy(row.get("youtube_used")) and not _truthy(row.get("after_correct"))
    ]
    correct_high = [
        row for row in rows if _truthy(row.get("after_correct")) and _confidence_bucket(row) == "high"
    ]
    correct_medium = [
        row for row in rows if _truthy(row.get("after_correct")) and _confidence_bucket(row) == "medium"
    ]
    unresolved = [row for row in rows if _truthy(row.get("unresolved")) or _confidence_bucket(row) == "unresolved"]
    incorrect = [row for row in rows if not _truthy(row.get("after_correct")) and row not in unresolved]
    return RegressionSummary(
        total=len(rows),
        previous_high_confidence=len(previous_high),
        previous_failed_or_uncertain=len(previous_failed),
        existing_high_confidence_still_correct=len(still_correct),
        previously_failed_recovered=len(recovered),
        incorrect_youtube_matches=len(incorrect_youtube),
        correct_high_confidence=len(correct_high),
        correct_medium_confidence=len(correct_medium),
        unresolved=len(unresolved),
        incorrect_identifications=len(incorrect),
        acoustid_resolved=sum(1 for row in rows if _truthy(row.get("acoustid_resolved"))),
        audd_fallback_resolved=sum(1 for row in rows if _truthy(row.get("audd_fallback_resolved"))),
        youtube_verified=sum(1 for row in rows if _truthy(row.get("youtube_verified")) or _truthy(row.get("youtube_used"))),
    )


def _truthy(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "y"}


def _confidence_bucket(row: dict[str, str]) -> str:
    explicit = (row.get("after_confidence_bucket") or "").strip().casefold()
    if explicit:
        return explicit
    try:
        score = int(row.get("after_confidence") or "")
    except ValueError:
        return "unresolved"
    if score >= 90:
        return "high"
    if score >= 70:
        return "medium"
    return "unresolved"
