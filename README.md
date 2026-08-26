# Music Metadata Cleaner

Music Metadata Cleaner is a local-first Python desktop application for safely cleaning MP3 metadata.

It scans local MP3 files, reads existing ID3 tags, fingerprints audio with Chromaprint/`fpcalc`, identifies songs through AcoustID, can fall back to short-clip AudD audio recognition for weak/no matches, retrieves canonical metadata from MusicBrainz, retrieves lyrics from LRCLIB, previews changes, and applies updates only after user confirmation.

## Features

- MP3 discovery from files or folders.
- ID3 read/write support through Mutagen.
- Chromaprint fingerprinting through `fpcalc`.
- AcoustID candidate identification.
- AudD fallback recognition using temporary multi-segment audio clips.
- MusicBrainz metadata enrichment.
- LRCLIB plain and synced lyrics lookup.
- YouTube Data API verification and fallback evidence for difficult YouTube-origin MP3s.
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

AudD fallback recognition also requires `ffmpeg`. Make `ffmpeg.exe` available on `PATH`, or set `FFMPEG_PATH` in `.env`.

## API Configuration

Copy `.env.example` to `.env`, then fill in your values:

```powershell
Copy-Item .env.example .env
notepad .env
```

Minimum useful settings:

```text
ACOUSTID_API_KEY=your-acoustid-api-key
YOUTUBE_API_KEY=your-youtube-data-api-key
MUSIC_METADATA_CLEANER_USER_AGENT=MusicMetadataCleaner/0.1 (your-email@example.com)
FPCALC_PATH=C:\Tools\chromaprint\fpcalc.exe
```

Optional audio-recognition fallback settings:

```text
AUDD_API_TOKEN=your-audd-token
MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED=true
MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_THRESHOLD=70
MUSIC_METADATA_CLEANER_MULTI_SEGMENT_RECOGNITION_ENABLED=true
MUSIC_METADATA_CLEANER_MAX_RECOGNITION_SEGMENTS=3
FFMPEG_PATH=C:\Tools\ffmpeg\bin\ffmpeg.exe
```

When enabled, the app still runs AcoustID first. AudD is used only for low-confidence, incomplete, or no-match audio identification unless you opt into medium-confidence verification. The app does not upload the full MP3 by default; it extracts short temporary clips around the middle portions of the song and deletes them after recognition.

Use the GUI's `Test Recognition Setup` button to confirm the runtime provider actually loaded the token, can execute ffmpeg, can extract a temporary clip, and can make a real AudD authentication request. The button never displays the token.

You can also set values in the current PowerShell session:

```powershell
$env:ACOUSTID_API_KEY="your-acoustid-api-key"
$env:MUSIC_METADATA_CLEANER_USER_AGENT="MusicMetadataCleaner/0.1 (you@example.com)"
```

The app creates local preferences at:

```text
config/preferences.json
```

YouTube is optional. The app uses the official YouTube Data API v3 only as a secondary search and verification source. It does not scrape YouTube, download videos, download subtitles, or recover an original source URL from third-party MP3 downloads.

Quota-aware defaults:

```text
MUSIC_METADATA_CLEANER_ALWAYS_USE_YOUTUBE_VERIFICATION=false
MUSIC_METADATA_CLEANER_YOUTUBE_SEARCH_BELOW_CONFIDENCE=90
```

With the default setting, high-confidence AcoustID/MusicBrainz matches skip YouTube. Medium, low, and no-match cases can use YouTube as supporting evidence when `YOUTUBE_API_KEY` is configured.

## Run From Source

From the project folder:

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
$env:PYTHONPATH="$PWD\src"
python -m music_metadata_cleaner
```

If you are using the local `music-cleaner` conda environment directly:

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
$env:PYTHONPATH="$PWD\src"
& "C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe" -m music_metadata_cleaner
```

For setup details, conda troubleshooting, API keys, `fpcalc`, `ffmpeg`, and first-use workflow, see the [User Guide](docs/USER_GUIDE.md).

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

## Manual Regression Reports

Do not commit sample MP3 files. To compare your 15 local samples before and after fallback recognition, keep a private CSV with columns:

```text
filename,before_high_confidence,after_confidence,after_correct,unresolved,acoustid_resolved,audd_fallback_resolved,youtube_verified
```

Then summarize it with:

```powershell
$env:PYTHONPATH="$PWD\src"
& "C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe" -c "from music_metadata_cleaner.app.regression_report import summarize_regression_csv; print(summarize_regression_csv('reports/manual-regression.csv'))"
```
