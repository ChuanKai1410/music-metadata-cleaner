# Search benchmark

[Documentation index](README.md) · [Recorded 15-song report](benchmarks/20260917-164448/REPORT.md)

## Recorded baseline

The real 15-file run was completed on **17 September 2026**, using the supplied SearXNG endpoint and exact user-selected MP3s:

| Measurement | Result |
| --- | --- |
| Processed | 15 files |
| Confidence | 2 High / 0 Medium / 13 Low |
| Identity proposals | 3: two High, one Low |
| High-resolution coverage | 2/15 (13.3%) |
| Ground-truth correctness | Unverified for all 15; independent labels were not supplied |
| Original MP3 integrity | All before/after SHA-256 hashes matched |

These are historical baseline results, not a new run or a 99% accuracy claim. Later manual-edit/UI work did not change the automatic scoring formula. See the full report for per-song evidence, parser failures, and the lyrics-network retry.

## Repeat a read-only run

Create a UTF-8 CSV manifest with one exact MP3 path per row:

```csv
path,expected_artist,expected_title
samples/song1.mp3,Known Artist,Known Title
samples/song2.mp3,,
```

Relative paths resolve from the manifest folder. Include independently checked artist, title, and recording/version details. Leave expected fields blank when unknown. For comparison with the original run, explicitly list the same 15 files.

Set `PYTHONPATH` to `src` as in the [build guide](BUILD.md), then run:

```sh
python -m music_metadata_cleaner.app.search_benchmark --endpoint http://localhost:8080 --manifest samples.csv --output benchmark-results.csv
```

Use your own endpoint. The benchmark CLI requires `--endpoint`; it does not load the desktop's saved URL or `.env` automatically. This is a live-network command, unlike normal mocked tests.

The runner performs discovery, search, and preview only. It never calls apply, rename, backup, or ID3 write. It creates an isolated `.cache.sqlite3` beside the output rather than opening application history. Use a new output filename each run: CSV output uses exclusive creation, although searches can occur before an existing-output error is raised.

## Outputs and interpretation

The CSV contains filename cleanup, queries, result count, proposed artist/title, confidence, supporting domains, lyrics/processing status, expected identity, and correctness. The console summary contains Total, Correct High, Correct Medium, Incorrect, Insufficient Information, Search Failed, and Unverified.

The runner scores Correct/Incorrect only when both expected fields and a proposal exist. A blank correctness field—including a row without a proposal—counts as Unverified. It does not itself generate the historical report's extra evidence JSON or file-hash audit; those were captured separately.

Review all candidates for collaboration names and covers/remixes/live versions. Artist comparison normalizes common separators; title comparison normalizes Unicode, case, whitespace, and selected punctuation, without translating names or stripping version meaning.

Measure automatic precision, automatic coverage, and manually assisted completion separately. Do not count manual entries as automatic success, treat High as a probability, or infer 99% accuracy from 15 samples. The existing benchmark exposes useful parsing failures; larger independently labelled hold-out data is still needed.

Test apply/undo separately on disposable copies after reviewing proposals. Confirm filenames, supported tags, and audio content survive undo, and that missing lyrics do not block metadata changes.
