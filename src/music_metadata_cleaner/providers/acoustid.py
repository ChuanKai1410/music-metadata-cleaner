"""AcoustID lookup client."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

import httpx

from music_metadata_cleaner.domain.models import AudioFingerprint, CandidateRecording
from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


class RequestCacheProtocol(Protocol):
    def get(self, provider: str, cache_key: str) -> dict[str, object] | None:
        """Return cached provider payload."""

    def set(self, provider: str, cache_key: str, payload: dict[str, object]) -> None:
        """Store provider payload."""


class AcoustIDClient:
    """Query AcoustID and normalize candidate recordings."""

    def __init__(
        self,
        api_key: str,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://api.acoustid.org/v2/lookup",
        timeout_seconds: float = 10.0,
        request_cache: RequestCacheProtocol | None = None,
    ) -> None:
        self.api_key = api_key
        self.http_client = http_client
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.request_cache = request_cache

    def lookup(self, fingerprint: AudioFingerprint) -> list[CandidateRecording]:
        if not self.api_key.strip():
            raise ProviderResponseError("AcoustID API key is required.")

        params = {
            "client": self.api_key,
            "duration": fingerprint.duration,
            "fingerprint": fingerprint.fingerprint,
            "meta": "recordings",
        }

        cache_key = f"{fingerprint.duration}:{fingerprint.fingerprint}"
        cached_payload = self.request_cache.get("acoustid", cache_key) if self.request_cache is not None else None
        if cached_payload is not None:
            return normalize_acoustid_candidates(cached_payload)

        try:
            response = self._get(params)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("AcoustID request timed out.") from exc
        except httpx.NetworkError as exc:
            raise ProviderNetworkError(f"AcoustID network error: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError(f"AcoustID request failed: {exc}") from exc

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            message = "AcoustID rate limit exceeded."
            if retry_after:
                message = f"{message} Retry after {retry_after} seconds."
            raise ProviderRateLimitError(message)

        if response.status_code >= 400:
            raise ProviderResponseError(f"AcoustID returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("AcoustID returned invalid JSON.") from exc

        if payload.get("status") != "ok":
            message = payload.get("error", {}).get("message") or payload.get("status") or "unknown error"
            raise ProviderResponseError(f"AcoustID lookup failed: {message}")

        if self.request_cache is not None:
            self.request_cache.set("acoustid", cache_key, payload)

        return normalize_acoustid_candidates(payload)

    def _get(self, params: dict[str, object]) -> httpx.Response:
        if self.http_client is not None:
            return self.http_client.get(self.base_url, params=params, timeout=self.timeout_seconds)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            return client.get(self.base_url, params=params)


def normalize_acoustid_candidates(payload: dict[str, object]) -> list[CandidateRecording]:
    """Normalize AcoustID lookup JSON into candidate recording models."""

    candidates: list[CandidateRecording] = []
    results = payload.get("results")
    if not isinstance(results, list):
        return candidates

    for result in results:
        if not isinstance(result, dict):
            continue

        score = _float_or_zero(result.get("score"))
        acoustid_result_id = _optional_str(result.get("id"))
        recordings = result.get("recordings")

        if isinstance(recordings, list) and recordings:
            candidates.extend(_recording_candidates(recordings, score, acoustid_result_id))
        elif acoustid_result_id is not None:
            candidates.append(
                CandidateRecording(
                    recording_id=acoustid_result_id,
                    artist=None,
                    title=None,
                    duration=None,
                    acoustid_score=score,
                    musicbrainz_recording_id=None,
                )
            )

    return candidates


def _recording_candidates(
    recordings: Iterable[object],
    score: float,
    acoustid_result_id: str | None,
) -> list[CandidateRecording]:
    candidates: list[CandidateRecording] = []

    for recording in recordings:
        if not isinstance(recording, dict):
            continue

        musicbrainz_recording_id = _optional_str(recording.get("id"))
        recording_id = musicbrainz_recording_id or acoustid_result_id
        if recording_id is None:
            continue

        candidates.append(
            CandidateRecording(
                recording_id=recording_id,
                artist=_artist_name(recording),
                title=_optional_str(recording.get("title")),
                duration=_duration_seconds(recording.get("duration")),
                acoustid_score=score,
                musicbrainz_recording_id=musicbrainz_recording_id,
            )
        )

    return candidates


def _artist_name(recording: dict[str, object]) -> str | None:
    artists = recording.get("artists")
    if not isinstance(artists, list):
        return None

    names = []
    for artist in artists:
        if isinstance(artist, dict):
            name = _optional_str(artist.get("name"))
            if name:
                names.append(name)

    return ", ".join(names) if names else None


def _duration_seconds(value: object) -> int | None:
    try:
        duration = int(round(float(value)))
    except (TypeError, ValueError):
        return None

    return duration if duration > 0 else None


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _optional_str(value: object) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None

