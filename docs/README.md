# Documentation

Current product: a local-first MP3 metadata cleaner using SearXNG text search, deterministic identity rules, optional LRCLIB plain lyrics, and confirmed file changes.

Development setup now uses `pyproject.toml` and `pip install -e .` after installing `requirements.txt`. Launch with the same interpreter using `-m music_metadata_cleaner`; no `PYTHONPATH` override is needed.

## Use and develop

| Document | Read it for |
| --- | --- |
| [Project README](../README.md) | Overview, screenshot, quick start, and tech stack |
| [User guide](USER_GUIDE.md) | Current controls, settings, safety, and troubleshooting |
| [Confidence & manual editing](CONFIDENCE_AND_MANUAL_EDIT.md) | Scoring rules and manual completion, explained in Chinese |
| [Build & tests](BUILD.md) | Editable package installation, offscreen GUI checks, and Windows builds |
| [Architecture](ARCHITECTURE.md) | Active modules, provider boundaries, UI theme, and file safety |
| [Requirements](REQUIREMENTS.md) | Current product scope and constraints |
| [Roadmap](ROADMAP.md) | Completed work and remaining validation |
| [Search benchmark](SEARCH_BENCHMARK.md) | Recorded results and how to repeat a read-only benchmark |

## Implementation and historical records

| Document | Status |
| --- | --- |
| [UI polish report](UI_POLISH_REPORT.md) | Completed styling pass; 203-test validation snapshot |
| [UI action audit](UI_ACTION_AUDIT.md) | Before/after rationale for consolidating Scan and Preview |
| [Phase 9 report](PHASE9_REPORT.md) | Refactor record with links to subsequent work |
| [17 September benchmark](benchmarks/20260917-164448/REPORT.md) | Preserved real-search baseline; not rerun by documentation updates |
| [MusicBrainz release selection](MUSICBRAINZ_RELEASE_SELECTION.md) | Archived implementation notes; not an active provider or roadmap |
| [Icon assets](../assets/icons/README.md) | Optional packaged icon and current control arrows |

Historical measurements retain their original dates and results. Current behavior is described in the user guide and architecture, rather than inferred from an older report.
