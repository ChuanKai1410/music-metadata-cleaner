# User Guide

## What Music Metadata Cleaner Does

Music Metadata Cleaner scans local MP3 files, identifies songs, retrieves canonical metadata and lyrics, previews proposed changes, and applies selected updates only after confirmation.

## Supported Formats

Current write support is MP3 ID3 metadata. Other audio formats are ignored.

## Configure APIs

Set environment variables before launching:

```powershell
$env:ACOUSTID_API_KEY="your-acoustid-api-key"
$env:MUSIC_METADATA_CLEANER_USER_AGENT="MusicMetadataCleaner/0.1 (you@example.com)"
```

The app also creates:

```text
config/preferences.json
```

Supported preferences include API key, default music folder, filename format, artist language preference, auto-apply confidence threshold, backup setting, database path, and log path.

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

