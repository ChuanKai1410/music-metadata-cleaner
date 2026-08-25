from __future__ import annotations

import httpx
import pytest

from music_metadata_cleaner.domain.models import AudioFingerprint
from music_metadata_cleaner.providers.acoustid import AcoustIDClient, normalize_acoustid_candidates
from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)


def test_normalize_acoustid_candidates_flattens_recordings():
    payload = {
        "status": "ok",
        "results": [
            {
                "id": "acoustid-result-id",
                "score": 0.98,
                "recordings": [
                    {
                        "id": "mb-recording-id",
                        "title": "Lemon",
                        "duration": 255,
                        "artists": [{"name": "米津玄師"}],
                    }
                ],
            }
        ],
    }

    candidates = normalize_acoustid_candidates(payload)

    assert len(candidates) == 1
    assert candidates[0].recording_id == "mb-recording-id"
    assert candidates[0].musicbrainz_recording_id == "mb-recording-id"
    assert candidates[0].artist == "米津玄師"
    assert candidates[0].title == "Lemon"
    assert candidates[0].duration == 255
    assert candidates[0].acoustid_score == 0.98


def test_acoustid_client_sends_lookup_request_and_returns_candidates():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["client"] == "api-key"
        assert request.url.params["duration"] == "255"
        assert request.url.params["fingerprint"] == "fingerprint"
        assert request.url.params["meta"] == "recordings"
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "results": [
                    {
                        "id": "acoustid-id",
                        "score": 0.91,
                        "recordings": [{"id": "mbid", "title": "Song", "artists": [{"name": "Artist"}]}],
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    candidates = AcoustIDClient("api-key", http_client=client).lookup(
        AudioFingerprint(duration=255, fingerprint="fingerprint")
    )

    assert len(candidates) == 1
    assert candidates[0].recording_id == "mbid"
    assert candidates[0].artist == "Artist"
    assert candidates[0].title == "Song"


def test_acoustid_client_reports_rate_limit():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "3"})))

    with pytest.raises(ProviderRateLimitError):
        AcoustIDClient("api-key", http_client=client).lookup(AudioFingerprint(duration=1, fingerprint="fp"))


def test_acoustid_client_reports_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderTimeoutError):
        AcoustIDClient("api-key", http_client=client).lookup(AudioFingerprint(duration=1, fingerprint="fp"))


def test_acoustid_client_reports_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderNetworkError):
        AcoustIDClient("api-key", http_client=client).lookup(AudioFingerprint(duration=1, fingerprint="fp"))


def test_acoustid_client_reports_non_ok_status_payload():
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"status": "error", "error": {"message": "bad api key"}})
        )
    )

    with pytest.raises(ProviderResponseError):
        AcoustIDClient("api-key", http_client=client).lookup(AudioFingerprint(duration=1, fingerprint="fp"))


def test_acoustid_client_requires_api_key():
    with pytest.raises(ProviderResponseError):
        AcoustIDClient("").lookup(AudioFingerprint(duration=1, fingerprint="fp"))

