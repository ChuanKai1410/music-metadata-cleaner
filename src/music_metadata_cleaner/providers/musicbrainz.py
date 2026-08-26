"""MusicBrainz metadata enrichment client."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol

import httpx

from music_metadata_cleaner.domain.models import CandidateRecording, MusicBrainzIdentifiers, MusicBrainzMetadata
from music_metadata_cleaner.domain.recognition import normalize_identity_text
from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


DEFAULT_USER_AGENT = "MusicMetadataCleaner/0.1 (https://example.com/music-metadata-cleaner)"
RECORDING_INCLUDES = "artist-credits+releases+release-groups+media"


class RequestCacheProtocol(Protocol):
    def get(self, provider: str, cache_key: str) -> dict[str, object] | None:
        """Return cached provider payload."""

    def set(self, provider: str, cache_key: str, payload: dict[str, object]) -> None:
        """Store provider payload."""


class MusicBrainzClient:
    """Retrieve canonical recording metadata from MusicBrainz."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://musicbrainz.org/ws/2",
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = 10.0,
        min_request_interval_seconds: float = 1.0,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        request_cache: RequestCacheProtocol | None = None,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("MusicBrainz requires a meaningful User-Agent header.")

        self.http_client = http_client
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self.monotonic = monotonic
        self.sleep = sleep
        self.request_cache = request_cache
        self._cache: dict[str, MusicBrainzMetadata] = {}
        self._last_request_at: float | None = None

    def get_recording_metadata(self, recording_id: str) -> MusicBrainzMetadata:
        recording_id = recording_id.strip()
        if not recording_id:
            raise ProviderResponseError("MusicBrainz recording ID is required.")

        cached = self._cache.get(recording_id)
        if cached is not None:
            return cached

        request_cache_key = f"recording:{recording_id}:{RECORDING_INCLUDES}"
        payload = self.request_cache.get("musicbrainz", request_cache_key) if self.request_cache is not None else None
        if payload is None:
            payload = self._get_recording(recording_id)
            if self.request_cache is not None:
                self.request_cache.set("musicbrainz", request_cache_key, payload)
        metadata = normalize_recording_metadata(payload)
        self._cache[recording_id] = metadata
        return metadata

    def search_recordings(
        self,
        *,
        artist: str,
        title: str,
        duration: int | None = None,
        limit: int = 5,
    ) -> list[CandidateRecording]:
        artist = artist.strip()
        title = title.strip()
        if not artist or not title:
            return []

        safe_limit = max(1, min(limit, 10))
        query = f'artist:"{artist}" AND recording:"{title}"'
        request_cache_key = f"recording-search:{query}:{duration}:{safe_limit}"
        payload = self.request_cache.get("musicbrainz", request_cache_key) if self.request_cache is not None else None
        if payload is None:
            payload = self._search_recordings(query, safe_limit)
            if self.request_cache is not None:
                self.request_cache.set("musicbrainz", request_cache_key, payload)
        return normalize_recording_search_results(payload, expected_artist=artist, expected_title=title, expected_duration=duration)

    def _search_recordings(self, query: str, limit: int) -> dict[str, object]:
        self._respect_rate_limit()
        url = f"{self.base_url}/recording"
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        params = {
            "fmt": "json",
            "query": query,
            "limit": str(limit),
        }

        try:
            response = self._get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("MusicBrainz request timed out.") from exc
        except httpx.NetworkError as exc:
            raise ProviderNetworkError(f"MusicBrainz network error: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(f"MusicBrainz request failed: {exc}") from exc

        if response.status_code in {429, 503}:
            retry_after = response.headers.get("Retry-After")
            message = "MusicBrainz rate limit or service throttle reached."
            if retry_after:
                message = f"{message} Retry after {retry_after} seconds."
            raise ProviderRateLimitError(message)
        if response.status_code >= 400:
            raise ProviderResponseError(f"MusicBrainz returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("MusicBrainz returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ProviderResponseError("MusicBrainz returned an invalid search payload.")
        return payload

    def _get_recording(self, recording_id: str) -> dict[str, object]:
        self._respect_rate_limit()
        url = f"{self.base_url}/recording/{recording_id}"
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        params = {
            "fmt": "json",
            "inc": RECORDING_INCLUDES,
        }

        try:
            response = self._get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("MusicBrainz request timed out.") from exc
        except httpx.NetworkError as exc:
            raise ProviderNetworkError(f"MusicBrainz network error: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(f"MusicBrainz request failed: {exc}") from exc

        if response.status_code in {429, 503}:
            retry_after = response.headers.get("Retry-After")
            message = "MusicBrainz rate limit or service throttle reached."
            if retry_after:
                message = f"{message} Retry after {retry_after} seconds."
            raise ProviderRateLimitError(message)

        if response.status_code == 404:
            raise ProviderResponseError(f"MusicBrainz recording not found: {recording_id}")

        if response.status_code >= 400:
            raise ProviderResponseError(f"MusicBrainz returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("MusicBrainz returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise ProviderResponseError("MusicBrainz returned an invalid recording payload.")

        return payload

    def _get(self, url: str, *, headers: dict[str, str], params: dict[str, str]) -> httpx.Response:
        if self.http_client is not None:
            return self.http_client.get(url, headers=headers, params=params, timeout=self.timeout_seconds)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.get(url, headers=headers, params=params)

    def _respect_rate_limit(self) -> None:
        now = self.monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            wait_seconds = self.min_request_interval_seconds - elapsed
            if wait_seconds > 0:
                self.sleep(wait_seconds)

        self._last_request_at = self.monotonic()


@dataclass(frozen=True)
class SelectedRelease:
    release: dict[str, object]
    track_number: str | None
    score: int
    reasons: tuple[str, ...]


def normalize_recording_metadata(payload: dict[str, object]) -> MusicBrainzMetadata:
    """Map a MusicBrainz recording lookup payload into canonical metadata."""

    recording_id = _required_str(payload.get("id"), "MusicBrainz recording payload missing recording id.")
    selected_release = select_best_release(payload)
    release = selected_release.release if selected_release is not None else None

    return MusicBrainzMetadata(
        artist=_artist_credit_name(payload.get("artist-credit")),
        title=_optional_str(payload.get("title")),
        album=_optional_str(release.get("title")) if release is not None else None,
        release_date=_release_date(release) if release is not None else _optional_str(payload.get("first-release-date")),
        track_number=selected_release.track_number if selected_release is not None else None,
        duration=_duration_seconds(payload.get("length")),
        identifiers=MusicBrainzIdentifiers(
            recording_id=recording_id,
            artist_ids=_artist_credit_ids(payload.get("artist-credit")),
            release_id=_optional_str(release.get("id")) if release is not None else None,
            release_group_id=_release_group_id(release) if release is not None else None,
        ),
    )


def normalize_recording_search_results(
    payload: dict[str, object],
    *,
    expected_artist: str,
    expected_title: str,
    expected_duration: int | None,
) -> list[CandidateRecording]:
    recordings = payload.get("recordings")
    if not isinstance(recordings, list):
        return []

    candidates: list[tuple[int, CandidateRecording]] = []
    for recording in recordings:
        if not isinstance(recording, dict):
            continue
        recording_id = _optional_str(recording.get("id"))
        title = _optional_str(recording.get("title"))
        artist = _artist_credit_name(recording.get("artist-credit"))
        if not recording_id or not artist or not title:
            continue

        score = _recording_search_score(
            artist=artist,
            title=title,
            duration=_duration_seconds(recording.get("length")),
            expected_artist=expected_artist,
            expected_title=expected_title,
            expected_duration=expected_duration,
        )
        candidates.append(
            (
                score,
                CandidateRecording(
                    recording_id=recording_id,
                    artist=artist,
                    title=title,
                    duration=_duration_seconds(recording.get("length")),
                    acoustid_score=score / 100,
                    musicbrainz_recording_id=recording_id,
                ),
            )
        )

    return [candidate for _, candidate in sorted(candidates, key=lambda item: (-item[0], item[1].recording_id))]


def _recording_search_score(
    *,
    artist: str,
    title: str,
    duration: int | None,
    expected_artist: str,
    expected_title: str,
    expected_duration: int | None,
) -> int:
    score = 40
    if normalize_identity_text(artist) == normalize_identity_text(expected_artist):
        score += 25
    if normalize_identity_text(title) == normalize_identity_text(expected_title):
        score += 25
    if duration is not None and expected_duration is not None:
        delta = abs(duration - expected_duration)
        if delta <= 2:
            score += 10
        elif delta <= 10:
            score += 6
        elif delta <= 20:
            score += 3
    return min(100, score)


def select_best_release(payload: dict[str, object]) -> SelectedRelease | None:
    """Select the most reliable release by scored metadata evidence."""

    recording_id = _optional_str(payload.get("id"))
    releases = payload.get("releases")
    if not isinstance(releases, list):
        return None

    scored: list[SelectedRelease] = []
    for release in releases:
        if not isinstance(release, dict):
            continue

        track_number = _track_number_for_recording(release, recording_id)
        score, reasons = _score_release(release, track_number)
        scored.append(SelectedRelease(release=release, track_number=track_number, score=score, reasons=tuple(reasons)))

    if not scored:
        return None

    return sorted(scored, key=_release_sort_key)[0]


def _release_sort_key(selected: SelectedRelease) -> tuple[int, str, str]:
    release = selected.release
    date = _release_date(release) or "9999-99-99"
    return (-selected.score, date, _optional_str(release.get("id")) or "")


def _score_release(release: dict[str, object], track_number: str | None) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if _optional_str(release.get("status")) == "Official":
        score += 40
        reasons.append("official")

    if track_number is not None:
        score += 30
        reasons.append("contains recording track")

    if _release_date(release):
        score += 15
        reasons.append("has release date")

    release_group = release.get("release-group")
    primary_type = _optional_str(release_group.get("primary-type")) if isinstance(release_group, dict) else None
    if primary_type in {"Album", "Single", "EP"}:
        score += 10
        reasons.append(f"preferred primary type: {primary_type}")

    if _optional_str(release.get("country")):
        score += 5
        reasons.append("has country")

    return score, reasons


def _track_number_for_recording(release: dict[str, object], recording_id: str | None) -> str | None:
    media = release.get("media")
    if not isinstance(media, list):
        return None

    for medium in media:
        if not isinstance(medium, dict):
            continue

        tracks = medium.get("tracks")
        if not isinstance(tracks, list):
            continue

        for track in tracks:
            if not isinstance(track, dict):
                continue

            track_recording = track.get("recording")
            track_recording_id = (
                _optional_str(track_recording.get("id")) if isinstance(track_recording, dict) else None
            )
            if recording_id is None or track_recording_id == recording_id:
                return _optional_str(track.get("number")) or _optional_str(track.get("position"))

    return None


def _release_date(release: dict[str, object] | None) -> str | None:
    if release is None:
        return None

    return _optional_str(release.get("date"))


def _release_group_id(release: dict[str, object] | None) -> str | None:
    if release is None:
        return None

    release_group = release.get("release-group")
    if not isinstance(release_group, dict):
        return None

    return _optional_str(release_group.get("id"))


def _artist_credit_name(value: object) -> str | None:
    if not isinstance(value, list):
        return None

    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            name = _optional_str(item.get("name"))
            if name:
                parts.append(name)
            joinphrase = _optional_str(item.get("joinphrase"))
            if joinphrase:
                parts.append(joinphrase)

    joined = "".join(parts).strip()
    return joined or None


def _artist_credit_ids(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()

    ids: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        artist = item.get("artist")
        if not isinstance(artist, dict):
            continue

        artist_id = _optional_str(artist.get("id"))
        if artist_id:
            ids.append(artist_id)

    return tuple(ids)


def _duration_seconds(value: object) -> int | None:
    try:
        duration_ms = int(round(float(value)))
    except (TypeError, ValueError):
        return None

    if duration_ms <= 0:
        return None

    return round(duration_ms / 1000)


def _required_str(value: object, message: str) -> str:
    text = _optional_str(value)
    if text is None:
        raise ProviderResponseError(message)
    return text


def _optional_str(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None
