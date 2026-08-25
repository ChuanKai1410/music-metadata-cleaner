from __future__ import annotations

import pytest
from mutagen.id3 import APIC, ID3, TALB, TDRC, TIT2, TPE1, TRCK, USLT

from music_metadata_cleaner.domain.models import CoverArt, Lyrics, MetadataUpdate
from music_metadata_cleaner.id3.reader import read_id3_metadata
from music_metadata_cleaner.id3.writer import LyricsOverwriteError, write_id3_metadata


def _write_test_tags(path):
    path.write_bytes(b"")
    tags = ID3()
    tags.add(TIT2(encoding=3, text="Lemon"))
    tags.add(TPE1(encoding=3, text="米津玄師"))
    tags.add(TALB(encoding=3, text="STRAY SHEEP"))
    tags.add(TDRC(encoding=3, text="2018-03-14"))
    tags.add(TRCK(encoding=3, text="8/15"))
    tags.add(USLT(encoding=3, lang="jpn", desc="", text="夢ならばどれほどよかったでしょう"))
    tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="cover", data=b"cover-bytes"))
    tags.save(path, v2_version=3)


def test_read_id3_metadata_supports_primary_fields_cover_and_lyrics(tmp_path):
    mp3_path = tmp_path / "lemon.mp3"
    _write_test_tags(mp3_path)

    metadata = read_id3_metadata(mp3_path)

    assert metadata.title == "Lemon"
    assert metadata.artist == "米津玄師"
    assert metadata.album == "STRAY SHEEP"
    assert metadata.release_date == "2018-03-14"
    assert metadata.track_number == "8/15"
    assert metadata.cover_art is not None
    assert metadata.cover_art.mime_type == "image/jpeg"
    assert metadata.cover_art.data == b"cover-bytes"
    assert metadata.lyrics is not None
    assert metadata.lyrics.language == "jpn"
    assert metadata.lyrics.text == "夢ならばどれほどよかったでしょう"


def test_read_id3_metadata_returns_empty_metadata_when_no_id3_header(tmp_path):
    mp3_path = tmp_path / "empty.mp3"
    mp3_path.write_bytes(b"not really an mp3")

    metadata = read_id3_metadata(mp3_path)

    assert metadata.title is None
    assert metadata.artist is None
    assert metadata.lyrics is None


def test_write_id3_metadata_updates_supported_fields(tmp_path):
    mp3_path = tmp_path / "new.mp3"
    mp3_path.write_bytes(b"")

    write_id3_metadata(
        mp3_path,
        MetadataUpdate(
            title="Lemon",
            artist="米津玄師",
            album="STRAY SHEEP",
            release_date="2018",
            track_number="8",
            cover_art=CoverArt(mime_type="image/png", data=b"png", description="cover"),
            lyrics=Lyrics(text="plain lyrics", language="eng"),
        ),
    )

    metadata = read_id3_metadata(mp3_path)

    assert metadata.title == "Lemon"
    assert metadata.artist == "米津玄師"
    assert metadata.album == "STRAY SHEEP"
    assert metadata.release_date == "2018"
    assert metadata.track_number == "8"
    assert metadata.cover_art is not None
    assert metadata.cover_art.mime_type == "image/png"
    assert metadata.lyrics is not None
    assert metadata.lyrics.text == "plain lyrics"


def test_write_id3_metadata_preserves_existing_lyrics_without_confirmation(tmp_path):
    mp3_path = tmp_path / "lyrics.mp3"
    _write_test_tags(mp3_path)

    with pytest.raises(LyricsOverwriteError):
        write_id3_metadata(mp3_path, MetadataUpdate(lyrics=Lyrics(text="replacement")))

    metadata = read_id3_metadata(mp3_path)
    assert metadata.lyrics is not None
    assert metadata.lyrics.text == "夢ならばどれほどよかったでしょう"


def test_write_id3_metadata_can_replace_lyrics_with_confirmation(tmp_path):
    mp3_path = tmp_path / "lyrics.mp3"
    _write_test_tags(mp3_path)

    write_id3_metadata(
        mp3_path,
        MetadataUpdate(lyrics=Lyrics(text="replacement", language="eng")),
        overwrite_lyrics=True,
    )

    metadata = read_id3_metadata(mp3_path)
    assert metadata.lyrics is not None
    assert metadata.lyrics.text == "replacement"
    assert metadata.lyrics.language == "eng"

