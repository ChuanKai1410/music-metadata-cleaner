"""Mutagen-based ID3 metadata writer."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TRCK, USLT

from music_metadata_cleaner.domain.models import MetadataUpdate


class LyricsOverwriteError(ValueError):
    """Raised when a write would replace existing lyrics without confirmation."""


def write_id3_metadata(
    path: str | Path,
    update: MetadataUpdate,
    *,
    overwrite_lyrics: bool = False,
) -> None:
    """Write confirmed metadata changes to an MP3 file.

    This function intentionally performs no renaming and never overwrites lyrics unless
    `overwrite_lyrics` is true. Callers are expected to persist original state before
    invoking it in a future apply workflow.
    """

    mp3_path = Path(path)
    if mp3_path.suffix.lower() != ".mp3":
        raise ValueError(f"Refusing to write ID3 metadata to non-MP3 path: {mp3_path}")

    tags = _load_or_create_tags(mp3_path)

    _set_text(tags, "TIT2", TIT2, update.title)
    _set_text(tags, "TPE1", TPE1, update.artist)
    _set_text(tags, "TALB", TALB, update.album)
    _set_text(tags, "TDRC", TDRC, update.release_date)
    _set_text(tags, "TRCK", TRCK, update.track_number)

    if update.cover_art is not None:
        tags.delall("APIC")
        tags.add(
            APIC(
                encoding=3,
                mime=update.cover_art.mime_type,
                type=3,
                desc=update.cover_art.description,
                data=update.cover_art.data,
            )
        )

    if update.lyrics is not None and update.lyrics.has_text:
        if tags.getall("USLT") and not overwrite_lyrics:
            raise LyricsOverwriteError("Existing lyrics require explicit overwrite confirmation.")
        tags.delall("USLT")
        tags.add(
            USLT(
                encoding=3,
                lang=update.lyrics.language,
                desc=update.lyrics.description,
                text=update.lyrics.text or "",
            )
        )

    tags.save(mp3_path, v2_version=3)


def _load_or_create_tags(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def _set_text(tags: ID3, frame_id: str, frame_type: type, value: str | None) -> None:
    if value is None:
        return

    cleaned = value.strip()
    if not cleaned:
        return

    tags.delall(frame_id)
    tags.add(frame_type(encoding=3, text=cleaned))

