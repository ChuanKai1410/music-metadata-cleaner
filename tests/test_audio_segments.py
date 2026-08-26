from __future__ import annotations

from music_metadata_cleaner.audio_segments import (
    build_ffmpeg_extract_command,
    check_ffmpeg_available,
    resolve_ffmpeg_executable,
    segment_start_times,
)


def test_segment_start_times_uses_middle_sections_for_long_tracks():
    assert segment_start_times(240, max_segments=3, clip_seconds=15) == [53, 113, 173]


def test_segment_start_times_handles_short_tracks():
    assert segment_start_times(10, max_segments=3, clip_seconds=15) == [0]


def test_build_ffmpeg_extract_command_is_non_destructive(tmp_path):
    source = tmp_path / "song.mp3"
    output = tmp_path / "clip.mp3"

    command = build_ffmpeg_extract_command(
        ffmpeg_executable="ffmpeg",
        source_path=source,
        output_path=output,
        start_seconds=60,
        clip_seconds=15,
    )

    assert command[:2] == ["ffmpeg", "-y"]
    assert "-ss" in command
    assert str(source) in command
    assert str(output) == command[-1]


def test_resolve_ffmpeg_accepts_configured_bin_directory(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "ffmpeg.exe"
    executable.write_text("", encoding="utf-8")

    assert resolve_ffmpeg_executable(bin_dir) == str(executable)


def test_check_ffmpeg_available_reports_invalid_path(tmp_path):
    available, resolved, status = check_ffmpeg_available(tmp_path / "missing" / "ffmpeg.exe")

    assert available is False
    assert resolved.endswith("ffmpeg.exe")
    assert status == "FFMPEG_INVALID_PATH"
