# AGENTS.md

## Product direction

Phase 9: SearXNG + deterministic rule-based identity resolution + LRCLIB plain lyrics.

MP3 → filename / existing useful ID3 → text cleanup → up to two SearXNG queries → rule-based Artist + Title candidates → preview → explicit confirmation → ID3 update + rename.

Do not implement audio recognition, paid search APIs, LLM resolution, synchronized lyrics, or LRC output. The application cannot listen to audio. Insufficient text must produce Insufficient Information and offer Manual Search.

## Safety

- Scanning, search and preview must not modify MP3 files.
- Require explicit user confirmation to apply; uncertain candidates require manual selection.
- Persist original supported tags and filename in SQLite before modification.
- Keep backup and undo functional. Never wipe user history or overwrite a filename silently.
- Preserve existing lyrics by default. Overwriting requires explicitly configured permission.
- Network and missing-lyrics failures are non-destructive.
- Keep original-language Unicode. Never invent identity or hidden translation equivalence.

## Architecture

- ui: PySide6 widgets and workers; application services perform orchestration.
- app: discovery, queries, preview, apply, undo, benchmark.
- domain: normalized models and deterministic evidence rules.
- providers: httpx adapters for SearXNG JSON and LRCLIB plain lyrics.
- id3: Mutagen reading/writing/snapshot adapters only.
- files: local scanning, safe filenames, non-overwriting renames and backups.
- db: SQLite history and expiring request cache.

SearXNG payloads stay in the provider/cache boundary. Search URL is configurable, with no key. No scrapers for result target sites. Provider code must not call PySide6.

## Tests and maintenance

Mock all search/LRCLIB requests. Use temporary files for write/rename/undo tests. Test Unicode, insufficient text, competing identities and versions, independent sources, endpoint-isolated caching and connection errors. GUI tests run offscreen when enabled.

Historical recognition modules and their regression tests are retained but disconnected. Remove a historical module only after verifying no imports, runtime paths, tests or migrations require it. See docs/PHASE9_REPORT.md. Do not resume old recognition architecture.
