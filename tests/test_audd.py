from __future__ import annotations

import httpx
import pytest

from music_metadata_cleaner.providers.audd import AudDClient, normalize_audd_result
from music_metadata_cleaner.providers.errors import ProviderRateLimitError, ProviderResponseError, ProviderTimeoutError


def test_normalize_audd_success_result_preserves_unicode_metadata():
    result = normalize_audd_result(
        {
            "status": "success",
            "result": {
                "artist": "Ado",
                "title": "唱",
                "album": "唱",
                "release_date": "2023-09-06",
                "song_link": "https://lis.tn/example",
            },
        },
        segment_index=2,
        start_seconds=60,
    )

    assert result.artist == "Ado"
    assert result.title == "唱"
    assert result.segment_index == 2
    assert result.start_seconds == 60


def test_normalize_audd_no_match_returns_none():
    assert normalize_audd_result({"status": "success", "result": None}, segment_index=1, start_seconds=0) is None


def test_audd_client_posts_file_without_exposing_token(tmp_path):
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"audio")

    def handler(request):
        assert request.method == "POST"
        assert "secret-token" not in str(request.url)
        return httpx.Response(200, json={"status": "success", "result": {"artist": "Artist", "title": "Title"}})

    result = AudDClient(
        "secret-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).recognize_file(clip, segment_index=1, start_seconds=10)

    assert result.artist == "Artist"
    assert result.title == "Title"


def test_audd_client_reports_quota_and_timeout(tmp_path):
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"audio")
    quota = AudDClient(
        "token",
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429))),
    )
    with pytest.raises(ProviderRateLimitError):
        quota.recognize_file(clip, segment_index=1, start_seconds=0)

    timeout = AudDClient(
        "token",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.TimeoutException("slow")))
        ),
    )
    with pytest.raises(ProviderTimeoutError):
        timeout.recognize_file(clip, segment_index=1, start_seconds=0)


def test_audd_client_requires_token(tmp_path):
    clip = tmp_path / "clip.mp3"
    clip.write_bytes(b"audio")
    with pytest.raises(ProviderResponseError):
        AudDClient("").recognize_file(clip, segment_index=1, start_seconds=0)
