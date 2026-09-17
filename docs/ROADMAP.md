# Roadmap

## Phase 9 — implemented

SearXNG JSON search, deterministic text identity resolution, Unicode cleanup, independent-source scoring, candidate review, manual search, evidence diagnostics, LRCLIB plain lyrics, simplified Settings, and preserved apply/backup/history/undo.

## Validation pending user inputs

Run the existing 15-song benchmark against the user's SearXNG endpoint and manually verify Artist + Title. The user will supply the endpoint and sample manifest. Do not inflate scores to improve apparent recovery.

## Follow-up candidates

- Tune parsing against verified benchmark failures without hidden identity guesses.
- Improve transactional/crash recovery and full-frame history snapshots.
- Support additional filesystem-safe rename mechanisms where hard links are unavailable.
- Remove historical modules only when their tests/imports and compatibility needs have been retired deliberately.

No audio recognition, paid search backend, LLM resolver, synchronized lyrics or LRC feature is planned.
