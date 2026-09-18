from dataclasses import replace
from pathlib import Path
import httpx
import pytest
from music_metadata_cleaner.domain.models import (
    TrackMetadata,
    Lyrics,
    LyricsResult,
    LyricsLookup,
)
from music_metadata_cleaner.domain.search import (
    clean_filename,
    build_search_queries,
    artist_key,
    normalized,
    SearchResult,
    RuleBasedIdentityResolver,
    source_weight,
    source_domain,
    extract_candidates,
)
from music_metadata_cleaner.providers.search import (
    SearXNGProvider,
    SearchError,
    normalize_search_results,
)
from music_metadata_cleaner.providers.lrclib import LRCLIBClient
from music_metadata_cleaner.app.lyrics_service import LyricsService
from music_metadata_cleaner.app.workflow_service import (
    MusicCleanerWorkflowService,
    WorkflowTrack,
    ApplySettings,
    CancellationToken,
)
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.schema import initialize_schema
from music_metadata_cleaner.db.request_cache import RequestCache
from music_metadata_cleaner.db.history import HistoryRepository
from music_metadata_cleaner.id3.reader import read_id3_metadata
from mutagen.id3 import ID3, TIT2, TPE1, USLT


@pytest.mark.parametrize(
    "filename,expected",
    [
        (
            "tomp3.cc - Just Kiddin x Camden Cox Stay The Night.mp3",
            "Just Kiddin x Camden Cox Stay The Night",
        ),
        ("米津玄師 Lemon Official MV Full HD.mp3", "米津玄師 Lemon"),
        ("YOASOBI アイドル Official Music Video.mp3", "YOASOBI アイドル"),
        ("y2mate.com - 周杰倫 - 夜曲【MV】.mp3", "周杰倫 - 夜曲"),
        ("ytmp3 - IU 좋은 날 [Official Video] (720p).mp3", "IU 좋은 날"),
        ("Artist - Full Moon.mp3", "Artist - Full Moon"),
        ("Artist - Audio.mp3", "Artist - Audio"),
        ("Artist - Song (Live).mp3", "Artist - Song (Live)"),
        (r"C:\Music\Artist - Title.mp3", "Artist - Title"),
        ("/home/me/music/Artist - Title.mp3", "Artist - Title"),
    ],
)
def test_filename_cleaner(filename, expected):
    assert clean_filename(filename) == expected


@pytest.mark.parametrize(
    "filename", ["track001.mp3", "流行歌曲推荐TikTok.mp3", "12345.mp3"]
)
def test_insufficient_information_never_searches(filename):
    service = MusicCleanerWorkflowService(search_provider=FailSearch())
    result = service.process_track(WorkflowTrack(Path(filename), TrackMetadata()))
    assert result.processing_status == "Insufficient Information"
    assert result.proposed is None
    assert result.confidence == "Low"


class FailSearch:
    def search(self, *args, **kwargs):
        raise AssertionError("Unexpected search")


def test_queries_prefer_id3_but_include_filename_alternative():
    queries = build_search_queries(
        "Lemon Official MV.mp3", TrackMetadata(artist="米津玄師", title="Lemon")
    )
    assert queries == ('"米津玄師 Lemon"', '"Lemon" song')
    assert build_search_queries("track001.mp3", TrackMetadata(), "Ado 唱") == (
        '"Ado 唱"',
        '"Ado 唱" song',
    )


@pytest.mark.parametrize(
    "separator", [" x ", " × ", " & ", " and ", ", ", " feat. ", " ft. ", " featuring "]
)
def test_artist_normalization(separator):
    assert artist_key("Just Kiddin" + separator + "Camden Cox") == artist_key(
        "Just Kiddin & Camden Cox"
    )


def test_punctuation_and_title_versions():
    assert normalized("  Don’t   Go — LIVE ") == "don't go - live"
    assert normalized("Title (Live)") != normalized("Title")


def sources(artist="米津玄師", title="Lemon"):
    return [
        SearchResult(f"{artist} - {title}", f"https://youtube.com/watch?v=1"),
        SearchResult(f"{title} by {artist}", "https://open.spotify.com/track/1"),
        SearchResult(f"{artist} – {title} Lyrics | Genius", "https://genius.com/1"),
    ]


def test_cross_source_unicode_agreement():
    result = RuleBasedIdentityResolver().resolve(
        "米津玄師 Lemon", TrackMetadata(), sources()
    )
    assert len(result) == 1
    assert (result[0].artist, result[0].title, result[0].confidence) == (
        "米津玄師",
        "Lemon",
        "High",
    )
    assert result[0].internal_score == 85


def test_collaboration_and_reversed_result_group_together():
    results = [
        SearchResult(
            "Just Kiddin x Camden Cox - Stay The Night", "https://youtube.com/1"
        ),
        SearchResult(
            "Stay The Night - Just Kiddin, Camden Cox | Spotify",
            "https://spotify.com/1",
        ),
        SearchResult(
            "Just Kiddin & Camden Cox – Stay The Night Lyrics | Genius",
            "https://genius.com/1",
        ),
    ]
    (identity,) = RuleBasedIdentityResolver().resolve(
        "Just Kiddin x Camden Cox Stay The Night", TrackMetadata(), results
    )
    assert len(identity.evidence) == 3
    assert identity.confidence == "High"
    assert artist_key(identity.artist) == artist_key("Just Kiddin & Camden Cox")


@pytest.mark.parametrize(
    "text",
    [
        "Artist - Title - YouTube",
        "Artist – Title",
        "Artist — Title Lyrics | Genius",
        "Title - Artist | Spotify",
        "Title by Artist",
        "Artist: Title",
        "Title | Artist",
        "Title - song by Artist | Spotify",
    ],
)
def test_result_patterns(text):
    pairs = extract_candidates(SearchResult(text, "https://spotify.com/1"))
    assert any((artist, title) == ("Artist", "Title") for artist, title, _ in pairs)


def test_weighting_and_same_publisher_are_not_independent():
    assert (
        source_weight("https://music.apple.com/x")
        > source_weight("https://genius.com/x")
        > source_weight("https://blog.example/x")
    )
    assert source_domain("https://youtu.be/1") == source_domain(
        "https://www.youtube.com/2"
    )
    assert source_domain("https://music.example.co.uk/a") == source_domain(
        "https://news.example.co.uk/b"
    )
    results = [
        SearchResult("Artist - Title", f"https://youtube.com/{i}") for i in range(5)
    ]
    (identity,) = RuleBasedIdentityResolver().resolve(
        "Artist Title", TrackMetadata(), results
    )
    assert identity.confidence != "High"


@pytest.mark.parametrize("title", ["Lemon Live", "Lemon Cover", "Lemon Remix"])
def test_version_conflicts_reduce_confidence(title):
    identities = RuleBasedIdentityResolver().resolve(
        "米津玄師 Lemon", TrackMetadata(), sources() + sources(title=title)
    )
    assert all(i.confidence != "High" for i in identities)
    assert any("Version" in " ".join(i.evidence_breakdown) for i in identities)


def test_unrelated_results_cannot_become_identity():
    assert (
        RuleBasedIdentityResolver().resolve(
            "Known Artist Known Title", TrackMetadata(), sources()
        )
        == ()
    )


def test_conflicting_artist_requires_review_without_translation():
    results = sources() + [
        SearchResult("Lemon by Kenshi Yonezu", "https://bandcamp.com/1")
    ]
    identities = RuleBasedIdentityResolver().resolve(
        "米津玄師 Lemon", TrackMetadata(), results
    )
    assert identities[0].artist == "米津玄師"
    assert all(i.confidence == "Low" for i in identities)


def payload():
    return {
        "results": [
            {
                "title": "<b>米津玄師</b> - Lemon",
                "url": "https://youtube.com/1",
                "content": "Song &amp; music",
                "engine": "test-engine",
            }
        ]
    }


def test_searxng_request_and_normalization():
    def handler(request):
        assert str(request.url).startswith("http://search.example/sub/search?")
        assert request.url.params["q"] == "米津玄師 Lemon"
        assert request.url.params["format"] == "json"
        assert "x-subscription-token" not in request.headers
        return httpx.Response(200, json=payload())

    provider = SearXNGProvider(
        "http://search.example/sub/",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    (result,) = provider.search("米津玄師 Lemon")
    assert result.snippet == "Song & music"
    assert result.source_domain == "youtube.com"
    assert result.engine == "test-engine"


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (403, {}, "JSON_FORMAT_DISABLED"),
        (404, {}, "INVALID_ENDPOINT"),
        (500, {}, "SERVER_UNREACHABLE"),
        (200, {}, "INVALID_RESPONSE"),
        (200, {"results": {}}, "INVALID_RESPONSE"),
        (200, {"results": []}, "PASS"),
    ],
)
def test_connection_statuses(status, body, expected):
    provider = SearXNGProvider(
        "https://search.example",
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(status, json=body))
        ),
    )
    assert provider.test_connection() == expected


@pytest.mark.parametrize(
    "exception,expected",
    [
        (httpx.ReadTimeout("slow"), "TIMEOUT"),
        (httpx.ConnectError("down"), "SERVER_UNREACHABLE"),
    ],
)
def test_network_errors(exception, expected):
    def handler(request):
        raise exception

    assert (
        SearXNGProvider(
            "http://search.example",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        ).test_connection()
        == expected
    )


def test_invalid_endpoint_and_html_json_disabled():
    assert SearXNGProvider("").test_connection() == "INVALID_ENDPOINT"
    assert SearXNGProvider("file:///tmp/a").test_connection() == "INVALID_ENDPOINT"
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, text="<html>search</html>", headers={"content-type": "text/html"}
            )
        )
    )
    assert (
        SearXNGProvider("https://search.example", http_client=client).test_connection()
        == "JSON_FORMAT_DISABLED"
    )


def test_cache_endpoint_query_expiration_and_test_bypass(tmp_path):
    connection = connect_database(tmp_path / "cache.sqlite3")
    initialize_schema(connection)
    cache = RequestCache(connection)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    one = SearXNGProvider(
        "https://one.example", http_client=client, request_cache=cache
    )
    two = SearXNGProvider(
        "https://two.example", http_client=client, request_cache=cache
    )
    one.search("A Song")
    one.search("a   song")
    two.search("A Song")
    assert len(calls) == 2
    one.test_connection()
    one.test_connection()
    assert len(calls) == 4
    connection.execute(
        "UPDATE request_cache SET created_at = '2000-01-01T00:00:00+00:00'"
    )
    connection.commit()
    one.search("A Song")
    assert len(calls) == 5
    connection.close()


class FakeSearch:
    def __init__(self, results=None):
        self.results = sources() if results is None else results
        self.queries = []

    def search(self, query, count=8):
        self.queries.append(query)
        return self.results


def test_workflow_early_stop_manual_review_and_plain_lyrics():
    provider = FakeSearch(sources("Ado", "唱"))
    service = MusicCleanerWorkflowService(
        search_provider=provider, retrieve_lyrics=False
    )
    track = WorkflowTrack(Path("track001.mp3"), TrackMetadata())
    resolved = service.manual_search(track, "Ado 唱")
    assert resolved.proposed.artist == "Ado"
    assert resolved.proposed.title == "唱"
    assert resolved.confidence == "High"
    assert len(provider.queries) == 1
    weak = MusicCleanerWorkflowService(
        search_provider=FakeSearch(sources("Ado", "唱")[:1]), retrieve_lyrics=False
    )
    preview = weak.manual_search(track, "Ado 唱")
    assert preview.requires_review
    assert weak.use_candidate(preview, 0).manually_reviewed


def test_search_retry_failure_clears_previous_proposal():
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(), retrieve_lyrics=False
    )
    track = service.process_track(
        WorkflowTrack(Path("米津玄師 Lemon.mp3"), TrackMetadata())
    )
    service.search_provider = FailSearch()
    failed = service.process_track(track)
    assert failed.processing_status == "Search Failed"
    assert failed.proposed is None


def test_existing_lyrics_and_missing_plain_lyrics():
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(), lyrics_service=LyricsService(FailSearch())
    )
    track = service.process_track(
        WorkflowTrack(
            Path("米津玄師 Lemon.mp3"), TrackMetadata(lyrics=Lyrics(text="keep"))
        )
    )
    assert track.lyrics_status == "Found"
    assert track.proposed.lyrics.plain_lyrics == "keep"
    service.lyrics_service = None
    missing = service.process_track(replace(track, current_metadata=TrackMetadata()))
    assert missing.proposed.artist == "米津玄師"
    assert missing.processing_status == "Lyrics Not Found"


def test_lrclib_drops_synced_payload_before_cache(tmp_path):
    connection = connect_database(tmp_path / "cache.sqlite3")
    initialize_schema(connection)
    cache = RequestCache(connection)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                json={
                    "artistName": "Ado",
                    "trackName": "唱",
                    "plainLyrics": "plain",
                    "syncedLyrics": "[00:01] hidden",
                },
            )
        )
    )
    lyrics = LRCLIBClient(http_client=client, request_cache=cache).get_lyrics(
        LyricsLookup("Ado", "唱")
    )
    assert lyrics.plain_lyrics == "plain"
    assert lyrics.synced_lyrics is None
    assert not lyrics.requires_review
    assert (
        "syncedLyrics"
        not in connection.execute("SELECT payload_json FROM request_cache").fetchone()[
            0
        ]
    )
    connection.close()


def make_mp3(path, lyrics=None):
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Lemon"))
    tags.add(TPE1(encoding=3, text="米津玄師"))
    if lyrics:
        tags.add(USLT(encoding=3, lang="und", text=lyrics))
    tags.save(path)


def test_end_to_end_preview_id3_rename_backup_undo(tmp_path):
    path = tmp_path / "米津玄師 Lemon Official MV.mp3"
    make_mp3(path, "keep me")
    original = path.read_bytes()
    conn = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(conn)
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(),
        history_repository=HistoryRepository(conn),
        backup_folder=tmp_path / "backup",
    )
    (track,) = service.discover([path])
    preview = service.process_track(track)
    assert path.read_bytes() == original
    assert preview.confidence == "High"
    (result,) = service.apply_tracks([preview], ApplySettings())
    assert result.success
    target = tmp_path / "米津玄師 - Lemon.mp3"
    assert read_id3_metadata(target).lyrics.text == "keep me"
    assert (tmp_path / "backup" / (path.name + ".backup")).read_bytes() == original
    assert not list(tmp_path.glob("*.lrc"))
    assert service.undo_last_batch()[0].success
    assert path.exists() and not target.exists()
    assert read_id3_metadata(path) == track.current_metadata
    conn.close()


def test_partial_batch_undo_and_conflict_do_not_change_failed_file(tmp_path):
    path = tmp_path / "米津玄師 Lemon.mp3"
    make_mp3(path)
    conflict = tmp_path / "other.mp3"
    make_mp3(conflict)
    conn = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(conn)
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(),
        history_repository=HistoryRepository(conn),
        backup_folder=tmp_path / "backup",
    )
    first = service.process_track(service.discover([path])[0])
    second = service.process_track(service.discover([conflict])[0])
    original = conflict.read_bytes()
    results = service.apply_tracks([first, second], ApplySettings())
    assert [r.success for r in results] == [True, False]
    assert conflict.read_bytes() == original
    assert service.undo_last_batch()[0].success
    assert path.exists()
    conn.close()


def test_production_import_graph_excludes_old_backends():
    import ast

    root = Path(__file__).resolve().parents[1] / "src"
    pending = ["music_metadata_cleaner.__main__"]
    visited = set()
    forbidden = {
        "music_metadata_cleaner.app.legacy_workflow_service",
        "music_metadata_cleaner.app.audio_identification_service",
        "music_metadata_cleaner.app.fallback_recognition_service",
        "music_metadata_cleaner.app.metadata_enrichment_service",
        "music_metadata_cleaner.providers.acoustid",
        "music_metadata_cleaner.providers.audd",
        "music_metadata_cleaner.providers.musicbrainz",
        "music_metadata_cleaner.providers.youtube",
        "music_metadata_cleaner.audio_segments",
        "music_metadata_cleaner.fingerprinting.fpcalc",
    }
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        assert module not in forbidden
        path = root.joinpath(*module.split(".")).with_suffix(".py")
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("music_metadata_cleaner")
            ):
                pending.append(node.module)
    assert "music_metadata_cleaner.providers.search" in visited
    assert "music_metadata_cleaner.providers.lrclib" in visited


def test_cancel_after_search_does_not_fetch_lyrics():
    token = CancellationToken()

    class CancellingSearch(FakeSearch):
        def search(self, query, count=8):
            token.cancel()
            return super().search(query, count)

    service = MusicCleanerWorkflowService(
        search_provider=CancellingSearch(), lyrics_service=LyricsService(FailSearch())
    )
    result = service.process_track(
        WorkflowTrack(Path("米津玄師 Lemon.mp3"), TrackMetadata()),
        cancellation_token=token,
    )
    assert result.processing_status == "Cancelled"
    assert result.proposed is None


@pytest.mark.parametrize(
    "preserve,overwrite,expected",
    [
        (True, False, "old"),
        (False, False, "old"),
        (False, True, "new"),
        (True, True, "old"),
    ],
)
def test_overwrite_requires_explicit_setting(tmp_path, preserve, overwrite, expected):
    path = tmp_path / "米津玄師 Lemon.mp3"
    make_mp3(path, "old")

    class PlainLyrics:
        def get_lyrics(self, lookup, **kwargs):
            assert (lookup.artist, lookup.title) == ("米津玄師", "Lemon")
            return LyricsResult(source="online", plain_lyrics="new")

    conn = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(conn)
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(),
        lyrics_service=PlainLyrics(),
        preserve_existing_lyrics=preserve,
        overwrite_existing_lyrics=overwrite,
        history_repository=HistoryRepository(conn),
    )
    track = service.process_track(service.discover([path])[0])
    assert service.apply_tracks([track], ApplySettings(rename_file=False))[0].success
    assert read_id3_metadata(path).lyrics.text == expected
    conn.close()


def test_uncertain_lyrics_are_never_written(tmp_path):
    path = tmp_path / "米津玄師 Lemon.mp3"
    make_mp3(path)

    class Mismatch:
        def get_lyrics(self, *args, **kwargs):
            return LyricsResult(
                source="online", plain_lyrics="wrong song", requires_review=True
            )

    conn = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(conn)
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(),
        lyrics_service=Mismatch(),
        history_repository=HistoryRepository(conn),
    )
    track = service.process_track(service.discover([path])[0])
    assert track.lyrics_status == "Not Found"
    assert service.apply_tracks([track], ApplySettings(rename_file=False))[0].success
    assert read_id3_metadata(path).lyrics is None
    conn.close()


def test_mid_write_failure_restores_backup(tmp_path):
    path = tmp_path / "米津玄師 Lemon.mp3"
    make_mp3(path)
    original = path.read_bytes()

    def failing_writer(path, update):
        path.write_bytes(b"failed write")
        raise OSError("disk error")

    conn = connect_database(tmp_path / "history.sqlite3")
    initialize_schema(conn)
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(),
        metadata_writer=failing_writer,
        history_repository=HistoryRepository(conn),
    )
    track = service.process_track(service.discover([path])[0])
    assert not service.apply_tracks([track], ApplySettings())[0].success
    assert path.read_bytes() == original
    conn.close()


def test_rename_never_overwrites_existing_target(tmp_path):
    from music_metadata_cleaner.files.safe_paths import rename_without_overwrite

    source, target = tmp_path / "one.mp3", tmp_path / "two.mp3"
    source.write_bytes(b"original")
    target.write_bytes(b"other")
    with pytest.raises(FileExistsError):
        rename_without_overwrite(source, target)
    assert source.read_bytes() == b"original"
    assert target.read_bytes() == b"other"


def test_benchmark_reports_unknown_truth_without_writes(tmp_path):
    from music_metadata_cleaner.app.search_benchmark import run_benchmark, summarize

    path = tmp_path / "米津玄師 Lemon.mp3"
    make_mp3(path)
    original = path.read_bytes()
    service = MusicCleanerWorkflowService(
        search_provider=FakeSearch(), retrieve_lyrics=False
    )
    rows = run_benchmark(service, [{"path": str(path)}])
    assert rows[0]["correct"] == ""
    assert summarize(rows)["Unverified"] == 1
    assert path.read_bytes() == original
