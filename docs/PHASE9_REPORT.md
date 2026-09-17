# Phase 9 implementation report

## 1–4. Interrupted work audit and repairs

The repository started this replacement task with seven modified tracked files and three untracked Python files, all attributable to the interrupted refactor. No staged changes were present. The baseline commit was `67f9b40`. No reset, broad restore, or history deletion was used.

The partial work contained a provider-specific HTTP adapter and key configuration, a generic search result/resolver module, a partially replaced workflow/factory, partial main-window changes, plain-lyrics changes, and a copied historical workflow. Settings and runtime/UI tests still expected removed recognition fields.

Removed/replaced: the BraveSearchProvider implementation, its HTTP endpoint/header/key fields, factory wiring and environment setting. There is no paid-provider selection logic. Unknown historical keys are ignored when loading preferences and are not emitted when saving new preferences.

Retained and refined: SearchProvider, SearchResult, ResolvedTrackIdentity, filename/query functions, the search-only orchestration scaffold, SQLite cache, existing write/history/backup/undo adapters, and the cleaned six-column GUI direction. Added explicit FilenameCleaner, SearchQueryBuilder and RuleBasedIdentityResolver interfaces.

Repaired: broken Settings imports/fields, outdated runtime tests, obsolete GUI expectations, confidence thresholds, stale previews after failures, asynchronous manual/candidate processing, worker close handling, resource cleanup, applied filename display, and undo availability for partial batches. The main table now fits all six columns.

## 5–10. Active architecture and deterministic rules

Production: MP3 → filename/existing ID3 → conservative cleanup → at most two SearXNG queries → RuleBasedIdentityResolver → supported Artist + Title → LRCLIB plain lyrics → preview → confirmed apply/rename.

SearXNG is the only search backend. The base URL is configurable and initially empty; SEARXNG_URL may override it. It uses GET `/search` with `q` and `format=json`, normalizes title/content/domain/engine/rank, and applies the configured result limit to the first page. Connection testing verifies structure and returns documented friendly status codes, without stack traces.

Cleanup strips known downloader prefixes, quality labels and explicit video wrappers; preserves Unicode, normal words such as Full Moon, and recording-version markers. Queries prefer useful ID3, with a filename alternative if different; otherwise the second query adds song. Manual keywords reuse the same logic. Generic filenames and recommendation labels return Insufficient Information without making a request.

The resolver parses dash, colon, pipe and by-artist patterns. It normalizes common collaboration separators for grouping, counts publisher domains rather than page count, prefers source-supported display strings, and keeps version/artist/title conflicts for review. No translation or hidden artist-alias equivalence is inferred. Snippets are exposed for review; automated candidate extraction currently uses titles.

Source reliability: 15 points for major music platforms, 10 for known secondary music references, 3 for unknown domains. Unverified official-looking sites are not assumed authoritative.

Score: filename 0–25 + ID3 0–15 + independent agreement 0–30 + source reliability 0–15 + orientation 0–15. High ≥80, Medium ≥60, otherwise Low. High also requires multiple domains, a credible music source and full filename or ID3 agreement. Version mismatch subtracts 25 and caps at Low. Competing plausible identities cap confidence at Low. Full details and limits are in ARCHITECTURE.md.

## 11–14. Manual review, lyrics and UI

Manual Search uses the normal background workflow. Use Candidate explicitly confirms identity and retrieves lyrics without blocking the UI. Evidence view contains filename cleanup, queries, titles, snippets, domains, engines, candidate groups and score breakdowns.

LRCLIB only exposes plainLyrics; other lyric formats are discarded before new cache writes and ignored when reading historical cached payloads. Missing lyrics do not discard identity or prevent cleanup. Missing/mismatched lyric identity fields require review and the lyrics are not written. Existing lyrics are preserved unless overwrite is enabled and preservation disabled.

Main table: File, Artist, Title, Confidence, Lyrics, Status. The current/proposed panel and query controls replace all recognition/provider status fields. No synchronized-lyrics or export controls remain.

Settings: General, Search, Lyrics, Files & Safety, Advanced. Search contains SearXNG URL, maximum results (8), timeout (10 seconds), automatic search and Test Connection. Advanced includes TTL, clear-search-cache, log/history paths and diagnostics guidance. No search key or old recognition configuration remains. Filename format and original-language behavior are currently fixed to the required safe convention.

## 15. Historical-module removal audit

All modules below are **disconnected from the production import graph** and excluded from the desktop package where applicable. They are not yet safe to physically delete under the requested “no test requires them” rule:

| Historical module/group | Remaining reason to retain |
| --- | --- |
| app/legacy_workflow_service.py | Historical test_workflow_service.py regression coverage |
| app/audio_identification_service.py; providers/acoustid.py | Historical identification/provider tests |
| fingerprinting/fpcalc.py and errors.py | Historical fingerprint and identification tests |
| providers/audd.py; app/fallback_recognition_service.py; audio_segments.py | Historical provider, segment and consensus tests |
| providers/musicbrainz.py; app/metadata_enrichment_service.py | Historical provider/enrichment tests and legacy workflow |
| providers/youtube.py; domain/youtube.py | Historical provider/ranking tests and legacy workflow |
| domain/recognition.py | Historical confidence tests and legacy workflow |
| Legacy LRC helper | Moved out of active lyrics service into historical workflow only |
| Legacy fields in domain/models.py | Historical tests and backward-compatible shared data models |

**Safe-to-remove now: none of those historical groups**, because their regression/import dependencies remain. No bulk deletion was performed. There were no Whisper/Demucs/alignment implementations to remove. A production import-graph test prevents these components from being reintroduced into startup, settings or scanning.

## 16–18. Dependencies, data and platforms

requirements.txt already contains only PySide6, Mutagen, httpx, pytest and PyInstaller. All remain used; no package was removed and no new dependency was added. SQLite and path handling use the standard library. No audio executable is required by production.

Schema version 1 and user history are preserved. Existing working-directory configuration/history are adopted by path without moving or deleting data. New installations use platform config/log locations. Search cache keys include endpoint + normalized query, expire by TTL, and can be cleared without touching history.

Preview is read-only. Apply checks for changed tags and requires stored history; backups are created exclusively. Rename avoids overwrite races through exclusive same-filesystem hard-link creation. Unsupported filesystems fail safely. Undo includes applied files in partially failed batches; original-name conflicts are checked before restoring tags.

Windows was exercised here. Linux path/config rules are covered by tests; native Linux Qt execution and packaging were not run in this Windows environment. Full-frame/multi-USLT undo and crash recovery beyond the existing supported snapshot remain future improvements; backups retain full original bytes when enabled.

## 19. Automated and visual validation

The complete suite passed with GUI enabled: **185 passed**. All external search and lyrics responses were mocked; no API quota or live SearXNG server was required.

The system Anaconda interpreter hit an existing Qt DLL loader failure. The bundled Python 3.12 runtime successfully loaded the same PySide6 installation and ran all tests, including seven offscreen GUI tests. Main-window and Settings screenshots were rendered and inspected with an explicitly loaded font for the offscreen renderer.

Coverage includes real-world text cases, Unicode, downloader cleanup, parser orientations, collaboration normalization, domain grouping, version conflicts, confidence, insufficient information, manual search, caching/errors, lyrics policy, ID3, rename, rollback, backup, partial-batch undo, settings, platform directories and production import isolation. Diff whitespace checks passed.

## 20. Manual benchmark and remaining limitations

The user will provide the SearXNG URL, exact existing 15-file set and ground truth later. The real-MP3 benchmark has **not** been run or represented as completed.

A read-only benchmark runner and procedure are ready in SEARCH_BENCHMARK.md. It reports per-file evidence and correctness, leaving unknown truth Unverified. It never calls apply or rename.

Rule-based parsing cannot understand arbitrary unstructured titles, translations, or missing textual identity. Ambiguous evidence requires user selection. Search quality depends on the configured SearXNG instance and enabled engines. A 403 may mean disabled JSON or server access restrictions. Search has a two-query limit; recall is intentionally secondary to avoiding invented identities.
