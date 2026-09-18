# Music Metadata Cleaner

A local-first PySide6 desktop application for reviewing and cleaning MP3 metadata.

MP3 → filename / existing ID3 → SearXNG → rule-based resolver → Artist + Title → LRCLIB plainLyrics → preview → confirmed ID3 update + rename.

The application does **not analyze audio content**. It has no active audio recognition, paid search API, LLM, or dedicated YouTube API integration. It uses search-result titles, domains, and supporting text. It does not scrape target music or lyric websites.

If the filename and ID3 contain insufficient information (for example `track001.mp3` or `流行歌曲推荐TikTok.mp3`), the result is **Insufficient Information**. Enter known details in **Search keywords** and use **Search**. No identity is invented.

## Setup

Install Python 3.10+ and dependencies:

```shell
python -m pip install -r requirements.txt
```

Configure your SearXNG instance in **Settings → Search → SearXNG URL**, or set `SEARXNG_URL`. There is no default server and no search API key. For example, a locally managed instance might use `http://localhost:8080`. Enable JSON in its `settings.yml`:

```yaml
search:
  formats:
    - html
    - json
```

Use **Test Connection** to validate the endpoint. See the [official SearXNG API documentation](https://docs.searxng.org/dev/search_api.html). A 403 commonly means JSON is disabled or access is restricted by that server.

Run on Windows:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m music_metadata_cleaner
```

Run on Linux:

```sh
PYTHONPATH=src python -m music_metadata_cleaner
```

## Use

1. Add MP3 files or a folder. Scanning reads tags without modifying files.
2. Scan & Preview searches at most two queries per track, stopping early on strong agreement.
3. Inspect **View Search Evidence**. Confidence is **High**, **Medium**, or **Low**, not a probability.
4. Use **Use Candidate** to confirm an ambiguous identity, or enter manual search keywords.
5. Confirm **Apply Selected** or **Apply All High Confidence**. The target name is `{Artist} - {Title}.mp3`.
6. Use **Undo Last Batch** to restore supported original tags and filenames, including successful files in a partial batch.

Existing lyrics are preserved by default. LRCLIB supplies plain lyrics only. Missing lyrics do not prevent metadata updates or renames. Mismatched lyrics are marked for review and never written. There is no LRC output.

History is written to SQLite before modifying files; backup defaults on. Existing filenames and backups are never silently overwritten. Files must be previewed again if their tags change. Rename uses exclusive target creation and requires filesystem hard-link support (NTFS/ext4 and typical local filesystems); unsupported filesystems fail safely.

New installations use platform config directories (`LOCALAPPDATA` on Windows; `XDG_CONFIG_HOME` / `~/.config` on Linux) and platform log/cache directories. Existing working-directory preferences and history are adopted without deleting or moving data. Search cache entries share the history database but are independently clearable and expire after one day by default.

## Development and validation

```shell
python -m pytest -q
```

All automated network requests are mocked. Offscreen GUI tests are enabled with `RUN_QT_GUI_TESTS=1` and `QT_QPA_PLATFORM=offscreen`; see [build instructions](docs/BUILD.md). Historical backend regression tests remain isolated from production imports.

See [architecture and confidence rules](docs/ARCHITECTURE.md), [manual benchmark procedure](docs/SEARCH_BENCHMARK.md), and [refactor audit](docs/PHASE9_REPORT.md).

Manual editing is available through **Edit Artist / Title / Lyrics**, including editable filename-derived dropdowns, swapping fields, and user-entered plain lyrics. Save Preview never writes files. See [confidence and manual editing](docs/CONFIDENCE_AND_MANUAL_EDIT.md).
