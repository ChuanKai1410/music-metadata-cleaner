"""Untrusted filename fragments for user selection, never automatic identities."""

from dataclasses import dataclass
import re
from music_metadata_cleaner.domain.search import clean_filename, normalized


@dataclass(frozen=True)
class ManualOptions:
    artists: tuple[str, ...]
    titles: tuple[str, ...]


def manual_options(filename, metadata, candidates=(), proposed=None):
    cleaned = clean_filename(filename)
    # These extractions only populate editable controls. Quoted tails and
    # unseparated CJK text cannot safely establish automatic identity.
    compact = re.split(r"[『「]", cleaned, maxsplit=1)[0].strip()
    compact = re.sub(
        r"【(?:動態歌詞|动态歌词|Lyrics).*?】", "", compact, flags=re.I
    ).strip()
    parts = re.split(
        r"\s+[-–—|_]\s+|\s{2,}|(?<=[\u3400-\u9fff])[-–—]|[-–—](?=[\u3400-\u9fff])",
        compact,
    )
    if len(parts) == 1:
        # Offer word-boundary prefix/suffix choices without guessing which is artist.
        words = compact.split()
        parts = [
            piece
            for i in range(1, min(len(words), 9))
            for piece in (" ".join(words[:i]), " ".join(words[i:]))
        ]
    fragments = [p.strip(" -_") for p in parts if p.strip(" -_")]

    def unique(values):
        seen = set()
        result = []
        for value in values:
            if value and normalized(value) not in seen:
                seen.add(normalized(value))
                result.append(value)
        return tuple(result[:30])

    return ManualOptions(
        unique(
            [
                getattr(proposed, "artist", None),
                metadata.artist,
                *(c.artist for c in candidates),
                *fragments,
                compact,
            ]
        ),
        unique(
            [
                getattr(proposed, "title", None),
                metadata.title,
                *(c.title for c in candidates),
                *fragments,
                compact,
            ]
        ),
    )
