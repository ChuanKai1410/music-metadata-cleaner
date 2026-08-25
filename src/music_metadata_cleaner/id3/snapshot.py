"""Full supported ID3 snapshot restore helpers."""

from __future__ import annotations

from pathlib import Path

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1, TRCK, USLT

from music_metadata_cleaner.domain.models import TrackMetadata


SUPPORTED_FRAME_IDS = ("TIT2", "TPE1", "TALB", "TDRC", "TYER", "TRCK", "APIC", "USLT")


def restore_id3_metadata(path: str | Path, metadata: TrackMetadata) -> None:
    """Replace supported ID3 frames with a stored metadata snapshot."""

    mp3_path = Path(path)
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        tags = ID3()

    for frame_id in SUPPORTED_FRAME_IDS:
        tags.delall(frame_id)

    _add_text(tags, TIT2, metadata.title)
    _add_text(tags, TPE1, metadata.artist)
    _add_text(tags, TALB, metadata.album)
    _add_text(tags, TDRC, metadata.release_date)
    _add_text(tags, TRCK, metadata.track_number)

    if metadata.cover_art is not None:
        tags.add(
            APIC(
                encoding=3,
                mime=metadata.cover_art.mime_type,
                type=3,
                desc=metadata.cover_art.description,
                data=metadata.cover_art.data,
            )
        )

    if metadata.lyrics is not None and metadata.lyrics.has_text:
        tags.add(
            USLT(
                encoding=3,
                lang=metadata.lyrics.language,
                desc=metadata.lyrics.description,
                text=metadata.lyrics.text or "",
            )
        )

    tags.save(mp3_path, v2_version=3)


def _add_text(tags: ID3, frame_type: type, value: str | None) -> None:
    if value and value.strip():
        tags.add(frame_type(encoding=3, text=value.strip()))

