"""Official YouTube Data API v3 provider."""

from __future__ import annotations

import re
from typing import Protocol

import httpx

from music_metadata_cleaner.domain.models import YouTubeCandidate
from music_metadata_cleaner.domain.youtube import clean_youtube_search_text
from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


YOUTUBE_BASE_URL = "https://www.googleapis.com/youtube/v3"
VIDEO_URL_TEMPLATE = "https://www.youtube.com/watch?v={video_id}"


class RequestCacheProtocol(Protocol):
    def get(
        self,
        provider: str,
        cache_key: str,
        max_age_seconds: int | None = None,
    ) -> dict[str, object] | None:
        """Return cached provider payload."""

    def set(self, provider: str, cache_key: str, payload: dict[str, object]) -> None:
        """Store provider payload."""


class YouTubeClient:
    """Search YouTube using the official Data API and return normalized candidates."""

    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = YOUTUBE_BASE_URL,
        timeout_seconds: float = 10.0,
        request_cache: RequestCacheProtocol | None = None,
        max_results: int = 5,
        cache_ttl_seconds: int = 60 * 60 * 24 * 30,
    ) -> None:
        self.api_key = api_key
        self.http_client = http_client
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.request_cache = request_cache
        self.max_results = max(1, min(max_results, 10))
        self.cache_ttl_seconds = cache_ttl_seconds

    def search(self, query: str) -> list[YouTubeCandidate]:
        normalized_query = clean_youtube_search_text(query)
        if not normalized_query:
            return []
        if not self.api_key.strip():
            raise ProviderResponseError("YouTube API key is required.")

        search_payload = self._cached_or_get(
            cache_key=f"search:{normalized_query}:{self.max_results}",
            endpoint="search",
            params={
                "part": "snippet",
                "q": normalized_query,
                "type": "video",
                "maxResults": self.max_results,
                "key": self.api_key,
            },
        )
        video_ids = _video_ids_from_search(search_payload)
        if not video_ids:
            return []

        details_payload = self._cached_or_get(
            cache_key=f"videos:{','.join(video_ids)}",
            endpoint="videos",
            params={
                "part": "snippet,contentDetails",
                "id": ",".join(video_ids),
                "key": self.api_key,
            },
        )
        return normalize_youtube_candidates(details_payload)

    def _cached_or_get(self, *, cache_key: str, endpoint: str, params: dict[str, object]) -> dict[str, object]:
        cached = (
            self.request_cache.get("youtube", cache_key, max_age_seconds=self.cache_ttl_seconds)
            if self.request_cache is not None
            else None
        )
        if cached is not None:
            return cached

        payload = self._get_payload(endpoint, params)
        if self.request_cache is not None:
            self.request_cache.set("youtube", cache_key, payload)
        return payload

    def _get_payload(self, endpoint: str, params: dict[str, object]) -> dict[str, object]:
        try:
            response = self._get(f"{self.base_url}/{endpoint}", params=params)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("YouTube request timed out.") from exc
        except httpx.NetworkError as exc:
            raise ProviderNetworkError("YouTube network error.") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError("YouTube request failed.") from exc

        if response.status_code == 403:
            raise ProviderRateLimitError("YouTube API quota exceeded or API key is not permitted.")
        if response.status_code == 429:
            raise ProviderRateLimitError("YouTube API rate limit exceeded.")
        if response.status_code >= 400:
            raise ProviderResponseError(f"YouTube returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("YouTube returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise ProviderResponseError("YouTube returned an invalid payload.")
        return payload

    def _get(self, url: str, *, params: dict[str, object]) -> httpx.Response:
        if self.http_client is not None:
            return self.http_client.get(url, params=params, timeout=self.timeout_seconds)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.get(url, params=params)


def normalize_youtube_candidates(payload: dict[str, object]) -> list[YouTubeCandidate]:
    candidates: list[YouTubeCandidate] = []
    items = payload.get("items")
    if not isinstance(items, list):
        return candidates

    for item in items:
        if not isinstance(item, dict):
            continue

        video_id = _optional_str(item.get("id"))
        snippet = item.get("snippet")
        content_details = item.get("contentDetails")
        if not video_id or not isinstance(snippet, dict):
            continue

        title = _optional_str(snippet.get("title"))
        if not title:
            continue

        candidates.append(
            YouTubeCandidate(
                video_id=video_id,
                video_url=VIDEO_URL_TEMPLATE.format(video_id=video_id),
                title=title,
                channel_id=_optional_str(snippet.get("channelId")),
                channel_name=_optional_str(snippet.get("channelTitle")),
                duration_seconds=(
                    parse_iso8601_duration(_optional_str(content_details.get("duration")))
                    if isinstance(content_details, dict)
                    else None
                ),
                published_at=_optional_str(snippet.get("publishedAt")),
            )
        )
    return candidates


def parse_iso8601_duration(value: str | None) -> int | None:
    if not value:
        return None
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        value,
    )
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def _video_ids_from_search(payload: dict[str, object]) -> list[str]:
    ids: list[str] = []
    items = payload.get("items")
    if not isinstance(items, list):
        return ids

    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id")
        video_id = _optional_str(item_id.get("videoId")) if isinstance(item_id, dict) else None
        if video_id:
            ids.append(video_id)
    return ids


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
