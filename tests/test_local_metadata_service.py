from __future__ import annotations

from mutagen.id3 import ID3, TIT2, TPE1

from music_metadata_cleaner.app.local_metadata_service import dry_run_local_metadata


def test_dry_run_local_metadata_reads_tags_and_proposes_filename(tmp_path):
    mp3_path = tmp_path / "messy name.mp3"
    mp3_path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Lemon"))
    tags.add(TPE1(encoding=3, text="米津玄師"))
    tags.save(mp3_path, v2_version=3)

    results = dry_run_local_metadata(tmp_path)

    assert len(results) == 1
    assert results[0].path == mp3_path
    assert results[0].metadata.title == "Lemon"
    assert results[0].metadata.artist == "米津玄師"
    assert results[0].proposed_filename == "米津玄師 - Lemon.mp3"
    assert results[0].proposed_path == tmp_path / "米津玄師 - Lemon.mp3"
    assert results[0].warnings == ()
    assert mp3_path.exists()


def test_dry_run_local_metadata_warns_when_target_exists(tmp_path):
    mp3_path = tmp_path / "messy.mp3"
    target = tmp_path / "Artist - Title.mp3"
    mp3_path.write_bytes(b"")
    target.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Title"))
    tags.add(TPE1(encoding=3, text="Artist"))
    tags.save(mp3_path, v2_version=3)

    results = dry_run_local_metadata(mp3_path)

    assert results[0].proposed_filename == "Artist - Title.mp3"
    assert results[0].warnings == ("Proposed filename already exists; no rename should be applied automatically.",)
    assert mp3_path.exists()
    assert target.exists()


def test_dry_run_local_metadata_warns_when_artist_or_title_missing(tmp_path):
    mp3_path = tmp_path / "missing.mp3"
    mp3_path.write_bytes(b"")

    results = dry_run_local_metadata(mp3_path)

    assert results[0].proposed_filename is None
    assert results[0].proposed_path is None
    assert results[0].warnings == ("Missing artist or title; filename cannot be proposed.",)
    assert mp3_path.exists()
