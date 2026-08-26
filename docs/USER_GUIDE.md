# User Guide

## What Music Metadata Cleaner Does

Music Metadata Cleaner scans local MP3 files, identifies songs, retrieves canonical metadata and lyrics, previews proposed changes, and applies selected updates only after confirmation.

## Supported Formats

Current write support is MP3 ID3 metadata. Other audio formats are ignored.

## Configure APIs

The easiest setup is to use the project `.env` file.

From the project folder:

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in at least:

```text
ACOUSTID_API_KEY=your-acoustid-api-key
YOUTUBE_API_KEY=your-youtube-data-api-key
MUSIC_METADATA_CLEANER_USER_AGENT=MusicMetadataCleaner/0.1 (your-email@example.com)
FPCALC_PATH=C:\Tools\chromaprint\fpcalc.exe
```

`MUSIC_METADATA_CLEANER_USER_AGENT` should include a contact email because MusicBrainz asks applications to identify themselves. It can be your Gmail account or another email address you are comfortable using for technical contact.

You can also set environment variables manually before launching:

```powershell
$env:ACOUSTID_API_KEY="your-acoustid-api-key"
$env:MUSIC_METADATA_CLEANER_USER_AGENT="MusicMetadataCleaner/0.1 (you@example.com)"
```

The app also creates:

```text
config/preferences.json
```

Supported preferences include API key, default music folder, filename format, artist language preference, auto-apply confidence threshold, backup setting, database path, and log path.

YouTube settings are optional:

```text
MUSIC_METADATA_CLEANER_ALWAYS_USE_YOUTUBE_VERIFICATION=false
MUSIC_METADATA_CLEANER_YOUTUBE_SEARCH_BELOW_CONFIDENCE=90
```

With defaults, high-confidence AcoustID/MusicBrainz matches do not spend YouTube quota. YouTube is used for medium-confidence verification and low/no-match fallback only when `YOUTUBE_API_KEY` is configured.

AudD fallback recognition is optional:

```text
AUDD_API_TOKEN=your-audd-token
MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED=true
MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_THRESHOLD=70
MUSIC_METADATA_CLEANER_MULTI_SEGMENT_RECOGNITION_ENABLED=true
MUSIC_METADATA_CLEANER_MAX_RECOGNITION_SEGMENTS=3
FFMPEG_PATH=C:\Tools\ffmpeg\bin\ffmpeg.exe
```

Install `ffmpeg.exe` and either put it on `PATH` or set `FFMPEG_PATH`. AudD fallback runs after weak, incomplete, or failed AcoustID recognition. It extracts short temporary clips from the MP3, sends those clips for recognition, and deletes them afterward. The original MP3 is not modified during recognition.

If `AUDD_API_TOKEN` is present, fallback recognition is enabled by default unless `MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED=false` is explicitly set in the environment.

## Start The Application

Recommended command on this machine:

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
$env:PYTHONPATH="$PWD\src"
& "C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe" -m music_metadata_cleaner
```

This works even when PowerShell still shows `(base)` or `conda activate music-cleaner` is broken, because it directly uses the Python installed inside the `music-cleaner` environment.

If conda activation works, you can use:

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
conda activate music-cleaner
$env:PYTHONPATH="$PWD\src"
python -m music_metadata_cleaner
```

The correct module name is:

```text
music_metadata_cleaner
```

Do not type backslashes in the module name.

To repair conda activation in PowerShell:

```powershell
& "C:\Users\SCSM11\anaconda3\Scripts\conda.exe" init powershell
```

After that, close all PowerShell windows and open a new one.

## Basic Workflow

1. Add MP3 files or a music folder.
2. Select Preview Changes.
3. Review confidence, metadata status, lyrics status, and proposed filename.
4. Adjust apply settings.
5. Apply selected rows or all high-confidence rows.
6. Use Undo Last Batch if you need to restore the previous metadata and filename.

When YouTube evidence is available, the table shows statuses such as `Matched`, `Candidates rejected`, `No results`, `API error`, `Not configured`, or `Not checked`. Select a row to view the YouTube candidate, channel, duration, and evidence strength. `Open YouTube Result` opens the matched video in your browser. It does not download anything.

The table also shows Recognition status, such as `AcoustID`, `AudD fallback (2/3)`, `AcoustID + AudD`, `No audio match`, or `AudD: not configured`. The detail panel shows diagnostics for AcoustID, AudD, and YouTube so failed files are easier to troubleshoot.

Use `Test Recognition Setup` before evaluating accuracy. Expected healthy output:

```text
AudD Provider        PASS
AudD Authentication  PASS
FFmpeg path          PASS
FFmpeg execution     PASS
Audio Extraction     PASS
```

The test performs a real AudD provider request against a tiny temporary audio clip. It may return `NO_MATCH`; that still means authentication succeeded.

## Safety Features

- Scanning does not modify files.
- Apply requires a SQLite history record first.
- Optional backup creates `.mp3.backup` files in `MusicCleaner_Backup/`.
- Existing lyrics are not overwritten automatically.
- Existing filenames and metadata are stored before changes.
- Rename conflicts and `.lrc` conflicts stop the operation.
- Failed operations attempt automatic recovery.

## Duplicate Detection

The backend can compare file hash, audio fingerprint, duration, and metadata similarity to identify:

- Exact duplicates.
- Same song with different filenames.
- Possible different quality or version.

Full duplicate review UI is a future enhancement.

## Troubleshooting

### No songs are identified

Check that `ACOUSTID_API_KEY` is set and `fpcalc.exe` is installed.

### YouTube is not checked

Check that `YOUTUBE_API_KEY` is set in `.env`. High-confidence rows skip YouTube by default to save quota.

### YouTube unavailable

The API key may be invalid, quota may be exhausted, or the network request may have failed. The app continues using AcoustID and MusicBrainz when YouTube is unavailable.

### AudD fallback is not used

Check that `AUDD_API_TOKEN` is set, `MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED=true`, and `ffmpeg.exe` is available through `FFMPEG_PATH` or `PATH`.

If the runtime panel says `AudD: disabled`, remove the explicit false value or set:

```text
MUSIC_METADATA_CLEANER_FALLBACK_RECOGNITION_ENABLED=true
```

If the runtime panel says `AudD: authentication failed`, the token was loaded by the app but AudD rejected it.

### AudD returns no match

The clip may not contain recognizable music, the token may be invalid, quota may be exhausted, or the track may not exist in AudD's recognition database. Existing AcoustID/MusicBrainz results are preserved when AudD fails.

### Missing fingerprint tool

Install Chromaprint and confirm `fpcalc.exe` is available on `PATH`.

### MusicBrainz or LRCLIB errors

Check internet connectivity and wait if rate-limited. Provider errors are logged to:

```text
logs/application.log
```

### PySide6 fails to launch

Some Anaconda environments can have Qt DLL conflicts. Try a clean virtual environment with dependencies installed from `requirements.txt`.

If the base Anaconda Python shows a Qt DLL error, run the app with the direct environment Python instead:

```powershell
$env:PYTHONPATH="$PWD\src"
& "C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe" -m music_metadata_cleaner
```

If the command exits but no window appears, check that Qt is not running in offscreen mode:

```powershell
echo $env:QT_QPA_PLATFORM
Remove-Item Env:QT_QPA_PLATFORM
```

Then start the app again.
