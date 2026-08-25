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
- Rate limiting, retries, timeouts, and provider-specific response mapping.

Provider clients should return domain-friendly DTOs or mapper outputs, not UI objects.

Suggested future modules:

- `acoustid.py`
- `musicbrainz.py`
- `lrclib.py`
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
-> providers MusicBrainz
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

Recommended thresholds:

- `90-100`: eligible for auto-selection.
- `70-89`: user review required.
- `<70`: no automatic apply.

The scoring implementation should produce both a numeric score and explainable evidence so users can understand why a match was suggested.

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

