# Read-only 15-song benchmark

The endpoint, exact existing 15-file set, and verified ground truth are to be supplied by the user. No real search or real-MP3 benchmark has been claimed from mocked results.

Create a UTF-8 CSV manifest:

```csv
path,expected_artist,expected_title
samples/song1.mp3,Known Artist,Known Title
```

Relative MP3 paths resolve from the manifest folder. Leave expected fields blank when unknown; the report keeps them Unverified instead of assuming correctness. Select the existing 15 files explicitly rather than choosing an arbitrary subset.

With PYTHONPATH set to src, run:

```sh
python -m music_metadata_cleaner.app.search_benchmark --endpoint http://your-instance:8080 --manifest samples.csv --output benchmark-results.csv
```

This invokes discovery, search and preview only. It does not call apply, rename, backup, or ID3 write. Cache data is stored alongside the output in a separate SQLite file; user history is not opened. Existing output CSVs are not overwritten.

Each row records original filename, cleaned filename, queries, result count, resolved artist/title, confidence, supporting domains, lyrics status, processing status, expected identity and correctness. Summary fields: Total, Correct High, Correct Medium, Incorrect, Insufficient Information, Search Failed, Unverified.

Review search evidence manually for all 15 rows, especially collaboration names and live/cover/remix distinctions. Correctness compares artist separators and normalized title punctuation, without translations or version removal. The primary metric is correct Artist + Title, not the number of High labels.

Test apply and undo separately on disposable copies only after reviewing the preview. Confirm original tags, audio content and filenames are preserved after undo, and that missing lyrics do not block metadata updates.
