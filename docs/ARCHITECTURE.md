# Architecture

## Overview

Music Metadata Cleaner should use a layered architecture that keeps UI, orchestration, domain rules, external providers, ID3 operations, filesystem operations, fingerprinting, and persistence independently testable.

```text
src/music_metadata_cleaner/
  app/              Application orchestration and workflows
  db/               SQLite persistence and migrations
  domain/           Plain models, rules, confidence scoring
  files/            Scanning, filename parsing, safe rename planning
  fingerprinting/   Chromaprint/fpcalc integration
  id3/              Mutagen-based ID3 read/write adapters
  providers/        AcoustID, MusicBrainz, LRCLIB clients
  ui/               PySide6 user interface
```

The UI should call application services. Application services coordinate domain rules and adapters. Provider clients, ID3 adapters, database repositories, and filesystem services should be replaceable in tests.

## Layer Responsibilities

### UI Layer

Package: `music_metadata_cleaner.ui`

Responsibilities:

- PySide6 windows, widgets, dialogs, and view models.
- Folder selection and user confirmation flows.
- Preview tables for proposed metadata, lyrics, artwork, and rename changes.
- Manual review screens for medium and low-confidence matches.
- Progress reporting and cancellation controls.

The UI must not directly call AcoustID, MusicBrainz, LRCLIB, Mutagen, or SQLite APIs.

### Application Layer

Package: `music_metadata_cleaner.app`

Responsibilities:

- Coordinate scan, identify, enrich, preview, apply, and undo workflows.
- Enforce no-write behavior during scanning.
- Build proposed changes from provider results and domain rules.
- Apply batches transactionally where possible.
- Ensure original state is persisted before modifications.
- Convert provider and filesystem failures into user-visible outcomes.

Suggested future modules:

- `scan_service.py`
- `match_service.py`
- `preview_service.py`
- `apply_service.py`
- `undo_service.py`

### Domain Layer

Package: `music_metadata_cleaner.domain`

Responsibilities:

- Plain data models for tracks, recordings, metadata, lyrics, artwork, changes, batches, and confidence evidence.
- Confidence scoring rules.
- Match decision thresholds.
- Filename output policy.
- Lyrics overwrite policy.

This layer should avoid PySide6, Mutagen, httpx, subprocess, and SQLite imports.

Suggested future modules:

- `models.py`
- `confidence.py`
- `policies.py`
- `changes.py`

### Providers Layer

Package: `music_metadata_cleaner.providers`

Responsibilities:

- AcoustID client for fingerprint lookup.
- MusicBrainz client for canonical recording, artist, release, and artwork metadata.
- LRCLIB client for plain and synchronized lyrics.
- YouTube Data API client for secondary song-identification evidence.
- AudD client for fallback audio recognition from short temporary clips.
- Rate limiting, retries, timeouts, and provider-specific response mapping.

Provider clients should return domain-friendly DTOs or mapper outputs, not UI objects.

Suggested future modules:

- `acoustid.py`
- `musicbrainz.py`
- `lrclib.py`
- `youtube.py`
- `errors.py`

### Fingerprinting Layer

Package: `music_metadata_cleaner.fingerprinting`

Responsibilities:

- Locate and validate `fpcalc`.
- Execute Chromaprint fingerprinting.
- Parse duration and fingerprint output.
- Report missing binary, unsupported file, timeout, and subprocess errors.

Suggested future modules:

- `fpcalc.py`
- `errors.py`

### ID3 Layer

Package: `music_metadata_cleaner.id3`

Responsibilities:

- Read MP3 ID3 metadata through Mutagen.
- Map ID3 frames to domain metadata.
- Prepare write plans for tags, lyrics, and artwork.
- Apply confirmed metadata changes.
- Preserve existing lyrics unless replacement is confirmed.

Suggested future modules:

- `reader.py`
- `writer.py`
- `frames.py`
- `lyrics.py`

### Files Layer

Package: `music_metadata_cleaner.files`

Responsibilities:

- Discover MP3 files.
- Parse noisy filenames.
- Build safe target filenames.
- Sanitize invalid path characters.
- Detect duplicate target paths.
- Plan conflict-free renames.
- Execute confirmed renames without overwriting existing files.

Suggested future modules:

- `scanner.py`
- `filename_parser.py`
- `rename_planner.py`
- `safe_paths.py`

### Database Layer

Package: `music_metadata_cleaner.db`

Responsibilities:

- SQLite connection management.
- Schema creation and migrations.
- Metadata cache.
- Provider result cache.
- Processing history.
- Batch history.
- Undo records.

Suggested future modules:

- `connection.py`
- `schema.py`
- `repositories.py`
- `migrations/`

## Data Flow

```text
UI
-> app scan service
-> files scanner
-> id3 reader
-> files filename parser
-> fingerprinting fpcalc
-> providers AcoustID
-> app fallback recognition service with temporary ffmpeg clips when AcoustID is weak/incomplete/no-match
-> providers AudD when configured
-> providers MusicBrainz
-> providers YouTube for medium/low/no-match verification when configured
-> providers LRCLIB
-> domain confidence scoring
-> app preview service
-> UI preview/manual review
-> app apply service
-> db history
-> id3 writer
-> files rename planner/executor
```

## Confidence Strategy

The confidence score should combine evidence from:

- Audio fingerprint match quality.
- Duration similarity.
- Existing ID3 artist/title similarity.
- Filename artist/title similarity.
- MusicBrainz recording identity.
- Release and track metadata consistency.
- YouTube video title, channel, duration, and version compatibility when YouTube verification is used.
- AudD segment consensus when fallback recognition is used.

Recommended thresholds:

- `90-100`: eligible for auto-selection.
- `70-89`: user review required.
- `<70`: no automatic apply.

The scoring implementation should produce both a numeric score and explainable evidence so users can understand why a match was suggested.

AcoustID remains the primary audio fingerprint signal. An AcoustID response with a score but no usable artist/title is treated as incomplete identity evidence and must not be promoted to a ready-to-apply metadata proposal. Fallback recognition can supply artist/title evidence, but the workflow still marks weak or conflicting segment consensus for manual review.

## Fallback Audio Recognition Strategy

AudD fallback recognition is optional and configured through `AUDD_API_TOKEN` plus `MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED=true`.

The workflow is:

```text
AcoustID high-confidence usable identity
-> skip AudD by default

AcoustID incomplete, low-confidence, or no match
-> extract temporary audio clips with ffmpeg
-> send clips progressively to AudD
-> stop early when two strong matching segments agree
-> build a consensus recognition result
-> enrich/verify through the rest of the pipeline where possible
```

The extractor samples around 25%, 50%, and 75% of the track for long files, adapting for short tracks. It creates collision-safe files in the OS temporary directory, never modifies the source MP3, and deletes clips after success or failure where possible.

The AudD provider only receives these short clips. API tokens are read from configuration, never hardcoded, and must not be written to logs or exception text.

## YouTube Evidence Strategy

YouTube is a secondary verification and fallback source. It must not replace Chromaprint, AcoustID, MusicBrainz, ID3 tags, or filename analysis. Audio fingerprint evidence remains the strongest signal.

The application cannot guarantee recovery of the exact original YouTube video because third-party MP3 download sites generally do not preserve the source URL, video ID, or `yt-dlp` metadata. Phase 8 therefore searches YouTube using cleaned identity evidence:

- MusicBrainz artist/title when available.
- AcoustID candidate artist/title.
- Existing ID3 artist/title.
- A conservatively cleaned filename.

The provider uses the official YouTube Data API v3 only:

- `search.list` returns a small set of video IDs.
- `videos.list` retrieves batched details including duration.
- Results are normalized into `YouTubeCandidate` domain models.
- Provider payloads are cached through the existing SQLite request cache.

YouTube searches are quota-aware:

- High-confidence existing matches skip YouTube by default.
- Medium-confidence matches can use YouTube as verification.
- Low-confidence or no-match tracks can use YouTube as fallback discovery.
- `MUSIC_METADATA_CLEANER_ALWAYS_USE_YOUTUBE_VERIFICATION=true` enables verification even for high-confidence tracks.

The YouTube scoring helper considers title similarity, artist/channel similarity, duration tolerance, official-source hints, and version compatibility. YouTube-only fallback proposals are kept review-required by design.

The workflow records diagnostic YouTube states such as not configured, empty query, searching, matched, no results, candidates rejected, API error, and quota/rate-limit failures. User-facing text is concise, while logs keep enough non-secret context to explain why verification did or did not run.

## Transaction and Undo Strategy

Before applying a batch:

1. Record original filename and ID3 metadata in SQLite.
2. Record proposed changes and target paths.
3. Check all rename conflicts.
4. Apply tag changes.
5. Export `.lrc` files if confirmed.
6. Rename files.
7. Mark the batch as applied.

Undo Last Batch should use stored original metadata and paths to restore the previous state where possible. If filesystem state has changed since the batch was applied, undo should stop and show a recoverable error instead of guessing.

## Testability

The architecture should support tests that replace:

- HTTP clients with mocked responses.
- `fpcalc` execution with fixture outputs.
- Filesystem operations with temporary directories.
- SQLite with temporary databases.
- ID3 adapters with test doubles for orchestration tests.

Domain scoring, filename parsing, rename planning, and lyrics overwrite policy should be unit-tested without network or GUI dependencies.
