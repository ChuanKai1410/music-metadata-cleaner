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

Recommended on this machine:

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
& "C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe" -m pip install -r requirements.txt
```

Generic install command, if your correct environment is already active:

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
python -m pip install -r requirements.txt
```

Install Chromaprint separately and either make `fpcalc.exe` available on `PATH`, or set `FPCALC_PATH` in `.env`.

## API Configuration

Copy `.env.example` to `.env`, then fill in your values:

```powershell
Copy-Item .env.example .env
notepad .env
```

Minimum useful settings:

```text
ACOUSTID_API_KEY=your-acoustid-api-key
MUSIC_METADATA_CLEANER_USER_AGENT=MusicMetadataCleaner/0.1 (your-email@example.com)
FPCALC_PATH=C:\Tools\chromaprint\fpcalc.exe
```

You can also set values in the current PowerShell session:

```powershell
$env:ACOUSTID_API_KEY="your-acoustid-api-key"
$env:MUSIC_METADATA_CLEANER_USER_AGENT="MusicMetadataCleaner/0.1 (you@example.com)"
```

The app creates local preferences at:

```text
config/preferences.json
```

## Run From Source

Recommended on this machine, even if `conda activate` is not working:

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
$env:PYTHONPATH="$PWD\src"
& "C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe" -m music_metadata_cleaner
```

If your `music-cleaner` environment is already active:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m music_metadata_cleaner
```

The module name uses underscores only: `music_metadata_cleaner`.

If PowerShell cannot activate the conda environment, repair conda once with:

```powershell
& "C:\Users\SCSM11\anaconda3\Scripts\conda.exe" init powershell
```

Then close PowerShell completely, open it again, and run:

```powershell
conda activate music-cleaner
```

## Tests

Recommended on this machine:

```powershell
$env:PYTHONPATH="$PWD\src"
& "C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe" -m pytest
```

If your correct environment is already active:

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
