from __future__ import annotations

from music_metadata_cleaner.files.safe_paths import (
    generate_mp3_filename,
    propose_mp3_path,
    sanitize_filename_component,
)


def test_sanitize_filename_component_removes_windows_invalid_characters():
    assert sanitize_filename_component('A/B:C*D?"E<F>G|') == "A B C D E F G"


def test_sanitize_filename_component_preserves_original_language_text():
    assert generate_mp3_filename("米津玄師", "Lemon") == "米津玄師 - Lemon.mp3"


def test_sanitize_filename_component_handles_reserved_names():
    assert sanitize_filename_component("CON") == "CON_"


def test_propose_mp3_path_uses_current_parent_without_renaming(tmp_path):
    current = tmp_path / "messy.mp3"

    assert propose_mp3_path(current, "Artist", "Title") == tmp_path / "Artist - Title.mp3"


def test_propose_mp3_path_requires_artist_and_title(tmp_path):
    current = tmp_path / "messy.mp3"

    assert propose_mp3_path(current, "", "Title") is None
    assert propose_mp3_path(current, "Artist", None) is None

