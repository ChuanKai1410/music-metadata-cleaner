"""YouTube search normalization and scoring helpers."""

from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
import re

from music_metadata_cleaner.domain.models import CandidateRecording, MusicBrainzMetadata, TrackMetadata, YouTubeCandidate


NOISE_PATTERNS = (
    r"\bofficial\s+music\s+video\b",
    r"\bofficial\s+video\b",
    r"\blyric\s+video\b",
    r"\bofficial\s+audio\b",
    r"\bfull\s+hd\b",
    r"\b1080p\b",
    r"\b720p\b",
    r"\b4k\b",
    r"\bmp3\b",
    r"\bdownload\b",
    r"\bmv\b",
    r"\bpv\b",
    r"\bhd\b",
    r"\bhq\b",
)
VERSION_PATTERNS = {
    "live": r"\blive\b",
    "remix": r"\bremix\b",
    "remaster": r"\bremaster(?:ed)?\b",
    "acoustic": r"\bacoustic\b",
    "instrumental": r"\binstrumental\b",
    "cover": r"\bcover\b",
    "karaoke": r"\bkaraoke\b",
    "nightcore": r"\bnightcore\b",
    "sped up": r"\b(?:speed|sped)\s+up\b",
    "slowed": r"\bslowed\b",
    "reverb": r"\breverb\b",
    "radio edit": r"\bradio\s+edit\b",
    "extended": r"\bextended\b",
    "music video": r"\bmusic\s+video\b|\bmv\b",
    "lyric video": r"\blyric\s+video\b",
}
BRACKET_RE = re.compile(r"[\[\(（【].*?[\]\)）】]")
SEPARATOR_RE = re.compile(r"\s+[-|:]\s+")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    text = value.casefold()
    text = BRACKET_RE.sub(" ", text)
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[^\w\s\u3040-\u30ff\u3400-\u9fff-]", " ", text, flags=re.UNICODE)
    return WHITESPACE_RE.sub(" ", text).strip()


def clean_youtube_search_text(value: str | None) -> str:
    text = normalize_title(value)
    text = re.sub(r"\.mp3$", "", text, flags=re.IGNORECASE)
    return text.strip()


def build_youtube_search_queries(
    *,
    filename: str,
    metadata: TrackMetadata,
    candidate: CandidateRecording | None = None,
    musicbrainz: MusicBrainzMetadata | None = None,
) -> list[str]:
    queries: list[str] = []
    for artist, title in (
        (musicbrainz.artist if musicbrainz else None, musicbrainz.title if musicbrainz else None),
        (candidate.artist if candidate else None, candidate.title if candidate else None),
        (metadata.artist, metadata.title),
    ):
        query = _artist_title_query(artist, title)
        if query:
            queries.append(query)

    filename_query = clean_youtube_search_text(filename.rsplit(".", 1)[0])
    if filename_query:
        queries.append(filename_query)

    return _dedupe_queries(queries)


def score_youtube_candidate(
    candidate: YouTubeCandidate,
    *,
    expected_artist: str | None,
    expected_title: str | None,
    filename: str | None = None,
    id3_metadata: TrackMetadata | None = None,
    expected_duration: int | None = None,
) -> YouTubeCandidate:
    breakdown: list[str] = []
    score = 0

    title_targets = [expected_title, id3_metadata.title if id3_metadata else None, filename]
    title_score = max((_similarity(candidate.title, target) for target in title_targets if target), default=0.0)
    if title_score >= 0.75:
        score += 38
        breakdown.append("YouTube title: strong")
    elif title_score >= 0.65:
        score += 26
        breakdown.append("YouTube title: moderate")
    elif title_score >= 0.45:
        score += 12
        breakdown.append("YouTube title: weak")

    artist_targets = [expected_artist, id3_metadata.artist if id3_metadata else None]
    artist_score = max(
        (
            max(_similarity(candidate.title, artist), _similarity(candidate.channel_name, artist))
            for artist in artist_targets
            if artist
        ),
        default=0.0,
    )
    if artist_score >= 0.75:
        score += 22
        breakdown.append("YouTube artist/channel: strong")
    elif artist_score >= 0.6:
        score += 14
        breakdown.append("YouTube artist/channel: moderate")
    elif artist_score >= 0.4:
        score += 7
        breakdown.append("YouTube artist/channel: weak")

    duration_score, duration_reason = score_duration_match(expected_duration, candidate.duration_seconds)
    score += duration_score
    if duration_reason:
        breakdown.append(duration_reason)

    official_bonus = _official_source_bonus(candidate)
    if official_bonus:
        score += official_bonus
        breakdown.append("Official-source hint: slight")

    version_penalty, version_reason = _version_penalty(candidate.title, filename, expected_title)
    score -= version_penalty
    if version_reason:
        breakdown.append(version_reason)

    inferred_artist, inferred_title = infer_artist_title(candidate.title)
    return replace(
        candidate,
        normalized_title=normalize_title(candidate.title),
        inferred_artist=inferred_artist,
        inferred_song_title=inferred_title,
        version_hints=detect_version_hints(candidate.title),
        score=max(0, min(100, score)),
        score_breakdown=tuple(breakdown),
    )


def rank_youtube_candidates(candidates: list[YouTubeCandidate], **score_kwargs: object) -> list[YouTubeCandidate]:
    scored = [score_youtube_candidate(candidate, **score_kwargs) for candidate in candidates]
    return sorted(scored, key=lambda candidate: (-candidate.score, candidate.title.casefold(), candidate.video_id))


def score_duration_match(expected_seconds: int | None, candidate_seconds: int | None) -> tuple[int, str | None]:
    if expected_seconds is None or candidate_seconds is None:
        return 0, None
    delta = abs(expected_seconds - candidate_seconds)
    if delta <= 2:
        return 28, "YouTube duration: very strong"
    if delta <= 5:
        return 23, "YouTube duration: strong"
    if delta <= 10:
        return 15, "YouTube duration: moderate"
    if delta <= 20:
        return 7, "YouTube duration: weak"
    if delta > 90:
        return -18, "YouTube duration: clearly different"
    return 0, "YouTube duration: different"


def detect_version_hints(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    text = value.casefold()
    return tuple(name for name, pattern in VERSION_PATTERNS.items() if re.search(pattern, text, flags=re.IGNORECASE))


def infer_artist_title(value: str | None) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    cleaned = BRACKET_RE.sub(" ", value)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    parts = SEPARATOR_RE.split(cleaned, maxsplit=1)
    if len(parts) == 2:
        artist = _clean_inferred_part(parts[0])
        title = _clean_inferred_part(parts[1])
        return artist or None, title or None
    return None, _clean_inferred_part(cleaned) or None


def youtube_confidence_contribution(candidate: YouTubeCandidate | None) -> tuple[int, str]:
    if candidate is None:
        return 0, "YouTube: not checked"
    if candidate.score >= 85:
        return 8, "YouTube: strong supporting evidence"
    if candidate.score >= 70:
        return 5, "YouTube: moderate supporting evidence"
    if candidate.score >= 50:
        return 2, "YouTube: weak supporting evidence"
    return 0, "YouTube: little supporting evidence"


def _artist_title_query(artist: str | None, title: str | None) -> str | None:
    if not artist or not title:
        return None
    return clean_youtube_search_text(f"{artist} {title}") or None


def _dedupe_queries(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = normalize_title(value)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped[:4]


def _similarity(left: str | None, right: str | None) -> float:
    left_norm = normalize_title(left)
    right_norm = normalize_title(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm in right_norm or right_norm in left_norm:
        shorter = min(len(left_norm), len(right_norm))
        longer = max(len(left_norm), len(right_norm))
        return max(0.75, shorter / longer)
    return SequenceMatcher(None, left_norm, right_norm).ratio()


def _official_source_bonus(candidate: YouTubeCandidate) -> int:
    title = candidate.title.casefold()
    channel = (candidate.channel_name or "").casefold()
    if "vevo" in channel or " - topic" in channel or "official" in channel:
        return 6
    if "official" in title:
        return 4
    return 0


def _version_penalty(title: str, filename: str | None, expected_title: str | None) -> tuple[int, str | None]:
    youtube_hints = set(detect_version_hints(title))
    local_hints = set(detect_version_hints(filename)) | set(detect_version_hints(expected_title))
    mismatched = youtube_hints - local_hints - {"music video", "lyric video"}
    if not mismatched:
        return 0, None
    return 12, "Version hint differs: " + ", ".join(sorted(mismatched))


def _clean_inferred_part(value: str) -> str:
    text = value
    for pattern in NOISE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return WHITESPACE_RE.sub(" ", text).strip(" -_|:")
