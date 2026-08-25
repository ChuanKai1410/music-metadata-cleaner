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
