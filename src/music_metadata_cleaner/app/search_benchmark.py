"""Read-only real-file benchmark. Requires a supplied endpoint and sample manifest."""

from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
from music_metadata_cleaner.app.workflow_service import MusicCleanerWorkflowService
from music_metadata_cleaner.app.lyrics_service import LyricsService
from music_metadata_cleaner.domain.search import artist_key, normalized
from music_metadata_cleaner.providers.search import SearXNGProvider
from music_metadata_cleaner.providers.lrclib import LRCLIBClient
from music_metadata_cleaner.db.connection import connect_database
from music_metadata_cleaner.db.request_cache import RequestCache
from music_metadata_cleaner.db.schema import initialize_schema

FIELDS = (
    "original_filename",
    "cleaned_filename",
    "search_queries",
    "search_result_count",
    "resolved_artist",
    "resolved_title",
    "confidence",
    "supporting_sources",
    "lyrics_status",
    "status",
    "expected_artist",
    "expected_title",
    "correct",
)


def run_benchmark(service, samples):
    rows = []
    for sample in samples:
        tracks = service.discover([sample["path"]])
        if len(tracks) != 1:
            raise ValueError("Each manifest path must identify exactly one MP3 file.")
        track = service.process_track(tracks[0])
        proposed = track.proposed
        artist, title = (
            (proposed.artist or "", proposed.title or "") if proposed else ("", "")
        )
        expected_artist, expected_title = sample.get("expected_artist", ""), sample.get(
            "expected_title", ""
        )
        correct = ""
        if expected_artist and expected_title and proposed:
            correct = (
                "Correct"
                if artist_key(artist) == artist_key(expected_artist)
                and normalized(title) == normalized(expected_title)
                else "Incorrect"
            )
        rows.append(
            dict(
                zip(
                    FIELDS,
                    (
                        track.path.name,
                        track.cleaned_filename,
                        " | ".join(track.search_queries),
                        len(track.search_results),
                        artist,
                        title,
                        track.confidence,
                        (
                            " | ".join(
                                sorted(
                                    {r.domain for r in track.resolved_identity.evidence}
                                )
                            )
                            if track.resolved_identity
                            else ""
                        ),
                        track.lyrics_status,
                        track.processing_status,
                        expected_artist,
                        expected_title,
                        correct,
                    ),
                )
            )
        )
    return rows


def summarize(rows):
    return {
        "Total": len(rows),
        "Correct High": sum(
            r["correct"] == "Correct" and r["confidence"] == "High" for r in rows
        ),
        "Correct Medium": sum(
            r["correct"] == "Correct" and r["confidence"] == "Medium" for r in rows
        ),
        "Incorrect": sum(r["correct"] == "Incorrect" for r in rows),
        "Insufficient Information": sum(
            r["status"] == "Insufficient Information" for r in rows
        ),
        "Search Failed": sum(r["status"] == "Search Failed" for r in rows),
        "Unverified": sum(not r["correct"] for r in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="CSV: path,expected_artist,expected_title",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.manifest.open(encoding="utf-8-sig", newline="") as stream:
        samples = list(csv.DictReader(stream))
    for sample in samples:
        path = Path(sample["path"])
        sample["path"] = str(
            path if path.is_absolute() else args.manifest.parent / path
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_database(args.output.with_suffix(".cache.sqlite3"))
    initialize_schema(connection)
    cache = RequestCache(connection)
    service = MusicCleanerWorkflowService(
        search_provider=SearXNGProvider(args.endpoint, request_cache=cache),
        lyrics_service=LyricsService(LRCLIBClient(request_cache=cache)),
    )
    try:
        rows = run_benchmark(service, samples)
        with args.output.open("x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        print(json.dumps(summarize(rows), indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
