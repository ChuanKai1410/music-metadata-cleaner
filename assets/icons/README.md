# Icon assets

The PyInstaller spec optionally uses `assets/icons/app.ico` for the Windows application icon. If the file is absent, the build uses the default executable icon. No decorative icon library is required by the desktop UI.

The small up/down control arrows live in `src/music_metadata_cleaner/ui/styles/up.svg` and `down.svg`; the shared QSS loads them and the packaging spec includes their directory. These are dropdown/spinbox affordances, not toolbar decorations. Standard message-box icons and native window chrome remain provided by Qt/the OS.

See [build and packaging](../../docs/BUILD.md) and the [UI report](../../docs/UI_POLISH_REPORT.md). README emojis are documentation decoration only; they are not application icons.
