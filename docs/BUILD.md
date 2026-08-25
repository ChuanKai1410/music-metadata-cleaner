# Build Instructions

## Windows Development Setup

```powershell
cd C:\Users\SCSM11\Documents\SelfProject\music-metadata-cleaner
python -m pip install -r requirements.txt
```

Optional runtime tools:

- Install Chromaprint and make `fpcalc.exe` available on `PATH`.
- Set `ACOUSTID_API_KEY` for audio identification.
- Set `MUSIC_METADATA_CLEANER_USER_AGENT` to a contactable app user agent for provider requests.

## Run From Source

```powershell
$env:PYTHONPATH="$PWD\src"
python -m music_metadata_cleaner
```

## Run Tests

```powershell
python -m pytest
```

GUI smoke tests are opt-in because some CI or Anaconda environments cannot load Qt:

```powershell
$env:RUN_QT_GUI_TESTS="1"
python -m pytest tests/test_gui_smoke.py
```

## Build Executable

```powershell
python -m PyInstaller packaging\MusicMetadataCleaner.spec --noconfirm
```

Expected output:

```text
dist\MusicMetadataCleaner.exe
```

The executable creates local runtime files next to the launch working directory unless configured otherwise:

- `config/preferences.json`
- `music_metadata_cleaner.sqlite3`
- `logs/application.log`
- `MusicCleaner_Backup/`

## Release Checklist

- Confirm PySide6 imports successfully outside Anaconda if Anaconda DLL conflicts occur.
- Add a valid `assets/icons/app.ico`.
- Verify `fpcalc.exe` installation or bundling strategy.
- Run tests on a clean Windows machine.
- Confirm no API keys are packaged.
- Smoke-test scanning, preview, apply, backup, and undo against disposable MP3 copies.

