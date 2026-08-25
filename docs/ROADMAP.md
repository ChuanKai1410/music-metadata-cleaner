# Roadmap

## Phase 1: Architecture and Skeleton

Status: current phase.

Deliverables:

- Requirements document.
- Architecture document.
- Roadmap.
- README.
- Agent guidance.
- Python package skeleton.
- Test skeleton.
- Dependency list.
- Ignore rules.

No full application code should be implemented in this phase.

## Phase 2: Domain and Safety Core

Goals:

- Define domain models for tracks, metadata, lyrics, recordings, confidence evidence, proposed changes, and batches.
- Implement filename parsing rules.
- Implement safe filename generation.
- Implement confidence scoring.
- Implement rename planning with duplicate detection.
- Implement lyrics overwrite policy.

Validation:

- Unit tests for confidence thresholds.
- Unit tests for noisy filename parsing.
- Unit tests for original-language output names.
- Unit tests for duplicate filename handling.
- Unit tests confirming no overwrite behavior.

## Phase 3: Local Metadata and Filesystem Adapters

Goals:

- Read existing MP3 metadata using Mutagen.
- Map ID3 frames into domain models.
- Prepare write plans for title, artist, album, release date, track number, artwork, and lyrics.
- Implement safe application of confirmed ID3 changes.
- Implement confirmed rename execution.

Validation:

- Tests using temporary fixture MP3 files where practical.
- Tests proving scan paths do not modify files.
- Tests proving existing lyrics are preserved by default.

## Phase 4: SQLite Persistence and Undo

Goals:

- Create SQLite schema and migration strategy.
- Store original metadata and filename before modifications.
- Store provider cache records.
- Store applied batch history.
- Implement Undo Last Batch.

Validation:

- Tests for batch persistence.
- Tests for undo restore behavior.
- Tests for interrupted or failed apply operations.

## Phase 5: Fingerprinting and Provider Integrations

Goals:

- Add `fpcalc` detection and execution.
- Query AcoustID with fingerprint and duration.
- Query MusicBrainz for canonical recording metadata.
- Query LRCLIB for plain and synchronized lyrics.
- Add retry, timeout, rate-limit, and user-agent handling.

Validation:

- Mocked provider tests.
- Fixture-based fingerprint parsing tests.
- Optional opt-in live integration tests.

## Phase 6: Application Orchestration

Goals:

- Implement scan workflow.
- Implement identify and enrich workflow.
- Build preview objects.
- Coordinate apply workflow.
- Coordinate undo workflow.
- Handle cancellation and partial failure states.

Validation:

- End-to-end orchestration tests with mocked adapters.
- Tests proving network failures do not write local files.
- Tests proving low-confidence matches are not automatically applied.

## Phase 7: PySide6 Desktop UI

Goals:

- Folder selection.
- Scan progress.
- Results table.
- Confidence badges.
- Preview diff.
- Manual review.
- Apply confirmation.
- Undo Last Batch.
- Settings for API key, cache path, lyrics behavior, and fpcalc path.

Validation:

- Manual GUI QA.
- View-model tests where possible.
- Smoke test app startup.

## Phase 8: Packaging

Goals:

- Prepare PyInstaller packaging for Windows.
- Document `fpcalc` installation or bundling strategy.
- Provide default local data directory behavior.
- Add release checklist.

Validation:

- Build executable.
- Test on clean Windows environment.
- Confirm no credentials are packaged.

## Phase 9: Refinement

Goals:

- Improve confidence explanations.
- Add richer manual review tools.
- Add better artwork handling.
- Improve cache controls.
- Add batch reports.
- Add user documentation.

