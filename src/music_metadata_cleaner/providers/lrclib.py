"""LRCLIB lyrics provider."""

from __future__ import annotations

import time
from typing import Callable

import httpx

from music_metadata_cleaner.domain.models import LyricsLookup, LyricsResult
from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


DEFAULT_USER_AGENT = "MusicMetadataCleaner/0.1 (https://example.com/music-metadata-cleaner)"


class LRCLIBClient:
    """Retrieve plain and synchronized lyrics from LRCLIB."""

    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://lrclib.net",
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = 10.0,
        min_request_interval_seconds: float = 0.25,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("LRCLIB requires a meaningful User-Agent header.")

        self.http_client = http_client
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent
        self.timeout_seconds = timeout_seconds
        self.min_request_interval_seconds = min_request_interval_seconds
        self.monotonic = monotonic
        self.sleep = sleep
        self._cache: dict[tuple[str, str, str | None, int | None], LyricsResult | None] = {}
        self._last_request_at: float | None = None

    def get_lyrics(self, lookup: LyricsLookup) -> LyricsResult | None:
        cache_key = _cache_key(lookup)
        if cache_key in self._cache:
            return self._cache[cache_key]

        payload = self._get_lyrics_payload(lookup)
        if payload is None:
            self._cache[cache_key] = None
            return None

        lyrics = normalize_lrclib_lyrics(payload, lookup)
        self._cache[cache_key] = lyrics
        return lyrics

    def _get_lyrics_payload(self, lookup: LyricsLookup) -> dict[str, object] | None:
        self._respect_rate_limit()
        headers = {
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }
        params: dict[str, object] = {
            "artist_name": lookup.artist,
            "track_name": lookup.title,
        }
        if lookup.album:
            params["album_name"] = lookup.album
        if lookup.duration is not None:
            params["duration"] = lookup.duration

        try:
            response = self._get(f"{self.base_url}/api/get", headers=headers, params=params)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("LRCLIB request timed out.") from exc
        except httpx.NetworkError as exc:
            raise ProviderNetworkError(f"LRCLIB network error: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(f"LRCLIB request failed: {exc}") from exc

        if response.status_code == 404:
            return None

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            message = "LRCLIB rate limit exceeded."
            if retry_after:
                message = f"{message} Retry after {retry_after} seconds."
            raise ProviderRateLimitError(message)

        if response.status_code >= 400:
            raise ProviderResponseError(f"LRCLIB returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("LRCLIB returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise ProviderResponseError("LRCLIB returned an invalid lyrics payload.")

        return payload

    def _get(self, url: str, *, headers: dict[str, str], params: dict[str, object]) -> httpx.Response:
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


def normalize_lrclib_lyrics(payload: dict[str, object], lookup: LyricsLookup) -> LyricsResult:
    """Normalize an LRCLIB response and mark uncertain matches for review."""

    returned_artist = _optional_str(payload.get("artistName"))
    returned_title = _optional_str(payload.get("trackName") or payload.get("name"))
    returned_album = _optional_str(payload.get("albumName"))
    returned_duration = _duration_seconds(payload.get("duration"))
    review_reasons: list[str] = []
    confidence = 1.0

    if returned_artist and _normalized(returned_artist) != _normalized(lookup.artist):
        confidence -= 0.35
        review_reasons.append("LRCLIB artist differs from confirmed artist.")

    if returned_title and _normalized(returned_title) != _normalized(lookup.title):
        confidence -= 0.35
        review_reasons.append("LRCLIB title differs from confirmed title.")

    if lookup.album and returned_album and _normalized(returned_album) != _normalized(lookup.album):
        confidence -= 0.1
        review_reasons.append("LRCLIB album differs from confirmed album.")

    if lookup.duration is not None and returned_duration is not None:
        delta = abs(returned_duration - lookup.duration)
        if delta > 2:
            confidence -= 0.4
            review_reasons.append("LRCLIB duration differs by more than 2 seconds.")
    elif lookup.duration is None or returned_duration is None:
        confidence -= 0.15
        review_reasons.append("Duration was unavailable for lyrics verification.")

    confidence = max(0.0, round(confidence, 2))

    return LyricsResult(
        source="online",
        plain_lyrics=_optional_str(payload.get("plainLyrics")),
        synced_lyrics=_optional_str(payload.get("syncedLyrics")),
        lrclib_id=_int_or_none(payload.get("id")),
        artist=returned_artist,
        title=returned_title,
        album=returned_album,
        duration=returned_duration,
        instrumental=bool(payload.get("instrumental")),
        confidence=confidence,
        requires_review=confidence < 0.9,
        review_reasons=tuple(review_reasons),
    )


def _cache_key(lookup: LyricsLookup) -> tuple[str, str, str | None, int | None]:
    return (
        _normalized(lookup.artist),
        _normalized(lookup.title),
        _normalized(lookup.album) if lookup.album else None,
        lookup.duration,
    )


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _duration_seconds(value: object) -> int | None:
    try:
        duration = int(round(float(value)))
    except (TypeError, ValueError):
        return None

    return duration if duration > 0 else None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None
