from __future__ import annotations

from music_metadata_cleaner.domain.models import CandidateRecording, MusicBrainzMetadata, MusicBrainzIdentifiers, TrackMetadata, YouTubeCandidate
from music_metadata_cleaner.domain.youtube import (
    build_youtube_search_queries,
    clean_youtube_search_text,
    detect_version_hints,
    infer_artist_title,
    rank_youtube_candidates,
    score_duration_match,
    score_youtube_candidate,
)


def test_clean_youtube_search_text_removes_common_upload_noise():
    assert clean_youtube_search_text("米津玄師 Lemon MV FULL HD Official Music Video 1080p.mp3") == "米津玄師 lemon"


def test_build_youtube_search_queries_prefers_confirmed_identity_before_filename():
    queries = build_youtube_search_queries(
        filename="Lemon MV FULL HD.mp3",
        metadata=TrackMetadata(artist="Old Artist", title="Old Title"),
        candidate=CandidateRecording("rec", "Fallback", "Fallback Song", 255, 0.8),
        musicbrainz=MusicBrainzMetadata(
            artist="米津玄師",
            title="Lemon",
            album=None,
            release_date=None,
            track_number=None,
            duration=255,
            identifiers=MusicBrainzIdentifiers(recording_id="mbid"),
        ),
    )

    assert queries[0] == "米津玄師 lemon"
    assert "lemon" in queries


def test_duration_scoring_uses_tolerance_bands():
    assert score_duration_match(255, 256)[0] == 28
    assert score_duration_match(255, 260)[0] == 23
    assert score_duration_match(255, 265)[0] == 15
    assert score_duration_match(255, 274)[0] == 7
    assert score_duration_match(255, 400)[0] < 0


def test_version_detection_and_penalty_reduces_cover_when_local_does_not_expect_cover():
    candidate = score_youtube_candidate(
        YouTubeCandidate(
            video_id="abc",
            video_url="https://www.youtube.com/watch?v=abc",
            title="米津玄師 - Lemon Cover",
            channel_name="Fan Channel",
            duration_seconds=255,
        ),
        expected_artist="米津玄師",
        expected_title="Lemon",
        filename="Lemon.mp3",
        id3_metadata=TrackMetadata(),
        expected_duration=255,
    )

    assert "cover" in detect_version_hints(candidate.title)
    assert any("Version hint differs" in reason for reason in candidate.score_breakdown)


def test_rank_youtube_candidates_prefers_title_artist_duration_match():
    candidates = [
        YouTubeCandidate("bad", "url", "Lemon Cover", channel_name="Fan", duration_seconds=255),
        YouTubeCandidate("good", "url", "米津玄師 - Lemon", channel_name="Kenshi Yonezu 米津玄師", duration_seconds=255),
    ]

    ranked = rank_youtube_candidates(
        candidates,
        expected_artist="米津玄師",
        expected_title="Lemon",
        filename="Lemon.mp3",
        id3_metadata=TrackMetadata(),
        expected_duration=255,
    )

    assert ranked[0].video_id == "good"
    assert ranked[0].score >= 85


def test_infer_artist_title_from_common_video_title_separator():
    assert infer_artist_title("米津玄師 - Lemon Official Video") == ("米津玄師", "Lemon")
