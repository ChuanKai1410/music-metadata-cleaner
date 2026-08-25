"""Mutagen-based ID3 metadata reader."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, SYLT, TALB, TDRC, TIT2, TPE1, TRCK, TYER, USLT

from music_metadata_cleaner.domain.models import CoverArt, Lyrics, TrackMetadata


def read_id3_metadata(path: str | Path) -> TrackMetadata:
    """Read supported ID3 metadata from an MP3 file."""

    mp3_path = Path(path)
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        return TrackMetadata()

    cover = _first_frame(tags, APIC)
    plain_lyrics = _first_frame(tags, USLT)
    synchronized_lyrics = _first_frame(tags, SYLT)

    return TrackMetadata(
        title=_text(tags, TIT2),
        artist=_text(tags, TPE1),
        album=_text(tags, TALB),
        release_date=_release_date(tags),
        track_number=_text(tags, TRCK),
        cover_art=(
            CoverArt(mime_type=cover.mime, data=cover.data, description=cover.desc or "")
            if cover is not None
            else None
        ),
        lyrics=_lyrics(plain_lyrics, synchronized_lyrics),
    )


def _first_frame(tags: ID3, frame_type: type) -> object | None:
    for frame in tags.values():
        if isinstance(frame, frame_type):
            return frame
    return None


def _text(tags: ID3, frame_type: type) -> str | None:
    frame = _first_frame(tags, frame_type)
    if frame is None:
        return None

    values = getattr(frame, "text", None)
    if not values:
        return None

    text = str(values[0]).strip()
    return text or None


def _release_date(tags: ID3) -> str | None:
    return _text(tags, TDRC) or _text(tags, TYER)


def _lyrics(plain_lyrics: USLT | None, synchronized_lyrics: SYLT | None) -> Lyrics | None:
    if plain_lyrics is None and synchronized_lyrics is None:
        return None

    if plain_lyrics is not None:
        text = plain_lyrics.text.strip() or None
        language = plain_lyrics.lang or "und"
        description = plain_lyrics.desc or ""
    else:
        text = None
        language = synchronized_lyrics.lang or "und"
        description = synchronized_lyrics.desc or ""

    return Lyrics(
        text=text,
        language=language,
        description=description,
        synchronized=synchronized_lyrics is not None,
    )

