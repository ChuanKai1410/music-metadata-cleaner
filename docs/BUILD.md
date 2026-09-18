# Build and test

[Documentation index](README.md) · [User setup](USER_GUIDE.md#connect-search)

## Source environment

Run from the repository root. Use Python 3.10+ and a compatible PySide6 installation. A clean virtual environment helps avoid conflicting Qt DLLs.

**Windows / PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PYTHONPATH="$PWD\src"
.\.venv\Scripts\python.exe -m music_metadata_cleaner
```

**Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python -m music_metadata_cleaner
```

Linux needs working native Qt platform/display libraries. No FFmpeg, fpcalc, recognition credentials, or bundled fonts are required. Configure SearXNG in Settings, `SEARXNG_URL`, or a launch-directory `.env`. New preferences use platform directories; legacy local history is preserved.

## Automated tests

Using the virtual-environment interpreter:

```sh
.venv/bin/python -m pytest -q
RUN_QT_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

PowerShell, including GUI tests:

```powershell
$env:RUN_QT_GUI_TESTS="1"
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe -m pytest -q
```

All automated search/LRCLIB requests are mocked. Write/rename/undo tests use temporary files. GUI tests are skipped unless explicitly enabled. Historical backend tests exercise retained historical modules, not production imports.

To check scaling, set `QT_SCALE_FACTOR` to `1.25` or `1.5` and run `tests/test_gui_smoke.py`. Start a new test process per scale. Unset `QT_QPA_PLATFORM` and `QT_SCALE_FACTOR` before a normal interactive launch.

Latest recorded validation: **203 full-suite tests passed**, including **15 GUI tests**; the GUI subset also passed at 125% and 150%. A compatible Python 3.12 runtime was used after the machine's Anaconda environment hit a Qt DLL conflict. Native Linux visual testing and a fresh packaged-binary smoke test remain pending.

## UI resources

`ui/theme.py` loads `ui/styles/app.qss` with shared palette tokens and applies it to QApplication. Dynamic properties provide primary, section, changed-value, and error styling. Avoid per-widget stylesheets. The system font is retained; offscreen capture environments may need local fonts loaded explicitly for rendering.

For visual review, inspect Main Window at 1280×720 and 1920×1080, Settings tabs, manual editor/search, candidates, evidence, history, and confirmations. Long detail content should scroll; table text may elide with tooltips. Native file pickers follow the OS theme.

## Packaging

From the project root, using the same environment:

```sh
python -m PyInstaller packaging/MusicMetadataCleaner.spec
```

Replace `python` with the virtual-environment interpreter if it is not activated. The spec includes the QSS/SVG style directory and uses `assets/icons/app.ico` when present. Output is under `dist/` with the name `MusicMetadataCleaner` (`.exe` on Windows).

Build separately on each target OS. Do not distribute local `.env`, preferences, databases, logs, caches, or sample MP3s. Historical recognition modules are excluded from the desktop bundle. After building, test launch, styling/arrows, endpoint configuration, preview, and confirmed apply/undo on disposable copies.

## Documentation figures

[Main window](images/main-window.png) and [manual editor](images/manual-edit.png) are captures of current Qt widgets using synthetic demonstration data, not claimed search matches. No personal settings, file paths, or lyrics are embedded. Refresh figures after visible UI changes; keep screenshots and [UI action audit](UI_ACTION_AUDIT.md) consistent with actual signals/slots.
