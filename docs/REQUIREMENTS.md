# Current product requirements

[Documentation index](README.md) · [User guide](USER_GUIDE.md)

The application is a Windows/Linux local MP3 cleaner using PySide6, Mutagen, httpx and SQLite.

## Identity

- Automatic identification uses filename and useful existing ID3 as textual input. Explicit manual search keywords can supplement them; the app never listens to the MP3.
- Preserve Unicode; normalize punctuation and collaboration separators only for comparison.
- Remove clear downloader prefixes and video-quality wrappers, preserving legitimate title words and version markers.
- Query the configured SearXNG `/search` endpoint with `q` and `format=json`; use no search API key.
- Maximum two first-page queries per track; stop early when evidence is strong.
- Group supported Artist + Title candidates, count independent publisher domains, weight music sources, and lower confidence for conflicts.
- Display High / Medium / Low; show internal score and reasoning in evidence diagnostics.
- Insufficient text yields Insufficient Information and no proposed identity. Manual Search uses the same pipeline.
- Candidate selection explicitly confirms identity before uncertain changes can apply.
- Manual editing offers editable Artist/Title dropdowns, filename-fragment suggestions, swapping, and free text. Save Preview stages a user-confirmed identity without inventing a High score.
- Identity confidence excludes lyrics entirely; manual completion is separate from automatic resolution accuracy.

## Lyrics and files

- LRCLIB plainLyrics only, validated against the resolved artist and title.
- Allow manual plain lyrics with explicit per-file permission to replace existing lyrics. ID3 writing must be enabled.
- Preserve existing USLT lyrics by default. Missing lyrics are nonfatal; mismatched lyrics are not written.
- Preview is read-only. Apply requires confirmation, SQLite history and optional backup (on by default).
- Use `{Artist} - {Title}.mp3`, keep the original folder, reject conflicts and support undo of applied files in partial batches.
- Retain existing history and legacy config paths; use platform-appropriate defaults for new installations.

## UI and settings

Six columns: File, Artist, Title, Confidence, Lyrics, Status. Details show current/proposed tags, search evidence, candidates, query input and plain-lyrics status.

The UI uses a shared neutral dark QSS theme, system fonts, readable keyboard focus, a resizable splitter, and contextual review controls. Scan & Preview is the single all-track search/preview entry point. Apply Selected and Apply All High Confidence remain distinct and confirmed. Logs are hidden by default; evidence/history use scrollable read-only dialogs. Remove, Clear, and Remove Applied Rows only affect the list.

Settings: General, Search, Lyrics, Files & Safety, Advanced. Search settings are SearXNG URL, maximum results (default 8), timeout (default 10 seconds), automatic search and Test Connection. Advanced includes cache TTL, clear search cache, logs and diagnostics location.

No production audio recognition, dedicated YouTube API verification, paid search APIs, LLMs, synchronized lyrics or LRC export.

## Validation status

The latest UI-pass snapshot recorded 203 passing tests (15 GUI cases), including 125%/150% GUI scaling checks. Native Linux UI/package validation remains pending. The [live 15-song baseline](SEARCH_BENCHMARK.md) is complete but lacks independent ground-truth labels; no 99% accuracy claim is supported.
