# Build and test

Use Python 3.10+ with a working PySide6 installation. A clean virtual environment is recommended when a system/Anaconda installation has conflicting Qt DLLs.

```sh
python -m pip install -r requirements.txt
```

Run from source on Linux:

```sh
PYTHONPATH=src python -m music_metadata_cleaner
```

Windows PowerShell:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m music_metadata_cleaner
```

No audio executables or recognition credentials are needed. Configure SearXNG through Settings or SEARXNG_URL. New preferences/logs use platform directories; existing working-directory history is preserved.

## Tests

```sh
python -m pytest -q
RUN_QT_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen python -m pytest -q
```

PowerShell GUI test environment:

```powershell
$env:RUN_QT_GUI_TESTS="1"
$env:QT_QPA_PLATFORM="offscreen"
python -m pytest -q
```

All automated web requests are mocked. GUI tests require compatible native Qt libraries. A DLL loader failure is an environment error, not a reason to skip checking the UI in a working interpreter.

## Packaging

```sh
python -m PyInstaller packaging/MusicMetadataCleaner.spec
```

Build separately on each target OS. The source supports Windows and Linux; native Linux packaging must be validated on Linux. Do not package local preferences, histories, credentials, or sample MP3s. Historical recognition modules are excluded from the desktop bundle.
