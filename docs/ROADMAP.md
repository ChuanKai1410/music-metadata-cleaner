# Roadmap

[Documentation index](README.md)

## Implemented

- SearXNG JSON search with endpoint-specific expiring cache and connection diagnostics.
- Deterministic Artist + Title candidates, Unicode cleanup, independent-domain scoring, version/conflict review, and inspectable evidence.
- LRCLIB plain lyrics, preservation of existing lyrics, and nonfatal missing-lyrics behavior.
- Manual keyword search, candidate confirmation, editable artist/title dropdowns, field swapping, and manual lyrics.
- Confirmed ID3 updates/rename, backups, SQLite history, and Undo Last Batch.
- Centralized dark QSS, a single Scan & Preview action, cleaner details/settings, and responsive table/detail layout.

## Validation completed

The [17 September 2026 live benchmark](benchmarks/20260917-164448/REPORT.md) processed all 15 user-selected files without changing their hashes. It produced 2 High, 0 Medium, and 13 Low results. No independent ground-truth manifest was supplied, so all correctness labels remain Unverified.

The subsequent UI pass recorded **203 passing tests**, including **15 GUI tests**, with GUI checks at 100%, 125%, and 150% scaling. This does not imply automatic recognition accuracy. UI work and documentation updates did not retune the resolver.

## Remaining work, not implemented promises

1. Obtain independently checked Artist + Title/version labels; measure precision and coverage on a broader held-out set before claiming 99%.
2. Improve parsing of quoted lyric tails, site decoration, title-internal “by,” and noisy long queries while keeping genuine versions distinct.
3. Validate native Linux GUI/packaging and freshly built desktop bundles on target systems.
4. Extend crash recovery and full-frame/multiple-USLT restoration if required; current backups retain full file bytes.
5. Consider safe alternatives for filesystems without hard-link support.
6. Retire historical modules only after deliberately removing their remaining test/import/compatibility dependencies.

Audio recognition, paid search APIs, LLM resolution, synchronized lyrics, and LRC export are outside the current product direction.
