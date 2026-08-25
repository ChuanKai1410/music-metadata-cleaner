# AGENTS.md

## Project Intent

Music Metadata Cleaner is a local-first desktop application for safely cleaning MP3 metadata. It scans local files, identifies songs through metadata, filenames, and Chromaprint fingerprints, retrieves canonical metadata and lyrics from online providers, previews proposed changes, and only modifies files after explicit user confirmation.

Phase 1 is limited to architecture, requirements, roadmap, dependency list, and project skeleton. Do not implement the full application until Phase 2 is requested.

## Safety Principles

- Never modify MP3 files during scanning.
- Always produce a preview or dry run before writing tags, lyrics, or filenames.
- Never silently overwrite an existing file.
- Store original metadata and filename in SQLite before any modification.
- Support undo for the last applied batch.
- Require manual review for low-confidence matches.
- Never delete the original MP3.
- Treat network failures as non-destructive; local files must remain unchanged.
- Preserve existing lyrics by default.
- Never overwrite lyrics without explicit user confirmation.

## Architecture Boundaries

Keep these layers separated:

- `ui`: PySide6 widgets, windows, dialogs, and view models only.
- `app`: orchestration of scans, matching, previews, applying changes, and undo.
- `domain`: plain data models, confidence scoring inputs, value objects, and rules.
- `providers`: online metadata and lyrics integrations.
- `fingerprinting`: Chromaprint/fpcalc execution and fingerprint result parsing.
- `id3`: Mutagen-based metadata read/write logic.
- `files`: local filesystem scanning, filename parsing, safe rename planning, and conflict handling.
- `db`: SQLite persistence for cache, processing history, and undo.

Provider clients must not call PySide6 classes directly. UI code should depend on application services, not raw HTTP clients or Mutagen objects.

## Implementation Guidance

- Prefer small, testable services with dependency injection for HTTP, filesystem, and database access.
- Keep domain rules deterministic and easy to unit test.
- Use `httpx` for HTTP requests.
- Use Mutagen only inside ID3/file metadata adapters.
- Use subprocess execution for `fpcalc`; validate that it exists and report actionable setup errors.
- Use SQLite migrations or a clearly versioned schema once persistence begins.
- Keep API credentials and rate-limit configuration out of source control.

## Testing Expectations

- Unit-test filename parsing, confidence scoring, safe rename planning, and ID3 mapping rules.
- Mock external providers in tests.
- Use temporary directories for filesystem tests.
- Do not require live AcoustID, MusicBrainz, or LRCLIB network calls in default test runs.

## Current Phase

Phase 1 only:

- Documentation
- Requirements
- Roadmap
- Project skeleton
- Dependency declaration
- Ignore rules

