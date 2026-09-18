# User Guide

See README.md for setup. The workflow is text-only; it does not identify a song from audio.

1. Configure your JSON-enabled SearXNG instance in Settings → Search. Test Connection checks both reachability and the response structure. No search key is required.
2. Add files or folders and preview. Source files are unchanged during this stage.
3. Read the six-column table: File, Artist, Title, Confidence, Lyrics, Status.
4. Inspect View Search Evidence for input cleanup, queries, result snippets, domains, grouping and score details.
5. If information is insufficient, enter known song details under Search keywords. Search runs the same pipeline as automatic search.
6. Select Use Candidate to explicitly confirm an uncertain identity. No automatic identity is fabricated for generic filenames.
7. Confirm Apply Selected or Apply All High Confidence. Album and other existing fields remain unchanged by the search-only proposal.
8. Undo Last Batch restores supported original tags and names. Successful files from a partial batch can also be undone.

Lyrics display Found or Not Found. Existing lyrics are kept by default. Missing or mismatched online lyrics do not affect identity confidence; mismatched lyrics are never written. Use Edit Artist / Title / Lyrics for editable dropdown suggestions, direct identity entry and manual plain lyrics. Confirm any replacement of existing lyrics, then Save Preview and Apply Selected.

The filename convention and original-language preference are currently fixed: Artist - Title.mp3, with no translation. Settings expose these values for clarity.

If a filename or backup conflict occurs, resolve it manually or select a different backup folder in the saved configuration. The application does not overwrite the conflicting file. Network failures leave files untouched.
