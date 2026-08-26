from __future__ import annotations

import httpx
import pytest

from music_metadata_cleaner.domain.models import Lyrics, LyricsLookup, LyricsResult
from music_metadata_cleaner.app.lyrics_service import LyricsService, build_lrc_export_filename
from music_metadata_cleaner.providers.errors import ProviderNetworkError, ProviderRateLimitError, ProviderTimeoutError
from music_metadata_cleaner.providers.lrclib import LRCLIBClient, normalize_lrclib_lyrics


def _lyrics_payload(**overrides):
    payload = {
        "id": 3396226,
        "trackName": "Lemon",
        "artistName": "米津玄師",
        "albumName": "STRAY SHEEP",
        "duration": 255,
        "instrumental": False,
        "plainLyrics": "plain lyrics",
        "syncedLyrics": "[00:01.00] plain lyrics",
    }
    payload.update(overrides)
    return payload


def test_normalize_lrclib_lyrics_marks_exact_match_as_online_without_review():
    result = normalize_lrclib_lyrics(
        _lyrics_payload(),
        LyricsLookup(artist="米津玄師", title="Lemon", album="STRAY SHEEP", duration=255),
    )

    assert result.source == "online"
    assert result.plain_lyrics == "plain lyrics"
    assert result.synced_lyrics == "[00:01.00] plain lyrics"
    assert result.lrclib_id == 3396226
    assert result.confidence == 1.0
    assert result.requires_review is False
    assert result.can_export_lrc is True


def test_normalize_lrclib_lyrics_requires_review_for_uncertain_duration():
    result = normalize_lrclib_lyrics(
        _lyrics_payload(duration=260),
        LyricsLookup(artist="米津玄師", title="Lemon", album="STRAY SHEEP", duration=255),
    )

    assert result.requires_review is True
    assert result.confidence == 0.6
    assert result.review_reasons == ("LRCLIB duration differs by more than 2 seconds.",)


def test_normalize_lrclib_lyrics_requires_review_for_identity_mismatch():
    result = normalize_lrclib_lyrics(
        _lyrics_payload(artistName="Other Artist", trackName="Other Title"),
        LyricsLookup(artist="米津玄師", title="Lemon", album="STRAY SHEEP", duration=255),
    )

    assert result.requires_review is True
    assert "LRCLIB artist differs from confirmed artist." in result.review_reasons
    assert "LRCLIB title differs from confirmed title." in result.review_reasons


def test_lrclib_client_sends_signature_request_with_user_agent_and_duration():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["User-Agent"] == "TestApp/1.0 (test@example.com)"
        assert request.url.path == "/api/get"
        assert request.url.params["artist_name"] == "米津玄師"
        assert request.url.params["track_name"] == "Lemon"
        assert request.url.params["album_name"] == "STRAY SHEEP"
        assert request.url.params["duration"] == "255"
        return httpx.Response(200, json=_lyrics_payload())

    client = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    result = client.get_lyrics(LyricsLookup(artist="米津玄師", title="Lemon", album="STRAY SHEEP", duration=255))

    assert result is not None
    assert result.source == "online"
    assert len(requests) == 1


def test_lrclib_client_returns_none_for_not_found():
    client = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    assert client.get_lyrics(LyricsLookup(artist="Artist", title="Title")) is None


def test_lrclib_client_caches_duplicate_lookup():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_lyrics_payload())

    client = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
    )
    lookup = LyricsLookup(artist="米津玄師", title="Lemon", album="STRAY SHEEP", duration=255)

    first = client.get_lyrics(lookup)
    second = client.get_lyrics(lookup)

    assert first == second
    assert len(requests) == 1


def test_lrclib_client_rate_limits_uncached_requests():
    now = {"value": 10.0}
    sleeps: list[float] = []

    def monotonic() -> float:
        return now["value"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now["value"] += seconds

    client = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=_lyrics_payload()))),
        user_agent="TestApp/1.0 (test@example.com)",
        min_request_interval_seconds=0.25,
        monotonic=monotonic,
        sleep=sleep,
    )

    client.get_lyrics(LyricsLookup(artist="Artist", title="One"))
    now["value"] += 0.1
    client.get_lyrics(LyricsLookup(artist="Artist", title="Two"))

    assert sleeps == pytest.approx([0.15])


def test_lrclib_client_reports_rate_limit():
    client = LRCLIBClient(
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={"Retry-After": "4"}))
        ),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    with pytest.raises(ProviderRateLimitError):
        client.get_lyrics(LyricsLookup(artist="Artist", title="Title"))


def test_lrclib_client_reports_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    client = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    with pytest.raises(ProviderTimeoutError):
        client.get_lyrics(LyricsLookup(artist="Artist", title="Title"))


def test_lrclib_client_reports_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    client = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        user_agent="TestApp/1.0 (test@example.com)",
    )

    with pytest.raises(ProviderNetworkError):
        client.get_lyrics(LyricsLookup(artist="Artist", title="Title"))


class FailingProvider:
    def get_lyrics(self, lookup: LyricsLookup) -> LyricsResult | None:
        raise AssertionError("Provider should not be called when existing lyrics are present.")


def test_lyrics_service_marks_existing_lyrics_and_does_not_query_online_provider():
    result = LyricsService(FailingProvider()).get_lyrics(
        LyricsLookup(artist="Artist", title="Title", album="Album", duration=100),
        existing_lyrics=Lyrics(text="already here"),
    )

    assert result is not None
    assert result.source == "existing"
    assert result.plain_lyrics == "already here"
    assert result.requires_review is False


def test_build_lrc_export_filename_uses_artist_title_convention():
    assert build_lrc_export_filename("米津玄師", "Lemon") == "米津玄師 - Lemon.lrc"
