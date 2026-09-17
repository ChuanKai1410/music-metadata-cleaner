# Requirements — Phase 9

The application is a Windows/Linux local MP3 cleaner using PySide6, Mutagen, httpx and SQLite.

## Identity

- Filename and useful existing ID3 are the only identification input.
- Preserve Unicode; normalize punctuation and collaboration separators only for comparison.
- Remove clear downloader prefixes and video-quality wrappers, preserving legitimate title words and version markers.
- Query the configured SearXNG `/search` endpoint with `q` and `format=json`; use no search API key.
- Maximum two first-page queries per track; stop early when evidence is strong.
- Group supported Artist + Title candidates, count independent publisher domains, weight music sources, and lower confidence for conflicts.
- Display High / Medium / Low; show internal score and reasoning in evidence diagnostics.
- Insufficient text yields Insufficient Information and no proposed identity. Manual Search uses the same pipeline.
- Candidate selection explicitly confirms identity before uncertain changes can apply.

## Lyrics and files

- LRCLIB plainLyrics only, validated against the resolved artist and title.
- Preserve existing USLT lyrics by default. Missing lyrics are nonfatal; mismatched lyrics are not written.
- Preview is read-only. Apply requires confirmation, SQLite history and optional backup (on by default).
- Use `{Artist} - {Title}.mp3`, keep the original folder, reject conflicts and support undo of applied files in partial batches.
- Retain existing history and legacy config paths; use platform-appropriate defaults for new installations.

## UI and settings

Six columns: File, Artist, Title, Confidence, Lyrics, Status. Details show current/proposed tags, search evidence, candidates, query input and plain-lyrics status.

Settings: General, Search, Lyrics, Files & Safety, Advanced. Search settings are SearXNG URL, maximum results (default 8), timeout (default 10 seconds), automatic search and Test Connection. Advanced includes cache TTL, clear search cache, logs and diagnostics location.

No production audio recognition, dedicated YouTube API verification, paid search APIs, LLMs, synchronized lyrics or LRC export.
