"""AudD fallback audio recognition provider."""

from __future__ import annotations

from pathlib import Path

import httpx

from music_metadata_cleaner.domain.models import AudioRecognitionSegmentResult
from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


class AudDClient:
    """Recognize short local audio clips with AudD's standard API."""

    def __init__(
        self,
        api_token: str,
        *,
        http_client: httpx.Client | None = None,
        base_url: str = "https://api.audd.io/",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_token = api_token
        self.http_client = http_client
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def recognize_file(
        self,
        path: str | Path,
        *,
        segment_index: int,
        start_seconds: int,
    ) -> AudioRecognitionSegmentResult | None:
        if not self.api_token.strip():
            raise ProviderResponseError("AudD API token is required.")

        try:
            response = self._post_file(Path(path))
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("AudD request timed out.") from exc
        except httpx.NetworkError as exc:
            raise ProviderNetworkError("AudD network error.") from exc
        except httpx.HTTPError as exc:
            raise ProviderNetworkError("AudD request failed.") from exc

        if response.status_code in {401, 403}:
            raise ProviderResponseError("AudD API token is invalid or not permitted.")
        if response.status_code == 429:
            raise ProviderRateLimitError("AudD usage limit exceeded.")
        if response.status_code >= 400:
            raise ProviderResponseError(f"AudD returned HTTP {response.status_code}.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderResponseError("AudD returned invalid JSON.") from exc

        return normalize_audd_result(payload, segment_index=segment_index, start_seconds=start_seconds)

    def _post_file(self, path: Path) -> httpx.Response:
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "audio/mpeg")}
            data = {"api_token": self.api_token}
            if self.http_client is not None:
                return self.http_client.post(self.base_url, data=data, files=files, timeout=self.timeout_seconds)
            with httpx.Client(timeout=self.timeout_seconds) as client:
                return client.post(self.base_url, data=data, files=files)


def normalize_audd_result(
    payload: dict[str, object],
    *,
    segment_index: int,
    start_seconds: int,
) -> AudioRecognitionSegmentResult | None:
    status = _optional_str(payload.get("status"))
    if status == "error":
        error = payload.get("error")
        message = _optional_str(error.get("error_message") if isinstance(error, dict) else error)
        if message and any(word in message.casefold() for word in ("limit", "quota", "usage")):
            raise ProviderRateLimitError("AudD usage limit exceeded.")
        raise ProviderResponseError("AudD returned an error.")
    if status != "success":
        raise ProviderResponseError("AudD returned an unexpected status.")

    result = payload.get("result")
    if result is None:
        return None
    if not isinstance(result, dict):
        raise ProviderResponseError("AudD returned an invalid result payload.")

    artist = _optional_str(result.get("artist"))
    title = _optional_str(result.get("title"))
    if not artist or not title:
        return None

    return AudioRecognitionSegmentResult(
        segment_index=segment_index,
        start_seconds=start_seconds,
        artist=artist,
        title=title,
        album=_optional_str(result.get("album")),
        release_date=_optional_str(result.get("release_date")),
        provider="AudD",
        provider_confidence=0.9,
        song_link=_optional_str(result.get("song_link")),
        raw_status="success",
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
