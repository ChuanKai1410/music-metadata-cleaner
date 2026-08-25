"""JSON-safe metadata serialization for history and undo."""

from __future__ import annotations

import base64
from typing import Any

from music_metadata_cleaner.domain.models import CoverArt, Lyrics, MetadataUpdate, TrackMetadata


def metadata_to_dict(metadata: TrackMetadata | MetadataUpdate) -> dict[str, Any]:
    cover_art = metadata.cover_art
    lyrics = metadata.lyrics
    return {
        "title": metadata.title,
        "artist": metadata.artist,
        "album": metadata.album,
        "release_date": metadata.release_date,
        "track_number": metadata.track_number,
        "cover_art": (
            {
                "mime_type": cover_art.mime_type,
                "description": cover_art.description,
                "data": base64.b64encode(cover_art.data).decode("ascii"),
            }
            if cover_art is not None
            else None
        ),
        "lyrics": (
            {
                "text": lyrics.text,
                "language": lyrics.language,
                "description": lyrics.description,
                "synchronized": lyrics.synchronized,
            }
            if lyrics is not None
            else None
        ),
    }


def metadata_from_dict(payload: dict[str, Any]) -> TrackMetadata:
    cover_payload = payload.get("cover_art")
    lyrics_payload = payload.get("lyrics")
    return TrackMetadata(
        title=payload.get("title"),
        artist=payload.get("artist"),
        album=payload.get("album"),
        release_date=payload.get("release_date"),
        track_number=payload.get("track_number"),
        cover_art=(
            CoverArt(
                mime_type=str(cover_payload.get("mime_type") or "application/octet-stream"),
                description=str(cover_payload.get("description") or ""),
                data=base64.b64decode(str(cover_payload.get("data") or "")),
            )
            if isinstance(cover_payload, dict)
            else None
        ),
        lyrics=(
            Lyrics(
                text=lyrics_payload.get("text"),
                language=str(lyrics_payload.get("language") or "und"),
                description=str(lyrics_payload.get("description") or ""),
                synchronized=bool(lyrics_payload.get("synchronized")),
            )
            if isinstance(lyrics_payload, dict)
            else None
        ),
    )

