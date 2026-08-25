# Requirements

## Product Goal

Build a local-first desktop application that safely cleans MP3 metadata, retrieves reliable canonical metadata and lyrics, previews proposed changes, and applies updates only after user confirmation.

## Functional Requirements

### Scanning

- Scan user-selected folders for MP3 files.
- Read existing ID3 metadata without modifying files.
- Parse filenames to infer possible artist and title.
- Detect missing, incomplete, suspicious, or noisy metadata.
- Never write to disk during scanning.

### Fingerprinting and Identification

- Generate audio fingerprints using Chromaprint through `fpcalc`.
- Query AcoustID using fingerprint and duration.
- Treat audio fingerprint matches as the highest-priority evidence.
- Retrieve MusicBrainz recording and release information for likely matches.
- Support original-language artist and title values when reliable canonical metadata is available.

### Metadata Retrieval

Primary metadata:

- Title
- Artist
- Album
- Release year/date
- Track number
- Cover artwork where available
- Lyrics

Canonical metadata source:

- MusicBrainz recording, artist, release, release group, and track data.

### Lyrics

- Preserve existing lyrics by default.
- Query LRCLIB only when lyrics are missing, unless the user explicitly requests replacement.
- Store plain lyrics in the appropriate ID3 lyrics field.
- Support synchronized lyrics export when available.
- Export synchronized lyrics as:

```text
Artist - Title.lrc
```

- Never overwrite existing lyrics without explicit user confirmation.

### Confidence and Review

Confidence ranges:

- `90-100%`: high confidence, eligible for auto-selection.
- `70-89%`: needs user review.
- `<70%`: must not be automatically applied.

Matching should consider:

- Audio fingerprint
- Duration
- Existing ID3 artist/title
- Filename artist/title
- MusicBrainz recording identity
- Release information

Audio fingerprint evidence should carry the highest weight.

### Preview and Apply

- Show all proposed tag, lyrics, artwork, and filename changes before applying.
- Support dry run output.
- Require confirmation before modifying files.
- Avoid applying low-confidence changes automatically.
- Allow users to accept, reject, or edit proposed metadata before applying.

### File Operations

- Rename MP3 files using:

```text
{Artist} - {Title}.mp3
```

- The filename must contain only artist and title.
- Sanitize path-invalid characters.
- Handle duplicate target filenames safely.
- Never silently overwrite an existing file.
- Never delete the original MP3.

### Persistence and Undo

- Use SQLite for:
  - Metadata cache
  - Provider response cache where appropriate
  - Processing history
  - Original filename
  - Original ID3 metadata
  - Applied batch records
  - Undo data

- Store original metadata and filename before any modification.
- Support Undo Last Batch.
- Undo must restore tags and filename when possible.

## Non-Functional Requirements

- Local-first: files remain local, and modifications are user-controlled.
- Testable architecture: UI, orchestration, providers, domain logic, file operations, and database access must be separated.
- Resilient networking: provider failures must not corrupt local files.
- Respect provider rate limits and user-agent requirements.
- Use deterministic domain logic where possible.
- Avoid tightly coupling API calls to PySide6 UI classes.
- Support eventual Windows packaging with PyInstaller.

## External Dependencies

- `fpcalc` from Chromaprint must be installed or bundled.
- AcoustID API access requires an API key.
- MusicBrainz requests must use an appropriate user agent.
- LRCLIB availability and results may vary.

## Out of Scope for Phase 1

- Full GUI implementation
- Real scanning engine
- Real provider integrations
- Mutagen write operations
- SQLite schema implementation
- PyInstaller packaging
- Live network behavior

