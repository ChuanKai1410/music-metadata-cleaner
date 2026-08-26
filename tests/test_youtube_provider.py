from __future__ import annotations

import httpx
import pytest

from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.request_cache import RequestCache
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.providers.errors import ProviderNetworkError, ProviderRateLimitError, ProviderResponseError, ProviderTimeoutError
from music_metadata_cleaner.providers.youtube import YouTubeClient, normalize_youtube_candidates, parse_iso8601_duration


def test_parse_iso8601_duration():
    assert parse_iso8601_duration("PT4M15S") == 255
    assert parse_iso8601_duration("PT1H2M3S") == 3723
    assert parse_iso8601_duration("bad") is None


def test_normalize_youtube_candidates_from_video_details_payload():
    payload = {
        "items": [
            {
                "id": "abc",
                "snippet": {
                    "title": "米津玄師 - Lemon",
                    "channelId": "channel-id",
                    "channelTitle": "Kenshi Yonezu 米津玄師",
                    "publishedAt": "2018-03-14T00:00:00Z",
                },
                "contentDetails": {"duration": "PT4M15S"},
            }
        ]
    }

    candidates = normalize_youtube_candidates(payload)

    assert candidates[0].video_id == "abc"
    assert candidates[0].video_url == "https://www.youtube.com/watch?v=abc"
    assert candidates[0].title == "米津玄師 - Lemon"
    assert candidates[0].channel_name == "Kenshi Yonezu 米津玄師"
    assert candidates[0].duration_seconds == 255


def test_youtube_client_searches_then_batches_video_details():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.params["key"] == "api-key"
        if request.url.path.endswith("/search"):
            assert request.url.params["type"] == "video"
            assert request.url.params["maxResults"] == "5"
            return httpx.Response(
                200,
                json={"items": [{"id": {"videoId": "abc"}, "snippet": {"title": "ignored"}}]},
            )
        assert request.url.path.endswith("/videos")
        assert request.url.params["id"] == "abc"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "abc",
                        "snippet": {"title": "Artist - Song", "channelId": "cid", "channelTitle": "Artist"},
                        "contentDetails": {"duration": "PT3M00S"},
                    }
                ]
            },
        )

    client = YouTubeClient("api-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    candidates = client.search("Artist Song Official Music Video")

    assert len(candidates) == 1
    assert candidates[0].duration_seconds == 180
    assert len(requests) == 2


def test_youtube_client_uses_request_cache(tmp_path):
    connection = connect_database(tmp_path / "cache.sqlite3")
    initialize_schema(connection)
    cache = RequestCache(connection)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "abc"}}]})
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "abc",
                        "snippet": {"title": "Artist - Song", "channelId": "cid", "channelTitle": "Artist"},
                        "contentDetails": {"duration": "PT3M00S"},
                    }
                ]
            },
        )

    client = YouTubeClient("api-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)), request_cache=cache)

    assert client.search("Artist Song") == client.search("Artist Song")
    assert len(requests) == 2


def test_youtube_client_reports_quota_or_invalid_key_without_exposing_key():
    client = YouTubeClient(
        "secret-key",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403))),
    )

    with pytest.raises(ProviderRateLimitError) as exc_info:
        client.search("Artist Song")

    assert "secret-key" not in str(exc_info.value)


def test_youtube_client_reports_timeout_and_network_errors():
    timeout_client = YouTubeClient(
        "api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.TimeoutException("slow")))),
    )
    with pytest.raises(ProviderTimeoutError):
        timeout_client.search("Artist Song")

    network_client = YouTubeClient(
        "api-key",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline")))),
    )
    with pytest.raises(ProviderNetworkError):
        network_client.search("Artist Song")


def test_youtube_client_requires_api_key():
    with pytest.raises(ProviderResponseError):
        YouTubeClient("").search("Artist Song")
