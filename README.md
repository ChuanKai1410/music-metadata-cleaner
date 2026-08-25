# Music Metadata Cleaner

Music Metadata Cleaner is a local-first Python desktop application for safely cleaning MP3 metadata.

It scans local MP3 files, reads existing ID3 tags, fingerprints audio with Chromaprint/`fpcalc`, identifies songs through AcoustID, retrieves canonical metadata from MusicBrainz, retrieves lyrics from LRCLIB, previews changes, and applies updates only after user confirmation.

## Features

- MP3 discovery from files or folders.
- ID3 read/write support through Mutagen.
- Chromaprint fingerprinting through `fpcalc`.
- AcoustID candidate identification.
- MusicBrainz metadata enrichment.
- LRCLIB plain and synced lyrics lookup.
- Desktop GUI with batch preview and apply controls.
- SQLite operation history.
- Undo Last Batch.
- Optional backup before modification.
- Duplicate detection helpers.
- Provider request caching.
- Application logging.

## Safety Model

- Scanning is read-only.
- Every change is previewed before application.
- A history record is required before modifying files.
- Existing lyrics are preserved by default.
- Existing files are never silently overwritten.
- Backup and rollback are used during apply.
- Low-confidence changes require review.

## Installation

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
python -m pip install -r requirements.txt
```

Install Chromaprint separately and make `fpcalc.exe` available on `PATH`.

## API Configuration

```powershell
$env:ACOUSTID_API_KEY="your-acoustid-api-key"
$env:MUSIC_METADATA_CLEANER_USER_AGENT="MusicMetadataCleaner/0.1 (you@example.com)"
```

The app creates local preferences at:

```text
config/preferences.json
```

## Run From Source

```powershell
$env:PYTHONPATH="$PWD\src"
python -m music_metadata_cleaner
```

## Tests

```powershell
python -m pytest
```

GUI smoke tests are opt-in:

```powershell
$env:RUN_QT_GUI_TESTS="1"
python -m pytest tests/test_gui_smoke.py
```

## Packaging

```powershell
python -m PyInstaller packaging\MusicMetadataCleaner.spec --noconfirm
```

See [docs/BUILD.md](docs/BUILD.md) for release notes and checklist.

## Documentation

- [Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [MusicBrainz Release Selection](docs/MUSICBRAINZ_RELEASE_SELECTION.md)
- [User Guide](docs/USER_GUIDE.md)
- [Build Instructions](docs/BUILD.md)

