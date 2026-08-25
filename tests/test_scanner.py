from __future__ import annotations

from music_metadata_cleaner.files.scanner import discover_mp3_files


def test_discover_mp3_files_accepts_single_mp3_file(tmp_path):
    mp3_path = tmp_path / "Song.MP3"
    mp3_path.write_bytes(b"")

    assert discover_mp3_files(mp3_path) == [mp3_path]


def test_discover_mp3_files_recurses_folders_and_ignores_non_mp3(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    first = tmp_path / "a.mp3"
    second = nested / "b.Mp3"
    ignored = nested / "notes.txt"
    first.write_bytes(b"")
    second.write_bytes(b"")
    ignored.write_text("not music")

    assert discover_mp3_files(tmp_path) == [first, second]


def test_discover_mp3_files_returns_empty_for_non_mp3_file(tmp_path):
    text_path = tmp_path / "notes.txt"
    text_path.write_text("not music")

    assert discover_mp3_files(text_path) == []

