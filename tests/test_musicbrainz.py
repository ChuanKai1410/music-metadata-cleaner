from __future__ import annotations

import httpx
import pytest

from music_metadata_cleaner.providers.errors import (
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from music_metadata_cleaner.providers.musicbrainz import (
    RECORDING_INCLUDES,
    MusicBrainzClient,
    normalize_recording_metadata,
    normalize_recording_search_results,
    select_best_release,
)


def _recording_payload():
    return {
        "id": "recording-id",
        "title": "Lemon",
        "length": 255000,
        "first-release-date": "2018-03-14",
        "artist-credit": [
            {
                "name": "米津玄師",
                "artist": {"id": "artist-id", "name": "Kenshi Yonezu"},
            }
        ],
        "releases": [
            {
                "id": "bootleg-release",
                "title": "Random Collection",
                "status": "Bootleg",
                "date": "2017",
                "release-group": {"id": "bootleg-group", "primary-type": "Album"},
            },
            {
                "id": "official-release",
                "title": "STRAY SHEEP",
                "status": "Official",
                "date": "2020-08-05",
                "country": "JP",
                "release-group": {"id": "release-group-id", "primary-type": "Album"},
                "media": [
                    {
                        "position": 1,
                        "tracks": [
                            {"number": "8", "recording": {"id": "recording-id"}},
                            {"number": "9", "recording": {"id": "other-recording"}},
                        ],
                    }
                ],
            },
        ],
    }


def test_normalize_recording_metadata_preserves_original_language_artist_and_title():
    metadata = normalize_recording_metadata(_recording_payload())

    assert metadata.artist == "米津玄師"
    assert metadata.title == "Lemon"
    assert metadata.album == "STRAY SHEEP"
    assert metadata.release_date == "2020-08-05"
    assert metadata.track_number == "8"
    assert metadata.duration == 255
    assert metadata.identifiers.recording_id == "recording-id"
    assert metadata.identifiers.artist_ids == ("artist-id",)
    assert metadata.identifiers.release_id == "official-release"
    assert metadata.identifiers.release_group_id == "release-group-id"


def test_normalize_recording_search_results_ranks_identity_and_duration():
    payload = {
        "recordings": [
            {
                "id": "weak",
                "title": "Song",
                "length": 310000,
                "artist-credit": [{"name": "Other Artist"}],
            },
            {
                "id": "strong",
                "title": "唱",
                "length": 185000,
                "artist-credit": [{"name": "Ado"}],
            },
        ]
    }

    candidates = normalize_recording_search_results(
        payload,
        expected_artist="Ado",
        expected_title="唱",
        expected_duration=184,
    )

    assert candidates[0].recording_id == "strong"
    assert candidates[0].artist == "Ado"
    assert candidates[0].title == "唱"
    assert candidates[0].musicbrainz_recording_id == "strong"


def test_select_best_release_does_not_blindly_choose_first_release():
    selected = select_best_release(_recording_payload())

    assert selected is not None
    assert selected.release["id"] == "official-release"
    assert selected.track_number == "8"
    assert "official" in selected.reasons


def test_normalize_recording_metadata_uses_first_release_date_when_no_reliable_release():
    payload = {
        "id": "recording-id",
        "title": "No Release",
        "length": 1000,
        "first-release-date": "2001",
        "artist-credit": [{"name": "Artist", "artist": {"id": "artist-id"}}],
        "releases": [],
    }

    metadata = normalize_recording_metadata(payload)

    assert metadata.album is None
    assert metadata.release_date == "2001"
    assert metadata.track_number is None
    assert metadata.identifiers.release_id is None


def test_musicbrainz_client_sends_required_headers_params_and_caches_response():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["User-Agent"] == "TestApp/1.0 (test@example.com)"
        assert request.url.params["fmt"] == "json"
        assert request.url.params["inc"] == RECORDING_INCLUDES
        return httpx.Response(200, json=_recording_payload())

    client = MusicBrainzClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
        min_request_interval_seconds=1.0,
    )

    first = client.get_recording_metadata("recording-id")
    second = client.get_recording_metadata("recording-id")

    assert first == second
    assert len(requests) == 1


def test_musicbrainz_client_rate_limits_uncached_requests():
    now = {"value": 10.0}
    sleeps: list[float] = []

    def monotonic() -> float:
        return now["value"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now["value"] += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        payload = _recording_payload() | {"id": request.url.path.rsplit("/", 1)[-1]}
        return httpx.Response(200, json=payload)

    client = MusicBrainzClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
        min_request_interval_seconds=1.0,
        monotonic=monotonic,
        sleep=sleep,
    )

    client.get_recording_metadata("one")
    now["value"] += 0.25
    client.get_recording_metadata("two")

    assert sleeps == [0.75]


def test_musicbrainz_client_reports_rate_limit_response():
    client = MusicBrainzClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(503, headers={"Retry-After": "2"}))
        ),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    with pytest.raises(ProviderRateLimitError):
        client.get_recording_metadata("recording-id")


def test_musicbrainz_client_reports_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client = MusicBrainzClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    with pytest.raises(ProviderTimeoutError):
        client.get_recording_metadata("recording-id")


def test_musicbrainz_client_reports_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = MusicBrainzClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    with pytest.raises(ProviderNetworkError):
        client.get_recording_metadata("recording-id")


def test_musicbrainz_client_reports_not_found():
    client = MusicBrainzClient(
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    with pytest.raises(ProviderResponseError):
        client.get_recording_metadata("missing")
