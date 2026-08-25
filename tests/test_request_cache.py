from __future__ import annotations

import httpx

from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.request_cache import RequestCache
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.domain.models import AudioFingerprint, LyricsLookup
from music_metadata_cleaner.providers.acoustid import AcoustIDClient
from music_metadata_cleaner.providers.lrclib import LRCLIBClient
from music_metadata_cleaner.providers.musicbrainz import MusicBrainzClient


def test_request_cache_round_trip(tmp_path):
    connection = connect_database(tmp_path / "cache.sqlite3")
    initialize_schema(connection)
    cache = RequestCache(connection)

    cache.set("provider", "key", {"value": "cached"})

    assert cache.get("provider", "key") == {"value": "cached"}


def test_acoustid_uses_sqlite_request_cache(tmp_path):
    connection = connect_database(tmp_path / "cache.sqlite3")
    initialize_schema(connection)
    cache = RequestCache(connection)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "results": [{"id": "acoustid-id", "score": 0.9}],
            },
        )

    client = AcoustIDClient("api-key", http_client=httpx.Client(transport=httpx.MockTransport(handler)), request_cache=cache)
    fingerprint = AudioFingerprint(duration=120, fingerprint="fp")

    first = client.lookup(fingerprint)
    second = client.lookup(fingerprint)

    assert first == second
    assert len(requests) == 1


def test_musicbrainz_uses_sqlite_request_cache(tmp_path):
    connection = connect_database(tmp_path / "cache.sqlite3")
    initialize_schema(connection)
    cache = RequestCache(connection)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"id": "recording-id", "title": "Title", "artist-credit": [{"name": "Artist"}], "releases": []},
        )

    client = MusicBrainzClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        request_cache=cache,
        user_agent="TestApp/1.0",
    )

    first = client.get_recording_metadata("recording-id")
    second = MusicBrainzClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        request_cache=cache,
        user_agent="TestApp/1.0",
    ).get_recording_metadata("recording-id")

    assert first == second
    assert len(requests) == 1


def test_lrclib_uses_sqlite_request_cache(tmp_path):
    connection = connect_database(tmp_path / "cache.sqlite3")
    initialize_schema(connection)
    cache = RequestCache(connection)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": 1,
                "trackName": "Title",
                "artistName": "Artist",
                "duration": 120,
                "plainLyrics": "lyrics",
            },
        )

    lookup = LyricsLookup(artist="Artist", title="Title", duration=120)
    client = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        request_cache=cache,
        user_agent="TestApp/1.0",
    )

    first = client.get_lyrics(lookup)
    second = LRCLIBClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        request_cache=cache,
        user_agent="TestApp/1.0",
    ).get_lyrics(lookup)

    assert first == second
    assert len(requests) == 1
