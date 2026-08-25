# Music Metadata Cleaner

Music Metadata Cleaner is a planned local-first Python desktop application for safely cleaning MP3 metadata.

It will scan local MP3 files, read existing ID3 tags, parse filenames, generate Chromaprint audio fingerprints, identify recordings through AcoustID, retrieve canonical metadata from MusicBrainz, retrieve lyrics from LRCLIB where available, show a preview, and then update files only after user confirmation.

The project is currently in **Phase 1: architecture and skeleton only**. The full application has not been implemented yet.

## Target Workflow

```text
MP3
-> read existing ID3 metadata
-> parse filename
-> generate Chromaprint fingerprint
-> query AcoustID
-> identify recording
-> retrieve canonical metadata from MusicBrainz
-> retrieve lyrics from LRCLIB
-> calculate confidence
-> show preview
-> user confirms
-> update ID3 metadata
-> optionally save .lrc
-> rename MP3
-> save change history for undo
```

## Core Technologies

- Python 3
- PySide6 for the desktop GUI
- Mutagen for MP3 and ID3 metadata
- Chromaprint / `fpcalc` for audio fingerprinting
- AcoustID for song identification
- MusicBrainz for canonical metadata
- LRCLIB for lyrics
- SQLite for local cache, processing history, and undo
- httpx for HTTP requests
- pytest for tests
- PyInstaller for eventual Windows executable packaging

## Safety Model

- Scanning is read-only.
- Every change is previewed before application.
- Existing lyrics are preserved by default.
- Original metadata and filenames are stored before modification.
- Undo Last Batch is a required feature.
- Low-confidence matches require manual review.
- Duplicate target filenames are handled safely.
- Existing files are never silently overwritten.

## File Naming

The target filename convention is:

```text
{Artist} - {Title}.mp3
```

Example:

```text
Before: Lemon MV Kenshi Yonezu Official Music Video Full HD.mp3
After:  米津玄師 - Lemon.mp3
```

The filename should contain only the artist and song title, using original-language names when reliable metadata supports them.

## Repository Layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the proposed module layout and responsibilities.

## Development Status

Phase 1 artifacts are prepared:

- Project documentation
- Architecture proposal
- Requirements
- Roadmap
- Python package skeleton
- Test skeleton
- Dependency list
- Ignore rules

Do not proceed to Phase 2 until explicitly requested.

