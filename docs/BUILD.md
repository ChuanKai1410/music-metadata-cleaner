# Build and test

[Documentation index](README.md) · [User setup](USER_GUIDE.md#connect-search)

## Source environment

The repository is an installable Python package project. `pyproject.toml` uses setuptools (`setuptools>=68`, `wheel`), discovers packages in `src/`, and declares `music-metadata-cleaner` version `0.1.0` with Python `>=3.10`. The import/module name is `music_metadata_cleaner`.

The current metadata does not declare application dependencies or command-line entry points. Install `requirements.txt` separately, then install the project in editable mode. Run these commands from the repository root.

**Windows / PowerShell — existing environment, no activation**

```powershell
$py = 'C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe'
& $py -m pip install -r requirements.txt
& $py -m pip install -e .
& $py -m music_metadata_cleaner
```

For a separate Windows virtual environment, create one with `python -m venv .venv`, set `$py = '.\.venv\Scripts\python.exe'`, and use the same install/run commands. The provided `build.ps1` still uses the exact music-cleaner interpreter configured in that script.

**Linux**

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
.venv/bin/python -m music_metadata_cleaner
```

After editable installation, launch with the same interpreter; setting `PYTHONPATH` is unnecessary. Ordinary source edits take effect on the next application launch. Reinstall if package metadata changes or the checkout moves, and rebuild the EXE after code changes. Installation does not update an already running app or a previously built EXE.

Opening a new PowerShell window is optional. A `(base)` prompt does not change the interpreter selected by its full path. In a new shell, define `$py` again or use the full path directly.

Check the installation without launching the GUI:

```powershell
& $py -m pip show music-metadata-cleaner
& $py -I -c "import music_metadata_cleaner; print(music_metadata_cleaner.__file__)"
```

Verified in the specified music-cleaner environment: package version `0.1.0`, editable checkout pointing to this project, and successful package/`__main__` imports with Python `-I` (which ignores `PYTHONPATH`). No reinstall was needed for this documentation update.

Editable development and PyInstaller distribution are separate workflows. The spec explicitly includes QSS/SVG assets; wheel/sdist resource inclusion is not explicitly configured or validated by this minimal `pyproject.toml`. Do not assume the desktop bundle's resource rules apply to a pip-built wheel.

Linux needs working native Qt platform/display libraries. No FFmpeg, fpcalc, recognition credentials, or bundled fonts are required. Configure SearXNG in Settings, `SEARXNG_URL`, or a launch-directory `.env`. New preferences use platform directories; legacy local history is preserved.

## Automated tests

Using the virtual-environment interpreter:

```sh
.venv/bin/python -m pytest -q
RUN_QT_GUI_TESTS=1 QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

PowerShell, including GUI tests:

```powershell
$py = 'C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe'
$env:RUN_QT_GUI_TESTS="1"
$env:QT_QPA_PLATFORM="offscreen"
& $py -m pytest -q
```

All automated search/LRCLIB requests are mocked. Write/rename/undo tests use temporary files. GUI tests are skipped unless explicitly enabled. Historical backend tests exercise retained historical modules, not production imports.

To check scaling, set `QT_SCALE_FACTOR` to `1.25` or `1.5` and run `tests/test_gui_smoke.py`. Start a new test process per scale. Unset `QT_QPA_PLATFORM` and `QT_SCALE_FACTOR` before a normal interactive launch.

Latest recorded validation: **207 full-suite tests passed**, including **15 GUI tests**; the GUI subset also passed at 125% and 150%. A compatible Python 3.12 runtime was used after the machine's Anaconda environment hit a Qt DLL conflict. Native Linux visual testing remains pending. Windows bundle verification is described below.

## UI resources

`ui/theme.py` loads `ui/styles/app.qss` with shared palette tokens and applies it to QApplication. Dynamic properties provide primary, section, changed-value, and error styling. Avoid per-widget stylesheets. The system font is retained; offscreen capture environments may need local fonts loaded explicitly for rendering.

For visual review, inspect Main Window at 1280×720 and 1920×1080, Settings tabs, manual editor/search, candidates, evidence, history, and confirmations. Long detail content should scroll; table text may elide with tooltips. Native file pickers follow the OS theme.

## Windows rebuild script

Run from the repository root:

```powershell
.\build.ps1
```

The script uses exactly `C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe`, without `conda activate`. It validates Python and PyInstaller before cleaning only `build/` and `dist/MusicMetadataCleaner/`. Linked output directories are refused. During the build, PATH is restricted to the selected environment and Windows system directories and PYTHONPATH is cleared; both are restored afterward. This prevents unrelated tools from contributing incompatible DLLs. It builds the existing spec, checks the native process exit code, verifies the expected EXE, and exits nonzero on failure.

If PyInstaller is missing, install it explicitly:

```powershell
& 'C:\Users\SCSM11\anaconda3\envs\music-cleaner\python.exe' -m pip install pyinstaller
```

If PowerShell blocks scripts, allow execution only for the current session:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build.ps1
```

No permanent execution-policy change or automatic dependency installation is made. The script anchors work to its own project directory. Close an older running build before rebuilding if Windows reports locked files. An old single-file `dist/MusicMetadataCleaner.exe` is not deleted; use the new path below.

```text
dist/
└── MusicMetadataCleaner/
    ├── MusicMetadataCleaner.exe
    └── _internal/
```

Distribute the whole folder. `console=False` in the spec implements **--windowed**, while `EXE(exclude_binaries=True)` plus `COLLECT` implements **--onedir**. Those makespec flags are not passed alongside an existing spec. The existing `src/music_metadata_cleaner/__main__.py` is the entry point; no duplicate launcher is needed.

QSS and SVG arrows are loaded relative to the theme module's `__file__`, which works in source and in the matching bundled package directory. PyInstaller's PySide6 hooks collect the Qt runtime/plugins. No user configuration template is required: defaults are defined in `AppConfig`. Optional `assets/icons/app.ico` is used only if present.

SearXNG/Docker are not bundled. The desktop still uses its configured external URL. Existing `.env`, settings, history/cache databases, logs, backups, media, and documentation figures are not build assets and are not collected. Runtime data continues to use the normal platform directories and existing migration behavior.

### Windows verification

The script was run successfully with the specified environment: Python 3.12.13, PyInstaller 6.22.2, and PySide6 6.11.2 on Windows 11. The final EXE's PE subsystem is Windows GUI (no console). A native hidden-window smoke test found the actual Music Metadata Cleaner window and closed it normally with exit code 0, using isolated temporary settings/history.

Bundled QSS and both SVG arrows match the source byte-for-byte. The Windows platform plugin (`qwindows.dll`), SVG image plugin (`qsvg.dll`), and SVG icon plugin (`qsvgicon.dll`) are present. No additional hidden imports, launcher, or application resource-loading changes were needed. The complete one-directory bundle is approximately 122 MiB. No custom `app.ico` is currently present, so the executable uses the default icon.

The first build exposed an incompatible ICU DLL collected from an unrelated tool on PATH. The script's isolated build PATH fixes that conflict. Build runners that forcibly replace child-process environment variables must allow the script's environment to reach PyInstaller; validation here required running outside such a sandbox restriction. Normal developer use remains `./build.ps1` without conda activation.

All **207 tests passed**, including four build-script checks for missing Python, missing PyInstaller, native build failure, and missing output. Those checks use disposable project copies and verify failure exits without a success message or unrelated-file deletion. Linux packaging and other Windows machines were not tested in this pass. Distribute the entire output folder, not just its EXE.

## Packaging

From the project root, using the same environment:

```sh
python -m PyInstaller packaging/MusicMetadataCleaner.spec
```

Replace `python` with the virtual-environment interpreter if it is not activated. The spec includes the QSS/SVG style directory and uses `assets/icons/app.ico` when present. The spec produces a windowed one-directory distribution under `dist/MusicMetadataCleaner/` (`MusicMetadataCleaner.exe` on Windows).

Build separately on each target OS. Do not distribute local `.env`, preferences, databases, logs, caches, or sample MP3s. Historical recognition modules are excluded from the desktop bundle. After building, test launch, styling/arrows, endpoint configuration, preview, and confirmed apply/undo on disposable copies.

## Documentation figures

[Main window](images/main-window.png) and [manual editor](images/manual-edit.png) are captures of current Qt widgets using synthetic demonstration data, not claimed search matches. No personal settings, file paths, or lyrics are embedded. Refresh figures after visible UI changes; keep screenshots and [UI action audit](UI_ACTION_AUDIT.md) consistent with actual signals/slots.
